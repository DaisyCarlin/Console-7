from __future__ import annotations

import time

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Strategic Insights", layout="wide")

# ----------------------------
# CONFIG
# ----------------------------

LAUNCH_RECENT_LIMIT = 60
FLIGHT_REQUEST_TIMEOUT = 20
LAUNCH_REQUEST_TIMEOUT = 45
REQUEST_RETRIES = 3
CACHE_TTL_SECONDS = 180

LAUNCH_API_URL = f"https://ll.thespacedevs.com/2.2.0/launch/previous/?limit={LAUNCH_RECENT_LIMIT}&mode=detailed"
OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"
REQUEST_HEADERS = {"User-Agent": "StrategicInsights/1.0"}

SENSITIVE_KEYWORDS = [
    "government",
    "national security",
    "military",
    "reconnaissance",
    "surveillance",
    "classified",
    "nrol",
    "nro",
    "ussf-",
    "gps",
    "wgs",
    "gssap",
    "missile warning",
    "missile tracking",
    "tracking layer",
    "satcom",
]

WATCHED_PROVIDERS = [
    "united launch alliance",
    "spacex",
    "rocket lab",
    "northrop grumman",
]

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

# ----------------------------
# STYLES
# ----------------------------


def inject_styles() -> None:
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

            .hero-card,
            .panel-card {
                border: 1px solid var(--stroke);
                background: linear-gradient(180deg, rgba(10, 23, 37, 0.9), rgba(14, 31, 49, 0.82));
                border-radius: 22px;
                box-shadow: 0 16px 34px rgba(4, 9, 18, 0.22);
            }

            .hero-card {
                padding: 1.35rem 1.5rem;
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

            .hero-copy,
            .panel-copy {
                color: var(--text-soft);
                font-size: 0.95rem;
                margin: 0.55rem 0 0 0;
                line-height: 1.5;
            }

            .panel-card {
                padding: 1rem 1rem 0.85rem 1rem;
            }

            .panel-title {
                font-size: 1rem;
                font-weight: 700;
                color: var(--text-main);
                margin-bottom: 0.25rem;
            }

            div[data-testid="stMetric"] {
                border: 1px solid var(--stroke);
                border-radius: 18px;
                padding: 0.9rem 1rem;
                background: linear-gradient(180deg, rgba(12, 24, 39, 0.9), rgba(14, 32, 50, 0.76));
                box-shadow: 0 12px 28px rgba(4, 9, 18, 0.2);
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


# ----------------------------
# HELPERS
# ----------------------------


def safe_text(value):
    return "" if value is None else str(value).strip()


def fetch_json_with_retry(url: str, timeout: int, retries: int = REQUEST_RETRIES, headers: dict | None = None):
    last_error = None
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=timeout, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            last_error = error
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last_error


def month_windows(now_utc: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    current_month_start = pd.Timestamp(year=now_utc.year, month=now_utc.month, day=1, tz="UTC")
    next_month_start = current_month_start + pd.offsets.MonthBegin(1)
    previous_month_start = current_month_start - pd.offsets.MonthBegin(1)
    return previous_month_start, current_month_start, next_month_start


def top_value_by_country(events_df: pd.DataFrame, value_col: str) -> pd.Series:
    if events_df.empty or value_col not in events_df.columns:
        return pd.Series(dtype="object")

    grouped = (
        events_df.groupby(["country", value_col], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["country", "count", value_col], ascending=[True, False, True])
    )
    return grouped.drop_duplicates(subset=["country"]).set_index("country")[value_col]


def detect_military_callsign(callsign):
    normalized = safe_text(callsign).upper().replace(" ", "")
    for prefix, reason in MILITARY_CALLSIGN_RULES:
        if normalized.startswith(prefix):
            return True, f"Callsign prefix {prefix}: {reason}"
    return False, ""


def looks_sensitive_launch(name: str, subcategory: str, source: str) -> bool:
    text = " ".join([safe_text(name).lower(), safe_text(subcategory).lower(), safe_text(source).lower()])

    if any(keyword in text for keyword in SENSITIVE_KEYWORDS):
        return True

    provider = safe_text(source).lower()
    if any(provider_name in provider for provider_name in WATCHED_PROVIDERS):
        watched_pattern = (
            "government",
            "military",
            "national security",
            "reconnaissance",
            "surveillance",
            "classified",
            "nrol",
            "nro",
            "gps",
            "wgs",
            "gssap",
            "missile",
        )
        return any(token in text for token in watched_pattern)

    return False


# ----------------------------
# LIVE LAUNCH EVENTS
# ----------------------------


def build_launch_events(raw_results) -> pd.DataFrame:
    rows = []

    for item in raw_results:
        mission = item.get("mission") or {}
        rocket = item.get("rocket") or {}
        configuration = rocket.get("configuration") or {}
        provider = item.get("launch_service_provider") or {}
        pad = item.get("pad") or {}
        location = pad.get("location") or {}

        name = safe_text(item.get("name")) or "Unknown launch"
        subcategory = safe_text(mission.get("type")) or "orbital_launch"
        source = safe_text(provider.get("name")) or "Unknown"
        timestamp = item.get("net")
        country = safe_text(location.get("country_code")) or "Unknown"

        rows.append(
            {
                "event_id": f"launch_{safe_text(item.get('id') or name)}_{safe_text(timestamp)}",
                "timestamp": timestamp,
                "country": country,
                "event_type": "launch",
                "subcategory": subcategory,
                "source": source,
                "sensitive": looks_sensitive_launch(name, subcategory, source),
                "name": name,
                "detail": safe_text(configuration.get("name")) or "Unknown rocket",
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    return df


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_recent_launch_events() -> pd.DataFrame:
    raw = fetch_json_with_retry(LAUNCH_API_URL, timeout=LAUNCH_REQUEST_TIMEOUT)["results"]
    df = build_launch_events(raw)
    if not df.empty:
        df = df.sort_values("timestamp", ascending=False)
    return df


# ----------------------------
# LIVE FLIGHT EVENTS
# ----------------------------


def build_flight_events(payload) -> pd.DataFrame:
    states = payload.get("states") or []
    rows = []

    for state in states:
        callsign = safe_text(state[1] if len(state) > 1 else None)
        origin_country = safe_text(state[2] if len(state) > 2 else None)
        last_contact = state[4] if len(state) > 4 else None

        is_military, military_reason = detect_military_callsign(callsign)
        if not is_military:
            continue

        timestamp = pd.to_datetime(last_contact, unit="s", utc=True, errors="coerce")
        if pd.isna(timestamp):
            continue

        rows.append(
            {
                "event_id": f"military_{safe_text(state[0] if len(state) > 0 else '')}_{safe_text(callsign)}_{int(last_contact) if pd.notna(last_contact) else 'unknown'}",
                "timestamp": timestamp,
                "country": origin_country or "Unknown",
                "event_type": "military_flight",
                "subcategory": "military_callsign_activity",
                "source": "opensky",
                "sensitive": True,
                "name": callsign or "N/A",
                "detail": military_reason,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    return df


@st.cache_data(ttl=45, show_spinner=False)
def get_military_flight_events() -> pd.DataFrame:
    payload = fetch_json_with_retry(
        OPENSKY_STATES_URL,
        timeout=FLIGHT_REQUEST_TIMEOUT,
        headers=REQUEST_HEADERS,
    )
    df = build_flight_events(payload)
    if not df.empty:
        df = df.sort_values("timestamp", ascending=False)
    return df


# ----------------------------
# BLENDED LOGIC
# ----------------------------


def get_blended_events() -> tuple[pd.DataFrame, list[str]]:
    sources_loaded = []
    frames = []

    launch_error = None
    flight_error = None

    try:
        launch_df = get_recent_launch_events()
        if not launch_df.empty:
            frames.append(launch_df)
        sources_loaded.append("Launches")
    except Exception as error:
        launch_error = str(error)

    try:
        military_df = get_military_flight_events()
        if not military_df.empty:
            frames.append(military_df)
        sources_loaded.append("Military flights")
    except Exception as error:
        flight_error = str(error)

    if not frames:
        error_parts = []
        if launch_error:
            error_parts.append(f"Launch feed: {launch_error}")
        if flight_error:
            error_parts.append(f"Flight feed: {flight_error}")
        raise RuntimeError(" | ".join(error_parts) if error_parts else "No event sources returned data.")

    events_df = pd.concat(frames, ignore_index=True)

    for required_col in ["event_id", "timestamp", "country", "event_type", "subcategory", "source", "sensitive"]:
        if required_col not in events_df.columns:
            if required_col == "sensitive":
                events_df[required_col] = False
            else:
                events_df[required_col] = ""

    events_df["timestamp"] = pd.to_datetime(events_df["timestamp"], utc=True, errors="coerce")
    events_df["country"] = events_df["country"].fillna("").astype(str).str.strip().replace("", "Unknown")
    events_df["event_type"] = events_df["event_type"].fillna("").astype(str).str.strip().replace("", "Unknown")
    events_df["subcategory"] = events_df["subcategory"].fillna("").astype(str).str.strip().replace("", "Unknown")
    events_df["source"] = events_df["source"].fillna("").astype(str).str.strip().replace("", "Unknown")
    events_df["sensitive"] = events_df["sensitive"].fillna(False).astype(bool)

    return events_df, sources_loaded


def apply_filters(events_df: pd.DataFrame, selected_event_types: list[str], sensitive_only: bool) -> pd.DataFrame:
    filtered_df = events_df.copy()

    if selected_event_types:
        filtered_df = filtered_df[filtered_df["event_type"].isin(selected_event_types)]

    if sensitive_only:
        filtered_df = filtered_df[filtered_df["sensitive"]]

    return filtered_df.reset_index(drop=True)


def calculate_country_summary(events_df: pd.DataFrame, now_utc: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    previous_month_start, current_month_start, next_month_start = month_windows(now_utc)

    valid_df = events_df.dropna(subset=["timestamp"]).copy()

    current_df = valid_df[
        (valid_df["timestamp"] >= current_month_start) & (valid_df["timestamp"] < next_month_start)
    ].copy()
    previous_df = valid_df[
        (valid_df["timestamp"] >= previous_month_start) & (valid_df["timestamp"] < current_month_start)
    ].copy()

    current_counts = current_df.groupby("country").size().rename("current_count")
    previous_counts = previous_df.groupby("country").size().rename("previous_count")
    all_countries = current_counts.index.union(previous_counts.index)

    summary_df = pd.DataFrame(index=all_countries).reset_index().rename(columns={"index": "country"})
    summary_df["current_count"] = summary_df["country"].map(current_counts).fillna(0).astype(int)
    summary_df["previous_count"] = summary_df["country"].map(previous_counts).fillna(0).astype(int)
    summary_df["absolute_change"] = summary_df["current_count"] - summary_df["previous_count"]

    summary_df["pct_change"] = 0.0
    has_previous = summary_df["previous_count"] > 0
    summary_df.loc[has_previous, "pct_change"] = (
        (summary_df.loc[has_previous, "current_count"] - summary_df.loc[has_previous, "previous_count"])
        / summary_df.loc[has_previous, "previous_count"]
    ) * 100.0
    summary_df.loc[(~has_previous) & (summary_df["current_count"] > 0), "pct_change"] = 100.0

    sensitive_counts = (
        current_df[current_df["sensitive"] == True]
        .groupby("country")
        .size()
        .rename("sensitive_count")
    )
    summary_df["sensitive_count"] = summary_df["country"].map(sensitive_counts).fillna(0).astype(int)

    summary_df["sensitive_share"] = 0.0
    has_current = summary_df["current_count"] > 0
    summary_df.loc[has_current, "sensitive_share"] = (
        summary_df.loc[has_current, "sensitive_count"] / summary_df.loc[has_current, "current_count"]
    ) * 100.0

    current_top_event_types = top_value_by_country(current_df, "event_type")
    previous_top_event_types = top_value_by_country(previous_df, "event_type")
    summary_df["top_event_type"] = summary_df["country"].map(current_top_event_types)
    summary_df["top_event_type"] = summary_df["top_event_type"].fillna(summary_df["country"].map(previous_top_event_types))
    summary_df["top_event_type"] = summary_df["top_event_type"].fillna("No events")

    current_top_subcategories = top_value_by_country(current_df, "subcategory")
    previous_top_subcategories = top_value_by_country(previous_df, "subcategory")
    summary_df["top_subcategory"] = summary_df["country"].map(current_top_subcategories)
    summary_df["top_subcategory"] = summary_df["top_subcategory"].fillna(summary_df["country"].map(previous_top_subcategories))
    summary_df["top_subcategory"] = summary_df["top_subcategory"].fillna("No events")

    current_top_sources = top_value_by_country(current_df, "source")
    previous_top_sources = top_value_by_country(previous_df, "source")
    summary_df["top_source"] = summary_df["country"].map(current_top_sources)
    summary_df["top_source"] = summary_df["top_source"].fillna(summary_df["country"].map(previous_top_sources))
    summary_df["top_source"] = summary_df["top_source"].fillna("Unknown")

    summary_df["significance"] = "Low"
    summary_df.loc[
        (summary_df["current_count"] >= 10) & (summary_df["pct_change"].abs() >= 10),
        "significance"
    ] = "Medium"
    summary_df.loc[
        (summary_df["current_count"] >= 20) & (summary_df["pct_change"].abs() >= 25),
        "significance"
    ] = "High"

    summary_df = summary_df.sort_values(
        ["current_count", "absolute_change", "country"],
        ascending=[False, False, True],
    ).reset_index(drop=True)

    return summary_df, current_df, previous_df


def describe_scope(selected_event_types: list[str], all_event_types: list[str]) -> str:
    selected = sorted([x for x in selected_event_types if x])
    all_types = sorted([x for x in all_event_types if x])

    if not selected or selected == all_types:
        return "overall tracked activity"

    if len(selected) == 1:
        mapping = {
            "launch": "launch activity",
            "military_flight": "military flight activity",
            "satellite": "satellite activity",
            "emergency_flight": "emergency flight activity",
        }
        return mapping.get(selected[0], f"{selected[0].replace('_', ' ')} activity")

    readable = [x.replace("_", " ") for x in selected]
    return f"blended {' + '.join(readable)} activity"


def describe_driver_mix(country: str, current_df: pd.DataFrame) -> str:
    country_df = current_df[current_df["country"] == country].copy()
    if country_df.empty:
        return "mixed activity"

    mix = (
        country_df.groupby("event_type")
        .size()
        .reset_index(name="count")
        .sort_values(["count", "event_type"], ascending=[False, True])
    )

    top_types = mix["event_type"].head(2).tolist()
    top_types = [t.replace("_", " ") for t in top_types if t]

    if not top_types:
        return "mixed activity"
    if len(top_types) == 1:
        return f"{top_types[0]} activity"
    return f"{top_types[0]} and {top_types[1]} activity"


def build_narrative_insights(
    summary_df: pd.DataFrame,
    current_df: pd.DataFrame,
    selected_event_types: list[str],
    all_event_types: list[str],
) -> list[str]:
    scope_text = describe_scope(selected_event_types, all_event_types)

    if summary_df.empty or int(summary_df["current_count"].sum()) == 0:
        return [f"No current-month {scope_text} matches the selected filters yet, so no country-level movement stands out."]

    insights: list[str] = []
    current_positive = summary_df[summary_df["current_count"] > 0].copy()

    most_active = current_positive.sort_values(["current_count", "country"], ascending=[False, True]).iloc[0]
    most_active_driver = describe_driver_mix(most_active["country"], current_df)
    insights.append(
        f"{most_active['country']} recorded the highest {scope_text} this month with "
        f"{int(most_active['current_count'])} events, driven mainly by {most_active_driver}."
    )

    biggest_increase_df = summary_df[summary_df["absolute_change"] > 0].sort_values(
        ["absolute_change", "pct_change", "current_count", "country"],
        ascending=[False, False, False, True],
    )
    if not biggest_increase_df.empty:
        biggest_increase = biggest_increase_df.iloc[0]
        biggest_increase_driver = describe_driver_mix(biggest_increase["country"], current_df)
        insights.append(
            f"{biggest_increase['country']} shows the strongest month-on-month increase in {scope_text}, up "
            f"{int(biggest_increase['absolute_change'])} events "
            f"({float(biggest_increase['pct_change']):+.1f}%), led by {biggest_increase_driver}."
        )

    biggest_decrease_df = summary_df[summary_df["absolute_change"] < 0].sort_values(
        ["absolute_change", "pct_change", "country"],
        ascending=[True, True, True],
    )
    if not biggest_decrease_df.empty:
        biggest_decrease = biggest_decrease_df.iloc[0]
        insights.append(
            f"{biggest_decrease['country']} records the sharpest decline in {scope_text}, down "
            f"{abs(int(biggest_decrease['absolute_change']))} events "
            f"({float(biggest_decrease['pct_change']):+.1f}%) compared with last month."
        )

    high_sensitive_df = current_positive[current_positive["sensitive_share"] >= 50].sort_values(
        ["sensitive_share", "sensitive_count", "country"],
        ascending=[False, False, True],
    )
    if not high_sensitive_df.empty:
        sensitive_leader = high_sensitive_df.iloc[0]
        insights.append(
            f"{sensitive_leader['country']} has the highest sensitive-event concentration in the current {scope_text} view, with "
            f"{sensitive_leader['sensitive_share']:.0f}% of its logged activity marked sensitive."
        )

    top_source_df = current_positive.sort_values(["current_count", "country"], ascending=[False, True])
    if not top_source_df.empty:
        source_leader = top_source_df.iloc[0]
        insights.append(
            f"The dominant source feeding current activity for {source_leader['country']} is "
            f"{source_leader['top_source']}."
        )

    high_significance_count = int((summary_df["significance"] == "High").sum())
    if high_significance_count > 0:
        highlighted = ", ".join(summary_df[summary_df["significance"] == "High"]["country"].head(3).tolist())
        insights.append(
            f"{high_significance_count} countries currently rate as high significance in this view, with {highlighted} standing out most clearly."
        )
    else:
        medium_significance_count = int((summary_df["significance"] == "Medium").sum())
        insights.append(
            f"No countries currently meet the high-significance threshold. "
            f"{medium_significance_count} countries sit in the medium-significance band."
        )

    return insights[:6]


def format_summary_table(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty:
        return summary_df

    display_df = summary_df.copy()
    display_df["pct_change"] = display_df["pct_change"].map(lambda value: f"{value:+.1f}%")
    display_df["sensitive_share"] = display_df["sensitive_share"].map(lambda value: f"{value:.1f}%")
    display_df = display_df.rename(
        columns={
            "country": "Country",
            "current_count": "Current Month",
            "previous_count": "Previous Month",
            "absolute_change": "Absolute Change",
            "pct_change": "Percent Change",
            "sensitive_count": "Sensitive Count",
            "sensitive_share": "Sensitive Share",
            "top_event_type": "Top Event Type",
            "top_subcategory": "Top Activity Type",
            "top_source": "Top Source",
            "significance": "Significance",
        }
    )
    return display_df


def format_movers_table(summary_df: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    if summary_df.empty:
        return summary_df

    movers_df = summary_df.copy()
    movers_df["movement_size"] = movers_df["absolute_change"].abs()
    movers_df = movers_df.sort_values(
        ["movement_size", "absolute_change", "current_count", "country"],
        ascending=[False, False, False, True],
    ).head(limit)
    movers_df = movers_df.drop(columns=["movement_size"])
    return format_summary_table(movers_df)


# ----------------------------
# PAGE
# ----------------------------

inject_styles()

st.markdown(
    """
    <div class="hero-card">
        <div class="hero-kicker">COUNTRY-LEVEL ANALYST VIEW</div>
        <h1 class="hero-title">Strategic Insights</h1>
        <p class="hero-copy">
            Blend live launch activity and live military-flight activity into one analyst view by default,
            then narrow the picture with filters whenever you want.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    events_df, loaded_sources = get_blended_events()
    data_error = None
except Exception as error:
    events_df = pd.DataFrame()
    loaded_sources = []
    data_error = str(error)

if data_error:
    st.error(f"Could not load live strategic data: {data_error}")
    st.stop()

all_event_types = sorted(
    [event_type for event_type in events_df["event_type"].dropna().unique().tolist() if str(event_type).strip()]
)

with st.sidebar:
    st.markdown("### Insight Filters")
    selected_event_types = st.multiselect(
        "Event types",
        options=all_event_types,
        default=all_event_types,
        help="Leave all selected for the blended view, or narrow the analysis to specific event types.",
    )
    sensitive_only = st.toggle(
        "Sensitive only",
        value=False,
        help="Only include events marked as sensitive.",
    )

if all_event_types and not selected_event_types:
    filtered_events_df = events_df.iloc[0:0].copy()
else:
    filtered_events_df = apply_filters(events_df, selected_event_types, sensitive_only)

now_utc = pd.Timestamp.now(tz="UTC")
previous_month_start, current_month_start, next_month_start = month_windows(now_utc)

summary_df, current_month_df, previous_month_df = calculate_country_summary(filtered_events_df, now_utc)
insights = build_narrative_insights(summary_df, current_month_df, selected_event_types, all_event_types)
scope_text = describe_scope(selected_event_types, all_event_types)

st.caption(
    f"Loaded sources: {', '.join(loaded_sources)} | View scope: {scope_text} | "
    f"Current month window: {current_month_start.strftime('%d %b %Y')} to {next_month_start.strftime('%d %b %Y')} UTC | "
    f"Previous month window: {previous_month_start.strftime('%d %b %Y')} to {current_month_start.strftime('%d %b %Y')} UTC"
)

metrics_col_1, metrics_col_2, metrics_col_3, metrics_col_4 = st.columns(4)

current_total = int(summary_df["current_count"].sum()) if not summary_df.empty else 0
previous_total = int(summary_df["previous_count"].sum()) if not summary_df.empty else 0
active_countries = int((summary_df["current_count"] > 0).sum()) if not summary_df.empty else 0
high_significance_total = int((summary_df["significance"] == "High").sum()) if not summary_df.empty else 0

largest_mover_label = "None"
largest_mover_delta = "No movement"
if not summary_df.empty:
    movers_base = summary_df[summary_df["absolute_change"] != 0].copy()
    if not movers_base.empty:
        largest_mover = movers_base.assign(movement_size=movers_base["absolute_change"].abs()).sort_values(
            ["movement_size", "absolute_change", "country"],
            ascending=[False, False, True],
        ).iloc[0]
        largest_mover_label = str(largest_mover["country"])
        largest_mover_delta = f"{int(largest_mover['absolute_change']):+d} events"

with metrics_col_1:
    st.metric("Current Month Events", f"{current_total:,}", delta=f"{current_total - previous_total:+,} vs prev month")

with metrics_col_2:
    st.metric("Active Countries", f"{active_countries:,}", delta=f"{len(summary_df):,} tracked in comparison set")

with metrics_col_3:
    st.metric("High Significance", f"{high_significance_total:,}", delta="Threshold-based country watch")

with metrics_col_4:
    st.metric("Largest Mover", largest_mover_label, delta=largest_mover_delta)

st.markdown(
    """
    <div class="panel-card">
        <div class="panel-title">Analyst Insights</div>
        <div class="panel-copy">
            Narrative takeaways generated directly from the live blended event stream and adapted automatically to the selected filter scope.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

for insight in insights:
    st.markdown(f"- {insight}")

left_col, right_col = st.columns([1.65, 1], gap="large")

with left_col:
    st.markdown(
        """
        <div class="panel-card">
            <div class="panel-title">Country Summary</div>
            <div class="panel-copy">
                Country-level totals, movement, sensitivity, dominant event type, dominant activity type, dominant source, and significance.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if summary_df.empty:
        st.info("No country summary is available for the current filters and month windows.")
    else:
        st.dataframe(format_summary_table(summary_df), use_container_width=True, hide_index=True)

with right_col:
    st.markdown(
        """
        <div class="panel-card">
            <div class="panel-title">Top Countries This Month</div>
            <div class="panel-copy">
                Current-month event volume by country under the active filter scope.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if summary_df.empty or int(summary_df["current_count"].sum()) == 0:
        st.info("No current-month event volume is available to chart.")
    else:
        chart_df = summary_df[summary_df["current_count"] > 0].head(10)[["country", "current_count"]].copy()
        chart_df = chart_df.rename(columns={"country": "Country", "current_count": "Current Month"})
        st.bar_chart(chart_df.set_index("Country"))

st.markdown(
    """
    <div class="panel-card">
        <div class="panel-title">Sensitive vs Non-Sensitive Activity</div>
        <div class="panel-copy">
            Compare how much of each country's current-month activity is marked sensitive versus routine.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if summary_df.empty or int(summary_df["current_count"].sum()) == 0:
    st.info("No current-month sensitivity split is available.")
else:
    sensitivity_chart_df = summary_df[summary_df["current_count"] > 0][["country", "sensitive_count", "current_count"]].copy()
    sensitivity_chart_df["non_sensitive_count"] = sensitivity_chart_df["current_count"] - sensitivity_chart_df["sensitive_count"]
    sensitivity_chart_df = sensitivity_chart_df[["country", "sensitive_count", "non_sensitive_count"]].set_index("country")
    st.bar_chart(sensitivity_chart_df)

st.markdown(
    """
    <div class="panel-card">
        <div class="panel-title">Top Sources This Month</div>
        <div class="panel-copy">
            Which feeds or providers are contributing the most current-month activity.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if current_month_df.empty:
    st.info("No current-month source mix is available.")
else:
    source_chart_df = (
        current_month_df.groupby("source")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .head(10)
        .set_index("source")
    )
    st.bar_chart(source_chart_df)

st.markdown(
    """
    <div class="panel-card">
        <div class="panel-title">Event-Type Mix This Month</div>
        <div class="panel-copy">
            See how the current-month activity picture breaks down across launches and military flights.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if current_month_df.empty:
    st.info("No current-month event-type mix is available.")
else:
    mix_chart_df = (
        current_month_df.groupby("event_type")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .set_index("event_type")
    )
    st.bar_chart(mix_chart_df)

st.markdown(
    """
    <div class="panel-card">
        <div class="panel-title">Movers</div>
        <div class="panel-copy">
            Countries with the largest absolute month-on-month movement under the current filters.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if summary_df.empty:
    st.info("No movers are available because there are no country comparisons yet.")
else:
    st.dataframe(format_movers_table(summary_df), use_container_width=True, hide_index=True)