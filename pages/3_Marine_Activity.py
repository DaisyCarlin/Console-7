import streamlit as st
import pandas as pd
import json
import websocket
import time
import plotly.express as px

st.set_page_config(layout="wide")

st.title("Abnormal Marine Activity Monitor")

AIS_KEY = st.secrets.get("aisstream_key")

CONTINENT_BOXES = {
    "Europe": [[[43.0, -10.0], [61.0, 20.0]]],
    "Asia": [[[1.0, 95.0], [30.0, 125.0]]],
    "North America": [[[24.0, -130.0], [50.0, -65.0]]],
    "South America": [[[-40.0, -75.0], [10.0, -35.0]]],
    "Africa": [[[-35.0, 10.0], [20.0, 45.0]]],
    "Oceania": [[[-45.0, 145.0], [-10.0, 175.0]]],
}

def fetch_ais(region):

    vessels = {}

    subscribe = {
        "APIKey": AIS_KEY,
        "BoundingBoxes": CONTINENT_BOXES[region],
        "FilterMessageTypes": ["PositionReport"]
    }

    try:
        ws = websocket.create_connection(
            "wss://stream.aisstream.io/v0/stream",
            timeout=10
        )

        ws.send(json.dumps(subscribe))

        start = time.time()

        while True:

            if time.time() - start > 20:
                break

            try:
                msg = ws.recv()
                data = json.loads(msg)

                if "MetaData" not in data:
                    continue

                mmsi = data["MetaData"]["MMSI"]

                lat = data["Message"]["PositionReport"]["Latitude"]
                lon = data["Message"]["PositionReport"]["Longitude"]
                sog = data["Message"]["PositionReport"]["Sog"]

                vessels[mmsi] = {
                    "lat": lat,
                    "lon": lon,
                    "speed": sog
                }

                if len(vessels) > 40:
                    break

            except:
                break

        ws.close()

    except Exception as e:
        return None, str(e)

    if len(vessels) == 0:
        return None, "No AIS messages received"

    df = pd.DataFrame(vessels.values())
    return df, None


selected_region = st.selectbox(
    "Continent",
    list(CONTINENT_BOXES.keys())
)

abnormal_only = st.checkbox("Show abnormal only")

if st.button("Load selected region"):

    if AIS_KEY is None:
        st.error("No AIS key set")
        st.stop()

    with st.spinner("Listening for live vessel transmissions..."):
        df, err = fetch_ais(selected_region)

    if err:
        st.warning(f"Live AIS unavailable: {err}")
        st.stop()

    df["abnormal"] = (
        (df["speed"] > 25) |
        (df["speed"] < 1)
    )

    if abnormal_only:
        df = df[df["abnormal"]]

    st.metric("Vessels detected", len(df))

    fig = px.scatter_mapbox(
        df,
        lat="lat",
        lon="lon",
        color="abnormal",
        zoom=3,
        height=700
    )

    fig.update_layout(mapbox_style="carto-darkmatter")

    st.plotly_chart(fig, use_container_width=True)
