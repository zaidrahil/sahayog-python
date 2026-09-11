"""
seed.py
-------
Populates the SQLite database with realistic demo data so you can explore
the whole app immediately, without registering accounts by hand first.

Run with:  python seed.py
"""

import os
import uuid
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from database import DB_PATH, get_connection, init_db


def new_id():
    return uuid.uuid4().hex


def main():
    # Start from a clean database file every time this script runs.
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()

    conn = get_connection()
    now = datetime.now()

    # --- Federations ---------------------------------------------------------
    fed1 = new_id()
    fed2 = new_id()
    conn.execute("INSERT INTO federations (id, name, state) VALUES (?, ?, ?)",
                 (fed1, "Hyderabad Labour Cooperative Federation", "Telangana"))
    conn.execute("INSERT INTO federations (id, name, state) VALUES (?, ?, ?)",
                 (fed2, "Pune Sahakari Seva Sangh", "Maharashtra"))

    # --- Admin (federation office) ---------------------------------------------
    conn.execute(
        "INSERT INTO users (id, role, name, phone, password_hash, language, created_at) "
        "VALUES (?, 'admin', 'Federation Admin', '9000000000', ?, 'en', ?)",
        (new_id(), generate_password_hash("admin123"), now.isoformat()),
    )

    def make_worker(name, phone, skills, federation_id, lat, lng, verified, rating, rating_count, wallet):
        user_id = new_id()
        conn.execute(
            "INSERT INTO users (id, role, name, phone, password_hash, language, created_at) "
            "VALUES (?, 'worker', ?, ?, ?, 'en', ?)",
            (user_id, name, phone, generate_password_hash("worker123"), now.isoformat()),
        )
        worker_id = new_id()
        conn.execute(
            """INSERT INTO workers
               (id, user_id, skills, federation_id, verified, certified, rating,
                rating_count, lat, lng, available, welfare_wallet, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (worker_id, user_id, ",".join(skills), federation_id, int(verified), int(verified),
             rating, rating_count, lat, lng, wallet, now.isoformat()),
        )
        return worker_id, user_id

    # Hyderabad-area workers
    ramesh_id, _ = make_worker("Ramesh Kumar", "9111111111", ["electrician", "technician"],
                               fed1, 17.4483, 78.3915, True, 4.7, 23, 340)
    make_worker("Suresh Naik", "9111111112", ["plumber"], fed1, 17.4239, 78.4738, True, 4.5, 15, 210)
    make_worker("Lakshmi Devi", "9111111113", ["domestic_help", "cleaner"], fed1, 17.3850, 78.4867, True, 4.9, 41, 560)
    make_worker("Anita Reddy", "9111111114", ["caregiver"], fed1, 17.4400, 78.3489, True, 4.8, 12, 175)
    make_worker("Mahesh Yadav", "9111111115", ["carpenter", "painter"], fed1, 17.4126, 78.4482, False, 0, 0, 0)

    # Pune-area workers
    make_worker("Sanjay Pawar", "9222222221", ["driver"], fed2, 18.5204, 73.8567, True, 4.6, 30, 410)
    make_worker("Vijay Shinde", "9222222222", ["gardener", "cleaner"], fed2, 18.5679, 73.9143, True, 4.4, 9, 95)

    # --- Sample customers ------------------------------------------------------
    cust1_id = new_id()
    conn.execute(
        "INSERT INTO users (id, role, name, phone, password_hash, language, created_at) "
        "VALUES (?, 'customer', 'Priya Sharma', '9333333331', ?, 'en', ?)",
        (cust1_id, generate_password_hash("customer123"), now.isoformat()),
    )
    conn.execute(
        "INSERT INTO users (id, role, name, phone, password_hash, language, created_at) "
        "VALUES (?, 'customer', 'Arjun Mehta', '9333333332', ?, 'hi', ?)",
        (new_id(), generate_password_hash("customer123"), now.isoformat()),
    )

    # --- Booking history, so the admin demand-forecast table has data --------
    sample_categories = ["electrician", "plumber", "domestic_help", "caregiver", "electrician", "domestic_help"]
    for i, category in enumerate(sample_categories):
        created_at = now - timedelta(hours=(i + 1) * 3)
        completed_at = created_at + timedelta(hours=1)
        conn.execute(
            """INSERT INTO bookings
               (id, customer_id, worker_id, category, description, status, urgent,
                lat, lng, distance_km, price, created_at, completed_at)
               VALUES (?, ?, ?, ?, 'Demo historical booking for forecasting/demo purposes',
                       'completed', 0, ?, ?, 1.2, ?, ?, ?)""",
            (new_id(), cust1_id, ramesh_id, category,
             17.44 + i * 0.001, 78.38 + i * 0.001, 400 + i * 50,
             created_at.isoformat(), completed_at.isoformat()),
        )

    conn.commit()
    conn.close()

    print("\n  Seed complete. Demo accounts:")
    print("  Admin:    phone 9000000000  / password admin123")
    print("  Worker:   phone 9111111111  / password worker123   (Ramesh Kumar, verified electrician)")
    print("  Worker:   phone 9111111115  / password worker123   (Mahesh Yadav, NOT yet verified)")
    print("  Customer: phone 9333333331  / password customer123 (Priya Sharma)")
    print(f"  Database file: {DB_PATH}\n")


if __name__ == "__main__":
    main()
