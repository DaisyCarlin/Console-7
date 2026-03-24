import json
import math
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from websocket import create_connection

st.set_page_config(page_title="Marine Activity", layout="wide")

st.title("Marine Activity Monitor")
st.caption("Open-source maritime monitoring for commercial shipping, tanker flows, and chokepoint activity.")

# =========================================================
# CONFIG
# =========================================================
AISSTREAM_WS_URL = "wss://stream.aisstream.io/v0/stream"

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

CHOKEPOINTS = {
    "Global": None,
    "Suez": {"lat_min": 29.0, "lat_max": 31.8, "lon_min": 31.0, "lon_max": 33.5},
    "Hormuz": {"lat_min": 25.0, "lat_max": 27.5, "lon_min": 55.0, "lon_max": 58.5},
    "Bab el-Mandeb": {"lat_min": 11.0, "lat_max": 14.5, "lon_min": 42.0, "lon_max": 45.5},
    "Malacca": {"lat_min": 0.5, "lat_max": 6.5, "lon_min": 96.0, "lon_max": 104.5},
    "Panama": {"lat_min": 7.0, "lat_max": 10.5, "lon_min": -81.5, "lon_max": -78.0},
    "Bosporus": {"lat_min": 40.8, "lat_max": 41.5, "lon_min": 28.8, "lon_max": 29.5},
}

DEMO_VESSELS = [
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
        "last_update": "2026-03-23T16:00:00Z",
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
    {
        "name": "RED SEA LINK",
        "mmsi": "636001234",
        "imo": "9567890",
        "flag": "Liberia",
        "ship_type": "Container Ship",
        "lat": 12.8,
        "lon": 43.3,
        "speed": 16.8,
        "course": 335,
        "destination": "JEDDAH",
        "status": "Under way using engine",
        "last_update": "2026-03-23T16:06:00Z",
    },
]

# =========================================================
# HELPERS
# =========================================================
def get_secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

def safe_str(value):
    if value is None:
        return ""
    return str(value).strip()

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

