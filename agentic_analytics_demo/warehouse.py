from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


REQUIRED_DATASET_FILES = [
    "events.csv",
    "item_properties_part1.csv",
    "item_properties_part2.csv",
    "category_tree.csv",
]


def ensure_demo_warehouse(db_path: Path, dataset_dir: Path | None = None) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists() and _has_retailrocket_data(db_path):
        return
    if dataset_dir and _has_raw_retailrocket_files(dataset_dir):
        create_retailrocket_warehouse(db_path, dataset_dir)
    else:
        create_sample_retailrocket_warehouse(db_path)


def create_retailrocket_warehouse(db_path: Path, dataset_dir: Path, chunksize: int = 200_000) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        _create_retailrocket_schema(conn)
        _import_events(conn, dataset_dir / "events.csv", chunksize)
        _import_category_tree(conn, dataset_dir / "category_tree.csv")
        _import_item_properties(conn, dataset_dir, chunksize)
        _create_latest_property_tables(conn)
        _create_indexes(conn)
        _write_metadata(conn, dataset_dir)
        conn.commit()
    finally:
        conn.close()


def create_sample_retailrocket_warehouse(db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        _create_retailrocket_schema(conn)
        events = pd.DataFrame(
            [
                [1433221332117, 257597, "view", 355908, None],
                [1433224214164, 992329, "view", 248676, None],
                [1433225000000, 257597, "addtocart", 355908, None],
                [1433226000000, 257597, "transaction", 355908, 4000],
                [1433311332117, 300001, "view", 248676, None],
                [1433312332117, 300002, "view", 111111, None],
                [1433313332117, 300002, "addtocart", 111111, None],
            ],
            columns=["timestamp", "visitorid", "event", "itemid", "transactionid"],
        )
        _append_events(conn, events)
        pd.DataFrame([[100, None], [200, 100]], columns=["categoryid", "parentid"]).to_sql(
            "category_tree", conn, if_exists="append", index=False
        )
        category_history = pd.DataFrame(
            [
                [1433041200000, 355908, 200],
                [1433041200000, 248676, 100],
                [1433041200000, 111111, 200],
            ],
            columns=["timestamp", "itemid", "categoryid"],
        )
        category_history["event_time"] = _to_event_time(category_history["timestamp"])
        category_history.to_sql("item_category_history", conn, if_exists="append", index=False)
        availability = pd.DataFrame(
            [[1433041200000, 355908, 1], [1433041200000, 248676, 1], [1433041200000, 111111, 1]],
            columns=["timestamp", "itemid", "available"],
        )
        availability["event_time"] = _to_event_time(availability["timestamp"])
        availability.to_sql("item_availability_history", conn, if_exists="append", index=False)
        _create_latest_property_tables(conn)
        _create_indexes(conn)
        conn.execute(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            ("dataset", "retailrocket_sample"),
        )
        conn.commit()
    finally:
        conn.close()


def get_schema(db_path: Path) -> dict[str, list[str]]:
    conn = sqlite3.connect(db_path)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        return {
            table: [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            for table in tables
        }
    finally:
        conn.close()


def _has_raw_retailrocket_files(dataset_dir: Path) -> bool:
    return all((dataset_dir / file_name).exists() for file_name in REQUIRED_DATASET_FILES)


def _has_retailrocket_data(db_path: Path) -> bool:
    try:
        conn = sqlite3.connect(db_path)
        event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        table_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        return event_count > 0 and {"events", "item_latest_category", "category_tree"} <= table_names
    except sqlite3.Error:
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _create_retailrocket_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE events (
            timestamp INTEGER NOT NULL,
            event_time TEXT NOT NULL,
            visitorid INTEGER NOT NULL,
            event TEXT NOT NULL,
            itemid INTEGER NOT NULL,
            transactionid INTEGER
        );

        CREATE TABLE category_tree (
            categoryid INTEGER PRIMARY KEY,
            parentid INTEGER
        );

        CREATE TABLE item_category_history (
            timestamp INTEGER NOT NULL,
            event_time TEXT NOT NULL,
            itemid INTEGER NOT NULL,
            categoryid INTEGER
        );

        CREATE TABLE item_availability_history (
            timestamp INTEGER NOT NULL,
            event_time TEXT NOT NULL,
            itemid INTEGER NOT NULL,
            available INTEGER
        );

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )


def _import_events(conn: sqlite3.Connection, events_path: Path, chunksize: int) -> None:
    for chunk in pd.read_csv(events_path, chunksize=chunksize):
        _append_events(conn, chunk)


def _append_events(conn: sqlite3.Connection, chunk: pd.DataFrame) -> None:
    frame = chunk.copy()
    frame["event_time"] = _to_event_time(frame["timestamp"])
    frame["transactionid"] = pd.to_numeric(frame["transactionid"], errors="coerce").astype("Int64")
    frame = frame[["timestamp", "event_time", "visitorid", "event", "itemid", "transactionid"]]
    frame.to_sql("events", conn, if_exists="append", index=False)


def _import_category_tree(conn: sqlite3.Connection, path: Path) -> None:
    category_tree = pd.read_csv(path)
    category_tree["parentid"] = pd.to_numeric(category_tree["parentid"], errors="coerce").astype("Int64")
    category_tree.to_sql("category_tree", conn, if_exists="append", index=False)


def _import_item_properties(conn: sqlite3.Connection, dataset_dir: Path, chunksize: int) -> None:
    for file_name in ["item_properties_part1.csv", "item_properties_part2.csv"]:
        path = dataset_dir / file_name
        for chunk in pd.read_csv(path, chunksize=chunksize):
            property_name = chunk["property"].astype(str)
            category_rows = chunk[property_name == "categoryid"].copy()
            if not category_rows.empty:
                category_rows["categoryid"] = pd.to_numeric(category_rows["value"], errors="coerce").astype("Int64")
                category_rows["event_time"] = _to_event_time(category_rows["timestamp"])
                category_rows[["timestamp", "event_time", "itemid", "categoryid"]].dropna(
                    subset=["categoryid"]
                ).to_sql("item_category_history", conn, if_exists="append", index=False)

            available_rows = chunk[property_name == "available"].copy()
            if not available_rows.empty:
                available_rows["available"] = pd.to_numeric(available_rows["value"], errors="coerce").astype("Int64")
                available_rows["event_time"] = _to_event_time(available_rows["timestamp"])
                available_rows[["timestamp", "event_time", "itemid", "available"]].dropna(
                    subset=["available"]
                ).to_sql("item_availability_history", conn, if_exists="append", index=False)


def _create_latest_property_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE item_latest_category AS
        SELECT itemid, categoryid, event_time AS observed_at
        FROM (
            SELECT
                itemid,
                categoryid,
                event_time,
                ROW_NUMBER() OVER (PARTITION BY itemid ORDER BY timestamp DESC) AS rn
            FROM item_category_history
            WHERE categoryid IS NOT NULL
        )
        WHERE rn = 1;

        CREATE TABLE item_latest_availability AS
        SELECT itemid, available, event_time AS observed_at
        FROM (
            SELECT
                itemid,
                available,
                event_time,
                ROW_NUMBER() OVER (PARTITION BY itemid ORDER BY timestamp DESC) AS rn
            FROM item_availability_history
            WHERE available IS NOT NULL
        )
        WHERE rn = 1;
        """
    )


def _create_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX idx_events_time ON events(event_time);
        CREATE INDEX idx_events_event ON events(event);
        CREATE INDEX idx_events_item ON events(itemid);
        CREATE INDEX idx_events_visitor ON events(visitorid);
        CREATE INDEX idx_latest_category_item ON item_latest_category(itemid);
        CREATE INDEX idx_latest_category_category ON item_latest_category(categoryid);
        CREATE INDEX idx_latest_availability_item ON item_latest_availability(itemid);
        """
    )


def _write_metadata(conn: sqlite3.Connection, dataset_dir: Path) -> None:
    min_time, max_time, event_count = conn.execute(
        "SELECT MIN(event_time), MAX(event_time), COUNT(*) FROM events"
    ).fetchone()
    metadata = {
        "dataset": "retailrocket",
        "dataset_dir": str(dataset_dir),
        "event_time_min": str(min_time),
        "event_time_max": str(max_time),
        "event_count": str(event_count),
    }
    conn.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items())


def _to_event_time(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, unit="ms", utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
