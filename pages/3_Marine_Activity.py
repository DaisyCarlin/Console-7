import math
import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Marine Activity", layout="wide")

st.title("Marine Activity Monitor")
st.caption("Live open-source maritime monitoring for commercial, government, and military-linked vessel activity.")

# =========================================================
# CONFIG
# =========================================================

# Optional live feed:
# If you later set st.secrets["marine_feed_url"], the page will try to load it.
# Expected JSON format:
# [
#   {
#     "name": "USNS EXAMPLE",
#     "mmsi": "123456789",
#     "imo": "1234567",
#     "flag": "United States",
#     "ship_type": "Military",
#     "lat": 36.1,
#     "lon": -5.3,
#     "speed": 14.2,
#     "course": 90,
#     "destination": "Unknown",
#     "status": "Under way using engine",
#     "last_update": "2026-03-23T16:00:00Z"
#   }
# ]

WATCH_FLAGS = [
    "United States",
    "United Kingdom",
    "France",
    "Germany",
    "Italy",
    "Turkey",
    "India",
    "China",
    "Russia",
    "Israel",
]

GOV_MIL_NAME_KEYWORDS = [
    "navy",
    "naval",
    "coast guard",
    "cgc",
    "usns",
    "uss",
    "hms",
    "fs ",
    "rfa",
    "pla",
    "warship",
    "destroyer",
    "frigate",
    "carrier",
    "patrol",
    "auxiliary",
]

GOV_MIL_TYPES = [
    "Military",
    "Naval",
    "Patrol",
    "Government",
    "Coast Guard",
]

TANKER_TYPES = [
    "Tanker",
    "Oil Tanker",
    "LNG Tanker",
    "Chemical Tanker",
    "Gas Tanker",
]

HIGH_INTEREST_STATUSES = [
    "Not under command",
    "Restricted manoeuverability",
    "Constrained by her draught",
    "Aground",
]

DEMO_VESSELS = [
    {
        "name": "USNS ARCTIC",
        "mmsi": "368123456",
        "imo": "0000001",
        "flag": "United States",
        "ship_type": "Military",
        "lat": 36.140,
        "lon": -5.353,
        "speed": 17.8,
        "course": 85,
        "destination": "Unknown",
        "status": "Under way using engine",
        "last_update": "2026-03-23T16:00:00Z",
    },
    {
        "name": "HMS EXAMPLE",
        "mmsi": "232111222",
        "imo": "0000002",
        "flag": "United Kingdom",
        "ship_type": "Naval",
        "lat": 50.367,
        "lon": -4.134,
        "speed": 12.4,
        "course": 210,
        "destination": "Portsmouth",
        "status": "Under way using engine",
        "last_update": "2026-03-23T16:01:00Z",
    },
    {
        "name": "GLOBAL ENERGY",
        "mmsi": "538009999",
        "imo": "9234567",
        "flag": "Marshall Islands",
        "ship_type": "Oil Tanker",
        "lat": 25.276,
        "lon": 55.296,
        "speed": 14.9,
        "course": 120,
        "destination": "SINGAPORE",
        "status": "Under way using engine",
        "last_update": "2026-03-23T16:02:00Z",
    },
    {
        "name": "PACIFIC BRIDGE",
        "mmsi": "563008888",
        "imo": "9345678",
        "flag": "Singapore",
        "ship_type": "Container Ship",
        "lat": 1.250,
        "lon": 103.840,
        "speed": 18.2,
        "course": 70,
        "destination": "BUSAN",
        "status": "Under way using engine",
        "last_update": "2026-03-23T16:03:00Z",
    },
    {
        "name": "COAST GUARD 12",
        "mmsi": "338007777",
        "imo": "",
        "flag": "United States",
        "ship_type": "Coast Guard",
        "lat": 29.760,
        "lon": -94.830,
        "speed": 22.5,
        "course": 145,
        "destination": "Patrol",
        "status": "Restricted manoeuverability",
        "last_update": "2026-03-23T16:04:00Z",
    },
    {
        "name": "MEDITERRANEAN STAR",
        "mmsi": "247006666",
        "imo": "9456789",
        "flag": "Italy",
        "ship_type": "Chemical Tanker",
        "lat": 37.983,
        "lon": 23.727,
        "speed": 0.3,
        "course": 0,
        "destination": "Piraeus",
        "status": "Moored",
        "last_update": "2026-03-23T16:05:00Z",
    },
]

# =========================================================
# HELPERS
# =========================================================
def safe_str(value):
    if value is None:
        return ""
    return str(value).strip()

def get_secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

def vessel_is_gov_mil(row):
    name = safe_str(row.get("name")).lower()
    flag = safe_str(row.get("flag"))
    ship_type = safe_str(row.get("ship_type"))

    name_match = any(k in name for k in GOV_MIL_NAME_KEYWORDS)
    flag_match = flag in WATCH_FLAGS
    type_match = ship_type in GOV_MIL_TYPES

    return name_match or type_match or (flag_match and name_match)