def in_bbox(lat, lon, bbox):
    if bbox is None:
        return True
    if pd.isna(lat) or pd.isna(lon):
        return False
    return (
        bbox["lat_min"] <= lat <= bbox["lat_max"]
        and bbox["lon_min"] <= lon <= bbox["lon_max"]
    )

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
# AISSTREAM LOADER
# =========================================================
@st.cache_data(ttl=120)
def load_vessels():
    aisstream_key = get_secret("aisstream_key")

    if not aisstream_key:
        df = pd.DataFrame(DEMO_VESSELS)
        source = "demo"
    else:
        ws = create_connection(AISSTREAM_WS_URL, timeout=20)

        subscribe_message = {
            "APIKey": aisstream_key,
            "BoundingBoxes": [[[-90, -180], [90, 180]]],
            "FilterMessageTypes": ["PositionReport"],
        }

        ws.send(json.dumps(subscribe_message))

        rows = []
        max_messages = 40

        for _ in range(max_messages):
            raw = ws.recv()
            payload = json.loads(raw)

            msg = payload.get("Message", {})
            meta = payload.get("MetaData", {})

            if "PositionReport" not in msg:
                continue

            report = msg["PositionReport"]

            rows.append({
                "name": meta.get("ShipName") or f"MMSI {meta.get('MMSI')}",
                "mmsi": str(meta.get("MMSI", "")),
                "imo": safe_str(meta.get("IMO")),
                "flag": safe_str(meta.get("Flag")),
                "ship_type": safe_str(meta.get("ShipType")),
                "lat": report.get("Latitude"),
                "lon": report.get("Longitude"),
                "speed": report.get("Sog"),
                "course": report.get("Cog"),
                "destination": safe_str(meta.get("Destination")),
                "status": safe_str(report.get("NavigationalStatus")),
                "last_update": safe_str(meta.get("time_utc")),
            })

        ws.close()

        df = pd.DataFrame(rows)
        source = "live"

        if df.empty:
            raise RuntimeError("AISStream returned no vessel messages in the snapshot window.")

    if not df.empty:
        for col in ["lat", "lon", "speed", "course"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df["is_tanker"] = df.apply(vessel_is_tanker, axis=1)
        df["is_high_interest"] = df.apply(vessel_is_high_interest, axis=1)

    return df, source

# =========================================================
# LOAD DATA
# =========================================================
data_error = None

try:
    vessels_df, data_source = load_vessels()
    feed_ok = True
except Exception as e:
    vessels_df = pd.DataFrame(DEMO_VESSELS)
    vessels_df["is_tanker"] = vessels_df.apply(vessel_is_tanker, axis=1)
    vessels_df["is_high_interest"] = vessels_df.apply(vessel_is_high_interest, axis=1)
    data_source = "demo"
    feed_ok = False
    data_error = str(e)

# =========================================================
# FILTERS
# =========================================================
st.subheader("Map Filters")

f1, f2, f3, f4 = st.columns(4)

with f1:
    selected_region = st.selectbox("Region", list(CHOKEPOINTS.keys()), index=0)

with f2:
    map_show_tankers_only = st.checkbox("Map: tankers only", value=False)

with f3:
    map_show_high_interest_only = st.checkbox("Map: high-interest only", value=False)

with f4:
    show_heading_lines = st.checkbox("Show direction lines", value=True)

map_df = vessels_df.copy()

if not map_df.empty:
    bbox = CHOKEPOINTS[selected_region]
    map_df = map_df[map_df.apply(lambda r: in_bbox(r.get("lat"), r.get("lon"), bbox), axis=1)]

    if map_show_tankers_only:
        map_df = map_df[map_df["is_tanker"] == True]

    if map_show_high_interest_only:
        map_df = map_df[map_df["is_high_interest"] == True]

# =========================================================
# DERIVED TABLES
# =========================================================
tanker_df = pd.DataFrame()
high_interest_df = pd.DataFrame()
chokepoint_df = pd.DataFrame()

if not vessels_df.empty:
    tanker_df = vessels_df[vessels_df["is_tanker"] == True].copy()
    high_interest_df = vessels_df[vessels_df["is_high_interest"] == True].copy()

    bbox = CHOKEPOINTS[selected_region]
    chokepoint_df = vessels_df[vessels_df.apply(lambda r: in_bbox(r.get("lat"), r.get("lon"), bbox), axis=1)].copy()

# =========================================================
# STATUS CARDS
# =========================================================
st.subheader("System Status")

c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.metric("Vessels loaded", len(vessels_df))

with c2:
    st.metric("Tankers", len(tanker_df))

with c3:
    st.metric("High-interest vessels", len(high_interest_df))

with c4:
    st.metric(f"{selected_region} vessels", len(chokepoint_df))

with c5:
    if feed_ok and data_source == "live":
        st.success("Marine Feed Online")
    elif data_source == "demo":
        st.warning("Demo Feed Active")
    else:
        st.error("Marine Feed Offline")

if data_error:
    st.warning(f"Live AIS snapshot unavailable, showing demo data instead: {data_error}")

st.divider()

# =========================================================
# MAP
# =========================================================
left, right = st.columns([2.2, 1])

with left:
    st.subheader("Live Vessel Map")

    if map_df.empty:
        st.info("No vessels match the current map filters.")
    else:
        coords_df = map_df.dropna(subset=["lat", "lon"]).copy()

        if coords_df.empty:
            st.info("No coordinates available for the current map filters.")
        else:
            if selected_region != "Global" and CHOKEPOINTS[selected_region] is not None:
                bbox = CHOKEPOINTS[selected_region]
                center_lat = (bbox["lat_min"] + bbox["lat_max"]) / 2
                center_lon = (bbox["lon_min"] + bbox["lon_max"]) / 2
                zoom_start = 6
            else:
                center_lat = coords_df["lat"].mean()
                center_lon = coords_df["lon"].mean()
                zoom_start = 3

            vessel_map = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=zoom_start,
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
- 🟠 **Orange** = tanker  
- 🟢 **Green** = other visible vessel  
"""
    )
    st.caption("Direction lines show approximate current heading only.")

st.divider()

# =========================================================
# TABLES
# =========================================================
st.subheader(f"{selected_region} Traffic")

if chokepoint_df.empty:
    st.info(f"No vessels are currently visible in {selected_region}.")
else:
    choke_display = chokepoint_df[
        ["name", "flag", "ship_type", "speed", "destination", "status", "last_update"]
    ].copy()

    choke_display = choke_display.rename(columns={
        "name": "Vessel",
        "flag": "Flag",
        "ship_type": "Type",
        "speed": "Speed (kn)",
        "destination": "Destination",
        "status": "Status",
        "last_update": "Last Update",
    })

    st.dataframe(choke_display, use_container_width=True, hide_index=True)

st.divider()

st.subheader("High-Interest Commercial Vessel Activity")

if high_interest_df.empty:
    st.success("No high-interest commercial vessel movements are currently flagged.")
else:
    hi_display = high_interest_df[
        ["name", "flag", "ship_type", "speed", "destination", "status", "last_update"]
    ].copy()

    hi_display = hi_display.rename(columns={
        "name": "Vessel",
        "flag": "Flag",
        "ship_type": "Type",
        "speed": "Speed (kn)",
        "destination": "Destination",
        "status": "Status",
        "last_update": "Last Update",
    })

    st.dataframe(hi_display, use_container_width=True, hide_index=True)

st.divider()

st.subheader("Tanker Traffic")

if tanker_df.empty:
    st.info("No tanker traffic is currently visible.")
else:
    tanker_display = tanker_df[
        ["name", "flag", "ship_type", "speed", "destination", "status", "last_update"]
    ].copy()

    tanker_display = tanker_display.rename(columns={
        "name": "Vessel",
        "flag": "Flag",
        "ship_type": "Type",
        "speed": "Speed (kn)",
        "destination": "Destination",
        "status": "Status",
        "last_update": "Last Update",
    })

    st.dataframe(tanker_display, use_container_width=True, hide_index=True)
