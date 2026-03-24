import json
import math
import time
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from websocket import create_connection, WebSocketTimeoutException

st.set_page_config(page_title="Abnormal Marine Activity", layout="wide")

st.title("Abnormal Marine Activity")
st.caption("Open-source monitoring for commercial vessel traffic and abnormal shipping behaviour by region.")

AISSTREAM_WS_URL = "wss://stream.aisstream.io/v0/stream"

# =========================================================
# CONTINENT REGIONS
# =========================================================
CONTINENT_BOXES = {
    "North America": [[[7.0, -170.0], [72.0, -50.0]]],
    "South America": [[[-57.0, -92.0], [15.0, -30.0]]],
    "Europe": [[[34.0, -25.0], [72.0, 45.0]]],
    "Africa": [[[-35.0, -20.0], [38.0, 55.0]]],
    "Asia": [[[0.0, 25.0], [78.0, 180.0]]],
    "Oceania": [[[-50.0, 110.0], [5.0, 180.0]]],
}

CONTINENT_CENTERS = {
    "North America": {"lat": 38.0, "lon": -98.0, "zoom": 3},
    "South America": {"lat": -15.0, "lon": -60.0, "zoom": 3},
    "Europe": {"lat": 52.0, "lon": 12.0, "zoom": 4},
    "Africa": {"lat": 4.0, "lon": 20.0, "zoom": 3},
    "Asia": {"lat": 30.0, "lon": 95.0, "zoom": 3},
    "Oceania": {"lat": -24.0, "lon": 135.0, "zoom": 4},
}

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
        "last_update": "2026-03-24T12:00:00Z",
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
        "last_update": "2026-03-24T12:01:00Z",
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
        "last_update": "2026-03-24T12:02:00Z",
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
        "last_update": "2026-03-24T12:03:00Z",
    },
    {
        "name": "STRAIT RUNNER",
        "mmsi": "525004321",
        "imo": "9678901",
        "flag": "Indonesia",
        "ship_type": "LNG Tanker",
        "lat": -6.2,
        "lon": 106.8,
        "speed": 13.1,
        "course": 140,
        "destination": "JAPAN",
        "status": "Under way using engine",
        "last_update": "2026-03-24T12:04:00Z",
    },
    {
        "name": "TIME TRAVELER",
        "mmsi": "368163240",
        "imo": "",
        "flag": "",
        "ship_type": "",
        "lat": 40.7,
        "lon": -74.0,
        "speed": 25.6,
        "course": 193.0,
        "destination": "",
        "status": "0",
        "last_update": "2026-03-24T12:12:54Z",
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

def heading_endpoint(lat, lon, bearing_deg, distance_deg=0.5):
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

def abnormal_reason(row):
    reasons = []
    if row.get("is_high_speed"):
        reasons.append("unusually high speed")
    if row.get("is_abnormal_status"):
        reasons.append("abnormal navigational status")
    if row.get("is_missing_destination"):
        reasons.append("missing destination")
    if row.get("is_tanker"):
        reasons.append("energy/tanker relevance")
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

def prepare_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    for col in ["lat", "lon", "speed", "course"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["is_tanker"] = df.apply(is_tanker, axis=1)
    df["is_high_speed"] = df.apply(is_high_speed, axis=1)
    df["is_abnormal_status"] = df.apply(is_abnormal_status, axis=1)
    df["is_missing_destination"] = df.apply(is_missing_destination, axis=1)
    df["abnormal_reason"] = df.apply(abnormal_reason, axis=1)
    df["is_abnormal"] = df["abnormal_reason"] != "none"
    return df

# =========================================================
# AIS LOADER
# =========================================================
def fetch_ais_region(region_name: str, max_messages: int = 60, recv_timeout: int = 20):
    aisstream_key = get_secret("aisstream_key")

    if not aisstream_key:
        demo_df = prepare_df(pd.DataFrame(DEMO_VESSELS))
        return demo_df, "demo", "No aisstream_key found in Streamlit secrets."

    ws = None
    try:
        ws = create_connection(AISSTREAM_WS_URL, timeout=15)
        ws.settimeout(recv_timeout)

        subscribe_message = {
            "APIKey": aisstream_key,
            "BoundingBoxes": CONTINENT_BOXES[region_name],
            "FilterMessageTypes": ["PositionReport"],
        }

        ws.send(json.dumps(subscribe_message))

        rows = []
        seen = set()
        start_time = time.time()

        while len(rows) < max_messages and (time.time() - start_time) < recv_timeout:
            try:
                raw = ws.recv()
            except WebSocketTimeoutException:
                break

            payload = json.loads(raw)
            msg = payload.get("Message", {})
            meta = payload.get("MetaData", {})

            if "PositionReport" not in msg:
                continue

            report = msg["PositionReport"]
            mmsi = str(meta.get("MMSI", ""))
            lat = report.get("Latitude")
            lon = report.get("Longitude")

            dedupe_key = (mmsi, lat, lon)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            rows.append({
                "name": meta.get("ShipName") or f"MMSI {mmsi}",
                "mmsi": mmsi,
                "imo": safe_str(meta.get("IMO")),
                "flag": safe_str(meta.get("Flag")),
                "ship_type": safe_str(meta.get("ShipType")),
                "lat": lat,
                "lon": lon,
                "speed": report.get("Sog"),
                "course": report.get("Cog"),
                "destination": safe_str(meta.get("Destination")),
                "status": safe_str(report.get("NavigationalStatus")),
                "last_update": safe_str(meta.get("time_utc")),
            })

        if not rows:
            raise RuntimeError("AISStream returned no vessel messages in the snapshot window.")

        live_df = prepare_df(pd.DataFrame(rows))
        return live_df, "live", None

    except Exception as e:
        demo_df = prepare_df(pd.DataFrame(DEMO_VESSELS))
        return demo_df, "demo", str(e)

    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

# =========================================================
# SESSION STATE
# =========================================================
if "marine_df" not in st.session_state:
    st.session_state.marine_df = pd.DataFrame()

if "marine_source" not in st.session_state:
    st.session_state.marine_source = "none"

if "marine_error" not in st.session_state:
    st.session_state.marine_error = None

if "marine_region" not in st.session_state:
    st.session_state.marine_region = None

# =========================================================
# LOAD CONTROLS
# =========================================================
st.subheader("Load a Region")

c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1])

