import html
import math
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import folium
import pandas as pd
import requests
import streamlit as st
from folium.features import DivIcon
from folium.plugins import Fullscreen, MousePosition
from sgp4.api import Satrec, jday
from streamlit_folium import st_folium

st.set_page_config(page_title="Satellite Radar", layout="wide")

CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=tle"
REQUEST_TIMEOUT_SECONDS = 25
CACHE_TTL_SECONDS = 600

MAP_THEMES = {
    "Light": {"tiles": "CartoDB positron", "attr": None},
    "Radar": {
        "tiles": "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
        "attr": "&copy; OpenStreetMap contributors &copy; CARTO",
    },
    "Dark": {"tiles": "CartoDB dark_matter", "attr": None},
}

SATELLITE_GROUPS = {
    "Stations": [("stations", "Crewed and station assets")],
    "Navigation": [("gps-ops", "GPS operational"), ("galileo", "Galileo"), ("glo-ops", "GLONASS")],
    "Weather": [("weather", "Weather satellites"), ("noaa", "NOAA weather"), ("goes", "GOES weather")],
    "Earth Observation": [("resource", "Earth observation"), ("science", "Science missions")],
    "Communications": [("geo", "GEO communications"), ("iridium", "Iridium")],
    "Military": [("military", "Public military catalogue")],
}

CATEGORY_COLORS = {
    "Stations": "#7dd3fc",
    "Navigation": "#58a6ff",
    "Weather": "#39d98a",
    "Earth Observation": "#ffb454",
    "Communications": "#14b8a6",
    "Military": "#ff5f6d",
}

CATEGORY_NOTES = {
    "Stations": "Crewed platforms and station-linked objects.",
    "Navigation": "Timing, positioning, and navigation constellations.",
    "Weather": "Meteorology and environmental monitoring satellites.",
    "Earth Observation": "Imaging, mapping, and science missions.",
    "Communications": "Relay and telecom spacecraft in orbit.",
    "Military": "Publicly catalogued defence and government-linked satellites.",
}

DEMO_SATELLITES = [
    ("ISS DEMO TRACK", "25544", "Stations", "Crewed and station assets", 19.0, -38.0, 418.0, 7.67, "LEO"),
    ("GPS DEMO VEHICLE", "32711", "Navigation", "GPS operational", 11.0, 74.0, 20190.0, 3.88, "MEO"),
    ("NOAA DEMO ORBITER", "33591", "Weather", "NOAA weather", -61.0, 109.0, 865.0, 7.42, "LEO"),
    ("LANDSAT DEMO", "39084", "Earth Observation", "Earth observation", 35.0, 126.0, 705.0, 7.48, "LEO"),
    ("GEO DEMO RELAY", "41866", "Communications", "GEO communications", 0.2, -16.0, 35786.0, 3.07, "GEO"),
    ("MILITARY DEMO WATCH", "43075", "Military", "Public military catalogue", 24.0, -132.0, 1090.0, 7.28, "LEO"),
]


