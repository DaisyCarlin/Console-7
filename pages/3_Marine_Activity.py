import json
import math
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from websocket import create_connection

st.set_page_config(page_title="Abnormal Marine Activity", layout="wide")

st.title("Abnormal Marine Activity")
st.caption("Open-source monitoring for high-interest commercial vessel behavior, tanker traffic, and chokepoint activity.")

# =========================================================
# CONFIG
# =========================================================
AISSTREAM_WS_URL = "wss://stream.aisstream.io/v0/stream"

TANKER_KEYWORDS = [
    "tanker",
    "oil",
    "lng",
    "gas",
    "chemical",
]

ABNORMAL_STATUS_KEYWORDS = [
    "not under command",
    "restricted manoeuverability",
    "restricted maneuverability",
    "constrained by her draught",
    "aground",
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
    {
        "name": "STRAIT RUNNER",
        "mmsi": "525004321",
        "imo": "9678901",
        "flag": "Indonesia",
        "ship_type": "LNG Tanker",
        "lat": 2.5,
        "lon": 101.6,
        "speed": 13.1,
        "course": 140,
        "destination": "JAPAN",
        "status": "Under way using engine",
        "last_update": "2026-03-23T16:07:00Z",
    },
    {
        "name": "CANAL TRANSIT",
        "mmsi": "351009876",
        "imo": "9789012",
        "flag": "Panama",
        "ship_type": "Bulk Carrier",
        "lat": 9.1,
        "lon": -79.7,
        "speed": 7.2,
        "course": 270,
        "destination": "",
        "status": "Restricted manoeuverability",
        "last_update": "2026-03-23T16:08:00Z",
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

def is_tanker(row):
    ship_type = safe_str(row.get("ship_type")).lower()
    name = safe_str(row.get("name")).lower()
    return any(k in ship_type for k in TANKER_KEYWORDS) or any(k in name for k in TANKER_KEYWORDS)

def is_abnormal_status(row):
    status = safe_str(row.get("status")).lower()
    return any(k in status for k in ABNORMAL_STATUS_KEYWORDS)

def is_missing_destination(row):
    return safe_str(row.get("destination")) == ""

def is_high_speed(row):
    speed = row.get("speed")
    return pd.notna(speed) and float(speed) >= 25

def is_in_chokepoint(row):
    lat = row.get("lat")
    lon = row.get("lon")
    for name, bbox in CHOKEPOINTS.items():
        if name == "Global":
            continue
        if in_bbox(lat, lon, bbox):
            return True
    return False

def abnormal_reason(row):
    reasons = []

    if row.get("is_tanker"):
        reasons.append("tanker / energy shipping")
    if row.get("is_high_speed"):
        reasons.append("unusually high speed")
    if row.get("is_abnormal_status"):
        reasons.append("abnormal navigational status")
    if row.get("is_missing_destination"):
        reasons.append("missing destination")
    if row.get("is_in_chokepoint"):
        reasons.append("operating in major chokepoint")

    return ", ".join(reasons) if reasons else "none"

def marker_color(row):
    if row.get("is_abnormal") is True:
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
    <b>Abnormal Reason:</b> {safe_str(row.get("abnormal_reason"))}<br>
    <b>Last Update:</b> {safe_str(row.get("last_update"))}
    """

# =========================================================
# LOADER
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
        max_messages = 80

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

        df["is_tanker"] = df.apply(is_tanker, axis=1)
        df["is_high_speed"] = df.apply(is_high_speed, axis=1)
        df["is_abnormal_status"] = df.apply(is_abnormal_status, axis=1)
        df["is_missing_destination"] = df.apply(is_missing_destination, axis=1)
        df["is_in_chokepoint"] = df.apply(is_in_chokepoint, axis=1)
        df["abnormal_reason"] = df.apply(abnormal_reason, axis=1)
        df["is_abnormal"] = df["abnormal_reason"] != "none"

    return df, source

# =========================================================
# LOAD
# =========================================================
data_error = None

try:
    vessels_df, data_source = load_vessels()
    feed_ok = True
except Exception as e:
    vessels_df = pd.DataFrame(DEMO_VESSELS)
    data_source = "demo"
    feed_ok = False
    data_error = str(e)

    for col in ["lat", "lon", "speed", "course"]:
        vessels_df[col] = pd.to_numeric(vessels_df[col], errors="coerce")

    vessels_df["is_tanker"] = vessels_df.apply(is_tanker, axis=1)
    vessels_df["is_high_speed"] = vessels_df.apply(is_high_speed, axis=1)
    vessels_df["is_abnormal_status"] = vessels_df.apply(is_abnormal_status, axis=1)
    vessels_df["is_missing_destination"] = vessels_df.apply(is_missing_destination, axis=1)
    vessels_df["is_in_chokepoint"] = vessels_df.apply(is_in_chokepoint, axis=1)
    vessels_df["abnormal_reason"] = vessels_df.apply(abnormal_reason, axis=1)
    vessels_df["is_abnormal"] = vessels_df["abnormal_reason"] != "none"

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
    map_show_abnormal_only = st.checkbox("Map: abnormal only", value=True)

with f4:
    show_heading_lines = st.checkbox("Show direction lines", value=True)

map_df = vessels_df.copy()

if not map_df.empty:
    bbox = CHOKEPOINTS[selected_region]
    map_df = map_df[map_df.apply(lambda r: in_bbox(r.get("lat"), r.get("lon"), bbox), axis=1)]

    if map_show_tankers_only:
        map_df = map_df[map_df["is_tanker"] == True]

    if map_show_abnormal_only:
        map_df = map_df[map_df["is_abnormal"] == True]

# =========================================================
# DERIVED TABLES
# =========================================================
tanker_df = vessels_df[vessels_df["is_tanker"] == True].copy() if not vessels_df.empty else pd.DataFrame()
abnormal_df = vessels_df[vessels_df["is_abnormal"] == True].copy() if not vessels_df.empty else pd.DataFrame()

bbox = CHOKEPOINTS[selected_region]
regional_df = vessels_df[vessels_df.apply(lambda r: in_bbox(r.get("lat"), r.get("lon"), bbox), axis=1)].copy() if not vessels_df.empty else pd.DataFrame()

# =========================================================
# STATUS
# =========================================================
st.subheader("System Status")

c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.metric("Vessels loaded", len(vessels_df))
with c2:
    st.metric("Tankers", len(tanker_df))
with c3:
    st.metric("Abnormal vessels", len(abnormal_df))
with c4:
    st.metric(f"{selected_region} vessels", len(regional_df))
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
# WHAT QUALIFIES AS ABNORMAL
# =========================================================
st.subheader("What Qualifies as Abnormal Activity?")

st.markdown("""
This page flags **abnormal marine activity** using public commercial shipping signals. A vessel may be marked abnormal when one or more of these apply:

- **Unusually high speed** for a merchant vessel
- **Abnormal navigational status**, such as not under command, restricted manoeuverability, constrained by draught, or aground
- **Missing destination**
- **Operation inside a major chokepoint**
- **Tanker / energy shipping relevance**, especially when combined with one of the above

These are **signal-based flags**, not proof of wrongdoing.
""")

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
    st.markdown("""
- 🔴 **Red** = abnormal vessel
- 🟠 **Orange** = tanker
- 🟢 **Green** = other visible vessel
""")
    st.caption("Direction lines show approximate current heading only.")

st.divider()

# =========================================================
# REGIONAL TRAFFIC
# =========================================================
st.subheader(f"{selected_region} Traffic")

if regional_df.empty:
    st.info(f"No vessels are currently visible in {selected_region}.")
else:
    regional_display = regional_df[
        ["name", "flag", "ship_type", "speed", "destination", "status", "abnormal_reason", "last_update"]
    ].copy()

    regional_display = regional_display.rename(columns={
        "name": "Vessel",
        "flag": "Flag",
        "ship_type": "Type",
        "speed": "Speed (kn)",
        "destination": "Destination",
        "status": "Status",
        "abnormal_reason": "Abnormal Reason",
        "last_update": "Last Update",
    })

    st.dataframe(regional_display, use_container_width=True, hide_index=True)

st.divider()

# =========================================================
# ABNORMAL SECTION
# =========================================================
st.subheader("Abnormal Commercial Vessel Activity")

if abnormal_df.empty:
    st.success("No abnormal commercial vessel movements are currently flagged.")
else:
    abnormal_display = abnormal_df[
        ["name", "flag", "ship_type", "speed", "destination", "status", "abnormal_reason", "last_update"]
    ].copy()

    abnormal_display = abnormal_display.rename(columns={
        "name": "Vessel",
        "flag": "Flag",
        "ship_type": "Type",
        "speed": "Speed (kn)",
        "destination": "Destination",
        "status": "Status",
        "abnormal_reason": "Abnormal Reason",
        "last_update": "Last Update",
    })

    st.dataframe(abnormal_display, use_container_width=True, hide_index=True)

st.divider()

# =========================================================
# TANKER SECTION
# =========================================================
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

st.divider()

# =========================================================
# ANALYST SUMMARY
# =========================================================
st.subheader("Analyst Summary")

source_text = "live feed" if feed_ok and data_source == "live" else "demo feed"

st.markdown(f"""
- **{len(vessels_df)}** vessel records were loaded from the **{source_text}**.
- **{len(tanker_df)}** vessels are currently categorized as tankers.
- **{len(abnormal_df)}** vessels are currently flagged for abnormal commercial activity.
- **{len(regional_df)}** vessels are currently visible in **{selected_region}**.
- Abnormal flags are based on **public movement and status signals**, not proof of wrongdoing.
""")
