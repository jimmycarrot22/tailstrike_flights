
import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import matplotlib.colors as mcolors
import altair as alt
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
from pyproj import Geod

# =============================================================
#                      DATA LOAD
# =============================================================

@st.cache_data
def load_csv(url):
    return pd.read_csv(url)

DF_URL = "https://raw.githubusercontent.com/jimmycarrot22/tailstrike_flights/main/data/tailstrike_flights.csv"
df = load_csv(DF_URL)

df["date_dep_form"] = pd.to_datetime(df["date_dep_form"], errors="coerce")
df["date_arr_form"] = pd.to_datetime(df["date_arr_form"], errors="coerce")

poly_df = df.copy()
trail_df = df.copy()


# =============================================================
#                        PAGE LAYOUT
# =============================================================
st.set_page_config(layout="wide")

# Optional: custom header
st.markdown("<h2 style='font-size:24px; font-weight:700; margin-bottom:10px;'>Tailstrike Flights </h2>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["Flight Map", "Global Stats", "Achievements"])
# =============================================================
#                      FILTERING SECTION
# =============================================================

with tab1:
    # --- Dropdown choices for existing filters ---
    all_aircraft     = sorted(df["aircraft"].unique())
    all_departures   = sorted(df["departure"].unique())
    all_arrivals     = sorted(df["arrival"].unique())
    all_airports_any = sorted(set(df["departure"].unique()) | set(df["arrival"].unique()))
    
    # --- Dropdown choices for aircraft-detail filters ---
    all_ac_models = (sorted(df["ac_icao_type"].dropna().astype(str).unique())
        if "ac_icao_type" in df.columns else [])
    
    all_ac_categories = sorted(df["ac_category"].dropna().unique()) if "ac_category" in df.columns else []
    all_ac_airlines = sorted(df["ac_airline_name"].dropna().unique()) if "ac_airline_name" in df.columns else []
    
    all_ac_is_ga_raw = df["ac_is_ga"].dropna().unique() if "ac_is_ga" in df.columns else []
    all_ac_is_ga = sorted({str(v) for v in all_ac_is_ga_raw})
    
    # --- Row 1: 5 core filters ---
    # st.markdown("### Flight filter")
    
    col2, col3, col4, col5 = st.columns(4)
    
    with col2:
        selected_aircraft = st.multiselect("", options=all_aircraft, placeholder="Aircraft")
    
    with col3:
        selected_departures = st.multiselect("", options=all_departures,  placeholder="Departure Airport")
    
    with col4:
        selected_arrivals = st.multiselect("", options=all_arrivals, placeholder="Arrival Airport")
    
    with col5:
        selected_any_airport = st.multiselect("", options=all_airports_any, placeholder="Departure or Arrival Airport")
    
    # --- Row 2: 4 aircraft-detail filters ---
    col6, col7, col8, col9 = st.columns(4)
    
    with col6:
        selected_ac_models = st.multiselect("", options=all_ac_models, placeholder="Aircraft ICAO code")
    
    with col7:
        selected_ac_categories = st.multiselect("", options=all_ac_categories, placeholder="Aircraft Category")
    
    with col8:
        selected_ac_airlines = st.multiselect("", options=all_ac_airlines, placeholder="Airline")
    
    with col9:
        selected_ac_is_ga = st.multiselect("", options=all_ac_is_ga, placeholder="GA Aircraft?" )
    
    # --------- DATE RANGE SLIDER ---------
    # st.markdown("### Date filter")
    
    min_date = df["date_dep_form"].min().date()
    max_date = df["date_dep_form"].max().date()
    
    selected_date_range = st.slider("", min_value=min_date, max_value=max_date, value=(min_date, max_date), format="YYYY-MM-DD",)
    
    start_date, end_date = selected_date_range
    
    # --------- APPLY FILTERS ---------
    filtered_df = df.copy()
    
    # Core filters
    if selected_aircraft:
        filtered_df = filtered_df[filtered_df["tailnumber"].isin(selected_aircraft)]
    
    if selected_departures:
        filtered_df = filtered_df[filtered_df["departure"].isin(selected_departures)]
    
    if selected_arrivals:
        filtered_df = filtered_df[filtered_df["arrival"].isin(selected_arrivals)]
    
    if selected_any_airport:
        filtered_df = filtered_df[(filtered_df["departure"].isin(selected_any_airport)) | (filtered_df["arrival"].isin(selected_any_airport))]
    
    # Aircraft detail filters
    if selected_ac_models and "ac_icao_type" in filtered_df.columns:
        filtered_df = filtered_df[
            filtered_df["ac_icao_type"].astype(str).isin(selected_ac_models)]
    
    if selected_ac_categories and "ac_category" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["ac_category"].isin(selected_ac_categories)]
    
    if selected_ac_airlines and "ac_airline_name" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["ac_airline_name"].isin(selected_ac_airlines)]
    
    if selected_ac_is_ga and "ac_is_ga" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["ac_is_ga"].astype(str).isin(selected_ac_is_ga)]
    
    # Date filter (by departure time)
    filtered_df = filtered_df[(filtered_df["date_dep_form"].dt.date >= start_date) & (filtered_df["date_dep_form"].dt.date <= end_date)]
    
    # =============================================================
    #          BUILD flight_lines FOR MAP (USING filtered_df)
    # =============================================================
    flight_lines = []
    
    for _, flight in filtered_df.iterrows():
    
        dep = (flight["dep_lat"], flight["dep_lon"])
        arr = (flight["arr_lat"], flight["arr_lon"])
    
        if pd.isna(dep[0]) or pd.isna(dep[1]) or pd.isna(arr[0]) or pd.isna(arr[1]):
            continue
    
        flight_lines.append({
            "from_lat": dep[0],
            "from_lon": dep[1],
            "to_lat":   arr[0],
            "to_lon":   arr[1],
            "pilot": flight["pilot"],
            "aircraft": flight["aircraft"],
            "distance_nm": flight["distance_nm"],   # ← FIXED
            "duration_min": flight["duration_min"],
            "departure": flight["departure"],
            "arrival": flight["arrival"],
        })
    
    flight_lines = pd.DataFrame(flight_lines)
    
    if flight_lines.empty:
        st.warning("No flights match the selected filters.")
        st.stop()
    
    
    # =============================================================
    #                       TOOLTIP TEXT
    # =============================================================
    def minutes_to_hhmm(minutes):
        h = int(minutes // 60)
        m = int(minutes % 60)
        return f"{h:02d}:{m:02d}"
    
    flight_lines["duration_hhmm"] = flight_lines["duration_min"].apply(minutes_to_hhmm)
    
    flight_lines["Hover"] = flight_lines.apply(
        lambda r: (f"<b>Pilot:</b> {r['pilot']}<br>"
                   f"<b>Aircraft:</b> {r['aircraft']}<br>"
                   f"<b>Duration:</b> {r['duration_hhmm']}<br>"
                   f"<b>Distance:</b> {r['distance_nm']} nm<br>"
                   f"<b>From:</b> {r['departure']}<br>"
                   f"<b>To:</b> {r['arrival']}"), axis=1)
    
    # =============================================================
    #                AIRPORT DOT DATAFRAME
    # =============================================================
    airport_points = []
    
    for _, r in flight_lines.iterrows():
        airport_points.append({"lat": r["from_lat"], "lon": r["from_lon"], "ICAO": r["departure"]})
        airport_points.append({"lat": r["to_lat"],   "lon": r["to_lon"],   "ICAO": r["arrival"]})
    
    airport_df = pd.DataFrame(airport_points).drop_duplicates(subset=["ICAO"])
    airport_df["Hover"] = airport_df["ICAO"].apply(lambda x: f"<b>Airport:</b> {x}")
    
    # =============================================================
    #                      MAP CENTER
    # =============================================================
    mid_lat = flight_lines[["from_lat", "to_lat"]].values.mean()
    mid_lon = flight_lines[["from_lon", "to_lon"]].values.mean()
    
    view_state = pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=2.4, pitch=0, bearing=0)
    
    # =============================================================
    #            READ COLORS FROM SESSION STATE
    # =============================================================
    default_line_hex = "#7896E1"
    default_dot_hex  = "#FFD700"
    
    line_color_hex = st.session_state.get("line_color_hex", default_line_hex)
    dot_color_hex  = st.session_state.get("dot_color_hex", default_dot_hex)
    
    line_color_rgb = [int(c * 255) for c in mcolors.to_rgb(line_color_hex)]
    dot_color_rgb  = [int(c * 255) for c in mcolors.to_rgb(dot_color_hex)]
    
    # =============================================================
    #                        MAP LAYERS
    # =============================================================
    basemap = pdk.Layer("TileLayer",
                        data=None,
                        tileset="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                        tile_size=256,)
    
    line_layer = pdk.Layer("GreatCircleLayer",
                            data=flight_lines,
                            get_source_position=["from_lon", "from_lat"],
                            get_target_position=["to_lon", "to_lat"],
                            get_source_color=line_color_rgb,
                            get_target_color=line_color_rgb,
                            great_circle=True,
                            width_scale=1,
                            width_min_pixels=2,
                            pickable=True,
                            wrapLongitude=True,)
    
    airport_layer = pdk.Layer("ScatterplotLayer",
                                data=airport_df,
                                get_position=["lon", "lat"],
                                get_fill_color=dot_color_rgb,
                                radius_min_pixels=4,
                                radius_max_pixels=4,
                                pickable=True,)
    
    # =============================================================
    #                       MAP RENDER
    # =============================================================
    deck = pdk.Deck(
        layers=[basemap, line_layer, airport_layer],
        initial_view_state=view_state,
        map_style=None,
        tooltip={"html": "{Hover}"},)
    
    st.pydeck_chart(deck, use_container_width=True)
    
    
    # =============================================================
    #            FLIGHTS PER DAY CHART
    # =============================================================
    # st.markdown("### Flights Per Day")
    
    daily = (filtered_df
            .groupby(filtered_df["date_dep_form"].dt.date)
            .size()
            .reset_index(name="Flights")
            .sort_values("date_dep_form"))
    
    if daily.empty:
        st.info("No flights available for the selected filters.")
    else:
        chart = (alt.Chart(daily)
                .mark_bar(color="#7896E1")
                .encode(
                    x=alt.X("date_dep_form:T", title="Date", axis=alt.Axis(format="%b %d")),
                    y=alt.Y("Flights:Q", title="Number of Flights"),
                    tooltip=[alt.Tooltip("date_dep_form:T", title="Date", format="%Y-%m-%d"), alt.Tooltip("Flights:Q", title="Flights")]
                ).properties(
                    width="container",
                    height=250,
                    title="Flights Per Day"))
    
        st.altair_chart(chart, use_container_width=True)
    
    # =============================================================
    #                MAP COLOR CONTROLS
    # =============================================================
    # st.markdown("### Map Colors")
    
    colA, colB = st.columns(2)
    
    with colA:
        st.color_picker("Flight Path Color", line_color_hex, key="line_color_hex")
    
    with colB:
        st.color_picker("Airport Dot Color", dot_color_hex, key="dot_color_hex")

with tab2:
    
    # =============================================================
    #                    GLOBAL STATS TAB
    # =============================================================
     
    # --- Stat metric selector ---
    STAT_OPTIONS = {
        "Pilots":                 ("nunique",       "Pilots",   "#7896E1"),
        "Flights":                ("count_flights", "Flights",  "#7896E1"),
        "Aircraft":               ("nunique_ac",    "Aircraft", "#7896E1"),
        "Total Flight Duration":  ("sum_dur",       "Minutes",  "#7896E1"),
        "Total Flight Distance":  ("sum_dist",      "NM",       "#7896E1"),
        "Avg Flight Duration":    ("mean_dur",      "Minutes",  "#7896E1"),
        "Avg Flight Distance":    ("mean_dist",     "NM",       "#7896E1"),
        "Longest Flight (Distance)": ("max_dist",   "NM",       "#7896E1"),
        "Longest Flight (Duration)": ("max_dur",    "Minutes",  "#7896E1"),
        "Cumulative Pilots":      ("cumsum_pilots", "Pilots",   "#7896E1"),
        "Cumulative Flights":     ("cumsum_flights", "Flights", "#7896E1"),
        "Cumulative Aircraft":    ("cumsum_ac", "Aircraft",     "#78A0E1"),
        }
    gs_stat = st.selectbox("", options=list(STAT_OPTIONS.keys()), key="gs_stat")
    
    # --- Same filter dropdowns (reuse same option lists) ---
    gs_col1, gs_col2, gs_col3, gs_col4 = st.columns(4)
    
    with gs_col1:
        gs_aircraft = st.multiselect("", options=all_aircraft, placeholder="Aircraft", key="gs_aircraft")
    with gs_col2:
        gs_departures = st.multiselect("", options=all_departures, placeholder="Departure Airport", key="gs_departures")
    with gs_col3:
        gs_arrivals = st.multiselect("", options=all_arrivals, placeholder="Arrival Airport", key="gs_arrivals")
    with gs_col4:
        gs_any_airport = st.multiselect("", options=all_airports_any, placeholder="Departure or Arrival Airport", key="gs_any_airport")
    
    gs_col5, gs_col6, gs_col7, gs_col8 = st.columns(4)
    
    with gs_col5:
        gs_ac_models = st.multiselect("", options=all_ac_models, placeholder="Aircraft ICAO code", key="gs_ac_models")
    with gs_col6:
        gs_ac_categories = st.multiselect("", options=all_ac_categories, placeholder="Aircraft Category", key="gs_ac_categories")
    with gs_col7:
        gs_ac_airlines = st.multiselect("", options=all_ac_airlines, placeholder="Airline", key="gs_ac_airlines")
    with gs_col8:
        gs_ac_is_ga = st.multiselect("", options=all_ac_is_ga, placeholder="GA Aircraft?", key="gs_ac_is_ga")
    
    # --- Date range slider ---
    gs_date_range = st.slider("", min_value=min_date, max_value=max_date, value=(min_date, max_date), format="YYYY-MM-DD", key="gs_date_slider")
    gs_start, gs_end = gs_date_range
    
    # --- Apply filters ---
    gs_df = df.copy()
    
    if gs_aircraft:
        gs_df = gs_df[gs_df["tailnumber"].isin(gs_aircraft)]
    if gs_departures:
        gs_df = gs_df[gs_df["departure"].isin(gs_departures)]
    if gs_arrivals:
        gs_df = gs_df[gs_df["arrival"].isin(gs_arrivals)]
    if gs_any_airport:
        gs_df = gs_df[(gs_df["departure"].isin(gs_any_airport)) | (gs_df["arrival"].isin(gs_any_airport))]
    if gs_ac_models and "ac_icao_type" in gs_df.columns:
        gs_df = gs_df[gs_df["ac_icao_type"].astype(str).isin(gs_ac_models)]
    if gs_ac_categories and "ac_category" in gs_df.columns:
        gs_df = gs_df[gs_df["ac_category"].isin(gs_ac_categories)]
    if gs_ac_airlines and "ac_airline_name" in gs_df.columns:
        gs_df = gs_df[gs_df["ac_airline_name"].isin(gs_ac_airlines)]
    if gs_ac_is_ga and "ac_is_ga" in gs_df.columns:
        gs_df = gs_df[gs_df["ac_is_ga"].astype(str).isin(gs_ac_is_ga)]
    
    gs_df = gs_df[(gs_df["date_dep_form"].dt.date >= gs_start) & (gs_df["date_dep_form"].dt.date <= gs_end)]
    
    if gs_df.empty:
        st.warning("No flights match the selected filters.")
        st.stop()
    
    # --- Compute daily series based on selected stat ---
    agg_type, y_label, bar_color = STAT_OPTIONS[gs_stat]
    grouped = gs_df.groupby(gs_df["date_dep_form"].dt.date)
    
    if agg_type == "count_flights":
        daily_gs = grouped.size().reset_index(name=y_label)
    
    elif agg_type == "count_pilots":
        daily_gs = grouped["pilot"].count().reset_index(name=y_label)
    
    elif agg_type == "nunique":
        daily_gs = grouped["pilot"].nunique().reset_index(name=y_label)
    
    elif agg_type == "mean_dur":
        daily_gs = grouped["duration_min"].mean().reset_index(name=y_label)
        daily_gs[y_label] = daily_gs[y_label].round(1)
    
    elif agg_type == "mean_dist":
        daily_gs = grouped["distance_nm"].mean().reset_index(name=y_label)
        daily_gs[y_label] = daily_gs[y_label].round(1)
    
    elif agg_type == "sum_dur":
        daily_gs = grouped["duration_min"].sum().reset_index(name=y_label)
        daily_gs[y_label] = daily_gs[y_label].round(1)
    
    elif agg_type == "sum_dist":
        daily_gs = grouped["distance_nm"].sum().reset_index(name=y_label)
        daily_gs[y_label] = daily_gs[y_label].round(1)
        
    elif agg_type == "nunique_ac":
        daily_gs = grouped["aircraft"].nunique().reset_index(name=y_label)
        
    elif agg_type == "max_dist":
        daily_gs = grouped["distance_nm"].max().reset_index(name=y_label)
        daily_gs[y_label] = daily_gs[y_label].round(1)
    elif agg_type == "max_dur":
        daily_gs = grouped["duration_min"].max().reset_index(name=y_label)
        daily_gs[y_label] = daily_gs[y_label].round(1)
            
    elif agg_type == "cumsum_flights":
        daily_gs = grouped.size().reset_index(name=y_label)
        daily_gs = daily_gs.sort_values("date_dep_form")
        daily_gs[y_label] = daily_gs[y_label].cumsum()
        
    elif agg_type == "cumsum_pilots":
        # Sort by date, then find first appearance of each pilot
        gs_sorted = gs_df.sort_values("date_dep_form")
        gs_sorted["is_first"] = ~gs_sorted.duplicated(subset=["pilot"], keep="first")
        daily_gs = (gs_sorted.groupby(gs_sorted["date_dep_form"].dt.date)["is_first"].sum().reset_index(name=y_label))
        daily_gs = daily_gs.sort_values("date_dep_form")
        daily_gs[y_label] = daily_gs[y_label].cumsum()
    elif agg_type == "cumsum_ac":
        gs_sorted = gs_df.sort_values("date_dep_form")
        gs_sorted["is_first"] = ~gs_sorted.duplicated(subset=["aircraft"], keep="first")
        daily_gs = (gs_sorted.groupby(gs_sorted["date_dep_form"].dt.date)["is_first"].sum().reset_index(name=y_label))
        daily_gs = daily_gs.sort_values("date_dep_form")
        daily_gs[y_label] = daily_gs[y_label].cumsum()
        
    daily_gs = daily_gs.sort_values("date_dep_form")

    def format_duration(minutes, is_total=False):
        if is_total:
            h = int(minutes // 60)
            m = int(minutes % 60)
            s_days = int(minutes // (60 * 24))
            s_hours = int((minutes % (60 * 24)) // 60)
            return f"{h}h ({s_days:02d}d {s_hours:02d}h {m:02d}m)"
        else:
            h = int(minutes // 60)
            m = int(minutes % 60)
            return f"{h}h {m:02d}m"
            
    # --- Convert minutes to hours for chart display ---
    if agg_type in ("mean_dur", "sum_dur", "max_dur"):
        daily_gs["display"] = daily_gs[y_label] / 60
        display_col = "display"
        y_axis_label = "Hours"
    else:
        display_col = y_label
        y_axis_label = y_label
    
    # --- Summary metric ---
    is_avg = gs_stat.startswith("Avg")
    if is_avg:
        if "Duration" in gs_stat:
            raw = gs_df["duration_min"].mean()
            summary_value = format_duration(raw, is_total=False)
        else:
            summary_value = f"{round(gs_df['distance_nm'].mean(), 1)} nm"
        summary_label = f"Overall {gs_stat}"
    else:
        if agg_type == "nunique":
            summary_value = int(gs_df["pilot"].nunique())
        elif agg_type == "nunique_ac":
            summary_value = int(gs_df["aircraft"].nunique())
        elif agg_type == "sum_dur":
            raw = daily_gs[y_label].sum()
            summary_value = format_duration(raw, is_total=True)
        elif agg_type == "mean_dist":
            summary_value = f"{round(daily_gs[y_label].sum(), 1)} nm"
        elif agg_type == "sum_dist":
            total_dist = round(daily_gs[y_label].sum(), 1)
            globes = total_dist / 21639
            globe_str = f" — {globes:.1f}x around the globe 🌍" if total_dist >= 21639 else ""
            summary_value = f"{total_dist:,} nm{globe_str}"
        elif agg_type == "max_dist":
            summary_value = f"{round(gs_df['distance_nm'].max(), 1)} nm"
        elif agg_type == "max_dur":
            raw = gs_df["duration_min"].max()
            summary_value = format_duration(raw, is_total=False)
        elif agg_type == "cumsum_flights":
            summary_value = int(gs_df.shape[0])
        elif agg_type == "cumsum_pilots":
            summary_value = int(gs_df["pilot"].nunique())
        elif agg_type == "cumsum_ac":
            summary_value = int(gs_df["aircraft"].nunique())
        else:
            summary_value = int(daily_gs[y_label].sum())
        summary_label = f"Total — {gs_stat}"
    
    st.metric(label=summary_label, value=summary_value)

    # --- Daily breakdown chart ---
    gs_chart = (
        alt.Chart(daily_gs)
        .mark_bar(color=bar_color)
        .encode(
            x=alt.X("date_dep_form:T", title="Date", axis=alt.Axis(format="%b %d")),
            y=alt.Y(f"{display_col}:Q", title=y_axis_label),
            tooltip=[
                alt.Tooltip("date_dep_form:T", title="Date", format="%Y-%m-%d"),
                alt.Tooltip(f"{display_col}:Q", title=y_axis_label, format=".2f"),
            ],
        )
        .properties(width="container", height=300, title=gs_stat)
    )
    
    st.altair_chart(gs_chart, use_container_width=True)

with tab3:

    def longest_snake(df):
        results = {}
    
        for aircraft, group in df.groupby('aircraft'):
            flights = group.sort_values('date_dep_form').reset_index(drop=True)
            best_chain = []
    
            def dfs(chain, visited_airports, used_indices):
                nonlocal best_chain
    
                if len(chain) > len(best_chain):
                    best_chain = chain.copy()
    
                last = chain[-1]
    
                next_legs = flights[
                    (flights['departure'] == last['arrival']) &
                    (flights['date_dep_form'] > last['date_dep_form']) &
                    (~flights.index.isin(used_indices))
                ].sort_values('date_dep_form')
    
                if len(next_legs) == 0:
                    return
    
                earliest = next_legs.iloc[0]
    
                if earliest['pilot'] == last['pilot']:
                    return
    
                if earliest['arrival'] in visited_airports:
                    return
    
                same_time_legs = next_legs[next_legs['date_dep_form'] == earliest['date_dep_form']]
    
                for idx, candidate in same_time_legs.iterrows():
                    if candidate['pilot'] == last['pilot']:
                        continue
                    if candidate['arrival'] in visited_airports:
                        continue
    
                    dfs(
                        chain + [candidate],
                        visited_airports | {candidate['arrival']},
                        used_indices | {idx}
                    )
    
            for start_idx, start in flights.iterrows():
                visited = {start['departure'], start['arrival']}
                dfs([start], visited, {start_idx})
    
            results[aircraft] = {
                'length': len(best_chain),
                'chain': [
                    {
                        'departure': r['departure'],
                        'arrival': r['arrival'],
                        'pilot': r['pilot'],
                        'date': r['date_dep_form']
                    }
                    for r in best_chain
                ]
            }
    
        return results

    def display_top_snake(df):
        results = longest_snake(df)
    
        top = sorted(results.items(), key=lambda x: x[1]['length'], reverse=True)[0]
        aircraft, data = top
        chain = data['chain']
    
        route = " → ".join([chain[0]['departure']] + [l['arrival'] for l in chain])
        pilots = ", ".join(dict.fromkeys(l['pilot'] for l in chain))
        first_date = chain[0]['date'].strftime("%Y-%m-%d") if hasattr(chain[0]['date'], 'strftime') else str(chain[0]['date'])
    
        summary_df = pd.DataFrame([{
            'aircraft': aircraft,
            'legs': data['length'],
            'started': first_date,
            'pilots': pilots
        }])
    
        route_df = pd.DataFrame([{'route': route}])
    
        st.markdown("### The Snake", help="Most flights by non-consecutive pilots, without flying to previosly used airport")
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
        st.dataframe(route_df, use_container_width=True, hide_index=True)
        
    

    def single_aircraft_pilot_hours(df):
        pilot_aircraft = df.groupby('pilot')['aircraft'].nunique()
        single_aircraft_pilots = pilot_aircraft[pilot_aircraft == 1].index
    
        filtered = df[df['pilot'].isin(single_aircraft_pilots)]
        result = filtered.groupby('pilot').agg(
            aircraft=('aircraft', 'first'),
            total_minutes=('duration_min', 'sum'),
            flights=('duration_min', 'count')
        ).reset_index()
    
        result['total_hours'] = result['total_minutes'].apply(
            lambda m: f"{int(m // 60):02d}:{int(m % 60):02d}"
        )
    
        result = result.drop(columns='total_minutes')
        result = result.sort_values('flights', ascending=False).head(5)
    
        return result.reset_index(drop=True)

    
    def compute_trailblazers(flights_frame):
        # Create a canonical route key ON THE INPUT DATAFRAME
        flights_frame = flights_frame.copy()
        flights_frame["route"] = flights_frame["departure"].astype(str) + "-" + flights_frame["arrival"].astype(str)
    
        # Sort by earliest time
        flights_sorted = flights_frame.sort_values("date_dep_form")
    
        trail_results = []
    
        # Group by route
        for route, group in flights_sorted.groupby("route"):
    
            # Earliest row in this group
            first_row = group.iloc[0]
            trailblazer = first_row["pilot"]
            first_time = first_row["date_dep_form"]
    
            # Other pilots who flew the same route later
            other_pilots = group.loc[group["pilot"] != trailblazer, "pilot"].unique()
            other_pilot_count = len(other_pilots)
    
            trail_results.append({
                "route": route,
                "trailblazer": trailblazer,
                "first_flight_time": first_time,
                "followers_count": other_pilot_count,
            })
    
        # Keep only routes with followers
        trail_result_frame = pd.DataFrame(trail_results)
        trail_result_frame = trail_result_frame[trail_result_frame["followers_count"] > 0]
    
        return trail_result_frame
    
    
    def top10_trailblazers(trail_result_frame):
        # Select useful columns
        trail_filtered = trail_result_frame[[
            "route", "trailblazer", "followers_count"
        ]].copy()
    
        # Remove NaN rows
        trail_filtered = trail_filtered.dropna(subset=["followers_count"])
    
        # Sort by followers DESC
        trail_sorted = trail_filtered.sort_values("followers_count", ascending=False)
    
        # Top 10 only
        trail_top10 = trail_sorted.head(5)
    
        return trail_top10.reset_index(drop=True)
  
    def compute_airline_network_size(flights_frame):
        # Use only the columns you actually have
        airline_tmp = flights_frame[["ac_airline_name", "departure", "arrival"]].copy()
    
        # Drop rows with missing airline
        airline_tmp = airline_tmp.dropna(subset=["ac_airline_name"])
    
        # Stack departure + arrival into a single "airport" column
        melted = airline_tmp.melt(id_vars="ac_airline_name", value_vars=["departure", "arrival"], value_name="airport" )
    
        # Drop missing airports
        melted = melted.dropna(subset=["airport"])
    
        # Count unique airports per airline
        network_size = (melted.groupby("ac_airline_name")["airport"].nunique().reset_index(name="network_airport_count").sort_values("network_airport_count", ascending=False))
    
        return network_size    
    
    def top10_airline_network_size(network_frame):
        airline_filtered = network_frame[["ac_airline_name","network_airport_count"]].copy()
    
        airline_filtered = airline_filtered.dropna(subset=["network_airport_count"])
        airline_sorted = airline_filtered.sort_values("network_airport_count", ascending=False )
    
        airline_top10 = airline_sorted.head(5)
        return airline_top10.reset_index(drop=True)    
        
    def busiest_airport(df):
        df['date_dep_form'] = pd.to_datetime(df['date_dep_form'])
    
        departures = df[['departure', 'date_dep_form']].rename(
            columns={'departure': 'airport', 'date_dep_form': 'time'}
        )
        arrivals = df[['arrival', 'date_dep_form']].rename(
            columns={'arrival': 'airport', 'date_dep_form': 'time'}
        )
    
        movements = pd.concat([departures, arrivals]).sort_values('time').reset_index(drop=True)
    
        results = []
    
        for _, row in movements.iterrows():
            window_start = row['time']
            window_end = window_start + pd.Timedelta(hours=24)
            airport = row['airport']
    
            count = len(movements[
                (movements['airport'] == airport) &
                (movements['time'] >= window_start) &
                (movements['time'] < window_end)
            ])
    
            results.append({
                'airport': airport,
                'count': count,
                'window_start': window_start,
                'window_end': window_end
            })
    
        top5 = sorted(results, key=lambda x: x['count'], reverse=True)[:5]
        return top5
    
        
    def display_busiest_airport(df):
        top5 = busiest_airport(df)
    
        busiest_df = pd.DataFrame([{
            'airport': r['airport'],
            'movements': r['count'],
            'window_start': pd.Timestamp(r['window_start']).strftime("%Y-%m-%d %H:%M"),
            'window_end': pd.Timestamp(r['window_end']).strftime("%Y-%m-%d %H:%M")
        } for r in top5])
    
        st.markdown("### Busy Skies", help="All movements in 24h period")
        st.dataframe(busiest_df, use_container_width=True, hide_index=True)
    
    def top5_aircraft_unique_pilots(df):
        result = (
            df.groupby('aircraft')['pilot']
            .nunique()
            .sort_values(ascending=False)
            .head(5)
            .reset_index()
        )
        result.columns = ['aircraft', 'unique_pilots']
        return result
    
    def top10_company_man(df):
        result = (
            df.groupby('pilot')['ac_airline_name']
            .nunique()
            .sort_values(ascending=False)
            .head(5)
            .reset_index()
        )
        result.columns = ['pilot', 'unique_airlines']
        return result
        
    
    # ===============================================================
    # DISPLAY BLOCK
    # ===============================================================
    
    
    row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
    row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
    
    
    with row1_col4:
        st.markdown("### Butts in seats", help="Unique pilots per aircraft")
        st.dataframe(top5_aircraft_unique_pilots(filtered_df), use_container_width=True, hide_index=True)
    
    trailblazer_table = compute_trailblazers(filtered_df)
    trailblazer_top10 = top10_trailblazers(trailblazer_table)
        
    with row1_col1:
        st.markdown("### Trailblazers", help="Trailblazer is first on route. Followers are pilots flying the same route afterwards")
        st.dataframe(trailblazer_top10, use_container_width=True, hide_index=True)
    

    with row1_col3:
        st.markdown("### Company Man", help="Number of unique airlines flown by pilot")
        st.dataframe(top10_company_man(filtered_df), use_container_width=True, hide_index=True)
        
    
    with row1_col2:
        single_ac_hours = single_aircraft_pilot_hours(filtered_df)
        st.markdown("### Loyalists", help="Most hours in one aircraft on the network. Lost if you fly more than that one aircraft")
        st.dataframe(single_ac_hours, use_container_width=True, hide_index=True)

    airline_network_frame = compute_airline_network_size(df)
    airline_network_top10 = top10_airline_network_size(airline_network_frame)
    
    with row2_col1:
        st.markdown("### Airline Network", help="Unique airports operated")
        st.dataframe(airline_network_top10, use_container_width=True, hide_index=True)
    
    with row2_col3:
        display_top_snake(filtered_df)
    
    with row2_col2:
        display_busiest_airport(filtered_df)
    
    with row2_col4:
        pass  # TBD
    

    

