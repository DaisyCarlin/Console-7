from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Strategic Insights", layout="wide")

EVENTS_FILE = Path("data/events.csv")


def load_events():
    if not EVENTS_FILE.exists():
        return pd.DataFrame(
            columns=[
                "event_id",
                "timestamp",
                "country",
                "event_type",
                "subcategory",
                "source",
                "sensitive",
            ]
        )

    df = pd.read_csv(EVENTS_FILE)

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

    if "sensitive" in df.columns:
        df["sensitive"] = df["sensitive"].astype(str).str.lower().isin(["true", "1", "yes"])

    return df


def get_period_data(df):
    now = pd.Timestamp.utcnow()
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_month_start = (current_month_start - pd.DateOffset(months=1)).replace(day=1)

    current_df = df[df["timestamp"] >= current_month_start].copy()
    previous_df = df[
        (df["timestamp"] >= previous_month_start) &
        (df["timestamp"] < current_month_start)
    ].copy()

    return current_df, previous_df, current_month_start, previous_month_start


def calculate_pct_change(current, previous):
    if previous == 0 and current > 0:
        return 100.0
    if previous == 0:
        return 0.0
    return ((current - previous) / previous) * 100


def build_country_summary(current_df, previous_df):
    current_counts = current_df.groupby("country").size().reset_index(name="current_count")
    previous_counts = previous_df.groupby("country").size().reset_index(name="previous_count")

    summary = current_counts.merge(previous_counts, on="country", how="outer").fillna(0)

    summary["current_count"] = summary["current_count"].astype(int)
    summary["previous_count"] = summary["previous_count"].astype(int)
    summary["absolute_change"] = summary["current_count"] - summary["previous_count"]
    summary["pct_change"] = summary.apply(
        lambda row: calculate_pct_change(row["current_count"], row["previous_count"]),
        axis=1,
    )

    if not current_df.empty:
        top_type = (
            current_df.groupby(["country", "event_type"])
            .size()
            .reset_index(name="count")
            .sort_values(["country", "count"], ascending=[True, False])
            .drop_duplicates("country")
            .rename(columns={"event_type": "top_event_type"})
            [["country", "top_event_type"]]
        )
        summary = summary.merge(top_type, on="country", how="left")
    else:
        summary["top_event_type"] = None

    summary["top_event_type"] = summary["top_event_type"].fillna("None")

    return summary


def significance_label(row):
    current = row["current_count"]
    pct = row["pct_change"]

    if current >= 20 and abs(pct) >= 25:
        return "High"
    if current >= 10 and abs(pct) >= 10:
        return "Medium"
    return "Low"


def generate_insights(summary_df):
    if summary_df.empty:
        return ["No strategic insights available yet. Add tracked events to events.csv first."]

    insights = []

    top_volume = summary_df.sort_values("current_count", ascending=False).iloc[0]
    top_riser = summary_df.sort_values("pct_change", ascending=False).iloc[0]
    top_faller = summary_df.sort_values("pct_change", ascending=True).iloc[0]

    insights.append(
        f"{top_volume['country']} was the most active country this month with {int(top_volume['current_count'])} tracked events."
    )

    if top_riser["current_count"] > 0:
        insights.append(
            f"{top_riser['country']} recorded {top_riser['pct_change']:.0f}% more activity than last month, driven mainly by {top_riser['top_event_type']} events."
        )

    if top_faller["previous_count"] > 0:
        insights.append(
            f"{top_faller['country']} showed the sharpest decline, down {abs(top_faller['pct_change']):.0f}% compared with last month."
        )

    return insights[:5]


st.title("Strategic Insights")
st.caption("Country-level comparison of tracked activity across your saved Console 7 events.")

df = load_events()

if df.empty:
    st.warning("No events have been logged yet. Start by saving events from your flight, launch, or satellite pages.")
    st.stop()

event_types = sorted(df["event_type"].dropna().unique()) if "event_type" in df.columns else []
selected_event_types = st.multiselect(
    "Filter by event type",
    options=event_types,
    default=event_types,
)

sensitive_only = st.toggle("Sensitive events only", value=False)

filtered_df = df.copy()

if selected_event_types:
    filtered_df = filtered_df[filtered_df["event_type"].isin(selected_event_types)]

if sensitive_only and "sensitive" in filtered_df.columns:
    filtered_df = filtered_df[filtered_df["sensitive"] == True]

current_df, previous_df, current_start, previous_start = get_period_data(filtered_df)
summary = build_country_summary(current_df, previous_df)

if summary.empty:
    st.info("No country comparison data is available for the current filters.")
    st.stop()

summary["significance"] = summary.apply(significance_label, axis=1)

most_active = summary.sort_values("current_count", ascending=False).iloc[0]
largest_increase = summary.sort_values("pct_change", ascending=False).iloc[0]
largest_decrease = summary.sort_values("pct_change", ascending=True).iloc[0]
total_events = int(current_df.shape[0])

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Most Active Country", most_active["country"], f"{int(most_active['current_count'])} events")

with col2:
    st.metric("Largest Increase", largest_increase["country"], f"{largest_increase['pct_change']:.0f}%")

with col3:
    st.metric("Largest Decrease", largest_decrease["country"], f"{largest_decrease['pct_change']:.0f}%")

with col4:
    st.metric("Total Events This Month", total_events)

st.markdown("## Key Insights")
for insight in generate_insights(summary):
    st.markdown(f"- {insight}")

st.markdown("## Country Activity Summary")

display_summary = summary.copy()
display_summary["pct_change"] = display_summary["pct_change"].round(1)
display_summary = display_summary.rename(
    columns={
        "country": "Country",
        "current_count": "Current Month",
        "previous_count": "Previous Month",
        "absolute_change": "Change",
        "pct_change": "% Change",
        "top_event_type": "Top Event Type",
        "significance": "Significance",
    }
)

st.dataframe(
    display_summary.sort_values("Country"),
    use_container_width=True,
    hide_index=True,
)

st.markdown("## Top Countries This Month")
chart_df = summary.sort_values("current_count", ascending=False).head(10)[["country", "current_count"]]
chart_df = chart_df.set_index("country")
st.bar_chart(chart_df)

st.markdown("## Highest Movers")
movers_df = display_summary.sort_values("% Change", ascending=False)
st.dataframe(movers_df, use_container_width=True, hide_index=True)
