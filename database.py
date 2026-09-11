"""
database.py
------------
All database access for Sahayog lives in this one file, using Python's
built-in `sqlite3` module - no external database server, no ORM "magic".
Every function here runs a plain, readable SQL statement, so a reader who
knows basic SQL can follow exactly what each function does.

Why SQLite?
- It's a single file (data/sahayog.db) - nothing to install or configure.
- It's part of the Python standard library (import sqlite3), so this
  project has zero extra dependencies just to have a real database.
- For a production deployment this would be swapped for PostgreSQL, but
  the SQL in this file would barely need to change.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "sahayog.db")


def get_connection():
    """Open a connection to the SQLite database file.

    `row_factory = sqlite3.Row` lets us access columns by name
    (row["name"]) instead of by numeric index (row[0]), which is much
    easier to read.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL CHECK(role IN ('customer', 'worker', 'admin')),
    name TEXT NOT NULL,
    phone TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS federations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    state TEXT
);

CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE REFERENCES users(id),
    skills TEXT NOT NULL,             -- comma-separated list, e.g. "electrician,technician"
    federation_id TEXT REFERENCES federations(id),
    verified INTEGER NOT NULL DEFAULT 0,
    certified INTEGER NOT NULL DEFAULT 0,
    rating REAL NOT NULL DEFAULT 0,
    rating_count INTEGER NOT NULL DEFAULT 0,
    lat REAL,
    lng REAL,
    available INTEGER NOT NULL DEFAULT 1,
    welfare_wallet REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bookings (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES users(id),
    worker_id TEXT REFERENCES workers(id),
    category TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending -> matched -> accepted -> completed
    urgent INTEGER NOT NULL DEFAULT 0,
    lat REAL,
    lng REAL,
    distance_km REAL,
    price REAL,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    booking_id TEXT NOT NULL UNIQUE REFERENCES bookings(id),
    amount REAL NOT NULL,
    method TEXT NOT NULL DEFAULT 'UPI',
    welfare_contribution REAL NOT NULL,
    federation_commission REAL NOT NULL,
    worker_payout REAL NOT NULL,
    invoice_no TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ratings (
    id TEXT PRIMARY KEY,
    booking_id TEXT NOT NULL UNIQUE REFERENCES bookings(id),
    worker_id TEXT NOT NULL REFERENCES workers(id),
    customer_id TEXT NOT NULL REFERENCES users(id),
    stars INTEGER NOT NULL CHECK(stars BETWEEN 1 AND 5),
    comment TEXT,
    created_at TEXT NOT NULL
);
"""

# The ten worker categories named explicitly in the SIH26089 problem statement.
SERVICE_CATEGORIES = [
    ("electrician", "Electrician"),
    ("plumber", "Plumber"),
    ("carpenter", "Carpenter"),
    ("painter", "Painter"),
    ("domestic_help", "Domestic Help"),
    ("caregiver", "Caregiver"),
    ("driver", "Driver"),
    ("gardener", "Gardener"),
    ("cleaner", "Cleaner"),
    ("technician", "Technician"),
]


def init_db():
    """Create all tables if they don't already exist. Safe to call every
    time the app starts - CREATE TABLE IF NOT EXISTS never wipes data."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def category_label(category_id):
    for cid, label in SERVICE_CATEGORIES:
        if cid == category_id:
            return label
    return category_id
