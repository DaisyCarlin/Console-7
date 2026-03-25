from __future__ import annotations

import time
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Strategic Insights", layout="wide")

RECENT_LIMIT = 60
REQUEST_TIMEOUT = 45
REQUEST_RETRIES = 3
CACHE_TTL_SECONDS = 300

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


def safe_text(value):
    return "" if value is None else str(value).strip()


def fetch_json_with_retry(url: str, timeout: int = REQUEST_TIMEOUT, retries: int = REQUEST_RETRIES):
    last_error = None
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            last_error = error
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last_error


def looks_sensitive(row: pd.Series) -> bool:
    name = safe_text(row.get("name")).lower()
    mission_type = safe_text(row.get("subcategory")).lower()
    provider = safe_text(row.get("source")).lower()
    text = " ".join([name, mission_type, provider])

    if any(keyword in text for keyword in SENSITIVE_KEYWORDS):
        return True

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


def build_launch_events(raw_results) -> pd.DataFrame:
    rows = []

    for item in raw_results:
        mission = item.get("mission") or {}
        rocket = item.get("rocket") or {}
        configuration = rocket.get("configuration") or {}
        provider = item.get("launch_service_provider") or {}
        pad = item.get("pad") or {}
        location = pad.get("location") or {}

        row = {
            "event_id": f"launch_{safe_text(item.get('id') or item.get('name'))}_{safe_text(item.get('net'))}",
            "timestamp": item.get("net"),
            "country": safe_text(location.get("country_code")) or "Unknown",
            "event_type": "launch",
            "subcategory": safe_text(mission.get("type")) or "orbital_launch",
            "source": safe_text(provider.get("name")) or "Unknown",
            "name": safe_text(item.get("name")) or "Unknown launch",
            "rocket": safe_text(configuration.get("name")) or "Unknown",
            "location_name": safe_text(location.get("name")) or "Unknown",
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["sensitive"] = df.apply(looks_sensitive, axis=1)
    return df


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_recent_launch_events() -> pd.DataFrame:
    url = f"https://ll.thespacedevs.com/2.2.0/launch/previous/?limit={RECENT_LIMIT}&mode=detailed"
    raw = fetch_json_with_retry(url)["results"]
    df = build_launch_events(raw)
    if not df.empty:
        df = df.sort_values("timestamp", ascending=False)
    return df


def apply_filters(events_df: pd.DataFrame, selected_event_types: list[str], sensitive_only: bool) -> pd.DataFrame:
    filtered_df = events_df.copy()

    if selected_event_types:
        filtered_df = filtered_df[filtered_df["event_type"].isin(selected_event_types)]

    if sensitive_only and "sensitive" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["sensitive"]]

    return filtered_df.reset_index(drop=True)


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
    summary_df.loc[
        (~has_previous) & (summary_df["current_count"] > 0),
        "pct_change"
    ] = 100.0

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


def build_narrative_insights(summary_df: pd.DataFrame) -> list[str]:
    if summary_df.empty or int(summary_df["current_count"].sum()) == 0:
        return ["No current-month launch events match the selected filters yet, so no country-level movement stands out."]

    insights: list[str] = []
    current_positive = summary_df[summary_df["current_count"] > 0].copy()

    most_active = current_positive.sort_values(
        ["current_count", "country"],
        ascending=[False, True],
    ).iloc[0]
    insights.append(
        f"{most_active['country']} is the most active country this month with "
        f"{int(most_active['current_count'])} logged launch events, mainly linked to "
        f"{most_active['top_subcategory']} activity."
    )

    biggest_increase_df = summary_df[summary_df["absolute_change"] > 0].sort_values(
        ["absolute_change", "pct_change", "current_count", "country"],
        ascending=[False, False, False, True],
    )
    if not biggest_increase_df.empty:
        biggest_increase = biggest_increase_df.iloc[0]
        insights.append(
            f"{biggest_increase['country']} shows the strongest month-on-month increase, up "
            f"{int(biggest_increase['absolute_change'])} events "
            f"({float(biggest_increase['pct_change']):+.1f}%), driven mainly by "
            f"{biggest_increase['top_subcategory']} launches."
        )

    high_sensitive_df = current_positive[current_positive["sensitive_share"] >= 50].sort_values(
        ["sensitive_share", "sensitive_count", "country"],
        ascending=[False, False, True],
    )
    if not high_sensitive_df.empty:
        sensitive_leader = high_sensitive_df.iloc[0]
        insights.append(
            f"{sensitive_leader['country']} has the highest sensitive-launch concentration this month, with "
            f"{sensitive_leader['sensitive_share']:.0f}% of its logged activity marked sensitive."
        )

    top_source_df = current_positive.sort_values(
        ["current_count", "country"],
        ascending=[False, True],
    )
    if not top_source_df.empty:
        source_leader = top_source_df.iloc[0]
        insights.append(
            f"The dominant launch provider feeding current activity for {source_leader['country']} is "
            f"{source_leader['top_source']}."
        )

    return insights[:5]


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
            "top_subcategory": "Top Activity Type",
            "top_source": "Top Source",
            "significance": "Significance",
        }
    )
    return display_df


inject_styles()

st.markdown(
    """
    <div class="hero-card">
        <div class="hero-kicker">COUNTRY-LEVEL ANALYST VIEW</div>
        <h1 class="hero-title">Strategic Insights</h1>
        <p class="hero-copy">
            Convert live launch activity into month-on-month country movements, sensitive-activity concentration,
            provider mix, and analyst-style insights.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    events_df = get_recent_launch_events()
    data_error = None
except Exception as error:
    events_df = pd.DataFrame()
    data_error = str(error)

st.write("LIVE ROWS LOADED:", len(events_df))

event_type_options = sorted(
    [event_type for event_type in events_df["event_type"].dropna().unique().tolist()]
) if not events_df.empty else []

with st.sidebar:
    st.markdown("### Insight Filters")
    selected_event_types = st.multiselect(
        "Event types",
        options=event_type_options,
        default=event_type_options,
    )
    sensitive_only = st.toggle("Sensitive only", value=False)

if data_error:
    st.error(f"Could not load live launch data: {data_error}")
    st.stop()

now_utc = pd.Timestamp.now(tz="UTC")
previous_month_start, current_month_start, next_month_start = month_windows(now_utc)

filtered_events_df = apply_filters(events_df, selected_event_types, sensitive_only)
summary_df, current_month_df, previous_month_df = calculate_country_summary(filtered_events_df, now_utc)
insights = build_narrative_insights(summary_df)

st.caption(
    f"Current month window: {current_month_start.strftime('%d %b %Y')} to "
    f"{next_month_start.strftime('%d %b %Y')} UTC | Previous month window: "
    f"{previous_month_start.strftime('%d %b %Y')} to {current_month_start.strftime('%d %b %Y')} UTC"
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
            Narrative takeaways generated directly from the month-on-month comparison, provider mix, and sensitivity profile.
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
                Country-level launch totals, movement, sensitivity, dominant activity type, dominant source, and significance score.
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
                Current-month launch volume by country.
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
            Compare how much of each country's current-month launch activity is marked sensitive versus routine.
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
            Which launch providers are contributing the most current-month activity.
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
