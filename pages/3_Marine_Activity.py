import html
import json
import math
import time

import folium
import pandas as pd
import streamlit as st
from folium.features import DivIcon
from folium.plugins import Fullscreen, MousePosition
from streamlit_folium import st_folium
from websocket import WebSocketTimeoutException, create_connection

st.set_page_config(page_title="Abnormal Marine Activity", layout="wide")

AISSTREAM_WS_URL = "wss://stream.aisstream.io/v0/stream"
REQUEST_TIMEOUT_SECONDS = 8
MAX_SNAPSHOT_MESSAGES = 35

MAP_THEMES = {
    "Light": {
        "tiles": "CartoDB positron",
        "attr": None,
    },
    "Radar": {
        "tiles": "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
        "attr": "&copy; OpenStreetMap contributors &copy; CARTO",
    },
    "Dark": {
        "tiles": "CartoDB dark_matter",
        "attr": None,
    },
}

VESSEL_COLORS = {
    "Abnormal": "#ff5f6d",
    "Energy / Tanker": "#ff9e3d",
    "Commercial": "#38bdf8",
}

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


def inject_styles():
    st.markdown(
        """
        <style>
            :root {
                --bg-0: #07111f;
                --bg-1: #0d1b2a;
                --stroke: rgba(130, 161, 191, 0.22);
                --text-main: #e8f1fb;
                --text-soft: #91a9c3;
            }

            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(56, 189, 248, 0.16), transparent 28%),
                    radial-gradient(circle at top right, rgba(88, 166, 255, 0.12), transparent 26%),
                    linear-gradient(180deg, var(--bg-0) 0%, var(--bg-1) 100%);
                color: var(--text-main);
                font-family: "Aptos", "Segoe UI", sans-serif;
            }

            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, rgba(9, 19, 32, 0.97), rgba(9, 19, 32, 0.92));
                border-right: 1px solid var(--stroke);
            }

            [data-testid="stSidebar"] * {
                color: var(--text-main);
            }

            .hero-card {
                border: 1px solid var(--stroke);
                background: linear-gradient(145deg, rgba(10, 21, 35, 0.92), rgba(15, 31, 49, 0.86));
                border-radius: 22px;
                padding: 1.35rem 1.5rem;
                box-shadow: 0 18px 40px rgba(4, 9, 18, 0.26);
                margin-bottom: 1rem;
            }

            .hero-kicker {
                letter-spacing: 0.16rem;
                font-size: 0.72rem;
                font-weight: 700;
                color: #84d7ff;
                margin-bottom: 0.4rem;
            }

            .hero-title {
                font-size: 2.2rem;
                line-height: 1.05;
                font-weight: 700;
                margin: 0;
                color: var(--text-main);
            }

            .hero-copy {
                margin: 0.55rem 0 0 0;
                max-width: 60rem;
                color: var(--text-soft);
                font-size: 0.98rem;
            }

            .metric-card {
                border: 1px solid var(--stroke);
                background: linear-gradient(180deg, rgba(12, 24, 39, 0.9), rgba(14, 32, 50, 0.76));
                border-radius: 20px;
                padding: 1rem 1rem 0.95rem 1rem;
                min-height: 120px;
                box-shadow: 0 12px 28px rgba(4, 9, 18, 0.24);
            }

            .metric-label {
                font-size: 0.8rem;
                text-transform: uppercase;
                letter-spacing: 0.08rem;
                color: var(--text-soft);
                margin-bottom: 0.45rem;
            }

            .metric-value {
                font-size: 2rem;
                font-weight: 700;
                line-height: 1;
                margin-bottom: 0.35rem;
                color: var(--text-main);
            }

            .metric-detail {
                font-size: 0.92rem;
                color: var(--text-soft);
            }

            .accent-bar {
                width: 54px;
                height: 4px;
                border-radius: 999px;
                margin-bottom: 0.8rem;
            }

            .panel-card {
                border: 1px solid var(--stroke);
                background: linear-gradient(180deg, rgba(10, 23, 37, 0.9), rgba(14, 31, 49, 0.82));
                border-radius: 20px;
                padding: 1rem 1rem 0.8rem 1rem;
                box-shadow: 0 12px 28px rgba(4, 9, 18, 0.22);
            }

            .panel-title {
                font-size: 1rem;
                font-weight: 700;
                margin-bottom: 0.2rem;
                color: var(--text-main);
            }

            .panel-copy {
                color: var(--text-soft);
                font-size: 0.92rem;
                margin-bottom: 0.8rem;
            }

            .stTabs [data-baseweb="tab-list"] {
                gap: 0.6rem;
            }

            .stTabs [data-baseweb="tab"] {
                border-radius: 999px;
                background: rgba(15, 31, 49, 0.7);
                border: 1px solid var(--stroke);
                color: var(--text-main);
                padding-left: 1rem;
                padding-right: 1rem;
            }

            .stDataFrame, div[data-testid="stTable"] {
                border-radius: 18px;
                overflow: hidden;
                border: 1px solid var(--stroke);
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def get_secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def safe_str(value):
    if value is None:
        return ""
    return str(value).strip()


def safe_heading(value):
    if pd.isna(value):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def format_knots(value):
    if pd.isna(value):
        return "Unknown"
    return f"{float(value):,.1f} kn"


def format_last_update(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "Unknown"
    try:
        parsed = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.notna(parsed):
            return parsed.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        pass
    text = safe_str(value)
    if not text:
        return "Unknown"
    return text.replace("T", " ").replace("Z", " UTC")


def destination_point(lat, lon, bearing_deg, distance_km):
    if pd.isna(lat) or pd.isna(lon) or pd.isna(bearing_deg):
        return None, None

    radius_km = 6371.0
    angular_distance = distance_km / radius_km
    bearing = math.radians(float(bearing_deg))
    lat1 = math.radians(float(lat))
    lon1 = math.radians(float(lon))

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )

    return math.degrees(lat2), math.degrees(lon2)


def is_tanker(row):
    ship_type = safe_str(row.get("ship_type")).lower()
    name = safe_str(row.get("name")).lower()
    return any(keyword in ship_type for keyword in TANKER_KEYWORDS) or any(
        keyword in name for keyword in TANKER_KEYWORDS
    )


def is_abnormal_status(row):
    status = safe_str(row.get("status")).lower()
    return any(keyword in status for keyword in ABNORMAL_STATUS_KEYWORDS)


def is_missing_destination(row):
    return safe_str(row.get("destination")) == ""


def is_high_speed(row):
    speed = row.get("speed")
    return pd.notna(speed) and float(speed) >= 25


def abnormal_reason(row):
    reasons = []
    if row.get("is_high_speed"):
        reasons.append("Unusually high speed")
    if row.get("is_abnormal_status"):
        reasons.append("Abnormal navigational status")
    if row.get("is_missing_destination"):
        reasons.append("Missing destination")
    if row.get("is_tanker"):
        reasons.append("Energy or tanker relevance")
    return ", ".join(reasons) if reasons else "No active signal flags"


def vessel_category(row):
    if row.get("is_abnormal"):
        return "Abnormal"
    if row.get("is_tanker"):
        return "Energy / Tanker"
    return "Commercial"


def build_popup_html(row):
    course_value = row.get("course")
    if pd.notna(course_value):
        course_text = f"{float(course_value):,.0f}"
    else:
        course_text = "Unknown"
    badge_color = row.get("marker_color", VESSEL_COLORS["Commercial"])
    category_text = safe_str(row.get("vessel_category") or "Commercial")

    return f"""
        <div style="min-width: 270px; font-family: Segoe UI, sans-serif;">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:8px;">
                <div>
                    <div style="font-size:15px; font-weight:700; color:#09111f;">{html.escape(safe_str(row.get("name") or "Unknown vessel"))}</div>
                    <div style="font-size:12px; color:#5a6d85;">{html.escape(safe_str(row.get("flag") or "Unknown flag"))}</div>
                </div>
                <div style="background:{badge_color}; color:#ffffff; font-size:11px; font-weight:700; border-radius:999px; padding:5px 8px;">
                    {html.escape(category_text)}
                </div>
            </div>
            <table style="width:100%; border-collapse:collapse; font-size:12px;">
                <tr><td style="padding:4px 0; color:#5a6d85;">MMSI</td><td style="padding:4px 0;">{html.escape(safe_str(row.get("mmsi")))}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">IMO</td><td style="padding:4px 0;">{html.escape(safe_str(row.get("imo") or "Unknown"))}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Type</td><td style="padding:4px 0;">{html.escape(safe_str(row.get("ship_type") or "Unknown"))}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Speed</td><td style="padding:4px 0;">{html.escape(format_knots(row.get("speed")))}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Course</td><td style="padding:4px 0;">{html.escape(course_text)}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Status</td><td style="padding:4px 0;">{html.escape(safe_str(row.get("status") or "Unknown"))}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Destination</td><td style="padding:4px 0;">{html.escape(safe_str(row.get("destination") or "Unknown"))}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Signal basis</td><td style="padding:4px 0;">{html.escape(safe_str(row.get("abnormal_reason")))}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Last update</td><td style="padding:4px 0;">{html.escape(format_last_update(row.get("last_update")))}</td></tr>
            </table>
        </div>
    """


def build_vessel_icon_html(row, show_label):
    color = row.get("marker_color", VESSEL_COLORS["Commercial"])
    angle = safe_heading(row.get("course"))
    glow = f"0 0 0 1px rgba(255,255,255,0.18), 0 10px 22px {color}55"

    label_html = ""
    if show_label:
        label = html.escape((safe_str(row.get("name")) or "Vessel")[:12])
        label_html = (
            f'<div style="margin-top:3px; padding:2px 7px; border-radius:999px; '
            f'background:rgba(7,17,31,0.88); color:#f4f9ff; font-size:10px; font-weight:700; '
            f'text-align:center; white-space:nowrap;">{label}</div>'
        )

    return f"""
        <div style="position: relative; width: 34px; height: 34px; transform: translate(-17px, -17px);">
            <div style="width: 34px; height: 34px; border-radius: 999px; background: rgba(8, 18, 30, 0.78);
                        box-shadow: {glow}; display: flex; align-items: center; justify-content: center;">
                <svg viewBox="0 0 24 24" width="20" height="20" style="transform: rotate({angle}deg);">
                    <path d="M12 3l3.6 6.3H8.4L12 3zm-5.7 8.2h11.4l2.3 3.8-3.5 1.8H7.5L4 15l2.3-3.8zm2 5.5h7.4l-1.3 3.3H9.6l-1.3-3.3z"
                          fill="{color}" stroke="#ffffff" stroke-width="0.8"></path>
                </svg>
            </div>
            {label_html}
        </div>
    """


def prepare_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    prepared = df.copy()
    for column in ["lat", "lon", "speed", "course"]:
        if column in prepared.columns:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    prepared["is_tanker"] = prepared.apply(is_tanker, axis=1)
    prepared["is_high_speed"] = prepared.apply(is_high_speed, axis=1)
    prepared["is_abnormal_status"] = prepared.apply(is_abnormal_status, axis=1)
    prepared["is_missing_destination"] = prepared.apply(is_missing_destination, axis=1)
    prepared["abnormal_reason"] = prepared.apply(abnormal_reason, axis=1)
    prepared["is_abnormal"] = (
        prepared["is_high_speed"] | prepared["is_abnormal_status"] | prepared["is_missing_destination"]
    )
    prepared["vessel_category"] = prepared.apply(vessel_category, axis=1)
    prepared["marker_color"] = prepared["vessel_category"].map(VESSEL_COLORS).fillna(VESSEL_COLORS["Commercial"])
    prepared["search_blob"] = (
        prepared["name"].fillna("")
        + " "
        + prepared["mmsi"].fillna("")
        + " "
        + prepared["flag"].fillna("")
        + " "
        + prepared["ship_type"].fillna("")
        + " "
        + prepared["destination"].fillna("")
        + " "
        + prepared["status"].fillna("")
    ).str.lower()
    return prepared.reset_index(drop=True)


def fetch_ais_region(region_name: str, max_messages: int = MAX_SNAPSHOT_MESSAGES, recv_timeout: int = REQUEST_TIMEOUT_SECONDS):
    aisstream_key = get_secret("aisstream_key")

    if not aisstream_key:
        demo_df = prepare_df(pd.DataFrame(DEMO_VESSELS))
        return demo_df, "demo", "No aisstream_key found in Streamlit secrets."

    ws = None
    try:
        ws = create_connection(AISSTREAM_WS_URL, timeout=10)
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
            message = payload.get("Message", {})
            meta = payload.get("MetaData", {})

            if "PositionReport" not in message:
                continue

            report = message["PositionReport"]
            mmsi = str(meta.get("MMSI", ""))
            lat = report.get("Latitude")
            lon = report.get("Longitude")

            dedupe_key = (mmsi, lat, lon)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            rows.append(
                {
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
                }
            )

        if not rows:
            raise RuntimeError("AISStream returned no vessel messages for this region during the snapshot window.")

        live_df = prepare_df(pd.DataFrame(rows))
        return live_df, "live", None

    except Exception as error:
        demo_df = prepare_df(pd.DataFrame(DEMO_VESSELS))
        return demo_df, "demo", str(error)

    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


def init_session_state():
    if "marine_df" not in st.session_state:
        st.session_state["marine_df"] = pd.DataFrame()
    if "marine_source" not in st.session_state:
        st.session_state["marine_source"] = "none"
    if "marine_error" not in st.session_state:
        st.session_state["marine_error"] = None
    if "marine_region" not in st.session_state:
        st.session_state["marine_region"] = None
    if "marine_loaded_at" not in st.session_state:
        st.session_state["marine_loaded_at"] = None


def render_metric_card(title, value, detail, accent):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="accent-bar" style="background:{accent};"></div>
            <div class="metric-label">{title}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-detail">{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def apply_filters(df: pd.DataFrame, search_query: str, visible_categories, abnormal_only: bool, tankers_only: bool):
    filtered = df.copy()
    if filtered.empty:
        return filtered

    if search_query:
        filtered = filtered[filtered["search_blob"].str.contains(search_query.lower(), na=False)]

    if abnormal_only:
        filtered = filtered[filtered["is_abnormal"]]

    if tankers_only:
        filtered = filtered[filtered["is_tanker"]]

    if visible_categories:
        filtered = filtered[filtered["vessel_category"].isin(visible_categories)]
    else:
        filtered = filtered.iloc[0:0]

    return filtered.reset_index(drop=True)


def create_vessel_map(df: pd.DataFrame, region_name: str, map_theme: str, show_vectors: bool, show_labels: bool):
    coords_df = df.dropna(subset=["lat", "lon"]).copy()
    if coords_df.empty:
        return None, False

    region_center = CONTINENT_CENTERS[region_name]
    vessel_map = folium.Map(
        location=[region_center["lat"], region_center["lon"]],
        zoom_start=region_center["zoom"],
        control_scale=True,
        prefer_canvas=True,
        tiles=None,
    )

    for theme_name, theme_config in MAP_THEMES.items():
        folium.TileLayer(
            tiles=theme_config["tiles"],
            attr=theme_config["attr"],
            name=theme_name,
            show=theme_name == map_theme,
        ).add_to(vessel_map)

    Fullscreen(position="topright").add_to(vessel_map)
    MousePosition(
        position="bottomright",
        separator=" | ",
        lng_first=False,
        num_digits=3,
        prefix="Lat / Lon",
    ).add_to(vessel_map)

    vector_layer = folium.FeatureGroup(name="Course vectors", show=show_vectors)
    marker_layer = folium.FeatureGroup(name="Vessels", show=True)
    effective_labels = show_labels and len(coords_df) <= 180

    for _, row in coords_df.iterrows():
        lat = row["lat"]
        lon = row["lon"]
        color = row["marker_color"]

        if show_vectors and pd.notna(row.get("course")) and pd.notna(row.get("speed")):
            distance_km = max(2.5, min(18.0, float(row.get("speed") or 0) * 0.45))
            end_lat, end_lon = destination_point(lat, lon, row.get("course"), distance_km)
            if end_lat is not None and end_lon is not None:
                folium.PolyLine(
                    locations=[[lat, lon], [end_lat, end_lon]],
                    color=color,
                    weight=2,
                    opacity=0.78,
                    dash_array="8 8",
                ).add_to(vector_layer)

        folium.Marker(
            location=[lat, lon],
            tooltip=f"{safe_str(row.get('name') or 'Unknown vessel')} | {safe_str(row.get('vessel_category'))}",
            popup=folium.Popup(build_popup_html(row), max_width=360),
            icon=DivIcon(html=build_vessel_icon_html(row, effective_labels)),
        ).add_to(marker_layer)

    vector_layer.add_to(vessel_map)
    marker_layer.add_to(vessel_map)
    folium.LayerControl(collapsed=True).add_to(vessel_map)
    return vessel_map, effective_labels


def make_abnormal_table(df: pd.DataFrame):
    if df.empty:
        return df
    table = df[
        ["name", "flag", "ship_type", "speed", "destination", "status", "abnormal_reason", "last_update"]
    ].copy()
    table["speed"] = table["speed"].apply(lambda value: None if pd.isna(value) else round(float(value), 1))
    table["last_update"] = table["last_update"].apply(format_last_update)
    table = table.rename(
        columns={
            "name": "Vessel",
            "flag": "Flag",
            "ship_type": "Type",
            "speed": "Speed (kn)",
            "destination": "Destination",
            "status": "Status",
            "abnormal_reason": "Signal Basis",
            "last_update": "Last Update",
        }
    )
    return table


def make_tanker_table(df: pd.DataFrame):
    if df.empty:
        return df
    table = df[
        ["name", "flag", "ship_type", "speed", "destination", "status", "last_update"]
    ].copy()
    table["speed"] = table["speed"].apply(lambda value: None if pd.isna(value) else round(float(value), 1))
    table["last_update"] = table["last_update"].apply(format_last_update)
    table = table.rename(
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
    return table


def make_feed_table(df: pd.DataFrame):
    if df.empty:
        return df
    table = df[
        ["name", "mmsi", "flag", "ship_type", "vessel_category", "speed", "destination", "status", "last_update"]
    ].copy()
    table["speed"] = table["speed"].apply(lambda value: None if pd.isna(value) else round(float(value), 1))
    table["last_update"] = table["last_update"].apply(format_last_update)
    table = table.rename(
        columns={
            "name": "Vessel",
            "mmsi": "MMSI",
            "flag": "Flag",
            "ship_type": "Type",
            "vessel_category": "Category",
            "speed": "Speed (kn)",
            "destination": "Destination",
            "status": "Status",
            "last_update": "Last Update",
        }
    )
    return table


inject_styles()
init_session_state()

st.markdown(
    """
    <div class="hero-card">
        <div class="hero-kicker">LIVE MARITIME SURVEILLANCE</div>
        <h1 class="hero-title">Abnormal Marine Activity</h1>
        <p class="hero-copy">
            A polished regional watchboard for commercial vessel traffic, abnormal movement signals,
            and tanker or energy shipping relevance using public AIS position snapshots.
        </p>
            
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### Region Controls")
    selected_region = st.selectbox("Continent", list(CONTINENT_BOXES.keys()), index=2)
    load_clicked = st.button("Load selected region", type="primary", use_container_width=True)

    if load_clicked:
        with st.spinner(f"Loading AIS snapshot for {selected_region}..."):
            df, source, error = fetch_ais_region(selected_region)
            st.session_state["marine_df"] = df
            st.session_state["marine_source"] = source
            st.session_state["marine_error"] = error
            st.session_state["marine_region"] = selected_region
            st.session_state["marine_loaded_at"] = pd.Timestamp.utcnow()
            st.rerun()

    st.markdown("### Traffic Filters")
    search_query = st.text_input(
        "Search vessels",
        placeholder="Vessel, MMSI, flag, type, destination, or status",
