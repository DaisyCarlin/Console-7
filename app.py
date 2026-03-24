import streamlit as st

st.set_page_config(page_title="Signal Console", layout="wide")


def inject_styles():
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

            .hero-card {
                border: 1px solid var(--stroke);
                background: linear-gradient(145deg, rgba(10, 21, 35, 0.92), rgba(15, 31, 49, 0.86));
                border-radius: 22px;
                padding: 1.35rem 1.5rem;
                box-shadow: 0 18px 40px rgba(4, 9, 18, 0.26);
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

            .hero-copy {
                margin: 0.55rem 0 0 0;
                max-width: 60rem;
                color: var(--text-soft);
                font-size: 0.98rem;
            }

            .metric-card {
                border: 1px solid var(--stroke);
                background: linear-gradient(180deg, rgba(12, 24, 39, 0.9), rgba(14, 32, 50, 0.76));
                border-radius: 20px;
                padding: 1rem 1rem 0.95rem 1rem;
                min-height: 120px;
                box-shadow: 0 12px 28px rgba(4, 9, 18, 0.24);
            }

            .metric-label {
                font-size: 0.8rem;
                text-transform: uppercase;
                letter-spacing: 0.08rem;
                color: var(--text-soft);
                margin-bottom: 0.45rem;
            }

            .metric-value {
                font-size: 2rem;
                font-weight: 700;
                line-height: 1;
                margin-bottom: 0.35rem;
                color: var(--text-main);
            }

            .metric-detail {
                font-size: 0.92rem;
                color: var(--text-soft);
            }

            .accent-bar {
                width: 54px;
                height: 4px;
                border-radius: 999px;
                margin-bottom: 0.8rem;
            }

            .panel-card {
                border: 1px solid var(--stroke);
                background: linear-gradient(180deg, rgba(10, 23, 37, 0.9), rgba(14, 31, 49, 0.82));
                border-radius: 20px;
                padding: 1rem 1rem 0.85rem 1rem;
                box-shadow: 0 12px 28px rgba(4, 9, 18, 0.22);
                min-height: 210px;
            }

            .panel-title {
                font-size: 1rem;
                font-weight: 700;
                margin-bottom: 0.25rem;
                color: var(--text-main);
            }

            .panel-copy {
                color: var(--text-soft);
                font-size: 0.92rem;
                margin-bottom: 0.75rem;
            }

            .status-chip {
                display: inline-block;
                padding: 0.28rem 0.65rem;
                border-radius: 999px;
                font-size: 0.76rem;
                font-weight: 700;
                color: #f3fbff;
                margin-bottom: 0.75rem;
            }

            .list-line {
                color: var(--text-soft);
                font-size: 0.92rem;
                margin-bottom: 0.42rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(title, value, detail, accent):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="accent-bar" style="background:{accent};"></div>
            <div class="metric-label">{title}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-detail">{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_module_card(title, status, status_color, summary, detail_lines):
    lines_html = "".join(f'<div class="list-line">{line}</div>' for line in detail_lines)
    st.markdown(
        f"""
        <div class="panel-card">
            <div class="status-chip" style="background:{status_color};">{status}</div>
            <div class="panel-title">{title}</div>
            <div class="panel-copy">{summary}</div>
            {lines_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


inject_styles()

st.markdown(
    """
    <div class="hero-card">
        <div class="hero-kicker">OPEN-SOURCE SIGNAL PLATFORM</div>
        <h1 class="hero-title">Signal Console</h1>
        <p class="hero-copy">
            A unified monitoring console for orbital launches, flight activity, and maritime movement,
            designed to bring open-source operational signals into one clean analyst workspace.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

metric_columns = st.columns(4)
with metric_columns[0]:
    render_metric_card("Platform status", "Online", "Core monitoring console is available", "#39d98a")
with metric_columns[1]:
    render_metric_card("Launch monitor", "Live", "Professional launch watchboard is available", "#38bdf8")
with metric_columns[2]:
    render_metric_card("Flight monitor", "Live", "Flight radar dashboard is available", "#58a6ff")
with metric_columns[3]:
    render_metric_card("Marine monitor", "Live", "Regional maritime watchboard is available", "#ff9e3d")

st.markdown("")

module_columns = st.columns(3, gap="large")
with module_columns[0]:
    render_module_card(
        "Orbital Launch Monitor",
        "Operational",
        "#38bdf8",
        "Tracks upcoming launches, recent failures, and sensitive mission profiles with official-context notes.",
        [
            "Upcoming launch schedule and site mapping",
            "Recent failure tracking",
            "Publicly signaled sensitive mission watch",
        ],
    )
with module_columns[1]:
    render_module_card(
        "Flight Activity",
        "Operational",
        "#58a6ff",
        "Monitors live aircraft positions with emergency squawk decoding, military filtering, and a radar-style map.",
        [
            "Emergency and government or military traffic focus",
            "Session trails and map filtering",
            "Fast search and table-to-map flight focus",
        ],
    )
with module_columns[2]:
    render_module_card(
        "Abnormal Marine Activity",
        "Operational",
        "#ff9e3d",
        "Loads regional AIS snapshots to surface abnormal vessel signals, tanker traffic, and maritime movement patterns.",
        [
            "Regional AIS snapshot loading",
            "Abnormal status and high-speed signal checks",
            "Tanker and energy shipping view",
        ],
    )

st.markdown("")

overview_col, nav_col = st.columns([2.2, 1], gap="large")

with overview_col:
    st.markdown(
        """
        <div class="panel-card" style="min-height: 0;">
            <div class="panel-title">Platform Purpose</div>
            <div class="panel-copy">
                This console brings together aerospace, aviation, and maritime open-source signals so you can track
                patterns, incidents, disruptions, and strategic activity from one consistent workspace.
            </div>
            <div class="list-line">Launch monitoring for schedule, failure, and sensitive mission context</div>
            <div class="list-line">Flight monitoring for emergency, military, and government-linked air traffic</div>
            <div class="list-line">Marine monitoring for AIS movement signals, tanker traffic, and regional vessel snapshots</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with nav_col:
    st.markdown(
        """
        <div class="panel-card" style="min-height: 0;">
            <div class="panel-title">Navigation</div>
            <div class="panel-copy">
                Use the Streamlit sidebar to open each monitoring page and move between the platform modules.
            </div>
            <div class="list-line">Launch monitor</div>
            <div class="list-line">Flight monitor</div>
            <div class="list-line">Marine monitor</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("---")
st.caption("Signal Console is online and ready to route into the launch, flight, and marine monitoring modules.")