def vessel_is_tanker(row):
    ship_type = safe_str(row.get("ship_type"))
    return ship_type in TANKER_TYPES

def vessel_is_high_interest(row):
    status = safe_str(row.get("status"))
    speed = row.get("speed")

    if status in HIGH_INTEREST_STATUSES:
        return True

    if pd.notna(speed) and float(speed) >= 25:
        return True

    return False

def heading_endpoint(lat, lon, bearing_deg, distance_deg=0.8):
    if pd.isna(lat) or pd.isna(lon) or pd.isna(bearing_deg):
        return None, None

    radians = math.radians(float(bearing_deg))
    dlat = distance_deg * math.cos(radians)
    dlon = distance_deg * math.sin(radians)

    return lat + dlat, lon + dlon

def marker_color(row):
    if row.get("is_high_interest") is True:
        return "red"
    if row.get("is_gov_mil") is True:
        return "blue"
    if row.get("is_tanker") is True:
        return "orange"
    return "green"

def popup_html(row):
    return f"""
    <b>Name:</b> {safe_str(row.get("name"))}<br>
    <b>MMSI:</b> {safe_str(row.get("mmsi"))}<br>
    <b>IMO:</b> {safe_str(row.get("imo"))}<br>
    <b>Flag:</b> {safe_str(row.get("flag"))}<br>
    <b>Type:</b> {safe_str(row.get("ship_type"))}<br>
    <b>Speed:</b> {safe_str(row.get("speed"))} kn<br>
    <b>Course:</b> {safe_str(row.get("course"))}<br>
    <b>Status:</b> {safe_str(row.get("status"))}<br>
    <b>Destination:</b> {safe_str(row.get("destination"))}<br>
    <b>Last Update:</b> {safe_str(row.get("last_update"))}
    """

# =========================================================
# DATA LOADING
# =========================================================
@st.cache_data(ttl=120)
def load_vessels():
    marine_feed_url = get_secret("marine_feed_url")

    if marine_feed_url:
        response = requests.get(marine_feed_url, timeout=20)
        response.raise_for_status()
        data = response.json()
        df = pd.DataFrame(data)
        source = "live"
    else:
        df = pd.DataFrame(DEMO_VESSELS)
        source = "demo"

    if df.empty:
        return df, source

    numeric_cols = ["lat", "lon", "speed", "course"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["is_gov_mil"] = df.apply(vessel_is_gov_mil, axis=1)
    df["is_tanker"] = df.apply(vessel_is_tanker, axis=1)
    df["is_high_interest"] = df.apply(vessel_is_high_interest, axis=1)

    return df, source

data_error = None

try:
    vessels_df, data_source = load_vessels()
    feed_ok = True
except Exception as e:
    vessels_df = pd.DataFrame()
    data_source = "error"
    feed_ok = False
    data_error = str(e)

# =========================================================
# FILTERS
# =========================================================
st.subheader("Map Filters")

f1, f2, f3, f4 = st.columns(4)

with f1:
    map_show_gov_mil_only = st.checkbox("Map: government / military-linked only", value=False)

with f2:
    map_show_tankers_only = st.checkbox("Map: tankers only", value=False)

with f3:
    map_show_high_interest_only = st.checkbox("Map: high-interest only", value=False)

with f4:
    show_heading_lines = st.checkbox("Show direction lines", value=True)

map_df = vessels_df.copy()

if not map_df.empty:
    if map_show_gov_mil_only:
        map_df = map_df[map_df["is_gov_mil"] == True]

    if map_show_tankers_only:
        map_df = map_df[map_df["is_tanker"] == True]

    if map_show_high_interest_only:
        map_df = map_df[map_df["is_high_interest"] == True]

# =========================================================
# DERIVED TABLES
# =========================================================
gov_mil_df = pd.DataFrame()
tanker_df = pd.DataFrame()
high_interest_df = pd.DataFrame()

if not vessels_df.empty:
    gov_mil_df = vessels_df[vessels_df["is_gov_mil"] == True].copy()
    tanker_df = vessels_df[vessels_df["is_tanker"] == True].copy()
    high_interest_df = vessels_df[vessels_df["is_high_interest"] == True].copy()

# =========================================================
# STATUS CARDS
# =========================================================
st.subheader("System Status")

c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.metric("Vessels loaded", len(vessels_df))

with c2:
    st.metric("Gov / military-linked", len(gov_mil_df))

with c3:
    st.metric("Tankers", len(tanker_df))

with c4:
    st.metric("High-interest vessels", len(high_interest_df))

with c5:
    if feed_ok:
        if data_source == "live":
            st.success("Marine Feed Online")
        else:
            st.warning("Demo Feed Active")
    else:
        st.error("Marine Feed Offline")

st.divider()

# =========================================================
# MAP + SIDE PANEL
# =========================================================
left, right = st.columns([2.2, 1])

with left:
    st.subheader("Live Vessel Map")

    if not feed_ok:
        st.error(data_error)
    elif map_df.empty:
        st.info("No vessels match the current map filters.")
    else:
        coords_df = map_df.dropna(subset=["lat", "lon"]).copy()

        if coords_df.empty:
            st.info("No coordinates available for the current map filters.")
        else:
            center_lat = coords_df["lat"].mean()
            center_lon = coords_df["lon"].mean()

            vessel_map = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=3,
                tiles="CartoDB positron",
                control_scale=True,
            )

            for _, row in coords_df.iterrows():
                lat = row["lat"]
                lon = row["lon"]
                color = marker_color(row)

                folium.CircleMarker(
                    location=[lat, lon],
                    radius=5,
                    color=color,
                    fill=True,
                    fill_opacity=0.85,
                    popup=folium.Popup(popup_html(row), max_width=320),
                    tooltip=safe_str(row.get("name")) or "Unknown vessel",
                ).add_to(vessel_map)

                if show_heading_lines and pd.notna(row.get("course")) and pd.notna(row.get("speed")):
                    end_lat, end_lon = heading_endpoint(lat, lon, row.get("course"), distance_deg=0.8)
                    if end_lat is not None and end_lon is not None:
                        folium.PolyLine(
                            locations=[[lat, lon], [end_lat, end_lon]],
                            color=color,
                            weight=2,
                            opacity=0.7,
                        ).add_to(vessel_map)

            st_folium(vessel_map, use_container_width=True, height=700)

