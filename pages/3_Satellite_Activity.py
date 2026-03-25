import html
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

import folium
import pandas as pd
import requests
import streamlit as st
from folium.features import DivIcon
from folium.plugins import Fullscreen, MousePosition
from requests.adapters import HTTPAdapter
from sgp4.api import Satrec, jday
from streamlit_folium import st_folium
from urllib3.util.retry import Retry

st.set_page_config(page_title="Satellite Radar", layout="wide")

CELESTRAK_JSON_URLS = [
    "https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=json",
    "https://www.celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=json",
]

REQUEST_TIMEOUT_SECONDS = 20
CACHE_TTL_SECONDS = 600
DISK_CACHE_FILE = "satellite_live_cache.pkl"

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


def build_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1.1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": "SatelliteRadar/1.0 (+Streamlit; contact: ops@example.com)"
        }
    )
    return session


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


def to_julian(dt):
    jd, fr = jday(
        dt.year,
        dt.month,
        dt.day,
        dt.hour,
        dt.minute,
        dt.second + dt.microsecond / 1_000_000,
    )
    return jd, fr


def sidereal_angle(jd_full):
    t = (jd_full - 2451545.0) / 36525.0
    gmst_deg = (
        280.46061837
        + 360.98564736629 * (jd_full - 2451545.0)
        + 0.000387933 * (t ** 2)
        - (t ** 3) / 38710000.0
    )
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


def propagate_omm(mean_motion, eccentricity, inclination, raan, arg_pericenter, mean_anomaly, epoch):
    sat = Satrec()
    sat.sgp4init(
        0,  # wgs72
        "i",
        99999,
        0.0,
        0.0,
        0.0,
        0.0,
        math.radians(arg_pericenter),
        math.radians(inclination),
        math.radians(mean_anomaly),
        mean_motion * 2 * math.pi / 1440.0,  # rev/day -> rad/min
        math.radians(raan),
        eccentricity,
    )

    dt = pd.to_datetime(epoch, utc=True, errors="coerce")
    if pd.isna(dt):
        return None

    dt = dt.to_pydatetime()
    jd, fr = to_julian(dt)
    sat.jdsatepoch = jd
    sat.jdsatepochF = fr

    now_utc = datetime.now(timezone.utc)
    jd_now, fr_now = to_julian(now_utc)
    error, position_km, velocity_kms = sat.sgp4(jd_now, fr_now)
    if error != 0:
        return None

    lat, lon, alt = eci_to_latlonalt(position_km, jd_now + fr_now)
    speed = math.sqrt(sum(v * v for v in velocity_kms))
    return lat, lon, alt, speed


def propagate_from_json_record(record, dt):
    required = [
        "MEAN_MOTION",
        "ECCENTRICITY",
        "INCLINATION",
        "RA_OF_ASC_NODE",
        "ARG_OF_PERICENTER",
        "MEAN_ANOMALY",
        "EPOCH",
    ]
    if any(field not in record or record[field] in (None, "") for field in required):
        return None

    sat = Satrec()
    epoch = pd.to_datetime(record["EPOCH"], utc=True, errors="coerce")
    if pd.isna(epoch):
        return None

    epoch = epoch.to_pydatetime()
    jd_epoch, fr_epoch = to_julian(epoch)

    mean_motion_rad_min = float(record["MEAN_MOTION"]) * 2.0 * math.pi / 1440.0

    sat.sgp4init(
        0,
        "i",
        int(record.get("NORAD_CAT_ID", 99999)),
        0.0,
        float(record.get("BSTAR", 0.0) or 0.0),
        float(record.get("MEAN_MOTION_DOT", 0.0) or 0.0),
        float(record.get("MEAN_MOTION_DDOT", 0.0) or 0.0),
        math.radians(float(record["ARG_OF_PERICENTER"])),
        math.radians(float(record["INCLINATION"])),
        math.radians(float(record["MEAN_ANOMALY"])),
        mean_motion_rad_min,
        math.radians(float(record["RA_OF_ASC_NODE"])),
        float(record["ECCENTRICITY"]),
    )
    sat.jdsatepoch = jd_epoch
    sat.jdsatepochF = fr_epoch

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


def track_segments_from_record(record, now_utc, minutes, step_minutes):
    points = []
    for offset in range(-minutes, minutes + step_minutes, step_minutes):
        state = propagate_from_json_record(record, now_utc + timedelta(minutes=offset))
        if state:
            points.append([state[0], state[1]])
    return split_segments(points)


