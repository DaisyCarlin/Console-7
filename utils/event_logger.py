from pathlib import Path
import pandas as pd

EVENTS_FILE = Path("data/events.csv")


def ensure_events_file():
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not EVENTS_FILE.exists():
        empty_df = pd.DataFrame(
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
        empty_df.to_csv(EVENTS_FILE, index=False)


def log_event(event: dict):
    ensure_events_file()

    new_df = pd.DataFrame([event])

    if EVENTS_FILE.exists():
        old_df = pd.read_csv(EVENTS_FILE)
    else:
        old_df = pd.DataFrame()

    if not old_df.empty and "event_id" in old_df.columns:
        if event["event_id"] in old_df["event_id"].astype(str).values:
            return

    combined = pd.concat([old_df, new_df], ignore_index=True)
    combined.to_csv(EVENTS_FILE, index=False)
