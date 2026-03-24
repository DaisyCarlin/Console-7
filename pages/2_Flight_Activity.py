import streamlit as st
import pandas as pd
import requests
import plotly.express as px

st.set_page_config(page_title="Flight Activity", layout="wide")

st.title("Flight Activity")
st.caption(
    "Open-source flight monitoring dashboard for public emergency squawks and government / military-related flight patterns."
)

# =========================================================
# CONFIG
# =========================================================
OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"

# Public-heuristic filters only
GOV_MIL_COUNTRY_KEYWORDS = [
    "united states",
    "russia",
    "china",
    "united kingdom",
    "france",
    "germany",
    "italy",
    "turkey",
    "israel",
    "india",
]

GOV_MIL_CALLSIGN_PREFIXES = [
    "RCH",   # US Air Mobility Command / transport patterns
    "MC",    # various military-style prefixes
    "RRR",   # RAF transport / tanker style patterns
    "QID",   # RAF / UK military patterns sometimes seen publicly
    "ASY",   # state / military style in some public datasets
    "CNV",
    "GAF",   # German Air Force style
    "IAM",   # Italian Air Force style
    "HKY",   # RAF / military support style
    "NATO",
]

SQUAWK_MEANINGS = {
    "7500": {
        "label": "Hijack / unlawful interference",
        "explanation": (
            "This code is publicly associated with hijack or unlawful interference. "
            "The app should treat this as a high-priority public alert, but not infer anything beyond the code itself."
        ),
        "severity": "HIGH",
    },
    "7600": {
        "label": "Radio failure",
        "explanation": (
            "This code is publicly associated with a loss of two-way radio communications. "
            "Possible causes include radio equipment failure or temporary communications issues."
        ),
        "severity": "HIGH",
    },
    "7700": {
        "label": "General emergency",
        "explanation": (
            "This code is publicly associated with a general emergency. "
            "Possible causes can range from medical or mechanical issues to operational emergencies."
        ),
        "severity": "HIGH",
    },
    "7400": {
        "label": "UAS lost link",
        "explanation": (
            "This code may be used by certain unmanned aircraft systems when the control link is lost."
        ),
        "severity": "MEDIUM",
    },
}


# =========================================================
# HELPERS
# =========================================================
def safe_str(value):
    if value is None:
        return ""
    return str(value).strip()


def classify_callsign(callsign: str) -> str:
    cs = safe_str(callsign).upper()
    if any(cs.startswith(prefix) for prefix in GOV_MIL_CALLSIGN_PREFIXES):
        return "Likely government/military-related"
    return "Unclassified by callsign"


def classify_country(country: str) -> str:
    c = safe_str(country).lower()
    if any(k in c for k in GOV_MIL_COUNTRY_KEYWORDS):
        return "Watched state/country"
    return "Other / unknown"


def public_flight_context(row) -> str:
    """
    Broad public-context note only.
    No hidden-intent inference.
    """
    callsign = safe_str(row.get("callsign")).upper()
    squawk = safe_str(row.get("squawk"))
    on_ground = row.get("on_ground")
    velocity = row.get("velocity")
    altitude = row.get("baro_altitude")

    notes = []

    if callsign:
        notes.append(f"Callsign observed: {callsign}.")
    if squawk in SQUAWK_MEANINGS:
        notes.append(SQUAWK_MEANINGS[squawk]["explanation"])
    if on_ground is True:
        notes.append("Aircraft appears to be on the ground.")
    elif on_ground is False:
        notes.append("Aircraft appears to be airborne.")
    if pd.notna(altitude):
        notes.append(f"Reported barometric altitude is about {int(altitude):,} m.")
    if pd.notna(velocity):
        notes.append(f"Reported groundspeed is about {int(velocity):,} m/s.")

    if not notes:
        return "No additional public context available."

    return " ".join(notes)


# =========================================================
# DATA LOADING
# =========================================================
@st.cache_data(ttl=60)
def get_live_states():
    response = requests.get(OPENSKY_STATES_URL, timeout=20)
    response.raise_for_status()
    payload = response.json()

    states = payload.get("states") or []

    rows = []
    for s in states:
        # OpenSky state vector order used here:
        # 0 icao24
        # 1 callsign
        # 2 origin_country
        # 3 time_position
        # 4 last_contact
        # 5 longitude
        # 6 latitude
        # 7 baro_altitude
        # 8 on_ground
        # 9 velocity
        # 10 true_track
        # 11 vertical_rate
        # 12 sensors
        # 13 geo_altitude
        # 14 squawk
        # 15 spi
        # 16 position_source
        # 17 category
        rows.append(
            {
                "icao24": s[0],
                "callsign": safe_str(s[1]),
                "origin_country": safe_str(s[2]),
                "time_position": s[3],
                "last_contact": s[4],
                "longitude": s[5],
                "latitude": s[6],
                "baro_altitude": s[7],
                "on_ground": s[8],
                "velocity": s[9],
                "true_track": s[10],
                "vertical_rate": s[11],
                "geo_altitude": s[13],
                "squawk": safe_str(s[14]),
                "spi": s[15],
                "position_source": s[16],
                "category": s[17] if len(s) > 17 else None,
            }
        )

    df = pd.DataFrame(rows)

    if not df.empty:
        df["gov_mil_callsign_flag"] = df["callsign"].apply(classify_callsign)
        df["country_watch_flag"] = df["origin_country"].apply(classify_country)
        df["is_emergency_squawk"] = df["squawk"].isin(SQUAWK_MEANINGS.keys())
        df["squawk_label"] = df["squawk"].apply(
            lambda x: SQUAWK_MEANINGS[x]["label"] if x in SQUAWK_MEANINGS else ""
        )
        df["squawk_severity"] = df["squawk"].apply(
            lambda x: SQUAWK_MEANINGS[x]["severity"] if x in SQUAWK_MEANINGS else "LOW"
        )
        df["public_context"] = df.apply(public_flight_context, axis=1)

    return df


