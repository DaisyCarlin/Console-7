import math
import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Flight Activity", layout="wide")

st.title("Flight Activity")
st.caption(
    "Open-source flight monitoring dashboard for live air traffic, emergency squawks, and public government / military-related heuristics."
)

# =========================================================
# CONFIG
# =========================================================
OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"

GOV_MIL_COUNTRY_KEYWORDS = [
    "united states",
    "russia",
    "china",
    "united kingdom",
    "france",
    "germany",
    "italy",
    "turkey",
    "israel",
    "india",
]

GOV_MIL_CALLSIGN_PREFIXES = [
    "RCH",
    "MC",
    "RRR",
    "QID",
    "ASY",
    "CNV",
    "GAF",
    "IAM",
    "HKY",
    "NATO",
]

SQUAWK_MEANINGS = {
    "7500": {
        "label": "Hijack / unlawful interference",
        "severity": "HIGH",
    },
    "7600": {
        "label": "Radio failure",
        "severity": "HIGH",
    },
    "7700": {
        "label": "General emergency",
        "severity": "HIGH",
    },
    "7400": {
        "label": "UAS lost link",
        "severity": "MEDIUM",
    },
}

# =========================================================
# HELPERS
# =========================================================
def safe_str(value):
    if value is None:
        return ""
    return str(value).strip()

def classify_callsign(callsign: str) -> str:
    cs = safe_str(callsign).upper()
    if any(cs.startswith(prefix) for prefix in GOV_MIL_CALLSIGN_PREFIXES):
        return "Likely government/military-related"
    return "Unclassified by callsign"

def classify_country(country: str) -> str:
    c = safe_str(country).lower()
    if any(k in c for k in GOV_MIL_COUNTRY_KEYWORDS):
        return "Watched state/country"
    return "Other / unknown"

def heading_endpoint(lat, lon, bearing_deg, distance_deg=1.0):
    if pd.isna(lat) or pd.isna(lon) or pd.isna(bearing_deg):
        return None, None

    radians = math.radians(float(bearing_deg))
    dlat = distance_deg * math.cos(radians)
    dlon = distance_deg * math.sin(radians)
    return lat + dlat, lon + dlon

def marker_color(row):
    if row.get("is_emergency_squawk") is True:
        return "red"
    if (
        row.get("gov_mil_callsign_flag") == "Likely government/military-related"
        or row.get("country_watch_flag") == "Watched state/country"
    ):
        return "blue"
    return "green"

def build_popup(row):
    callsign = row.get("callsign") or "Unknown"
    country = row.get("origin_country") or "Unknown"
    squawk = row.get("squawk") or "None"
    meaning = row.get("squawk_label") or "None"
    altitude = row.get("baro_altitude")
    velocity = row.get("velocity")
    gov_flag = row.get("gov_mil_callsign_flag") or "None"
    country_flag = row.get("country_watch_flag") or "None"

    altitude_text = f"{int(altitude):,} m" if pd.notna(altitude) else "Unknown"
    velocity_text = f"{int(velocity):,} m/s" if pd.notna(velocity) else "Unknown"

    return f"""
    <b>Callsign:</b> {callsign}<br>
    <b>Origin Country:</b> {country}<br>
    <b>Squawk:</b> {squawk}<br>
    <b>Meaning:</b> {meaning}<br>
    <b>Altitude:</b> {altitude_text}<br>
    <b>Velocity:</b> {velocity_text}<br>
    <b>Callsign Heuristic:</b> {gov_flag}<br>
    <b>Country Heuristic:</b> {country_flag}
    """