def search_blob(row):
    return " ".join(
        [
            safe_str(row.get("name")),
            safe_str(row.get("norad_id")),
            safe_str(row.get("category")),
            safe_str(row.get("feed")),
            safe_str(row.get("orbit_regime")),
        ]
    ).lower()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_group_json(group_name):
    session = build_session()
    last_error = None

    for base_url in CELESTRAK_JSON_URLS:
        url = base_url.format(group=quote_plus(group_name))
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()

            payload = response.json()
            if isinstance(payload, list) and payload:
                return payload

            last_error = RuntimeError(f"Empty JSON payload for group '{group_name}'")
        except Exception as e:
            last_error = e

    raise RuntimeError(f"Failed to load group '{group_name}': {last_error}")


def save_live_cache(df, loaded_at_iso, feeds, failures):
    payload = {
        "df": df,
        "loaded_at_iso": loaded_at_iso,
        "feeds": feeds,
        "failures": failures,
    }
    pd.to_pickle(payload, DISK_CACHE_FILE)


def load_live_cache():
    path = Path(DISK_CACHE_FILE)
    if not path.exists():
        return None

    try:
        payload = pd.read_pickle(path)
        df = payload.get("df")
        if df is None or df.empty:
            return None

        return (
            df,
            payload.get("loaded_at_iso"),
            payload.get("feeds", []),
            payload.get("failures", []),
        )
    except Exception:
        return None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def build_live_dataset(categories, per_category_limit, track_window, track_step):
    now_utc = datetime.now(timezone.utc)

    rows = []
    feeds_loaded = []
    failures = []

    for category in categories:
        category_rows = []

        for group_name, feed_label in SATELLITE_GROUPS.get(category, []):
            try:
                records = fetch_group_json(group_name)
                feeds_loaded.append(group_name)

                for record in records:
                    state = propagate_from_json_record(record, now_utc)
                    if not state:
                        continue

                    lat, lon, alt, speed = state

                    category_rows.append(
                        {
                            "name": record.get("OBJECT_NAME") or f"NORAD {record.get('NORAD_CAT_ID', 'Unknown')}",
                            "norad_id": str(record.get("NORAD_CAT_ID", "")),
                            "category": category,
                            "feed": feed_label,
                            "latitude": lat,
                            "longitude": lon,
                            "altitude_km": alt,
                            "speed_kms": speed,
                            "orbit_regime": orbit_regime(alt),
                            "track_segments": track_segments_from_record(
                                record,
                                now_utc,
                                track_window,
                                track_step,
                            ),
                        }
                    )

            except Exception as e:
                failures.append(f"{group_name}: {e}")

        category_rows = sorted(category_rows, key=lambda item: item["name"])[:per_category_limit]
        rows.extend(category_rows)

    if not rows:
        raise RuntimeError("No live satellite tracks could be computed from any selected public feeds.")

    df = pd.DataFrame(rows)
    df["marker_color"] = df["category"].map(CATEGORY_COLORS)
    df["priority_rank"] = df["category"].map(
        {
            "Stations": 0,
            "Military": 1,
            "Navigation": 2,
            "Weather": 3,
            "Earth Observation": 4,
            "Communications": 5,
        }
    ).fillna(99)
    df["search_blob"] = df.apply(search_blob, axis=1)

    loaded_at_iso = now_utc.isoformat()
    feeds_loaded = sorted(set(feeds_loaded))

    save_live_cache(df, loaded_at_iso, feeds_loaded, failures)

    return df.reset_index(drop=True), loaded_at_iso, feeds_loaded, failures


def load_dataset(categories, per_category_limit, track_window, track_step):
    try:
        df, loaded_at, feeds, failures = build_live_dataset(
            tuple(categories),
            per_category_limit,
            track_window,
            track_step,
        )

        if failures and feeds:
            return df, loaded_at, feeds, "partial_live", failures
        return df, loaded_at, feeds, "live", None

    except Exception as live_error:
        cached = load_live_cache()
        if cached is not None:
            cached_df, cached_loaded_at, cached_feeds, cached_failures = cached
            return cached_df, cached_loaded_at, cached_feeds, "cached_live", [str(live_error)]

        return pd.DataFrame(), None, [], "unavailable", [str(live_error)]
