"""
app.py
------
Sahayog - Cooperative Gig Services Platform for Household & Community Services
(SIH26089, Ministry of Cooperation / NCCT)

This is the main Flask application. It is intentionally written as a single,
readable file with plain Flask routes (no blueprints, no class-based views)
so someone new to Flask can read it top-to-bottom and follow the whole app.

Run with:  python app.py
"""

import os
import uuid
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

import database
from database import get_connection, init_db, SERVICE_CATEGORIES, category_label
from utils.geo import find_best_worker, distance_km
from utils.forecast import forecast_demand
from translations import translate

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "sahayog-dev-secret-change-in-production")

# Cooperative economics: every payment is split three ways. Named constants,
# not logic buried elsewhere, so a federation admin could tune them easily.
FEDERATION_COMMISSION_PCT = 0.08   # 8% retained by the cooperative federation
WELFARE_CONTRIBUTION_PCT = 0.05   # 5% auto-contributed to the worker's welfare wallet


# ---------------------------------------------------------------------------
# Small helpers used by several routes
# ---------------------------------------------------------------------------

def new_id():
    """A short unique ID for database rows. uuid4 guarantees (for all
    practical purposes) that two calls never produce the same value."""
    return uuid.uuid4().hex


def now():
    return datetime.now().isoformat()