# =========================================================
# DATA LOADING
# =========================================================
@st.cache_data(ttl=60)
def load_flights():
    response = requests.get(OPENSKY_STATES_URL, timeout=20)
    response.raise_for_status()
    payload = response.json()

    states = payload.get("states") or []

    rows = []
    for s in states:
        rows.append(
            {
                "icao24": s[0],
                "callsign": safe_str(s[1]),
                "origin_country": safe_str(s[2]),
                "time_position": s[3],
                "last_contact": s[4],
                "longitude": s[5],
                "latitude": s[6],
                "baro_altitude": s[7],
                "on_ground": s[8],
                "velocity": s[9],
                "true_track": s[10],
                "vertical_rate": s[11],
                "geo_altitude": s[13],
                "squawk": safe_str(s[14]),
                "spi": s[15],
                "position_source": s[16],
                "category": s[17] if len(s) > 17 else None,
            }
        )

    df = pd.DataFrame(rows)

    if not df.empty:
        df["gov_mil_callsign_flag"] = df["callsign"].apply(classify_callsign)
        df["country_watch_flag"] = df["origin_country"].apply(classify_country)
        df["is_emergency_squawk"] = df["squawk"].isin(SQUAWK_MEANINGS.keys())
        df["squawk_label"] = df["squawk"].apply(
            lambda x: SQUAWK_MEANINGS[x]["label"] if x in SQUAWK_MEANINGS else ""
        )
        df["squawk_severity"] = df["squawk"].apply(
            lambda x: SQUAWK_MEANINGS[x]["severity"] if x in SQUAWK_MEANINGS else "LOW"
        )

    return df

data_error = None

try:
    flights_df = load_flights()
except Exception as e:
    flights_df = pd.DataFrame()
    data_error = str(e)

# =========================================================
# FILTERS
# =========================================================
st.subheader("Map Filters")

f1, f2, f3, f4 = st.columns(4)

with f1:
    map_show_gov_mil_only = st.checkbox("Map: government / military-related only", value=False)

with f2:
    map_show_airborne_only = st.checkbox("Map: airborne only", value=True)

with f3:
    map_country_filter = st.text_input("Map: country contains", value="").strip().lower()

with f4:
    show_heading_lines = st.checkbox("Show direction lines", value=True)

map_df = flights_df.copy()

if not map_df.empty:
    if map_show_gov_mil_only:
        map_df = map_df[
            (map_df["gov_mil_callsign_flag"] == "Likely government/military-related")
            | (map_df["country_watch_flag"] == "Watched state/country")
        ]

    if map_show_airborne_only:
        map_df = map_df[map_df["on_ground"] == False]

    if map_country_filter:
        map_df = map_df[
            map_df["origin_country"].fillna("").str.lower().str.contains(map_country_filter, na=False)
        ]

# =========================================================
# DERIVED TABLES
# =========================================================
emergency_df = pd.DataFrame()
gov_mil_df = pd.DataFrame()

if not flights_df.empty:
    emergency_df = flights_df[flights_df["is_emergency_squawk"] == True].copy()

    gov_mil_df = flights_df[
        (flights_df["gov_mil_callsign_flag"] == "Likely government/military-related")
        | (flights_df["country_watch_flag"] == "Watched state/country")
    ].copy()

# =========================================================
# STATUS CARDS
# =========================================================
st.subheader("System Status")

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric("Flights loaded", len(flights_df))

with c2:
    st.metric("Emergency squawks", len(emergency_df))

with c3:
    st.metric("Gov / military-related", len(gov_mil_df))

with c4:
    if data_error:
        st.error("Flight Feed Offline")
    else:
        st.success("Flight Feed Online")

st.divider()

# =========================================================
# MAP + SIDE PANEL
# =========================================================
left, right = st.columns([2.2, 1])

with left:
    st.subheader("Live Flight Map")

    if data_error:
        st.error(f"Flight data unavailable: {data_error}")
    elif map_df.empty:
        st.info("No flights match the current map filters.")
    else:
        coords_df = map_df.dropna(subset=["latitude", "longitude"]).copy()

        if coords_df.empty:
            st.info("No coordinates available for the current map filters.")
        else:
            center_lat = coords_df["latitude"].mean()
            center_lon = coords_df["longitude"].mean()

            flight_map = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=4,
                tiles="CartoDB positron",
                control_scale=True,
            )

            for _, row in coords_df.iterrows():
                lat = row["latitude"]
                lon = row["longitude"]
                color = marker_color(row)

                folium.CircleMarker(
                    location=[lat, lon],
                    radius=5,
                    color=color,
                    fill=True,
                    fill_opacity=0.85,
                    popup=folium.Popup(build_popup(row), max_width=320),
                    tooltip=row.get("callsign") or "Unknown",
                ).add_to(flight_map)

                if show_heading_lines and row.get("on_ground") is False:
                    end_lat, end_lon = heading_endpoint(
                        lat,
                        lon,
                        row.get("true_track"),
                        distance_deg=1.0,
                    )
                    if end_lat is not None and end_lon is not None:
                        folium.PolyLine(
                            locations=[[lat, lon], [end_lat, end_lon]],
                            color=color,
                            weight=2,
                            opacity=0.7,
                        ).add_to(flight_map)

            st_folium(flight_map, use_container_width=True, height=650)

