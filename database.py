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
    address TEXT DEFAULT '',
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
    spoken_languages TEXT NOT NULL DEFAULT 'en,hi',
    aadhaar_last4 TEXT,
    cert_type TEXT,
    cert_id TEXT,
    peer_reference TEXT,
    tools_verified INTEGER NOT NULL DEFAULT 0,
    verification_status TEXT NOT NULL DEFAULT 'unsubmitted',
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
    completion_otp TEXT,
    escrow_status TEXT NOT NULL DEFAULT 'held',
    language TEXT NOT NULL DEFAULT 'en',
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

CREATE TABLE IF NOT EXISTS welfare_disbursals (
    id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL REFERENCES workers(id),
    grant_type TEXT NOT NULL,
    amount REAL NOT NULL,
    officer_notes TEXT,
    disbursed_at TEXT NOT NULL
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

    # Safe runtime migration for existing databases
    cursor_b = conn.execute("PRAGMA table_info(bookings)")
    b_cols = [row["name"] for row in cursor_b.fetchall()]
    if "completion_otp" not in b_cols:
        conn.execute("ALTER TABLE bookings ADD COLUMN completion_otp TEXT")
    if "escrow_status" not in b_cols:
        conn.execute("ALTER TABLE bookings ADD COLUMN escrow_status TEXT NOT NULL DEFAULT 'unpaid'")
    if "language" not in b_cols:
        conn.execute("ALTER TABLE bookings ADD COLUMN language TEXT NOT NULL DEFAULT 'en'")

    cursor_w = conn.execute("PRAGMA table_info(workers)")
    w_cols = [row["name"] for row in cursor_w.fetchall()]
    if "spoken_languages" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN spoken_languages TEXT NOT NULL DEFAULT 'en,hi'")
    if "aadhaar_last4" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN aadhaar_last4 TEXT")
    if "cert_type" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN cert_type TEXT")
    if "cert_id" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN cert_id TEXT")
    if "peer_reference" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN peer_reference TEXT")
    if "tools_verified" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN tools_verified INTEGER NOT NULL DEFAULT 0")
    if "verification_status" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN verification_status TEXT NOT NULL DEFAULT 'unsubmitted'")
    if "aadhaar_name" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN aadhaar_name TEXT")
    if "aadhaar_dob" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN aadhaar_dob TEXT")
    if "cert_level" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN cert_level TEXT")
    if "cert_issue_year" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN cert_issue_year TEXT")
    if "peer_phone" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN peer_phone TEXT")
    if "pcc_number" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN pcc_number TEXT")
    if "toolkit_items" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN toolkit_items TEXT")
    if "officer_remarks" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN officer_remarks TEXT")
    if "coop_id" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN coop_id TEXT")
    if "verified_at" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN verified_at TEXT")

    cursor_u = conn.execute("PRAGMA table_info(users)")
    u_cols = [row["name"] for row in cursor_u.fetchall()]
    if "address" not in u_cols:
        conn.execute("ALTER TABLE users ADD COLUMN address TEXT DEFAULT ''")

    # Backfill default accreditation info for existing workers
    conn.execute(
        """UPDATE workers
           SET aadhaar_last4 = '8492',
               aadhaar_name = 'Ramesh Kumar',
               aadhaar_dob = '1988-04-12',
               cert_type = 'NCCT Master Craftsman',
               cert_id = 'NCCT-HYD-2025-091',
               cert_level = 'NSQF Level 5 (Master Craftsman)',
               cert_issue_year = '2023',
               peer_reference = 'Hyderabad Labour Union #104',
               peer_phone = '9848011223',
               pcc_number = 'CCTNS-TS-2025-88129',
               toolkit_items = 'Insulated Screwdrivers (1000V), Fluke Digital Multimeter, Heavy-Duty Wire Stripper, Safety Helmet & High-Tension Gloves, Tool Bag',
               officer_remarks = 'Passed in-person federation trade audit at Hyderabad Central Guild on 15-Jan-2025. Tools and safety gear verified.',
               coop_id = 'SHY-COOP-HYD-0104',
               verified_at = '2025-01-15T11:30:00',
               tools_verified = 1, verification_status = 'verified'
           WHERE verified = 1 AND (coop_id IS NULL OR coop_id = '')"""
    )
    conn.execute(
        """UPDATE workers
           SET aadhaar_last4 = '4819',
               aadhaar_name = 'Mahesh Yadav',
               aadhaar_dob = '1993-08-22',
               cert_type = 'Skill India Digital (SID)',
               cert_id = 'SID-2026-TS-8910',
               cert_level = 'NSQF Level 4 (Certified Electrician)',
               cert_issue_year = '2024',
               peer_reference = 'Mukhiya Anand Rao (Fed #102)',
               peer_phone = '9876501234',
               pcc_number = 'CCTNS-TS-2026-44019',
               toolkit_items = 'Heavy Duty Drill, Pipe Wrench Set, Digital Multimeter, Insulated Cutters, Safety Goggles & Gloves',
               coop_id = 'SHY-COOP-HYD-04819',
               tools_verified = 1, verification_status = 'submitted'
           WHERE verified = 0 AND (coop_id IS NULL OR coop_id = '')"""
    )

    # Ensure welfare_disbursals table exists
    conn.execute(
        """CREATE TABLE IF NOT EXISTS welfare_disbursals (
            id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL REFERENCES workers(id),
            grant_type TEXT NOT NULL,
            amount REAL NOT NULL,
            officer_notes TEXT,
            disbursed_at TEXT NOT NULL
        )"""
    )
    w_cols = [r["name"] for r in conn.execute("PRAGMA table_info(workers)").fetchall()]
    if "retraining_status" not in w_cols:
        conn.execute("ALTER TABLE workers ADD COLUMN retraining_status TEXT DEFAULT 'none'")

    # Seed sample welfare disbursal if empty
    disbursal_count = conn.execute("SELECT COUNT(*) as c FROM welfare_disbursals").fetchone()["c"]
    if disbursal_count == 0:
        sample_w = conn.execute("SELECT id FROM workers WHERE verified = 1 LIMIT 1").fetchone()
        if sample_w:
            conn.execute(
                """INSERT INTO welfare_disbursals (id, worker_id, grant_type, amount, officer_notes, disbursed_at)
                   VALUES ('wgrant-1001', ?, 'Emergency Medical Assistance', 2500.0, 'Approved for hospitalization bill co-payment under Sahayog Cooperative Welfare bylaws.', '2026-08-20T14:30:00')""",
                (sample_w["id"],)
            )

    conn.commit()
    conn.close()


def category_label(category_id):
    for cid, label in SERVICE_CATEGORIES:
        if cid == category_id:
            return label
    return category_id