with right:
    st.subheader("Map Legend")

    st.markdown(
        """
- 🔴 **Red** = high-interest vessel  
- 🔵 **Blue** = government / military-linked  
- 🟠 **Orange** = tanker  
- 🟢 **Green** = other visible vessel  
"""
    )

    st.caption("Direction lines show approximate current heading only.")

    if data_source == "demo":
        st.info("This page is currently using demo vessel data. Add `marine_feed_url` in Streamlit secrets later for a live JSON feed.")

st.divider()

# =========================================================
# GOV / MIL SECTION
# =========================================================
st.subheader("Government / Military-Linked Vessels")

if not feed_ok:
    st.error(data_error)
elif gov_mil_df.empty:
    st.info("No government / military-linked vessels are visible right now.")
else:
    gov_display = gov_mil_df[
        ["name", "mmsi", "imo", "flag", "ship_type", "speed", "destination", "status", "last_update"]
    ].copy()

    gov_display = gov_display.rename(
        columns={
            "name": "Vessel",
            "mmsi": "MMSI",
            "imo": "IMO",
            "flag": "Flag",
            "ship_type": "Type",
            "speed": "Speed (kn)",
            "destination": "Destination",
            "status": "Status",
            "last_update": "Last Update",
        }
    )

    st.dataframe(gov_display, use_container_width=True, hide_index=True)

st.divider()

# =========================================================
# HIGH-INTEREST SECTION
# =========================================================
st.subheader("High-Interest Vessel Activity")

if not feed_ok:
    st.error(data_error)
elif high_interest_df.empty:
    st.success("No high-interest vessel movements are currently flagged.")
else:
    hi_display = high_interest_df[
        ["name", "flag", "ship_type", "speed", "destination", "status", "last_update"]
    ].copy()

    hi_display = hi_display.rename(
        columns={
            "name": "Vessel",
            "flag": "Flag",
            "ship_type": "Type",
            "speed": "Speed (kn)",
            "destination": "Destination",
            "status": "Status",
            "last_update": "Last Update",
        }
    )

    st.dataframe(hi_display, use_container_width=True, hide_index=True)

st.divider()

# =========================================================
# TANKER SECTION
# =========================================================
st.subheader("Tanker Traffic")

if not feed_ok:
    st.error(data_error)
elif tanker_df.empty:
    st.info("No tanker traffic is currently visible.")
else:
    tanker_display = tanker_df[
        ["name", "flag", "ship_type", "speed", "destination", "status", "last_update"]
    ].copy()

    tanker_display = tanker_display.rename(
        columns={
            "name": "Vessel",
            "flag": "Flag",
            "ship_type": "Type",
            "speed": "Speed (kn)",
            "destination": "Destination",
            "status": "Status",
            "last_update": "Last Update",
        }
    )

    st.dataframe(tanker_display, use_container_width=True, hide_index=True)

st.divider()

# =========================================================
# ANALYST SUMMARY
# =========================================================
st.subheader("Analyst Summary")

if not feed_ok:
    st.markdown(
        f"""
- The marine feed is currently unavailable.
- Error returned by the upstream source: `{data_error}`
- The page is online, but the vessel data source needs attention.
"""
    )
else:
    source_text = "live feed" if data_source == "live" else "demo feed"

    st.markdown(
        f"""
- **{len(vessels_df)}** vessel records were loaded from the **{source_text}**.
- **{len(gov_mil_df)}** vessels are currently categorized as government / military-linked.
- **{len(tanker_df)}** vessels are currently categorized as tankers.
- **{len(high_interest_df)}** vessels are currently flagged as high-interest.
- The map shows all visible vessels by default unless filters are applied.
"""
    )