with right:
    st.subheader("Map Legend")
    st.markdown(
        """
- 🔴 **Red** = emergency squawk  
- 🔵 **Blue** = government / military-related heuristic match  
- 🟢 **Green** = other visible flights  
"""
    )
    st.caption("Direction lines show approximate current heading only. They are not full route histories.")

    if not emergency_df.empty:
        st.markdown("**Active emergency examples**")
        sample = emergency_df.head(5)[["callsign", "squawk", "squawk_label"]].copy()
        sample = sample.rename(
            columns={
                "callsign": "Callsign",
                "squawk": "Squawk",
                "squawk_label": "Meaning",
            }
        )
        st.dataframe(sample, use_container_width=True, hide_index=True)
    else:
        st.info("No active emergency squawks in the current feed.")

st.divider()

# =========================================================
# EMERGENCY EVENTS
# =========================================================
st.subheader("Emergency Squawk Events")

if data_error:
    st.error(f"Flight feed unavailable: {data_error}")
elif emergency_df.empty:
    st.success("No emergency squawk events are currently visible.")
else:
    emergency_display = emergency_df[
        [
            "callsign",
            "origin_country",
            "squawk",
            "squawk_label",
            "on_ground",
            "velocity",
            "baro_altitude",
        ]
    ].copy()

    emergency_display = emergency_display.rename(
        columns={
            "callsign": "Callsign",
            "origin_country": "Origin Country",
            "squawk": "Squawk",
            "squawk_label": "Meaning",
            "on_ground": "On Ground",
            "velocity": "Velocity (m/s)",
            "baro_altitude": "Baro Altitude (m)",
        }
    )

    st.dataframe(emergency_display, use_container_width=True, hide_index=True)

st.divider()

# =========================================================
# GOV / MIL SECTION
# =========================================================
st.subheader("Government / Military-Related Flights")
st.caption("This section uses public callsign and country heuristics only.")

if data_error:
    st.error(f"Flight feed unavailable: {data_error}")
elif gov_mil_df.empty:
    st.info("No flights matched the current public government / military heuristics.")
else:
    gov_display = gov_mil_df[
        [
            "callsign",
            "origin_country",
            "gov_mil_callsign_flag",
            "country_watch_flag",
            "squawk",
            "squawk_label",
            "on_ground",
            "velocity",
            "baro_altitude",
        ]
    ].copy()

    gov_display = gov_display.rename(
        columns={
            "callsign": "Callsign",
            "origin_country": "Origin Country",
            "gov_mil_callsign_flag": "Callsign Heuristic",
            "country_watch_flag": "Country Heuristic",
            "squawk": "Squawk",
            "squawk_label": "Meaning",
            "on_ground": "On Ground",
            "velocity": "Velocity (m/s)",
            "baro_altitude": "Baro Altitude (m)",
        }
    )

    st.dataframe(gov_display, use_container_width=True, hide_index=True)

st.divider()

# =========================================================
# ANALYST SUMMARY
# =========================================================
st.subheader("Analyst Summary")

if data_error:
    st.markdown(
        f"""
- The live flight feed is currently unavailable.
- Error returned by the upstream source: `{data_error}`
- The page is online, but the flight data source needs to recover.
"""
    )
else:
    st.markdown(
        f"""
- **{len(flights_df)}** live flight state records were loaded.
- **{len(emergency_df)}** flights are currently showing emergency squawk codes.
- **{len(gov_mil_df)}** flights matched the public government / military heuristics.
- The main map now shows **all matching live flights by default**.
- Direction lines show **approximate current heading**, not full historical routes.
"""
    )
