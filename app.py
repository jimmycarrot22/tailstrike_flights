
import streamlit as st
import pandas as pd
import pydeck as pdk
import matplotlib.colors as mcolors
import altair as alt

# csv load
@st.cache_data
def load_csv(url):
    return pd.read_csv(url)

DF_URL = "https://raw.githubusercontent.com/jimmycarrot22/tailstrike_flights/main/data/tailstrike_flights.csv"
AIRPORTS_URL = "https://raw.githubusercontent.com/jimmycarrot22/tailstrike_flights/main/data/airports.csv"

# Load dataframes
df = load_csv(DF_URL)
airports = load_csv(AIRPORTS_URL)

# Convert date column from string to datetime
df["date_dep_form"] = pd.to_datetime(df["date_dep_form"], errors="coerce")

st.set_page_config(layout="wide")

# header
st.markdown("<h2 style='font-size:24px; font-weight:700; margin-bottom:10px;'>Tailstrike Flights </h2>", unsafe_allow_html=True)

def get_coords(code):
    row = airports[airports["icao_code"] == code]
    if not row.empty:
        return row.iloc[0]["latitude_deg"], row.iloc[0]["longitude_deg"]

    row = airports[airports["gps_code"] == code]
    if not row.empty:
        return row.iloc[0]["latitude_deg"], row.iloc[0]["longitude_deg"]

    row = airports[airports["ident"] == code]
    if not row.empty:
        return row.iloc[0]["latitude_deg"], row.iloc[0]["longitude_deg"]

    return None

# =============================================================
#                      FILTERING SECTION
# =============================================================

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
    dep = get_coords(flight["departure"])
    arr = get_coords(flight["arrival"])

    if dep is None or arr is None:
        continue

    flight_lines.append({"from_lat": dep[0],
                        "from_lon": dep[1],
                        "to_lat": arr[0],
                        "to_lon": arr[1],
                        "pilot": flight["pilot"],
                        "aircraft": flight["aircraft"],
                        "distance": flight["distance_nm"],
                        "duration_min": flight["duration_min"],
                        "departure": flight["departure"],
                        "arrival": flight["arrival"],})

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
            f"<b>Distance:</b> {r['distance']} nm<br>"
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



