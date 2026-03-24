import html
import math
import time

import folium
import pandas as pd
import requests
import streamlit as st
from folium.features import DivIcon
from folium.plugins import Fullscreen, MeasureControl, MousePosition
from streamlit_folium import st_folium

st.set_page_config(page_title="Flight Activity", layout="wide")

OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"
REQUEST_HEADERS = {"User-Agent": "FlightActivity/1.0"}
TRAIL_RETENTION_SECONDS = 30 * 60
TRAIL_STORE_LIMIT = 14
DEFAULT_MAP_RENDER_LIMIT = 350
MAX_MAP_RENDER_LIMIT = 900
TRAIL_AUTO_LIMIT = 260
VECTOR_AUTO_LIMIT = 380

WATCHED_COUNTRIES = {
    "united states": "Government watchlist traffic",
    "russia": "Government watchlist traffic",
    "china": "Government watchlist traffic",
    "united kingdom": "Government watchlist traffic",
    "france": "Government watchlist traffic",
    "germany": "Government watchlist traffic",
    "italy": "Government watchlist traffic",
    "turkey": "Government watchlist traffic",
    "israel": "Government watchlist traffic",
    "india": "Government watchlist traffic",
}

MILITARY_CALLSIGN_RULES = [
    ("RCH", "US Air Mobility Command / Reach transport"),
    ("MC", "Military transport callsign family"),
    ("RRR", "UK Royal Air Force transport"),
    ("QID", "US military special mission"),
    ("ASY", "Special air mission / government support"),
    ("CNV", "Convoy or government support callsign"),
    ("GAF", "German Air Force"),
    ("IAM", "Italian Air Force"),
    ("HKY", "Military support / Hawkeye family"),
    ("NATO", "NATO aircraft"),
    ("DUKE", "US Air Force mission callsign"),
    ("SUSAF", "US Air Force support"),
    ("RAFAIR", "RAF support callsign"),
    ("CFC", "Canadian Forces"),
    ("LAGR", "Military operations callsign family"),
]

SQUAWK_MEANINGS = {
    "7500": {
        "label": "Hijack / unlawful interference",
        "reason": "Special squawk 7500 is used for unlawful interference or hijacking.",
        "severity": "CRITICAL",
        "color": "#ff5f6d",
    },
    "7600": {
        "label": "Radio failure",
        "reason": "Special squawk 7600 indicates a communications failure.",
        "severity": "HIGH",
        "color": "#ff9e3d",
    },
    "7700": {
        "label": "General emergency",
        "reason": "Special squawk 7700 signals a general emergency requiring priority handling.",
        "severity": "CRITICAL",
        "color": "#ff5f6d",
    },
    "7400": {
        "label": "UAS lost link",
        "reason": "Special squawk 7400 is commonly used for unmanned aircraft lost-link events.",
        "severity": "MEDIUM",
        "color": "#f2cc60",
    },
}

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

ALERT_COLORS = {
    "Emergency": "#ff5f6d",
    "Military": "#58a6ff",
    "Government": "#8a7dff",
}

ALERT_PRIORITY = {
    "Emergency": 0,
    "Military": 1,
    "Government": 2,
}


