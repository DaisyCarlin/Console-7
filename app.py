import streamlit as st

st.set_page_config(page_title="Signal Console", layout="wide")

st.title("Signal Console")
st.caption("Open-source activity dashboard for launches, flights, and marine monitoring.")

st.markdown("## Available Modules")
st.write("- Orbital Launch Monitor")
st.write("- Flight Activity")
st.write("- Marine Activity (coming soon)")

st.markdown("## What this platform does")
st.write(
    "This dashboard brings together open-source signals from aerospace, aviation, and maritime activity "
    "to help track patterns, incidents, and strategic developments."
)

st.markdown("## Current Status")
st.success("Platform online")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Launch Module", "Live")

with col2:
    st.metric("Flight Module", "Coming next")

with col3:
    st.metric("Marine Module", "Coming soon")

st.markdown("## Navigation")
st.write("Use the sidebar to open each monitoring page.")