# =========================================================
# LOAD
# =========================================================
data_error = None

try:
    flights_df = get_live_states()
except Exception as e:
    flights_df = pd.DataFrame()
    data_error = str(e)

# =========================================================
# FILTERS
# =========================================================
st.subheader("Filters")

f1, f2, f3 = st.columns(3)

with f1:
    show_emergency_only = st.checkbox("Emergency squawks only", value=True)

with f2:
    show_gov_mil_only = st.checkbox("Government / military-related only", value=False)

with f3:
    show_airborne_only = st.checkbox("Airborne only", value=True)

filtered_df = flights_df.copy()

if not filtered_df.empty:
    if show_emergency_only:
        filtered_df = filtered_df[filtered_df["is_emergency_squawk"] == True]

    if show_gov_mil_only:
        filtered_df = filtered_df[
            (filtered_df["gov_mil_callsign_flag"] == "Likely government/military-related")
            | (filtered_df["country_watch_flag"] == "Watched state/country")
        ]

    if show_airborne_only:
        filtered_df = filtered_df[filtered_df["on_ground"] == False]

# =========================================================
# STATUS CARDS
# =========================================================
st.subheader("System Status")

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric("Flights loaded", len(flights_df))

with c2:
    emergency_count = int(flights_df["is_emergency_squawk"].sum()) if not flights_df.empty else 0
    st.metric("Emergency squawks", emergency_count)

with c3:
    govmil_count = int(
        (
            (flights_df["gov_mil_callsign_flag"] == "Likely government/military-related")
            | (flights_df["country_watch_flag"] == "Watched state/country")
        ).sum()
    ) if not flights_df.empty else 0
    st.metric("Gov / military-related", govmil_count)

with c4:
    if data_error:
        st.error("Flight Feed Offline")
    else:
        st.success("Flight Feed Online")

st.divider()

# =========================================================
# MAP + EXPLANATION PANEL
# =========================================================
left, right = st.columns([1.5, 1])

with left:
    st.subheader("Live Flight Map")

    if data_error:
        st.error(f"Flight data unavailable: {data_error}")
    elif filtered_df.empty:
        st.info("No flights match the current filters.")
    else:
        map_df = filtered_df.dropna(subset=["latitude", "longitude"]).copy()

        if map_df.empty:
            st.info("No flight coordinates available for the current filters.")
        else:
            fig = px.scatter_geo(
                map_df,
                lat="latitude",
                lon="longitude",
                hover_name="callsign",
                hover_data=["origin_country", "squawk", "squawk_label", "velocity", "baro_altitude"],
                title="Filtered Live Flights",
            )
            fig.update_traces(marker=dict(size=8))
            fig.update_layout(height=520, margin=dict(l=0, r=0, t=50, b=0))
            st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("How the AI-style explanation works")
    st.caption("These are broad public explanations, not factual determinations of cause or intent.")

    st.markdown(
        """
- **7500** → hijack / unlawful interference  
- **7600** → radio failure  
- **7700** → general emergency  
- **7400** → UAS lost-link context in some cases  

The dashboard only gives **plausible public explanations** based on the squawk code and visible flight context. It does **not** claim to know the real reason.
"""
    )

    if not filtered_df.empty:
        first_row = filtered_df.iloc[0]
        st.markdown("**Example explanation**")
        st.write(first_row.get("public_context", "No explanation available."))

st.divider()

# =========================================================
# SQUAWK TABLE
# =========================================================
st.subheader("Emergency Squawk Watchlist")

if data_error:
    st.error(f"Flight feed unavailable: {data_error}")
elif filtered_df.empty:
    st.info("No flights match the current filters.")
else:
    display_df = filtered_df[
        [
            "callsign",
            "origin_country",
            "squawk",
            "squawk_label",
            "gov_mil_callsign_flag",
            "country_watch_flag",
            "on_ground",
            "velocity",
            "baro_altitude",
            "public_context",
        ]
    ].copy()

    display_df = display_df.rename(
        columns={
            "callsign": "Callsign",
            "origin_country": "Origin Country",
            "squawk": "Squawk",
            "squawk_label": "Meaning",
            "gov_mil_callsign_flag": "Callsign Heuristic",
            "country_watch_flag": "Country Heuristic",
            "on_ground": "On Ground",
            "velocity": "Velocity (m/s)",
            "baro_altitude": "Baro Altitude (m)",
            "public_context": "Public Explanation",
        }
    )

    st.dataframe(display_df, use_container_width=True, hide_index=True)

st.divider()

# =========================================================
# ANALYST SUMMARY
# =========================================================
st.subheader("Analyst Summary")

if data_error:
    st.markdown(
        f"""
- The live flight feed is currently unavailable.
- Error returned by the upstream source: `{data_error}`
- The page is online, but the flight data source needs to recover.
"""
    )
else:
    st.markdown(
        f"""
- **{len(flights_df)}** live flight state records were loaded.
- **{int(flights_df["is_emergency_squawk"].sum())}** flights are showing emergency squawk codes.
- **{int(((flights_df["gov_mil_callsign_flag"] == "Likely government/military-related") | (flights_df["country_watch_flag"] == "Watched state/country")).sum())}** flights matched the public government / military heuristics.
- The explanations shown for squawks are **broad public interpretations** based on FAA emergency code meanings and visible flight context, not confirmed causes.
"""
    )