def inject_styles():
    st.markdown(
        """
        <style>
            :root {
                --bg-0: #07111f;
                --bg-1: #0d1b2a;
                --panel: rgba(13, 27, 42, 0.86);
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
                max-width: 58rem;
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


def safe_str(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_flight_key(value):
    return safe_str(value).lower()


def normalize_squawk(value):
    raw = safe_str(value)
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 4:
        return digits
    return raw


def get_state_value(state, index):
    if len(state) > index:
        return state[index]
    return None


def detect_military_callsign(callsign):
    normalized = safe_str(callsign).upper().replace(" ", "")
    for prefix, reason in MILITARY_CALLSIGN_RULES:
        if normalized.startswith(prefix):
            return True, f"Callsign prefix {prefix}: {reason}"
    return False, ""


def detect_state_watch(country):
    lowered = safe_str(country).lower()
    for keyword, reason in WATCHED_COUNTRIES.items():
        if keyword in lowered:
            return True, reason
    return False, ""


def decode_squawk(squawk):
    normalized = normalize_squawk(squawk)
    meta = SQUAWK_MEANINGS.get(normalized)
    if meta:
        return True, meta["label"], meta["reason"], meta["severity"], meta["color"]
    return False, "", "", "NORMAL", ALERT_COLORS["Government"]


def determine_alert_category(row):
    if row["is_emergency"]:
        return "Emergency"
    if row["is_military"]:
        return "Military"
    if row["is_state_watch"]:
        return "Government"
    return "Other"


def meters_to_feet(value):
    if pd.isna(value):
        return None
    return float(value) * 3.28084


def mps_to_knots(value):
    if pd.isna(value):
        return None
    return float(value) * 1.94384


def mps_to_fpm(value):
    if pd.isna(value):
        return None
    return float(value) * 196.8504


def format_altitude(value):
    if pd.isna(value):
        return "Unknown"
    return f"{meters_to_feet(value):,.0f} ft"


def format_speed(value):
    if pd.isna(value):
        return "Unknown"
    return f"{mps_to_knots(value):,.0f} kt"


def format_vertical_rate(value):
    if pd.isna(value):
        return "Unknown"
    return f"{mps_to_fpm(value):,.0f} fpm"


def format_timestamp(epoch_seconds):
    if pd.isna(epoch_seconds):
        return "Unknown"
    try:
        return time.strftime("%H:%M:%S UTC", time.gmtime(int(epoch_seconds)))
    except (TypeError, ValueError):
        return "Unknown"


def pick_timestamp(*values):
    for value in values:
        if pd.notna(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return int(time.time())


def safe_heading(value):
    if pd.isna(value):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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


def update_trail_history(df):
    history = st.session_state.setdefault("flight_history", {})
    now = int(time.time())

    coords_df = df.dropna(subset=["latitude", "longitude"]).copy()
    for row in coords_df.itertuples(index=False):
        icao24 = safe_str(row.icao24).lower()
        if not icao24:
            continue

        sample_time = pick_timestamp(row.last_contact, row.time_position, now)
        sample = {
            "ts": sample_time,
            "lat": round(float(row.latitude), 5),
            "lon": round(float(row.longitude), 5),
        }

        trail = history.get(icao24, [])
        trail = [point for point in trail if sample_time - point["ts"] <= TRAIL_RETENTION_SECONDS]

        if trail:
            last = trail[-1]
            moved = abs(last["lat"] - sample["lat"]) > 0.01 or abs(last["lon"] - sample["lon"]) > 0.01
            if moved:
                trail.append(sample)
            else:
                trail[-1] = sample
        else:
            trail.append(sample)

        history[icao24] = trail[-TRAIL_STORE_LIMIT:]

    fresh_history = {}
    for icao24, trail in history.items():
        recent = [point for point in trail if now - point["ts"] <= TRAIL_RETENTION_SECONDS]
        if recent:
            fresh_history[icao24] = recent

    st.session_state["flight_history"] = fresh_history


def get_trail_points(icao24, visible_points):
    history = st.session_state.get("flight_history", {})
    trail = history.get(safe_str(icao24).lower(), [])
    if not trail:
        return []
    limited = trail[-visible_points:]
    return [[point["lat"], point["lon"]] for point in limited]


def build_plane_icon_html(row, show_label):
    color = row.get("marker_color", ALERT_COLORS["Government"])
    angle = safe_heading(row.get("true_track"))
    glow = f"0 0 0 1px rgba(255,255,255,0.18), 0 10px 22px {color}55"

    label_html = ""
    if show_label:
        label = html.escape((row.get("callsign") or row.get("icao24") or "Unknown")[:10])
        label_html = (
            f'<div style="margin-top:3px; padding:2px 7px; border-radius:999px; '
            f'background:rgba(7,17,31,0.88); color:#f4f9ff; font-size:10px; font-weight:700; '
            f'text-align:center; white-space:nowrap;">{label}</div>'
        )

    return f"""
        <div style="position: relative; width: 34px; height: 34px; transform: translate(-17px, -17px);">
            <div style="width: 34px; height: 34px; border-radius: 999px; background: rgba(8, 18, 30, 0.78);
                        box-shadow: {glow}; display: flex; align-items: center; justify-content: center;">
                <svg viewBox="0 0 24 24" width="22" height="22" style="transform: rotate({angle}deg);">
                    <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5L21 16z"
                          fill="{color}" stroke="#ffffff" stroke-width="0.8"></path>
                </svg>
            </div>
            {label_html}
        </div>
    """


def build_popup_html(row):
    callsign = html.escape(row.get("callsign") or row.get("icao24") or "Unknown")
    country = html.escape(row.get("origin_country") or "Unknown")
    squawk = html.escape(row.get("squawk") or "None")
    emergency_reason = html.escape(row.get("emergency_reason") or "No special squawk detected")
    military_reason = html.escape(row.get("military_reason") or "No military callsign heuristic match")
    state_reason = html.escape(row.get("state_watch_reason") or "No government heuristic match")
    category = html.escape(row.get("alert_category") or "Government")
    color = row.get("marker_color", ALERT_COLORS["Government"])

    return f"""
        <div style="min-width: 260px; font-family: Segoe UI, sans-serif;">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:10px;">
                <div>
                    <div style="font-size:15px; font-weight:700; color:#09111f;">{callsign}</div>
                    <div style="font-size:12px; color:#5a6d85;">{country}</div>
                </div>
                <div style="background:{color}; color:#ffffff; font-size:11px; font-weight:700; border-radius:999px; padding:5px 9px;">
                    {category}
                </div>
            </div>
            <table style="width:100%; border-collapse:collapse; font-size:12px;">
                <tr><td style="padding:4px 0; color:#5a6d85;">Squawk</td><td style="padding:4px 0; font-weight:600;">{squawk}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Emergency</td><td style="padding:4px 0;">{emergency_reason}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Military</td><td style="padding:4px 0;">{military_reason}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Government</td><td style="padding:4px 0;">{state_reason}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Altitude</td><td style="padding:4px 0;">{format_altitude(row.get("baro_altitude"))}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Speed</td><td style="padding:4px 0;">{format_speed(row.get("velocity"))}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Vertical rate</td><td style="padding:4px 0;">{format_vertical_rate(row.get("vertical_rate"))}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Track</td><td style="padding:4px 0;">{row.get("true_track") if pd.notna(row.get("true_track")) else "Unknown"}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Last contact</td><td style="padding:4px 0;">{format_timestamp(row.get("last_contact"))}</td></tr>
            </table>
        </div>
    """


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


@st.cache_data(ttl=45, show_spinner=False)
def load_flights():
    response = requests.get(OPENSKY_STATES_URL, headers=REQUEST_HEADERS, timeout=20)
    response.raise_for_status()
    payload = response.json()
    states = payload.get("states") or []

    rows = []
    for state in states:
        rows.append(
            {
                "icao24": get_state_value(state, 0),
                "callsign": safe_str(get_state_value(state, 1)),
                "origin_country": safe_str(get_state_value(state, 2)),
                "time_position": get_state_value(state, 3),
                "last_contact": get_state_value(state, 4),
                "longitude": get_state_value(state, 5),
                "latitude": get_state_value(state, 6),
                "baro_altitude": get_state_value(state, 7),
                "on_ground": get_state_value(state, 8),
                "velocity": get_state_value(state, 9),
                "true_track": get_state_value(state, 10),
                "vertical_rate": get_state_value(state, 11),
                "geo_altitude": get_state_value(state, 13),
                "squawk": normalize_squawk(get_state_value(state, 14)),
                "spi": get_state_value(state, 15),
                "position_source": get_state_value(state, 16),
                "category": get_state_value(state, 17),
                "feed_time": payload.get("time"),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    military_matches = df["callsign"].apply(detect_military_callsign)
    df[["is_military", "military_reason"]] = pd.DataFrame(military_matches.tolist(), index=df.index)

    state_matches = df["origin_country"].apply(detect_state_watch)
    df[["is_state_watch", "state_watch_reason"]] = pd.DataFrame(state_matches.tolist(), index=df.index)

    emergency_matches = df["squawk"].apply(decode_squawk)
    df[
        [
            "is_emergency",
            "squawk_label",
            "emergency_reason",
            "emergency_severity",
            "emergency_color",
        ]
    ] = pd.DataFrame(emergency_matches.tolist(), index=df.index)

    df["alert_category"] = df.apply(determine_alert_category, axis=1)
    df["marker_color"] = df["alert_category"].map(ALERT_COLORS).fillna(ALERT_COLORS["Government"])
    df["altitude_ft"] = df["baro_altitude"].apply(meters_to_feet)
    df["speed_kt"] = df["velocity"].apply(mps_to_knots)
    df["vertical_rate_fpm"] = df["vertical_rate"].apply(mps_to_fpm)
    df["icao_key"] = df["icao24"].apply(normalize_flight_key)
    df["alert_sort"] = df["alert_category"].map(ALERT_PRIORITY).fillna(99)
    df = df.sort_values(["alert_sort", "last_contact"], ascending=[True, False]).reset_index(drop=True)

    return df


def filter_base_flights(df, airborne_only, selected_squawks, altitude_range, flight_search):
    filtered = df.copy()
    if filtered.empty:
        return filtered

    if airborne_only:
        filtered = filtered[filtered["on_ground"] == False]

    low_altitude, high_altitude = altitude_range
    filtered = filtered[
        filtered["altitude_ft"].fillna(0).between(float(low_altitude), float(high_altitude))
    ]

    if not selected_squawks:
        filtered = filtered[~filtered["is_emergency"]]
    elif len(selected_squawks) < len(SQUAWK_MEANINGS):
        filtered = filtered[(~filtered["is_emergency"]) | (filtered["squawk"].isin(selected_squawks))]

    if flight_search:
        search_text = flight_search.lower()
        filtered = filtered[
            filtered["callsign"].fillna("").str.lower().str.contains(search_text, na=False)
            | filtered["icao_key"].fillna("").str.contains(search_text, na=False)
            | filtered["origin_country"].fillna("").str.lower().str.contains(search_text, na=False)
            | filtered["squawk"].fillna("").str.lower().str.contains(search_text, na=False)
            | filtered["squawk_label"].fillna("").str.lower().str.contains(search_text, na=False)
        ]

    return filtered.reset_index(drop=True)


def filter_map_categories(df, visible_categories):
    if df.empty:
        return df
    if not visible_categories:
        return df.iloc[0:0].copy()
    return df[df["alert_category"].isin(visible_categories)].reset_index(drop=True)


def get_flight_by_key(df, icao_key):
    if df.empty or not icao_key:
        return pd.DataFrame()
    return df[df["icao_key"] == normalize_flight_key(icao_key)].head(1).copy()


def prepare_map_dataframe(df, flights_df, visible_categories, map_render_limit, selected_flight_key):
    map_df = filter_map_categories(df, visible_categories)
    total_matches = len(map_df)

    if map_render_limit and len(map_df) > map_render_limit:
        map_df = map_df.head(map_render_limit).copy()

    selected_row = get_flight_by_key(flights_df, selected_flight_key)
    if not selected_row.empty:
        selected_key = selected_row.iloc[0]["icao_key"]
        if map_df.empty or selected_key not in map_df["icao_key"].tolist():
            map_df = pd.concat([selected_row, map_df], ignore_index=True)
            map_df = map_df.drop_duplicates(subset=["icao_key"], keep="first").reset_index(drop=True)

    return map_df, total_matches, selected_row


def extract_selected_rows(widget_state):
    if not widget_state:
        return []

    selection = None
    if isinstance(widget_state, dict):
        selection = widget_state.get("selection")
    else:
        selection = getattr(widget_state, "selection", None)

    if not selection:
        return []

    if isinstance(selection, dict):
        return selection.get("rows", []) or []

    return getattr(selection, "rows", []) or []


def sync_selected_flight_from_rows(selection_rows, source_df):
    if source_df.empty:
        return False

    if not selection_rows:
        return False

    selected_index = selection_rows[0]
    if selected_index >= len(source_df):
        return False

    selected_key = normalize_flight_key(source_df.iloc[selected_index]["icao24"])
    if not selected_key:
        return False

    if st.session_state.get("focused_flight_key") != selected_key:
        st.session_state["focused_flight_key"] = selected_key
        return True

    return False


def create_map(
    df,
    map_theme,
    show_trails,
    show_heading_vectors,
    show_labels,
    trail_points,
    selected_flight_key,
):
    coords_df = df.dropna(subset=["latitude", "longitude"]).copy()
    if coords_df.empty:
        return None, False

    selected_coords = coords_df[coords_df["icao_key"] == normalize_flight_key(selected_flight_key)].head(1)
    if not selected_coords.empty:
        center_lat = float(selected_coords.iloc[0]["latitude"])
        center_lon = float(selected_coords.iloc[0]["longitude"])
        zoom_start = 6
    else:
        center_lat = coords_df["latitude"].mean()
        center_lon = coords_df["longitude"].mean()
        zoom_start = 4

    flight_map = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_start,
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
        ).add_to(flight_map)

    Fullscreen(position="topright").add_to(flight_map)
    MeasureControl(position="topleft", primary_length_unit="kilometers").add_to(flight_map)
    MousePosition(
        position="bottomright",
        separator=" | ",
        lng_first=False,
        num_digits=3,
        prefix="Lat / Lon",
    ).add_to(flight_map)

    effective_trails = show_trails and len(coords_df) <= TRAIL_AUTO_LIMIT
    effective_vectors = show_heading_vectors and len(coords_df) <= VECTOR_AUTO_LIMIT

    trail_layer = folium.FeatureGroup(name="Session trails", show=effective_trails)
    vector_layer = folium.FeatureGroup(name="Heading vectors", show=effective_vectors)
    marker_layer = folium.FeatureGroup(name="Aircraft", show=True)

    label_budget = 220
    effective_labels = show_labels and len(coords_df) <= label_budget

    for _, row in coords_df.iterrows():
        color = row["marker_color"]
        lat = row["latitude"]
        lon = row["longitude"]

        is_selected = row["icao_key"] == normalize_flight_key(selected_flight_key)

        if effective_trails:
            trail = get_trail_points(row["icao24"], trail_points)
            if len(trail) > 1:
                folium.PolyLine(
                    locations=trail,
                    color="#ffffff",
                    weight=5,
                    opacity=0.08,
                ).add_to(trail_layer)
                folium.PolyLine(
                    locations=trail,
                    color=color,
                    weight=2.8,
                    opacity=0.78,
                ).add_to(trail_layer)

        if effective_vectors and row["on_ground"] == False:
            velocity = row.get("velocity")
            distance_km = 40.0
            if pd.notna(velocity):
                distance_km = max(18.0, min(140.0, float(velocity) * 0.18))

            end_lat, end_lon = destination_point(lat, lon, row.get("true_track"), distance_km)
            if end_lat is not None and end_lon is not None:
                folium.PolyLine(
                    locations=[[lat, lon], [end_lat, end_lon]],
                    color=color,
                    weight=2,
                    opacity=0.75,
                    dash_array="8 8",
                ).add_to(vector_layer)

        tooltip = f"{row.get('callsign') or row.get('icao24') or 'Unknown'} | {row['alert_category']}"
        folium.Marker(
            location=[lat, lon],
            tooltip=tooltip,
            popup=folium.Popup(build_popup_html(row), max_width=360),
            icon=DivIcon(html=build_plane_icon_html(row, effective_labels or is_selected)),
        ).add_to(marker_layer)

        if is_selected:
            folium.CircleMarker(
                location=[lat, lon],
                radius=18,
                color="#ffffff",
                weight=2,
                fill=False,
                opacity=0.95,
            ).add_to(marker_layer)
            folium.CircleMarker(
                location=[lat, lon],
                radius=24,
                color=color,
                weight=2,
                fill=False,
                opacity=0.45,
            ).add_to(marker_layer)

    trail_layer.add_to(flight_map)
    vector_layer.add_to(flight_map)
    marker_layer.add_to(flight_map)
    folium.LayerControl(collapsed=True).add_to(flight_map)

    return flight_map, effective_labels


def make_emergency_table(df):
    if df.empty:
        return df

    table = df[
        [
            "callsign",
            "origin_country",
            "squawk",
            "squawk_label",
            "emergency_reason",
            "speed_kt",
            "altitude_ft",
            "on_ground",
            "last_contact",
        ]
    ].copy()
    table = table.rename(
        columns={
            "callsign": "Callsign",
            "origin_country": "Origin Country",
            "squawk": "Special Squawk",
            "squawk_label": "Alert",
            "emergency_reason": "Why It Matters",
            "speed_kt": "Speed (kt)",
            "altitude_ft": "Altitude (ft)",
            "on_ground": "On Ground",
            "last_contact": "Last Contact",
        }
    )
    table["Last Contact"] = table["Last Contact"].apply(format_timestamp)
    table["Speed (kt)"] = table["Speed (kt)"].apply(
        lambda value: None if pd.isna(value) else round(float(value))
    )
    table["Altitude (ft)"] = table["Altitude (ft)"].apply(
        lambda value: None if pd.isna(value) else round(float(value))
    )
    return table


def make_military_table(df):
    if df.empty:
        return df

    table = df[
        [
            "callsign",
            "origin_country",
            "military_reason",
            "squawk",
            "squawk_label",
            "speed_kt",
            "altitude_ft",
            "last_contact",
        ]
    ].copy()
    table = table.rename(
        columns={
            "callsign": "Callsign",
            "origin_country": "Origin Country",
            "military_reason": "Military Heuristic Reason",
            "squawk": "Squawk",
            "squawk_label": "Emergency Label",
            "speed_kt": "Speed (kt)",
            "altitude_ft": "Altitude (ft)",
            "last_contact": "Last Contact",
        }
    )
    table["Last Contact"] = table["Last Contact"].apply(format_timestamp)
    table["Speed (kt)"] = table["Speed (kt)"].apply(
        lambda value: None if pd.isna(value) else round(float(value))
    )
    table["Altitude (ft)"] = table["Altitude (ft)"].apply(
        lambda value: None if pd.isna(value) else round(float(value))
    )
    return table


def make_feed_table(df):
    if df.empty:
        return df

    table = df[
        [
            "callsign",
            "origin_country",
            "alert_category",
            "squawk",
            "squawk_label",
            "military_reason",
            "state_watch_reason",
            "speed_kt",
            "altitude_ft",
            "true_track",
            "last_contact",
        ]
    ].copy()
    table = table.rename(
        columns={
            "callsign": "Callsign",
            "origin_country": "Origin Country",
            "alert_category": "Category",
            "squawk": "Squawk",
            "squawk_label": "Emergency Label",
            "military_reason": "Military Reason",
            "state_watch_reason": "Government Reason",
            "speed_kt": "Speed (kt)",
            "altitude_ft": "Altitude (ft)",
            "true_track": "Track",
            "last_contact": "Last Contact",
        }
    )
    table["Last Contact"] = table["Last Contact"].apply(format_timestamp)
    table["Speed (kt)"] = table["Speed (kt)"].apply(
        lambda value: None if pd.isna(value) else round(float(value))
    )
    table["Altitude (ft)"] = table["Altitude (ft)"].apply(
        lambda value: None if pd.isna(value) else round(float(value))
    )
    table["Track"] = table["Track"].apply(
        lambda value: None if pd.isna(value) else round(float(value))
    )
    return table


def render_selectable_flight_table(source_df, display_df, widget_key):
    if source_df.empty or display_df.empty:
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        return

    normalized_source = source_df.reset_index(drop=True).copy()
    normalized_display = display_df.reset_index(drop=True).copy()

    event = st.dataframe(
        normalized_display,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=widget_key,
    )

    if sync_selected_flight_from_rows(extract_selected_rows(event), normalized_source):
        st.rerun()


inject_styles()

st.markdown(
    """
    <div class="hero-card">
        <div class="hero-kicker">LIVE AIRSPACE SURVEILLANCE</div>
        <h1 class="hero-title">Flight Activity</h1>
        <p class="hero-copy">
            
    </div>
    """,
    unsafe_allow_html=True,
)

data_error = None
try:
    flights_df = load_flights()
except Exception as error:
    flights_df = pd.DataFrame()
    data_error = str(error)

if not flights_df.empty:
    update_trail_history(flights_df)

with st.sidebar:
    st.markdown("### Radar Controls")
    refresh_clicked = st.button("Refresh live feed", use_container_width=True)
    if refresh_clicked:
        load_flights.clear()
        st.rerun()

    flight_search = st.text_input(
        "Search flights",
        placeholder="Callsign, ICAO, country, or squawk",
    )

    airborne_only = st.toggle("Airborne only", value=True)

    selected_squawks = st.multiselect(
        "Emergency filters",
        options=list(SQUAWK_MEANINGS.keys()),
        default=list(SQUAWK_MEANINGS.keys()),
        format_func=lambda code: f"{code} - {SQUAWK_MEANINGS[code]['label']}",
    )

    if not flights_df.empty and flights_df["altitude_ft"].notna().any():
        max_altitude = int(
            max(
                20000,
                min(60000, math.ceil(flights_df["altitude_ft"].fillna(0).max() / 5000) * 5000),
            )
        )
    else:
        max_altitude = 60000

    altitude_range = st.slider(
        "Altitude band (ft)",
        min_value=0,
        max_value=max_altitude,
        value=(0, max_altitude),
        step=1000,
    )

    st.markdown("### Map Filters")
    visible_categories = st.multiselect(
        "Show on map",
        options=["Emergency", "Military", "Government"],
        default=["Emergency", "Military", "Government"],
    )
    map_render_limit = st.slider(
        "Map flight limit",
        min_value=100,
        max_value=MAX_MAP_RENDER_LIMIT,
        value=DEFAULT_MAP_RENDER_LIMIT,
        step=50,
    )

    st.markdown("### Map Layers")
    map_theme = st.selectbox("Map theme", options=list(MAP_THEMES.keys()), index=1)
    show_trails = st.toggle("Show session trails", value=True)
    trail_points = st.slider("Trail points", min_value=2, max_value=10, value=6)
    show_heading_vectors = st.toggle("Show heading vectors", value=True)
    show_labels = st.toggle("Show callsign labels", value=False)

    if st.session_state.get("focused_flight_key"):
        if st.button("Clear selected flight", use_container_width=True):
            st.session_state["focused_flight_key"] = ""
            st.rerun()

if data_error:
    priority_only_df = pd.DataFrame()
    filtered_df = pd.DataFrame()
    feed_df = pd.DataFrame()
    map_df = pd.DataFrame()
    selected_flight_row = pd.DataFrame()
    total_map_matches = 0
else:
    priority_only_df = flights_df[
        flights_df["is_emergency"] | flights_df["is_military"] | flights_df["is_state_watch"]
    ].copy()
    filtered_df = filter_base_flights(
        priority_only_df,
        airborne_only=airborne_only,
        selected_squawks=selected_squawks,
        altitude_range=altitude_range,
        flight_search=flight_search.strip().lower(),
    )
    feed_df = filter_map_categories(filtered_df, visible_categories)
    map_df, total_map_matches, selected_flight_row = prepare_map_dataframe(
        filtered_df,
        priority_only_df,
        visible_categories=visible_categories,
        map_render_limit=map_render_limit,
        selected_flight_key=st.session_state.get("focused_flight_key", ""),
    )

emergency_df = filtered_df[filtered_df["is_emergency"]].copy() if not filtered_df.empty else pd.DataFrame()
military_df = filtered_df[filtered_df["is_military"]].copy() if not filtered_df.empty else pd.DataFrame()
state_watch_df = filtered_df[filtered_df["is_state_watch"]].copy() if not filtered_df.empty else pd.DataFrame()

metric_columns = st.columns(4)
visible_map_detail = f"{total_map_matches:,} match the current map filters"
if len(map_df) > total_map_matches:
    visible_map_detail += " plus 1 selected flight"

with metric_columns[0]:
    render_metric_card(
        "Tracked flights",
        f"{len(priority_only_df):,}",
        "Emergency and military or government traffic in the live feed",
        "#38bdf8",
    )
with metric_columns[1]:
    render_metric_card(
        "Visible on map",
        f"{len(map_df):,}",
        visible_map_detail,
        "#7dd3fc",
    )
with metric_columns[2]:
    render_metric_card("Emergency squawks", f"{len(emergency_df):,}", "Decoded special squawks with reasons", "#ff5f6d")
with metric_columns[3]:
    if data_error:
        render_metric_card("Feed status", "Offline", "Upstream flight feed error detected", "#ff5f6d")
    else:
        last_contact = flights_df["last_contact"].dropna().max() if not flights_df.empty else None
        render_metric_card("Feed status", "Online", f"Latest contact: {format_timestamp(last_contact)}", "#39d98a")

st.markdown("")

map_col, side_col = st.columns([3.1, 1.15], gap="large")

with map_col:
    st.markdown(
        """
        <div class="panel-card">
            <div class="panel-title">Live Radar Map</div>
            <div class="panel-copy">
                Emergency flights are red, military heuristics are blue, and government heuristics are purple.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if data_error:
        st.error(f"Flight data unavailable: {data_error}")
    elif map_df.empty:
        st.info("No flights match the active filters.")
    else:
        flight_map, labels_used = create_map(
            map_df,
            map_theme=map_theme,
            show_trails=show_trails,
            show_heading_vectors=show_heading_vectors,
            show_labels=show_labels,
            trail_points=trail_points,
            selected_flight_key=st.session_state.get("focused_flight_key", ""),
        )

        if flight_map is None:
            st.info("No coordinate data is available for the filtered flights.")
        else:
            st_folium(flight_map, use_container_width=True, height=720)
            if total_map_matches > len(map_df):
                st.caption(
                    f"Showing {len(map_df):,} of {total_map_matches:,} matching flights on the map for faster loading."
                )
            if show_labels and not labels_used:
                st.caption("Callsign labels were automatically reduced because the map has too many aircraft for clear labels.")

with side_col:
    st.markdown("#### Selected flight")
    if selected_flight_row.empty:
        st.info("Click a flight in one of the tables below to focus it on the map.")
    else:
        selected_record = selected_flight_row.iloc[0]
        st.markdown(
            f"""
            <div class="panel-card">
                <div class="panel-title">{html.escape(safe_str(selected_record.get("callsign") or selected_record.get("icao24") or "Unknown"))}</div>
                <div class="panel-copy">
                    {html.escape(safe_str(selected_record.get("origin_country") or "Unknown"))}<br>
                    {html.escape(safe_str(selected_record.get("alert_category") or "Government"))}<br>
                    Squawk: {html.escape(safe_str(selected_record.get("squawk") or "None"))}<br>
                    Altitude: {format_altitude(selected_record.get("baro_altitude"))}<br>
                    Speed: {format_speed(selected_record.get("velocity"))}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if {"is_emergency", "is_military", "is_state_watch"}.issubset(feed_df.columns):
        active_alerts = feed_df[
            feed_df["is_emergency"] | feed_df["is_military"] | feed_df["is_state_watch"]
        ].copy()
    else:
        active_alerts = pd.DataFrame()

    st.markdown("#### Active alerts")
    if active_alerts.empty:
        st.info("No priority traffic is visible under the current filters.")
    else:
        alert_table = active_alerts[
            ["callsign", "alert_category", "squawk", "squawk_label", "military_reason"]
        ].head(10)
        alert_table = alert_table.rename(
            columns={
                "callsign": "Callsign",
                "alert_category": "Category",
                "squawk": "Squawk",
                "squawk_label": "Emergency",
                "military_reason": "Military reason",
            }
        )
        st.dataframe(alert_table, use_container_width=True, hide_index=True)

    st.markdown("#### Special squawk guide")
    squawk_guide = pd.DataFrame(
        [
            {
                "Squawk": code,
                "Alert": meta["label"],
                "Meaning": meta["reason"],
                "Severity": meta["severity"],
            }
            for code, meta in SQUAWK_MEANINGS.items()
        ]
    )
    st.dataframe(squawk_guide, use_container_width=True, hide_index=True)

    st.caption("Military and government markers are public heuristics only and should not be treated as authoritative identification.")

tab_emergency, tab_military, tab_feed = st.tabs(["Emergency Watch", "Military Watch", "Live Feed"])

with tab_emergency:
    st.markdown("### Emergency Flights")
    st.caption("These are aircraft currently broadcasting one of the known special squawk codes in the live feed.")
    if data_error:
        st.error(f"Flight feed unavailable: {data_error}")
    elif emergency_df.empty:
        st.success("No emergency squawk flights are currently visible in the feed.")
    else:
        render_selectable_flight_table(
            emergency_df,
            make_emergency_table(emergency_df),
            "emergency_table",
        )

with tab_military:
    st.markdown("### Military Filter")
    st.caption("This view uses callsign-prefix heuristics for likely military or government-support traffic.")
    if data_error:
        st.error(f"Flight feed unavailable: {data_error}")
    elif military_df.empty:
        st.info("No flights matched the current military callsign heuristic rules.")
    else:
        render_selectable_flight_table(
            military_df,
            make_military_table(military_df),
            "military_table",
        )

with tab_feed:
    st.markdown("### Filtered Feed")
    st.caption("This table follows the sidebar search and map filters so you can inspect exactly what the map is showing.")
    if data_error:
        st.error(f"Flight feed unavailable: {data_error}")
    elif feed_df.empty:
        st.info("No flights match the current filters.")
    else:
        render_selectable_flight_table(
            feed_df,
            make_feed_table(feed_df),
            "feed_table",
        )

st.markdown("---")
st.caption(
    f"Tracking {len(priority_only_df):,} flights, with {len(emergency_df):,} emergency squawks, "
    f"{len(military_df):,} military heuristic matches, and {len(state_watch_df):,} government heuristic matches."
)