def inject_styles():
    st.markdown(
        """
        <style>
            :root { --bg-0:#07111f; --bg-1:#0d1b2a; --stroke:rgba(130,161,191,.22); --text-main:#e8f1fb; --text-soft:#91a9c3; }
            .stApp { background:radial-gradient(circle at top left, rgba(56,189,248,.16), transparent 28%), radial-gradient(circle at top right, rgba(88,166,255,.12), transparent 26%), linear-gradient(180deg, var(--bg-0) 0%, var(--bg-1) 100%); color:var(--text-main); font-family:"Aptos","Segoe UI",sans-serif; }
            [data-testid="stSidebar"] { background:linear-gradient(180deg, rgba(9,19,32,.97), rgba(9,19,32,.92)); border-right:1px solid var(--stroke); }
            [data-testid="stSidebar"] * { color:var(--text-main); }
            .hero-card,.panel-card,.metric-card { border:1px solid var(--stroke); border-radius:22px; box-shadow:0 12px 28px rgba(4,9,18,.22); }
            .hero-card { background:linear-gradient(145deg, rgba(10,21,35,.92), rgba(15,31,49,.86)); padding:1.35rem 1.5rem; margin-bottom:1rem; }
            .panel-card { background:linear-gradient(180deg, rgba(10,23,37,.9), rgba(14,31,49,.82)); padding:1rem 1rem .85rem 1rem; }
            .metric-card { background:linear-gradient(180deg, rgba(12,24,39,.9), rgba(14,32,50,.76)); padding:1rem 1rem .95rem 1rem; min-height:120px; }
            .hero-kicker { letter-spacing:.16rem; font-size:.72rem; font-weight:700; color:#84d7ff; margin-bottom:.4rem; }
            .hero-title { font-size:2.2rem; line-height:1.05; font-weight:700; margin:0; color:var(--text-main); }
            .hero-copy,.panel-copy,.metric-detail { color:var(--text-soft); font-size:.94rem; }
            .metric-label { font-size:.8rem; text-transform:uppercase; letter-spacing:.08rem; color:var(--text-soft); margin-bottom:.45rem; }
            .metric-value { font-size:2rem; font-weight:700; line-height:1; margin-bottom:.35rem; color:var(--text-main); }
            .accent-bar { width:54px; height:4px; border-radius:999px; margin-bottom:.8rem; }
            .panel-title { font-size:1rem; font-weight:700; margin-bottom:.25rem; color:var(--text-main); }
            .stTabs [data-baseweb="tab-list"] { gap:.6rem; }
            .stTabs [data-baseweb="tab"] { border-radius:999px; background:rgba(15,31,49,.7); border:1px solid var(--stroke); color:var(--text-main); padding-left:1rem; padding-right:1rem; }
            .stDataFrame, div[data-testid="stTable"] { border-radius:18px; overflow:hidden; border:1px solid var(--stroke); }
        </style>
        """,
        unsafe_allow_html=True,
    )


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


def safe_str(value):
    return "" if value is None else str(value).strip()


def format_time(value):
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    return "Unknown" if pd.isna(parsed) else parsed.strftime("%Y-%m-%d %H:%M UTC")


def orbit_regime(altitude_km):
    if altitude_km < 2000:
        return "LEO"
    if altitude_km < 30000:
        return "MEO"
    if altitude_km <= 37000:
        return "GEO"
    return "HEO"