def current_user():
    """Read the logged-in user (if any) from the Flask session cookie and
    fetch their full row from the database. Returns None if nobody is
    logged in."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return user


def require_role(role):
    """Call at the top of a route to enforce that only a given role may
    view it. Returns a redirect if the check fails, or None if it passes."""
    user = current_user()
    if user is None:
        return redirect(url_for("index"))
    if user["role"] != role:
        flash("You don't have access to that page.", "error")
        return redirect(url_for("index"))
    return None


@app.context_processor
def inject_globals():
    """Makes these available inside every Jinja2 template automatically,
    without passing them into every single render_template() call."""
    lang = session.get("lang", "en")
    return {
        "current_user": current_user(),
        "lang": lang,
        "categories": SERVICE_CATEGORIES,
        "t": lambda key: translate(key, lang),
    }


@app.route("/lang/<code>")
def set_language(code):
    """Simple language switch - stores the choice in the session and
    returns to whatever page the person was on."""
    if code in ("en", "hi"):
        session["lang"] = code
    return redirect(request.referrer or url_for("index"))


# ---------------------------------------------------------------------------
# Public landing page + authentication
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    user = current_user()
    if user:
        return redirect(url_for(f"{user['role']}_dashboard"))

    conn = get_connection()
    verified_worker_count = conn.execute(
        "SELECT COUNT(*) AS c FROM workers WHERE verified = 1"
    ).fetchone()["c"]
    completed_bookings = conn.execute(
        "SELECT COUNT(*) AS c FROM bookings WHERE status = 'completed'"
    ).fetchone()["c"]
    conn.close()

    return render_template(
        "index.html",
        verified_worker_count=verified_worker_count,
        completed_bookings=completed_bookings,
    )


@app.route("/register", methods=["POST"])
def register():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role")
    language = request.form.get("language", "en")
    skills = request.form.getlist("skills")  # only present when role == 'worker'

    if not name or not phone or not password or role not in ("customer", "worker"):
        flash("Please fill in all required fields.", "error")
        return redirect(url_for("index"))

    conn = get_connection()
    existing = conn.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
    if existing:
        conn.close()
        flash("An account with this phone number already exists.", "error")
        return redirect(url_for("index"))

    if role == "worker" and not skills:
        conn.close()
        flash("Please select at least one skill.", "error")
        return redirect(url_for("index"))

    user_id = new_id()
    conn.execute(
        "INSERT INTO users (id, role, name, phone, password_hash, language, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, role, name, phone, generate_password_hash(password), language, now()),
    )

    if role == "worker":
        # New workers start UNVERIFIED - an admin must confirm their
        # Aadhaar e-KYC + skill certificate before they can be matched to jobs.
        # This models the PS's "service provider registration and verification".
        conn.execute(
            """INSERT INTO workers
               (id, user_id, skills, verified, certified, rating, rating_count,
                lat, lng, available, welfare_wallet, created_at)
               VALUES (?, ?, ?, 0, 0, 0, 0, ?, ?, 1, 0, ?)""",
            (new_id(), user_id, ",".join(skills), 17.44, 78.40, now()),
        )

    conn.commit()
    conn.close()

    session["user_id"] = user_id
    session["lang"] = language
    flash("Account created!" + (" Your worker profile is pending verification." if role == "worker" else ""), "success")
    return redirect(url_for(f"{role}_dashboard"))


@app.route("/login", methods=["POST"])
def login():
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")

    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    conn.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        flash("Invalid phone number or password.", "error")
        return redirect(url_for("index"))

    session["user_id"] = user["id"]
    session["lang"] = user["language"]
    return redirect(url_for(f"{user['role']}_dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Customer dashboard
# ---------------------------------------------------------------------------

@app.route("/customer")
def customer_dashboard():
    redirect_response = require_role("customer")
    if redirect_response:
        return redirect_response

    user = current_user()
    conn = get_connection()
    bookings = conn.execute(
        "SELECT * FROM bookings WHERE customer_id = ? ORDER BY created_at DESC",
        (user["id"],),
    ).fetchall()
    conn.close()

    return render_template("customer_dashboard.html", bookings=bookings, category_label=category_label)


@app.route("/customer/book", methods=["POST"])
def customer_book():
    redirect_response = require_role("customer")
    if redirect_response:
        return redirect_response

    user = current_user()
    category = request.form.get("category")
    description = request.form.get("description", "")
    lat = float(request.form.get("lat"))
    lng = float(request.form.get("lng"))
    urgent = request.form.get("urgent") == "on"

    conn = get_connection()
    workers = conn.execute("SELECT * FROM workers").fetchall()
    matched_worker, distance = find_best_worker(workers, category, lat, lng)

    booking_id = new_id()
    conn.execute(
        """INSERT INTO bookings
           (id, customer_id, worker_id, category, description, status, urgent,
            lat, lng, distance_km, price, created_at, completed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL)""",
        (booking_id, user["id"], matched_worker["id"] if matched_worker else None,
         category, description, "matched" if matched_worker else "pending",
         1 if urgent else 0, lat, lng, distance, now()),
    )
    conn.commit()
    conn.close()

    if matched_worker:
        flash(f"Matched with a verified {category_label(category)} worker {distance} km away.", "success")
    else:
        flash("No verified worker is available right now - your booking is queued as pending.", "info")

    return redirect(url_for("customer_dashboard"))


@app.route("/customer/pay/<booking_id>", methods=["POST"])
def customer_pay(booking_id):
    redirect_response = require_role("customer")
    if redirect_response:
        return redirect_response

    user = current_user()
    conn = get_connection()
    booking = conn.execute(
        "SELECT * FROM bookings WHERE id = ? AND customer_id = ?", (booking_id, user["id"])
    ).fetchone()

    if booking is None:
        conn.close()
        flash("Booking not found.", "error")
        return redirect(url_for("customer_dashboard"))
    if booking["status"] != "completed":
        conn.close()
        flash("This booking isn't marked completed by the worker yet.", "error")
        return redirect(url_for("customer_dashboard"))

    already_paid = conn.execute(
        "SELECT id FROM payments WHERE booking_id = ?", (booking_id,)
    ).fetchone()
    if already_paid:
        conn.close()
        flash("This booking has already been paid.", "error")
        return redirect(url_for("customer_dashboard"))

    amount = booking["price"]
    welfare_contribution = round(amount * WELFARE_CONTRIBUTION_PCT, 2)
    federation_commission = round(amount * FEDERATION_COMMISSION_PCT, 2)
    worker_payout = round(amount - welfare_contribution - federation_commission, 2)

    payment_count = conn.execute("SELECT COUNT(*) AS c FROM payments").fetchone()["c"]
    invoice_no = f"SHY-{datetime.now().year}-{1001 + payment_count}"

    conn.execute(
        """INSERT INTO payments
           (id, booking_id, amount, method, welfare_contribution,
            federation_commission, worker_payout, invoice_no, created_at)
           VALUES (?, ?, ?, 'UPI', ?, ?, ?, ?, ?)""",
        (new_id(), booking_id, amount, welfare_contribution,
         federation_commission, worker_payout, invoice_no, now()),
    )
    conn.execute(
        "UPDATE workers SET welfare_wallet = welfare_wallet + ? WHERE id = ?",
        (welfare_contribution, booking["worker_id"]),
    )
    conn.commit()
    conn.close()

    flash(f"Payment successful. Invoice {invoice_no} - Rs.{welfare_contribution} added to the worker's welfare wallet.", "success")
    return redirect(url_for("customer_dashboard"))


@app.route("/customer/rate/<booking_id>", methods=["POST"])
def customer_rate(booking_id):
    redirect_response = require_role("customer")
    if redirect_response:
        return redirect_response

    user = current_user()
    stars = int(request.form.get("stars", 5))
    comment = request.form.get("comment", "")

    conn = get_connection()
    booking = conn.execute(
        "SELECT * FROM bookings WHERE id = ? AND customer_id = ?", (booking_id, user["id"])
    ).fetchone()
    if booking is None or booking["status"] != "completed":
        conn.close()
        flash("You can only rate a completed booking.", "error")
        return redirect(url_for("customer_dashboard"))

    already_rated = conn.execute("SELECT id FROM ratings WHERE booking_id = ?", (booking_id,)).fetchone()
    if already_rated:
        conn.close()
        flash("This booking has already been rated.", "error")
        return redirect(url_for("customer_dashboard"))

    conn.execute(
        """INSERT INTO ratings (id, booking_id, worker_id, customer_id, stars, comment, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (new_id(), booking_id, booking["worker_id"], user["id"], stars, comment, now()),
    )

    worker = conn.execute("SELECT * FROM workers WHERE id = ?", (booking["worker_id"],)).fetchone()
    new_count = worker["rating_count"] + 1
    new_avg = round((worker["rating"] * worker["rating_count"] + stars) / new_count, 2)
    conn.execute(
        "UPDATE workers SET rating = ?, rating_count = ? WHERE id = ?",
        (new_avg, new_count, worker["id"]),
    )
    conn.commit()
    conn.close()

    flash("Thanks for your feedback!", "success")
    return redirect(url_for("customer_dashboard"))


