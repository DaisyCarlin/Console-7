import json
import math
import threading
import time

import folium
import pandas as pd
import streamlit as st
import websocket
from streamlit_folium import st_folium

st.set_page_config(page_title="Abnormal Marine Activity", layout="wide")

st.title("Abnormal Marine Activity")
st.caption("Open-source monitoring for commercial vessel traffic and abnormal shipping behaviour by continent.")

AISSTREAM_WS_URL = "wss://stream.aisstream.io/v0/stream"

# =========================================================
# REGIONS
# =========================================================
CONTINENT_BOXES = {
    "North America": [[24, -130], [55, -60]],
    "South America": [[-40, -82], [13, -34]],
    "Europe": [[35, -15], [71, 40]],
    "Africa": [[-35, -20], [37, 55]],
    "Asia": [[0, 40], [60, 150]],
    "Oceania": [[-48, 110], [0, 180]],
}

CONTINENT_CENTERS = {
    "North America": {"lat": 39, "lon": -96, "zoom": 3},
    "South America": {"lat": -16, "lon": -60, "zoom": 3},
    "Europe": {"lat": 52, "lon": 12, "zoom": 4},
    "Africa": {"lat": 3, "lon": 20, "zoom": 3},
    "Asia": {"lat": 28, "lon": 95, "zoom": 3},
    "Oceania": {"lat": -24, "lon": 135, "zoom": 4},
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
]

# =========================================================
# HELPERS
# =========================================================
def get_secret(name: str, default=None):
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
    return any()
