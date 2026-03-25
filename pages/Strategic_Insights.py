from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Strategic Insights", layout="wide")

EVENTS_CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "events.csv"

st.title("Strategic Insights")
st.write("Page loaded successfully")
st.write("Looking for file at:", str(EVENTS_CSV_PATH))
st.write("File exists:", EVENTS_CSV_PATH.exists())

if EVENTS_CSV_PATH.exists():
    try:
        df = pd.read_csv(EVENTS_CSV_PATH)
        st.write("Rows found:", len(df))
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"Could not read CSV: {e}")
else:
    st.warning("events.csv does not exist")