def parse_tle_text(tle_text):
    records = []
    lines = [line.rstrip() for line in tle_text.splitlines() if line.strip()]
    i = 0
    while i < len(lines):
        if i + 2 < len(lines) and not lines[i].startswith("1 ") and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            records.append({"name": lines[i], "line1": lines[i + 1], "line2": lines[i + 2], "norad_id": lines[i + 1][2:7].strip()})
            i += 3
            continue
        if i + 1 < len(lines) and lines[i].startswith("1 ") and lines[i + 1].startswith("2 "):
            records.append({"name": f"NORAD {lines[i][2:7].strip()}", "line1": lines[i], "line2": lines[i + 1], "norad_id": lines[i][2:7].strip()})
            i += 2
            continue
        i += 1
    return records


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_group(group_name):
    response = requests.get(CELESTRAK_URL.format(group=quote_plus(group_name)), timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    records = parse_tle_text(response.text)
    if not records:
        raise RuntimeError(f"No records returned for the {group_name} public feed.")
    return records


def to_julian(dt):
    jd, fr = jday(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second + dt.microsecond / 1_000_000)
    return jd, fr


def sidereal_angle(jd_full):
    t = (jd_full - 2451545.0) / 36525.0
    gmst_deg = 280.46061837 + 360.98564736629 * (jd_full - 2451545.0) + 0.000387933 * (t**2) - (t**3) / 38710000.0
    return math.radians(gmst_deg % 360.0)


def eci_to_latlonalt(position_km, jd_full):
    x, y, z = position_km
    theta = sidereal_angle(jd_full)
    x_ecef = x * math.cos(theta) + y * math.sin(theta)
    y_ecef = -x * math.sin(theta) + y * math.cos(theta)
    z_ecef = z
    a = 6378.137
    f = 1 / 298.257223563
    e2 = f * (2 - f)
    lon = math.atan2(y_ecef, x_ecef)
    r = math.hypot(x_ecef, y_ecef)
    lat = math.atan2(z_ecef, r)
    for _ in range(6):
        n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        alt = r / max(math.cos(lat), 1e-9) - n
        lat = math.atan2(z_ecef, r * (1 - e2 * n / (n + alt)))
    n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    alt = r / max(math.cos(lat), 1e-9) - n
    return math.degrees(lat), ((math.degrees(lon) + 180) % 360) - 180, alt


def propagate(line1, line2, dt):
    sat = Satrec.twoline2rv(line1, line2)
    jd, fr = to_julian(dt)
    error, position_km, velocity_kms = sat.sgp4(jd, fr)
    if error != 0:
        return None
    lat, lon, alt = eci_to_latlonalt(position_km, jd + fr)
    speed = math.sqrt(sum(component * component for component in velocity_kms))
    return lat, lon, alt, speed


def split_segments(points):
    segments, current = [], []
    for point in points:
        if not current or abs(point[1] - current[-1][1]) <= 180:
            current.append(point)
        else:
            if len(current) > 1:
                segments.append(current)
            current = [point]
    if len(current) > 1:
        segments.append(current)
    return segments


def track_segments(line1, line2, now_utc, minutes, step_minutes):
    points = []
    for offset in range(-minutes, minutes + step_minutes, step_minutes):
        state = propagate(line1, line2, now_utc + timedelta(minutes=offset))
        if state:
            points.append([state[0], state[1]])
    return split_segments(points)


def demo_tracks(mode_lat, mode_lon, regime):
    points = []
    for step in range(-6, 7):
        if regime == "GEO":
            lat = 0.4 * math.sin(math.radians(step * 20))
            lon = ((mode_lon + step * 2) + 180) % 360 - 180
        elif regime == "MEO":
            lat = max(-55, min(55, mode_lat + 20 * math.sin(math.radians(step * 28))))
            lon = ((mode_lon + step * 18) + 180) % 360 - 180
        else:
            lat = max(-75, min(75, mode_lat + 16 * math.sin(math.radians(step * 30))))
            lon = ((mode_lon + step * 20) + 180) % 360 - 180
        points.append([lat, lon])
    return split_segments(points)


def search_blob(row):
    return " ".join([safe_str(row.get("name")), safe_str(row.get("norad_id")), safe_str(row.get("category")), safe_str(row.get("feed")), safe_str(row.get("orbit_regime"))]).lower()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def build_live_dataset(categories, per_category_limit, track_window, track_step):
    now_utc = datetime.now(timezone.utc)
    rows, feeds = [], []
    for category in categories:
        category_rows = []
        for group_name, feed_label in SATELLITE_GROUPS.get(category, []):
            feeds.append(group_name)
            for record in fetch_group(group_name):
                state = propagate(record["line1"], record["line2"], now_utc)
                if not state:
                    continue
                lat, lon, alt, speed = state
                category_rows.append(
                    {
                        "name": record["name"],
                        "norad_id": record["norad_id"],
                        "category": category,
                        "feed": feed_label,
                        "latitude": lat,
                        "longitude": lon,
                        "altitude_km": alt,
                        "speed_kms": speed,
                        "orbit_regime": orbit_regime(alt),
                        "track_segments": track_segments(record["line1"], record["line2"], now_utc, track_window, track_step),
                    }
                )
        rows.extend(sorted(category_rows, key=lambda item: item["name"])[:per_category_limit])
    if not rows:
        raise RuntimeError("No public satellite tracks could be computed from the selected feeds.")
    df = pd.DataFrame(rows)
    df["marker_color"] = df["category"].map(CATEGORY_COLORS)
    df["priority_rank"] = df["category"].map({"Stations": 0, "Military": 1, "Navigation": 2, "Weather": 3, "Earth Observation": 4, "Communications": 5}).fillna(99)
    df["search_blob"] = df.apply(search_blob, axis=1)
    return df.reset_index(drop=True), now_utc.isoformat(), sorted(set(feeds))


def build_demo_dataset(categories):
    now_utc = datetime.now(timezone.utc)
    rows = []
    for name, norad_id, category, feed, lat, lon, alt, speed, regime in DEMO_SATELLITES:
        if category not in categories:
            continue
        rows.append({"name": name, "norad_id": norad_id, "category": category, "feed": feed, "latitude": lat, "longitude": lon, "altitude_km": alt, "speed_kms": speed, "orbit_regime": regime, "track_segments": demo_tracks(lat, lon, regime)})
    df = pd.DataFrame(rows if rows else [{"name": item[0], "norad_id": item[1], "category": item[2], "feed": item[3], "latitude": item[4], "longitude": item[5], "altitude_km": item[6], "speed_kms": item[7], "orbit_regime": item[8], "track_segments": demo_tracks(item[4], item[5], item[8])} for item in DEMO_SATELLITES])
    df["marker_color"] = df["category"].map(CATEGORY_COLORS)
    df["priority_rank"] = df["category"].map({"Stations": 0, "Military": 1, "Navigation": 2, "Weather": 3, "Earth Observation": 4, "Communications": 5}).fillna(99)
    df["search_blob"] = df.apply(search_blob, axis=1)
    return df.reset_index(drop=True), now_utc.isoformat(), ["demo-orbital-watch"]


def load_dataset(categories, per_category_limit, track_window, track_step):
    try:
        return (*build_live_dataset(tuple(categories), per_category_limit, track_window, track_step), "live", None)
    except Exception as error:
        demo_df, loaded_at, feeds = build_demo_dataset(categories)
        return demo_df, loaded_at, feeds, "demo", str(error)


def apply_filters(df, search_query, regimes):
    filtered = df.copy()
    if search_query:
        filtered = filtered[filtered["search_blob"].str.contains(search_query.lower(), na=False)]
    if regimes:
        filtered = filtered[filtered["orbit_regime"].isin(regimes)]
    else:
        filtered = filtered.iloc[0:0]
    return filtered.reset_index(drop=True)


def popup_html(row):
    return f"""
        <div style="min-width:280px; font-family:Segoe UI,sans-serif;">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:8px;">
                <div>
                    <div style="font-size:15px; font-weight:700; color:#09111f;">{html.escape(safe_str(row.get("name") or "Unknown object"))}</div>
                    <div style="font-size:12px; color:#5a6d85;">NORAD {html.escape(safe_str(row.get("norad_id") or "Unknown"))}</div>
                </div>
                <div style="background:{row.get("marker_color", "#7dd3fc")}; color:#fff; font-size:11px; font-weight:700; border-radius:999px; padding:5px 8px;">
                    {html.escape(safe_str(row.get("category") or "Tracked"))}
                </div>
            </div>
            <table style="width:100%; border-collapse:collapse; font-size:12px;">
                <tr><td style="padding:4px 0; color:#5a6d85;">Feed</td><td style="padding:4px 0;">{html.escape(safe_str(row.get("feed") or "Unknown"))}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Orbit</td><td style="padding:4px 0;">{html.escape(safe_str(row.get("orbit_regime") or "Unknown"))}</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Altitude</td><td style="padding:4px 0;">{float(row.get("altitude_km")):,.0f} km</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Velocity</td><td style="padding:4px 0;">{float(row.get("speed_kms")):.2f} km/s</td></tr>
                <tr><td style="padding:4px 0; color:#5a6d85;">Note</td><td style="padding:4px 0;">{html.escape(CATEGORY_NOTES.get(row.get("category"), "Tracked public orbital object."))}</td></tr>
            </table>
        </div>
    """


def satellite_icon_html(row, show_label):
    color = row.get("marker_color", "#7dd3fc")
    label_html = ""
    if show_label:
        label = html.escape((safe_str(row.get("name")) or "Satellite")[:16])
        label_html = f'<div style="margin-top:3px; padding:2px 7px; border-radius:999px; background:rgba(7,17,31,.9); color:#f4f9ff; font-size:10px; font-weight:700; text-align:center; white-space:nowrap;">{label}</div>'
    return f"""
        <div style="position:relative; width:38px; height:38px; transform:translate(-19px,-19px);">
            <div style="width:38px; height:38px; border-radius:999px; background:rgba(8,18,30,.84); box-shadow:0 0 0 1px rgba(255,255,255,.14), 0 12px 26px {color}55; display:flex; align-items:center; justify-content:center;">
                <svg viewBox="0 0 32 32" width="24" height="24">
                    <circle cx="16" cy="16" r="5.5" fill="{color}" stroke="#ffffff" stroke-width="1"></circle>
                    <ellipse cx="16" cy="16" rx="11.5" ry="5.5" fill="none" stroke="#ffffff" stroke-width="1.1" opacity="0.85"></ellipse>
                    <path d="M7 16h3.5M21.5 16H25M16 5v3M16 24v3" stroke="#ffffff" stroke-width="1" opacity="0.72"></path>
                </svg>
            </div>
            {label_html}
        </div>
    """


def create_map(df, map_theme, show_tracks, show_labels):
    coords = df.dropna(subset=["latitude", "longitude"]).copy()
    if coords.empty:
        return None, False
    satellite_map = folium.Map(location=[16, 0], zoom_start=2, control_scale=True, prefer_canvas=True, tiles=None)
    for theme_name, theme_config in MAP_THEMES.items():
        folium.TileLayer(tiles=theme_config["tiles"], attr=theme_config["attr"], name=theme_name, show=theme_name == map_theme).add_to(satellite_map)
    Fullscreen(position="topright").add_to(satellite_map)
    MousePosition(position="bottomright", separator=" | ", lng_first=False, num_digits=3, prefix="Lat / Lon").add_to(satellite_map)
    track_layer = folium.FeatureGroup(name="Ground tracks", show=show_tracks)
    marker_layer = folium.FeatureGroup(name="Satellites", show=True)
    effective_labels = show_labels and len(coords) <= 140
    for _, row in coords.iterrows():
        if show_tracks:
            for segment in row.get("track_segments") or []:
                folium.PolyLine(locations=segment, color=row["marker_color"], weight=2, opacity=0.78, dash_array="7 8").add_to(track_layer)
        folium.Marker(location=[row["latitude"], row["longitude"]], tooltip=f"{safe_str(row.get('name'))} | {safe_str(row.get('category'))}", popup=folium.Popup(popup_html(row), max_width=360), icon=DivIcon(html=satellite_icon_html(row, effective_labels))).add_to(marker_layer)
    track_layer.add_to(satellite_map)
    marker_layer.add_to(satellite_map)
    folium.LayerControl(collapsed=True).add_to(satellite_map)
    return satellite_map, effective_labels


def priority_table(df):
    if df.empty:
        return df
    table = df[["name", "category", "feed", "norad_id", "orbit_regime", "altitude_km", "speed_kms"]].copy()
    table["altitude_km"] = table["altitude_km"].round(0)
    table["speed_kms"] = table["speed_kms"].round(2)
    return table.rename(columns={"name": "Satellite", "category": "Category", "feed": "Feed", "norad_id": "NORAD", "orbit_regime": "Orbit", "altitude_km": "Altitude (km)", "speed_kms": "Velocity (km/s)"})


def summary_table(df):
    if df.empty:
        return df
    summary = df.groupby("category", dropna=False).agg(Objects=("name", "size"), Mean_Altitude_km=("altitude_km", "mean"), Mean_Velocity_kms=("speed_kms", "mean"), Example_Object=("name", "first")).reset_index()
    summary["Mean_Altitude_km"] = summary["Mean_Altitude_km"].round(0)
    summary["Mean_Velocity_kms"] = summary["Mean_Velocity_kms"].round(2)
    return summary.rename(columns={"category": "Category", "Mean_Altitude_km": "Mean Altitude (km)", "Mean_Velocity_kms": "Mean Velocity (km/s)", "Example_Object": "Example Object"})


def feed_table(df):
    if df.empty:
        return df
    table = df[["name", "norad_id", "category", "feed", "orbit_regime", "altitude_km", "speed_kms", "latitude", "longitude"]].copy()
    table["altitude_km"] = table["altitude_km"].round(0)
    table["speed_kms"] = table["speed_kms"].round(2)
    table["latitude"] = table["latitude"].round(2)
    table["longitude"] = table["longitude"].round(2)
    return table.rename(columns={"name": "Satellite", "norad_id": "NORAD", "category": "Category", "feed": "Feed", "orbit_regime": "Orbit", "altitude_km": "Altitude (km)", "speed_kms": "Velocity (km/s)", "latitude": "Latitude", "longitude": "Longitude"})


inject_styles()

st.markdown(
    """
    <div class="hero-card">
        <div class="hero-kicker">LIVE ORBITAL TRACKING</div>
        <h1 class="hero-title">Satellite Radar</h1>
        <p class="hero-copy">
            A professional orbital watchboard for public satellite tracking, showing live ground positions,
            orbital categories, and short projected tracks from open orbital catalogues.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### Radar Filters")
    categories = st.multiselect("Track categories", options=list(SATELLITE_GROUPS.keys()), default=["Stations", "Navigation", "Weather", "Military"])
    per_category_limit = st.slider("Objects per category", min_value=6, max_value=30, value=14)
    search_query = st.text_input("Search satellites", placeholder="Satellite, NORAD, category, or feed").strip()
    regimes = st.multiselect("Orbit regimes", options=["LEO", "MEO", "GEO", "HEO"], default=["LEO", "MEO", "GEO", "HEO"])
    st.markdown("### Map Layers")
    map_theme = st.selectbox("Map theme", options=list(MAP_THEMES.keys()), index=1)
    show_tracks = st.toggle("Show orbital tracks", value=True)
    show_labels = st.toggle("Show satellite labels", value=False)
    track_window = st.slider("Track window (minutes)", min_value=20, max_value=90, value=45, step=5)
    track_step = st.slider("Track step (minutes)", min_value=5, max_value=20, value=10, step=5)

if not categories:
    st.warning("Choose at least one satellite category to build the radar view.")
    st.stop()

with st.spinner("Loading public satellite tracks..."):
    satellites_df, loaded_at_iso, loaded_feeds, data_source, data_error = load_dataset(categories, per_category_limit, track_window, track_step)

filtered_df = apply_filters(satellites_df, search_query, regimes)
priority_df = filtered_df.sort_values(["priority_rank", "altitude_km", "name"]).head(20).copy() if not filtered_df.empty else pd.DataFrame()
military_df = filtered_df[filtered_df["category"] == "Military"].copy() if not filtered_df.empty else pd.DataFrame()
navigation_df = filtered_df[filtered_df["category"] == "Navigation"].copy() if not filtered_df.empty else pd.DataFrame()

metric_columns = st.columns(5)
with metric_columns[0]:
    render_metric_card("Objects loaded", f"{len(satellites_df):,}", "Loaded from the selected public orbital feeds", "#38bdf8")
with metric_columns[1]:
    render_metric_card("Objects in view", f"{len(filtered_df):,}", "Search and orbit filtered satellite set", "#7dd3fc")
with metric_columns[2]:
    render_metric_card("Military watch", f"{len(military_df):,}", "Public military catalogue objects in view", "#ff5f6d")
with metric_columns[3]:
    render_metric_card("Navigation watch", f"{len(navigation_df):,}", "PNT constellation objects in view", "#58a6ff")
with metric_columns[4]:
    render_metric_card("Feed status", "Live" if data_source == "live" else "Demo", format_time(loaded_at_iso) if data_source == "live" else "Fallback orbital dataset in use", "#39d98a" if data_source == "live" else "#ff9e3d")

st.markdown("")
map_col, side_col = st.columns([3.1, 1.15], gap="large")

with map_col:
    st.markdown(
        """
        <div class="panel-card">
            <div class="panel-title">Orbital Radar Map</div>
            <div class="panel-copy">
                The radar map plots public satellite subpoints on a world view. Dashed tracks show a short
                forward and backward ground-track window from the selected public orbital elements.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if filtered_df.empty:
        st.info("No satellites match the current search and orbit filters.")
    else:
        orbital_map, labels_used = create_map(filtered_df, map_theme, show_tracks, show_labels)
        if orbital_map is None:
            st.info("No satellite positions are available for the current view.")
        else:
            st_folium(orbital_map, use_container_width=True, height=720)
            if show_labels and not labels_used:
                st.caption("Satellite labels were automatically reduced because too many objects are visible for clean labelling.")

with side_col:
    feed_text = ", ".join(feed.replace("-", " ").title() for feed in loaded_feeds[:6])
    if len(loaded_feeds) > 6:
        feed_text += ", ..."
    st.markdown("#### Orbital brief")
    st.markdown(
        f"""
        <div class="panel-card">
            <div class="panel-title">Current radar scope</div>
            <div class="panel-copy">
                {'Live public orbital feed' if data_source == 'live' else 'Demo orbital fallback'}<br>
                Loaded at: {html.escape(format_time(loaded_at_iso))}<br>
                Categories: {html.escape(", ".join(categories))}<br>
                Public feeds: {html.escape(feed_text)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("#### Signal logic")
    st.markdown(
        """
        <div class="panel-card">
            <div class="panel-title">How to read this radar</div>
            <div class="panel-copy">
                Positions are derived from public TLE data. LEO tracks move fastest across the map,
                MEO objects dominate navigation constellations, and GEO satellites stay close to fixed longitudes.
                This is a public tracking picture, not a classified sensor feed.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if data_error:
        st.warning(f"Live orbital feed unavailable, using demo radar data instead: {data_error}")

tab_priority, tab_summary, tab_feed = st.tabs(["Priority Watch", "Category Summary", "Tracked Objects"])

with tab_priority:
    st.markdown("### Priority Orbital Watch")
    st.caption("This view prioritises crewed platforms, military watch objects, navigation satellites, and other high-interest public orbital assets.")
    if priority_df.empty:
        st.info("No satellites are visible under the active filters.")
    else:
        st.dataframe(priority_table(priority_df), use_container_width=True, hide_index=True)

with tab_summary:
    st.markdown("### Category Summary")
    st.caption("A quick breakdown of how the current orbital picture is distributed across the selected public categories.")
    if filtered_df.empty:
        st.info("No category summary is available for the current filters.")
    else:
        st.dataframe(summary_table(filtered_df), use_container_width=True, hide_index=True)

with tab_feed:
    st.markdown("### Tracked Satellite Feed")
    st.caption("This table follows the current search and orbit filters so you can inspect exactly what the radar map is showing.")
    if filtered_df.empty:
        st.info("No satellites match the current filters.")
    else:
        st.dataframe(feed_table(filtered_df.sort_values(["priority_rank", "name"])), use_container_width=True, hide_index=True)

st.markdown("---")
st.caption(
    f"Loaded {len(satellites_df):,} satellite records from the "
    f"{'live public orbital feed' if data_source == 'live' else 'demo fallback'}, with "
    f"{len(filtered_df):,} objects visible after filtering and {len(priority_df):,} entries highlighted in the priority watch."
)
