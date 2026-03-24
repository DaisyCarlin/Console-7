import math
import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Flight Activity", layout="wide")

st.title("Flight Activity Monitor")
st.caption("Live open-source global flight monitoring.")

OPENSKY_URL = "https://opensky-network.org/api/states/all"

EMERGENCY_SQUAWKS = {
    "7500": "Hijacking / unlawful interference",
    "7600": "Radio failure",
    "7700": "General emergency",
}

MIL_CALLSIGN_PREFIXES = [
    "RCH", "RRR", "ASY", "IAM", "GAF", "HKY", "QID", "NATO"
]

WATCH_COUNTRIES = [
    "United States", "Russia", "China", "Israel",
    "India", "Turkey", "France", "United Kingdom"
]

@st.cache_data(ttl=60)
def load_flights():
    r = requests.get(OPENSKY_URL, timeout=20)
    r.raise_for_status()
    data = r.json()["states"]

    rows = []
    for s in data:
        rows.append({
            "callsign": (s[1] or "").strip(),
            "country": s[2],
            "lon": s[5],
            "lat": s[6],
            "altitude": s[7],
            "velocity": s[9],
            "heading": s[10],
            "on_ground": s[8],
            "squawk": (s[14] or "").strip()
        })

    df = pd.DataFrame(rows)

    df["is_emergency"] = df["squawk"].isin(EMERGENCY_SQUAWKS.keys())

    df["is_military"] = df["callsign"].str.startswith(tuple(MIL_CALLSIGN_PREFIXES))

    df["is_watch_country"] = df["country"].isin(WATCH_COUNTRIES)

    return df

try:
    flights = load_flights()
    feed_ok = True
except Exception as e:
    flights = pd.DataFrame()
    feed_ok = False
    error_msg = str(e)

st.subheader("System Status")

c1, c2, c3 = st.columns(3)

c1.metric("Flights Loaded", len(flights))
c2.metric("Emergency Flights", len(flights[flights["is_emergency"]]) if feed_ok else 0)
c3.metric("Gov / Military Flights", len(flights[(flights["is_military"]) | (flights["is_watch_country"])]) if feed_ok else 0)

st.divider()

st.subheader("Live Global Flight Map")

if not feed_ok:
    st.error(error_msg)
else:
    m = folium.Map(location=[30, 10], zoom_start=2, tiles="CartoDB positron")

    for _, r in flights.dropna(subset=["lat","lon"]).iterrows():

        if r["is_emergency"]:
            color = "red"
        elif r["is_military"] or r["is_watch_country"]:
            color = "blue"
        else:
            color = "green"

        folium.CircleMarker(
            [r["lat"], r["lon"]],
            radius=4,
            color=color,
            fill=True,
            fill_opacity=0.8,
            popup=f"""
            Callsign: {r['callsign']}<br>
            Country: {r['country']}<br>
            Squawk: {r['squawk']}<br>
            Altitude: {r['altitude']}
            """
        ).add_to(m)

        if not r["on_ground"] and pd.notna(r["heading"]):
            dx = math.sin(math.radians(r["heading"]))
            dy = math.cos(math.radians(r["heading"]))

            folium.PolyLine(
                [[r["lat"], r["lon"]],
                 [r["lat"] + dy, r["lon"] + dx]],
                color=color,
                weight=2
            ).add_to(m)

    st_folium(m, use_container_width=True, height=700)

st.divider()

st.subheader("Emergency Flights")

if feed_ok:
    st.dataframe(
        flights[flights["is_emergency"]][
            ["callsign","country","squawk","altitude","velocity"]
        ],
        use_container_width=True
    )

st.divider()

st.subheader("Government / Military-Linked Flights")

if feed_ok:
    st.dataframe(
        flights[(flights["is_military"]) | (flights["is_watch_country"])][
            ["callsign","country","altitude","velocity","squawk"]
        ],
        use_container_width=True
    )