with c1:
    selected_region = st.selectbox("Continent", list(CONTINENT_BOXES.keys()), index=2)

with c2:
    map_show_all = st.checkbox("Show all vessels", value=True)

with c3:
    map_show_abnormal_only = st.checkbox("Map: abnormal only", value=False)

with c4:
    show_heading_lines = st.checkbox("Show direction lines", value=True)

load_clicked = st.button("Load selected region", type="primary")

if load_clicked:
    with st.spinner(f"Loading live AIS snapshot for {selected_region}..."):
        df, source, err = fetch_ais_region(selected_region)
        st.session_state.marine_df = df
        st.session_state.marine_source = source
        st.session_state.marine_error = err
        st.session_state.marine_region = selected_region

# =========================================================
# DATA IN MEMORY
# =========================================================
vessels_df = st.session_state.marine_df.copy()
data_source = st.session_state.marine_source
data_error = st.session_state.marine_error
loaded_region = st.session_state.marine_region

if vessels_df.empty:
    st.info("Choose a continent and click 'Load selected region' to fetch marine data.")
    st.stop()

map_df = vessels_df.copy()

if not map_show_all and map_show_abnormal_only:
    map_df = map_df[map_df["is_abnormal"] == True]
elif map_show_abnormal_only:
    map_df = map_df[map_df["is_abnormal"] == True]

abnormal_df = vessels_df[vessels_df["is_abnormal"] == True].copy()
tanker_df = vessels_df[vessels_df["is_tanker"] == True].copy()

# =========================================================
# STATUS
# =========================================================
st.subheader("System Status")

s1, s2, s3, s4, s5 = st.columns(5)

with s1:
    st.metric("Loaded continent", loaded_region if loaded_region else "None")

with s2:
    st.metric("Vessels loaded", len(vessels_df))

with s3:
    st.metric("Abnormal vessels", len(abnormal_df))

with s4:
    st.metric("Tankers", len(tanker_df))

with s5:
    if data_source == "live":
        st.success("Live Feed")
    elif data_source == "demo":
        st.warning("Demo Feed")
    else:
        st.info("Not loaded")

if data_error:
    st.warning(f"Live AIS snapshot unavailable, showing demo data instead: {data_error}")

st.divider()

# =========================================================
# WHAT COUNTS AS ABNORMAL
# =========================================================
st.subheader("What Qualifies as Abnormal Activity?")

st.markdown("""
This page flags **abnormal marine activity** using public commercial shipping signals. A vessel may be marked abnormal when one or more of these apply:

- **Unusually high speed** for a merchant vessel
- **Abnormal navigational status**, such as not under command, restricted manoeuverability, constrained by draught, or aground
- **Missing destination**
- **Tanker / energy shipping relevance**, especially when combined with one of the above

These are **signal-based flags**, not proof of wrongdoing.
""")

st.divider()

# =========================================================
# MAP
# =========================================================
left, right = st.columns([2.2, 1])

with left:
    st.subheader("Loaded Vessel Map")

    if map_df.empty:
        st.info("No vessels match the current map filters.")
    else:
        coords_df = map_df.dropna(subset=["lat", "lon"]).copy()

        if coords_df.empty:
            st.info("No coordinates available for the current map filters.")
        else:
            center = CONTINENT_CENTERS[loaded_region]
            vessel_map = folium.Map(
                location=[center["lat"], center["lon"]],
                zoom_start=center["zoom"],
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
                    end_lat, end_lon = heading_endpoint(lat, lon, row.get("course"), distance_deg=0.5)
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
    st.info("Click a continent to load only that area, which keeps it faster.")

st.divider()

# =========================================================
# ABNORMAL TABLE
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
# ANALYST SUMMARY
# =========================================================
st.subheader("Analyst Summary")

source_text = "live AIS snapshot" if data_source == "live" else "demo fallback"

st.markdown(f"""
/mount/src/console-7/pages/3_Marine_Activity.py:524                          

  st.markdown(f"""                                                              
# ---------- System Summary ----------

st.markdown("### System Summary")

source_text = "live AIS feed" if live_mode else "demo dataset"

st.markdown(f"""
- **{len(vessels_df)} vessels** loaded in the selected region.
- **{len(abnormal_df)} vessels** flagged for abnormal commercial behaviour.
- **{len(tanker_df)} vessels** classified as tankers.
- Data source currently: **{source_text}**
- Abnormal flags are based on publicly visible movement / status anomalies.
""")
              ▲                                                                 