# ---------------------------------------------------------------------------
# Worker dashboard
# ---------------------------------------------------------------------------

@app.route("/worker")
def worker_dashboard():
    redirect_response = require_role("worker")
    if redirect_response:
        return redirect_response

    user = current_user()
    conn = get_connection()
    profile = conn.execute("SELECT * FROM workers WHERE user_id = ?", (user["id"],)).fetchone()
    bookings = conn.execute(
        "SELECT * FROM bookings WHERE worker_id = ? ORDER BY created_at DESC", (profile["id"],)
    ).fetchall()
    conn.close()

    return render_template(
        "worker_dashboard.html", profile=profile, bookings=bookings, category_label=category_label
    )


@app.route("/worker/availability", methods=["POST"])
def worker_availability():
    redirect_response = require_role("worker")
    if redirect_response:
        return redirect_response

    user = current_user()
    available = request.form.get("available") == "on"
    conn = get_connection()
    conn.execute("UPDATE workers SET available = ? WHERE user_id = ?", (1 if available else 0, user["id"]))
    conn.commit()
    conn.close()
    return redirect(url_for("worker_dashboard"))


@app.route("/worker/accept/<booking_id>", methods=["POST"])
def worker_accept(booking_id):
    redirect_response = require_role("worker")
    if redirect_response:
        return redirect_response

    user = current_user()
    conn = get_connection()
    profile = conn.execute("SELECT * FROM workers WHERE user_id = ?", (user["id"],)).fetchone()
    booking = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()

    if booking is None or booking["worker_id"] != profile["id"]:
        conn.close()
        flash("This booking was not matched to you.", "error")
        return redirect(url_for("worker_dashboard"))

    conn.execute("UPDATE bookings SET status = 'accepted' WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()
    flash("Job accepted.", "success")
    return redirect(url_for("worker_dashboard"))


@app.route("/worker/complete/<booking_id>", methods=["POST"])
def worker_complete(booking_id):
    redirect_response = require_role("worker")
    if redirect_response:
        return redirect_response

    user = current_user()
    price = request.form.get("price")
    if not price or float(price) <= 0:
        flash("Enter a valid final price.", "error")
        return redirect(url_for("worker_dashboard"))

    conn = get_connection()
    profile = conn.execute("SELECT * FROM workers WHERE user_id = ?", (user["id"],)).fetchone()
    booking = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()

    if booking is None or booking["worker_id"] != profile["id"]:
        conn.close()
        flash("This booking was not matched to you.", "error")
        return redirect(url_for("worker_dashboard"))

    conn.execute(
        "UPDATE bookings SET status = 'completed', price = ?, completed_at = ? WHERE id = ?",
        (float(price), now(), booking_id),
    )
    conn.commit()
    conn.close()
    flash("Job marked completed. The customer can now pay.", "success")
    return redirect(url_for("worker_dashboard"))


# ---------------------------------------------------------------------------
# Admin / federation dashboard
# ---------------------------------------------------------------------------

@app.route("/admin")
def admin_dashboard():
    redirect_response = require_role("admin")
    if redirect_response:
        return redirect_response

    conn = get_connection()

    total_workers = conn.execute("SELECT COUNT(*) AS c FROM workers").fetchone()["c"]
    verified_workers = conn.execute("SELECT COUNT(*) AS c FROM workers WHERE verified = 1").fetchone()["c"]
    total_customers = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'customer'").fetchone()["c"]
    total_bookings = conn.execute("SELECT COUNT(*) AS c FROM bookings").fetchone()["c"]
    completed_bookings = conn.execute("SELECT COUNT(*) AS c FROM bookings WHERE status = 'completed'").fetchone()["c"]

    revenue_row = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS revenue, COALESCE(SUM(welfare_contribution),0) AS welfare, "
        "COALESCE(SUM(federation_commission),0) AS commission FROM payments"
    ).fetchone()

    avg_rating_row = conn.execute(
        "SELECT AVG(rating) AS avg_rating FROM workers WHERE rating_count > 0"
    ).fetchone()

    bookings_by_category = conn.execute(
        "SELECT category, COUNT(*) AS c FROM bookings GROUP BY category ORDER BY c DESC"
    ).fetchall()

    pending_workers = conn.execute(
        """SELECT workers.*, users.name AS name FROM workers
           JOIN users ON users.id = workers.user_id
           WHERE workers.verified = 0"""
    ).fetchall()

    all_workers = conn.execute(
        """SELECT workers.*, users.name AS name FROM workers
           JOIN users ON users.id = workers.user_id
           ORDER BY workers.verified ASC, users.name ASC"""
    ).fetchall()

    all_bookings = conn.execute("SELECT category, created_at FROM bookings").fetchall()
    forecast = forecast_demand(all_bookings)

    conn.close()

    stats = {
        "total_workers": total_workers,
        "verified_workers": verified_workers,
        "total_customers": total_customers,
        "total_bookings": total_bookings,
        "completed_bookings": completed_bookings,
        "completion_rate": round(completed_bookings / total_bookings * 100) if total_bookings else 0,
        "total_revenue": revenue_row["revenue"],
        "total_welfare": revenue_row["welfare"],
        "total_commission": revenue_row["commission"],
        "avg_rating": round(avg_rating_row["avg_rating"], 2) if avg_rating_row["avg_rating"] else None,
    }

    return render_template(
        "admin_dashboard.html",
        stats=stats,
        bookings_by_category=bookings_by_category,
        pending_workers=pending_workers,
        all_workers=all_workers,
        forecast=forecast[:12],
    )


@app.route("/admin/verify/<worker_id>", methods=["POST"])
def admin_verify(worker_id):
    redirect_response = require_role("admin")
    if redirect_response:
        return redirect_response

    conn = get_connection()
    conn.execute("UPDATE workers SET verified = 1, certified = 1 WHERE id = ?", (worker_id,))
    conn.commit()
    conn.close()
    flash("Worker verified.", "success")
    return redirect(url_for("admin_dashboard"))


# ---------------------------------------------------------------------------
# App startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
