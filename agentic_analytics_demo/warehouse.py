from __future__ import annotations

import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path


COUNTRIES = [
    ("Sweden", "sv"),
    ("Germany", "de"),
    ("United States", "en"),
    ("China", "zh"),
    ("Japan", "ja"),
    ("Brazil", "pt"),
    ("France", "fr"),
    ("United Kingdom", "en"),
    ("India", "en"),
    ("Netherlands", "nl"),
]
CHANNELS = ["organic", "paid_search", "partner", "social", "referral"]
TIERS = ["free", "pro", "enterprise"]
DEVICES = ["mobile", "desktop", "tablet"]
BROWSERS = ["Chrome", "Safari", "Edge", "Firefox"]
PAGES = ["/home", "/pricing", "/docs", "/dashboard", "/camera-search", "/alerts", "/reports"]
FEATURES = ["search", "live_view", "export", "alert_rules", "heatmap", "report_builder"]
FUNNEL_STEPS = ["view_product", "start_trial", "checkout", "paid"]
EXPERIMENTS = [("onboarding_flow", ["control", "guided"]), ("pricing_page", ["control", "compact", "detailed"])]


def ensure_demo_warehouse(db_path: Path, seed: int = 42) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists() and _has_data(db_path):
        return
    create_demo_warehouse(db_path, seed=seed)


def create_demo_warehouse(db_path: Path, seed: int = 42) -> None:
    rng = random.Random(seed)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        _create_schema(conn)
        _populate(conn, rng)
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


def _has_data(db_path: Path) -> bool:
    try:
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        return count > 0
    except sqlite3.Error:
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY,
            country TEXT NOT NULL,
            language TEXT NOT NULL,
            signup_date TEXT NOT NULL,
            acquisition_channel TEXT NOT NULL,
            account_tier TEXT NOT NULL
        );

        CREATE TABLE sessions (
            session_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            device_type TEXT NOT NULL,
            browser TEXT NOT NULL,
            session_country TEXT NOT NULL,
            started_at TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );

        CREATE TABLE events (
            event_id INTEGER PRIMARY KEY,
            session_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            page TEXT NOT NULL,
            feature TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        );

        CREATE TABLE conversions (
            conversion_id INTEGER PRIMARY KEY,
            session_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            funnel_step TEXT NOT NULL,
            converted INTEGER NOT NULL,
            revenue REAL NOT NULL,
            occurred_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(session_id),
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );

        CREATE TABLE experiments (
            experiment_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            experiment_name TEXT NOT NULL,
            variant TEXT NOT NULL,
            exposed_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );

        CREATE INDEX idx_users_country ON users(country);
        CREATE INDEX idx_sessions_user ON sessions(user_id);
        CREATE INDEX idx_events_session ON events(session_id);
        CREATE INDEX idx_conversions_user ON conversions(user_id);
        CREATE INDEX idx_experiments_user ON experiments(user_id);
        """
    )


def _populate(conn: sqlite3.Connection, rng: random.Random) -> None:
    base = date(2026, 1, 1)
    user_count = 900
    session_id = 1
    event_id = 1
    conversion_id = 1
    experiment_id = 1

    for user_id in range(1, user_count + 1):
        country, language = rng.choice(COUNTRIES)
        signup_date = base + timedelta(days=rng.randint(0, 135))
        tier = rng.choices(TIERS, weights=[0.66, 0.26, 0.08])[0]
        channel = rng.choice(CHANNELS)
        conn.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, country, language, signup_date.isoformat(), channel, tier),
        )

        for experiment_name, variants in EXPERIMENTS:
            if rng.random() < 0.72:
                exposed_at = signup_date + timedelta(days=rng.randint(0, 28))
                conn.execute(
                    "INSERT INTO experiments VALUES (?, ?, ?, ?, ?)",
                    (experiment_id, user_id, experiment_name, rng.choice(variants), exposed_at.isoformat()),
                )
                experiment_id += 1

        for _ in range(rng.randint(2, 8)):
            started = datetime.combine(signup_date + timedelta(days=rng.randint(0, 150)), datetime.min.time())
            started += timedelta(hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
            device = rng.choices(DEVICES, weights=[0.48, 0.42, 0.10])[0]
            browser = rng.choice(BROWSERS)
            session_country = country if rng.random() < 0.92 else rng.choice(COUNTRIES)[0]
            duration = rng.randint(45, 2400)
            conn.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, user_id, device, browser, session_country, started.isoformat(), duration),
            )

            for _ in range(rng.randint(3, 9)):
                occurred = started + timedelta(seconds=rng.randint(5, duration))
                event_type = rng.choices(
                    ["page_view", "feature_use", "search", "report_export", "alert_created"],
                    weights=[0.45, 0.24, 0.16, 0.08, 0.07],
                )[0]
                conn.execute(
                    "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
                    (event_id, session_id, event_type, rng.choice(PAGES), rng.choice(FEATURES), occurred.isoformat()),
                )
                event_id += 1

            for step_index, step in enumerate(FUNNEL_STEPS):
                base_probability = [0.78, 0.45, 0.28, 0.18][step_index]
                country_bonus = 0.05 if country in {"Sweden", "Germany", "Netherlands"} else 0.0
                device_penalty = -0.03 if device == "mobile" and step in {"checkout", "paid"} else 0.0
                converted = int(rng.random() < max(0.02, base_probability + country_bonus + device_penalty))
                revenue = 0.0
                if step == "paid" and converted:
                    revenue = round(rng.choice([49, 99, 199, 499]) * rng.uniform(0.85, 1.3), 2)
                occurred = started + timedelta(minutes=step_index * rng.randint(2, 18))
                conn.execute(
                    "INSERT INTO conversions VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (conversion_id, session_id, user_id, step, converted, revenue, occurred.isoformat()),
                )
                conversion_id += 1

            session_id += 1

