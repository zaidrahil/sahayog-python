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
import random
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

# Ensure database tables and runtime migrations exist on cold start (essential for Vercel/serverless)
try:
    init_db()
except Exception:
    pass

# WSGI handler alias for serverless deployment
handler = app

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
        """SELECT bookings.*,
                  workers.rating AS worker_rating,
                  workers.rating_count AS worker_rating_count,
                  workers.spoken_languages AS worker_spoken_languages,
                  worker_users.name AS worker_name,
                  worker_users.phone AS worker_phone,
                  payments.invoice_no, payments.worker_payout,
                  payments.welfare_contribution, payments.federation_commission,
                  escrow_transactions.id AS escrow_id,
                  escrow_transactions.amount AS escrow_amount,
                  escrow_transactions.gateway_name AS escrow_gateway,
                  escrow_transactions.gateway_tx_id AS escrow_tx_id,
                  escrow_transactions.status AS escrow_tx_status,
                  escrow_transactions.dispute_reason,
                  escrow_transactions.dispute_opened_by,
                  escrow_transactions.resolution_notes
           FROM bookings
           LEFT JOIN workers ON workers.id = bookings.worker_id
           LEFT JOIN users AS worker_users ON worker_users.id = workers.user_id
           LEFT JOIN payments ON payments.booking_id = bookings.id
           LEFT JOIN escrow_transactions ON escrow_transactions.booking_id = bookings.id
           WHERE bookings.customer_id = ?
           ORDER BY bookings.created_at DESC""",
        (user["id"],),
    ).fetchall()

    workers = conn.execute(
        """SELECT workers.id, workers.lat, workers.lng, workers.skills, workers.rating, workers.available, workers.spoken_languages, users.name
           FROM workers
           JOIN users ON users.id = workers.user_id
           WHERE workers.verified = 1 AND workers.lat IS NOT NULL"""
    ).fetchall()
    conn.close()

    worker_pins = [
        {
            "id": w["id"],
            "name": w["name"],
            "lat": w["lat"],
            "lng": w["lng"],
            "skills": [category_label(s) for s in w["skills"].split(",")],
            "rating": w["rating"],
            "available": bool(w["available"]),
            "spoken_languages": w["spoken_languages"] if "spoken_languages" in w.keys() and w["spoken_languages"] else "en,hi",
        }
        for w in workers
    ]

    return render_template(
        "customer_dashboard.html",
        bookings=bookings,
        category_label=category_label,
        worker_pins=worker_pins,
    )


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
    preferred_lang = request.form.get("preferred_lang", "en").strip()
    try:
        escrow_amount = float(request.form.get("escrow_amount", 350.0))
    except (ValueError, TypeError):
        escrow_amount = 350.0
    gateway_name = request.form.get("gateway_name", "UPI").strip()

    conn = get_connection()
    workers = conn.execute("SELECT * FROM workers").fetchall()
    matched_worker, distance = find_best_worker(workers, category, lat, lng, preferred_lang=preferred_lang)

    completion_otp = f"{random.randint(1000, 9999)}"
    booking_id = new_id()
    escrow_id = new_id()
    gateway_tx_id = f"ESCR-{gateway_name.upper()}-{random.randint(10000000, 99999999)}"

    conn.execute(
        """INSERT INTO bookings
           (id, customer_id, worker_id, category, description, status, urgent,
            lat, lng, distance_km, price, completion_otp, escrow_status, language, created_at, completed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'held', ?, ?, NULL)""",
        (booking_id, user["id"], matched_worker["id"] if matched_worker else None,
         category, description, "matched" if matched_worker else "pending",
         1 if urgent else 0, lat, lng, distance, escrow_amount, completion_otp, preferred_lang, now()),
    )
    conn.execute(
        """INSERT INTO escrow_transactions
           (id, booking_id, customer_id, worker_id, amount, gateway_name, gateway_tx_id, status, held_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'held', ?)""",
        (escrow_id, booking_id, user["id"], matched_worker["id"] if matched_worker else None,
         escrow_amount, gateway_name, gateway_tx_id, now()),
    )
    conn.commit()
    conn.close()

    lang_labels = {"en": "English", "hi": "Hindi", "te": "Telugu", "mr": "Marathi", "bn": "Bengali", "ta": "Tamil", "kn": "Kannada"}
    lang_name = lang_labels.get(preferred_lang, preferred_lang.upper())

    if matched_worker:
        flash(f"Matched with verified {lang_name}-speaking {category_label(category)} ({distance} km away)! ₹{int(escrow_amount)} secured in Cooperative Escrow Vault ({gateway_tx_id}). Completion OTP: {completion_otp}.", "success")
    else:
        flash(f"₹{int(escrow_amount)} locked in Escrow Vault ({gateway_tx_id}). No {lang_name}-speaking worker available immediately — request queued.", "info")

    return redirect(url_for("customer_dashboard") + "#bookings")


@app.route("/customer/dispute/<booking_id>", methods=["POST"])
def customer_dispute(booking_id):
    redirect_response = require_role("customer")
    if redirect_response:
        return redirect_response

    user = current_user()
    reason = request.form.get("reason", "Service not delivered as expected / quality dispute").strip()

    conn = get_connection()
    booking = conn.execute("SELECT * FROM bookings WHERE id = ? AND customer_id = ?", (booking_id, user["id"])).fetchone()
    if not booking:
        conn.close()
        flash("Booking not found.", "error")
        return redirect(url_for("customer_dashboard") + "#bookings")

    if booking["escrow_status"] in ("released", "refunded"):
        conn.close()
        flash("Cannot dispute an escrow that has already been released or refunded.", "error")
        return redirect(url_for("customer_dashboard") + "#bookings")

    conn.execute("UPDATE bookings SET escrow_status = 'disputed' WHERE id = ?", (booking_id,))
    conn.execute(
        """UPDATE escrow_transactions
           SET status = 'disputed', dispute_reason = ?, dispute_opened_by = 'customer'
           WHERE booking_id = ?""",
        (reason, booking_id),
    )
    conn.commit()
    conn.close()

    flash(f"Dispute logged. Escrow funds are frozen under Federation Conciliation. Case reason: '{reason}'.", "info")
    return redirect(url_for("customer_dashboard") + "#bookings")


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
    conn.execute(
        "UPDATE bookings SET escrow_status = 'paid' WHERE id = ?",
        (booking_id,),
    )
    conn.commit()
    conn.close()

    flash(f"Payment of Rs.{amount} completed successfully! Invoice {invoice_no} generated - Rs.{welfare_contribution} credited to worker's welfare wallet.", "success")
    return redirect(url_for("customer_dashboard") + "#bookings")


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
    return redirect(url_for("customer_dashboard") + "#bookings")


@app.route("/customer/settings", methods=["GET"])
def customer_settings():
    redirect_response = require_role("customer")
    if redirect_response:
        return redirect_response

    user = current_user()
    conn = get_connection()
    stats = {
        "total_bookings": conn.execute("SELECT COUNT(*) AS c FROM bookings WHERE customer_id = ?", (user["id"],)).fetchone()["c"],
        "completed_bookings": conn.execute("SELECT COUNT(*) AS c FROM bookings WHERE customer_id = ? AND status = 'completed'", (user["id"],)).fetchone()["c"],
        "welfare_generated": round(conn.execute(
            """SELECT COALESCE(SUM(payments.welfare_contribution), 0) AS s
               FROM payments
               JOIN bookings ON bookings.id = payments.booking_id
               WHERE bookings.customer_id = ?""",
            (user["id"],)
        ).fetchone()["s"] or 0, 2),
    }
    conn.close()

    available_languages = [
        ("en", "🇬🇧 English"),
        ("hi", "🇮🇳 हिन्दी (Hindi)"),
        ("te", "🇮🇳 తెలుగు (Telugu)"),
        ("mr", "🇮🇳 मराठी (Marathi)"),
        ("bn", "🇮🇳 বাংলা (Bengali)"),
        ("ta", "🇮🇳 தமிழ் (Tamil)"),
        ("kn", "🇮🇳 ಕನ್ನಡ (Kannada)"),
    ]

    return render_template(
        "customer_settings.html",
        user=user,
        stats=stats,
        available_languages=available_languages,
    )


@app.route("/customer/settings/profile", methods=["POST"])
def customer_update_profile():
    redirect_response = require_role("customer")
    if redirect_response:
        return redirect_response

    user = current_user()
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    language = request.form.get("language", "en").strip()
    address = request.form.get("address", "").strip()

    if not name or len(name) < 2:
        flash("Please enter a valid full name.", "error")
        return redirect(url_for("customer_settings"))

    if not phone or not phone.isdigit() or len(phone) != 10:
        flash("Phone number must be exactly 10 digits.", "error")
        return redirect(url_for("customer_settings"))

    conn = get_connection()
    existing = conn.execute("SELECT id FROM users WHERE phone = ? AND id != ?", (phone, user["id"])).fetchone()
    if existing:
        conn.close()
        flash(f"Phone number {phone} is already registered to another account.", "error")
        return redirect(url_for("customer_settings"))

    conn.execute(
        "UPDATE users SET name = ?, phone = ?, language = ?, address = ? WHERE id = ?",
        (name, phone, language, address, user["id"]),
    )
    conn.commit()
    conn.close()

    session["lang"] = language
    flash("Profile settings updated successfully!", "success")
    return redirect(url_for("customer_settings"))


@app.route("/customer/settings/password", methods=["POST"])
def customer_update_password():
    redirect_response = require_role("customer")
    if redirect_response:
        return redirect_response

    user = current_user()
    current_pw = request.form.get("current_password", "").strip()
    new_pw = request.form.get("new_password", "").strip()
    confirm_pw = request.form.get("confirm_password", "").strip()

    if not check_password_hash(user["password_hash"], current_pw):
        flash("Your current password was incorrect.", "error")
        return redirect(url_for("customer_settings"))

    if len(new_pw) < 6:
        flash("New password must be at least 6 characters long.", "error")
        return redirect(url_for("customer_settings"))

    if new_pw != confirm_pw:
        flash("New password and confirmation do not match.", "error")
        return redirect(url_for("customer_settings"))

    new_hash = generate_password_hash(new_pw)
    conn = get_connection()
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user["id"]))
    conn.commit()
    conn.close()

    flash("Password updated successfully! Please keep it safe.", "success")
    return redirect(url_for("customer_settings"))


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
        """SELECT bookings.*, users.name AS customer_name, users.phone AS customer_phone,
                  escrow_transactions.id AS escrow_id,
                  escrow_transactions.amount AS escrow_amount,
                  escrow_transactions.gateway_name AS escrow_gateway,
                  escrow_transactions.gateway_tx_id AS escrow_tx_id,
                  escrow_transactions.status AS escrow_tx_status,
                  escrow_transactions.dispute_reason,
                  escrow_transactions.dispute_opened_by
           FROM bookings
           JOIN users ON users.id = bookings.customer_id
           LEFT JOIN escrow_transactions ON escrow_transactions.booking_id = bookings.id
           WHERE bookings.worker_id = ?
           ORDER BY bookings.created_at DESC""",
        (profile["id"],),
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


@app.route("/worker/verification")
def worker_verification():
    redirect_response = require_role("worker")
    if redirect_response:
        return redirect_response

    user = current_user()
    conn = get_connection()
    profile = conn.execute(
        """SELECT workers.*, users.name, users.phone, users.address
           FROM workers JOIN users ON users.id = workers.user_id
           WHERE workers.user_id = ?""",
        (user["id"],),
    ).fetchone()
    conn.close()

    return render_template("worker_verification.html", profile=profile)


@app.route("/worker/verification/save", methods=["POST"])
def worker_verification_save():
    redirect_response = require_role("worker")
    if redirect_response:
        return redirect_response

    user = current_user()
    aadhaar_last4 = request.form.get("aadhaar_last4", "").strip()
    aadhaar_name = request.form.get("aadhaar_name", "").strip() or user["name"]
    aadhaar_dob = request.form.get("aadhaar_dob", "").strip()
    cert_type = request.form.get("cert_type", "NCCT Master Craftsman").strip()
    cert_id = request.form.get("cert_id", "").strip()
    cert_level = request.form.get("cert_level", "NSQF Level 4 - Master Craftsman").strip()
    cert_issue_year = request.form.get("cert_issue_year", "2024").strip()
    peer_reference = request.form.get("peer_reference", "").strip()
    peer_phone = request.form.get("peer_phone", "").strip()
    pcc_number = request.form.get("pcc_number", "").strip()
    police_declaration = 1 if request.form.get("police_declaration") == "on" else 0
    toolkit_items = request.form.get("toolkit_items", "").strip()
    tools_verified = 1 if request.form.get("tools_verified") == "on" else 0

    if len(aadhaar_last4) != 4 or not aadhaar_last4.isdigit():
        flash("Please enter the valid last 4 digits of your Aadhaar card.", "error")
        return redirect(url_for("worker_verification"))

    if not cert_id:
        flash("Please provide your NCCT / Trade Certificate Registration ID.", "error")
        return redirect(url_for("worker_verification"))

    if not police_declaration:
        flash("Please complete the criminal background self-declaration affidavit.", "error")
        return redirect(url_for("worker_verification"))

    conn = get_connection()
    conn.execute(
        """UPDATE workers
           SET aadhaar_last4 = ?, aadhaar_name = ?, aadhaar_dob = ?,
               cert_type = ?, cert_id = ?, cert_level = ?, cert_issue_year = ?,
               peer_reference = ?, peer_phone = ?, pcc_number = ?,
               toolkit_items = ?, tools_verified = ?, verification_status = 'submitted'
           WHERE user_id = ?""",
        (aadhaar_last4, aadhaar_name, aadhaar_dob, cert_type, cert_id, cert_level,
         cert_issue_year, peer_reference, peer_phone, pcc_number, toolkit_items,
         tools_verified, user["id"]),
    )
    conn.commit()
    conn.close()

    flash("Comprehensive 4-Pillar verification saved & submitted for Federation Field Officer audit!", "success")
    return redirect(url_for("worker_verification"))


@app.route("/worker/verify/submit", methods=["POST"])
def worker_verify_submit():
    redirect_response = require_role("worker")
    if redirect_response:
        return redirect_response

    user = current_user()
    aadhaar_last4 = request.form.get("aadhaar_last4", "").strip()
    cert_type = request.form.get("cert_type", "NCCT Master Craftsman").strip()
    cert_id = request.form.get("cert_id", "").strip()
    peer_reference = request.form.get("peer_reference", "").strip()
    police_declaration = 1 if request.form.get("police_declaration") == "on" else 0
    tools_verified = 1 if request.form.get("tools_verified") == "on" else 0

    if len(aadhaar_last4) != 4 or not aadhaar_last4.isdigit():
        flash("Please enter the valid last 4 digits of your Aadhaar card.", "error")
        return redirect(url_for("worker_dashboard"))

    if not cert_id:
        flash("Please provide your NCCT / Trade Certificate Registration ID.", "error")
        return redirect(url_for("worker_dashboard"))

    if not police_declaration:
        flash("Please complete the criminal background self-declaration affidavit.", "error")
        return redirect(url_for("worker_dashboard"))

    conn = get_connection()
    conn.execute(
        """UPDATE workers
           SET aadhaar_last4 = ?, aadhaar_name = COALESCE(aadhaar_name, ?),
               cert_type = ?, cert_id = ?, peer_reference = ?,
               tools_verified = ?, verification_status = 'submitted'
           WHERE user_id = ?""",
        (aadhaar_last4, user["name"], cert_type, cert_id, peer_reference, tools_verified, user["id"]),
    )
    conn.commit()
    conn.close()

    flash("4-Pillar accreditation credentials submitted! The Cooperative Federation Officer will inspect your toolkit and sign off.", "success")
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
    price_raw = request.form.get("price")
    entered_otp = request.form.get("otp", "").strip()

    conn = get_connection()
    profile = conn.execute("SELECT * FROM workers WHERE user_id = ?", (user["id"],)).fetchone()
    booking = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()

    if booking is None or booking["worker_id"] != profile["id"]:
        conn.close()
        flash("This booking was not matched to you.", "error")
        return redirect(url_for("worker_dashboard"))

    if not entered_otp:
        conn.close()
        flash("Please enter the 4-digit customer completion OTP.", "error")
        return redirect(url_for("worker_dashboard"))

    expected_otp = str(booking["completion_otp"]).strip() if booking["completion_otp"] else None
    if expected_otp and entered_otp != expected_otp:
        conn.close()
        flash(f"Invalid OTP '{entered_otp}'. Ask the customer for the 4-digit verification code shown on their dashboard.", "error")
        return redirect(url_for("worker_dashboard"))

    try:
        amount = float(price_raw) if price_raw and float(price_raw) > 0 else (booking["price"] or 350.0)
    except (ValueError, TypeError):
        amount = booking["price"] or 350.0

    welfare_contribution = round(amount * WELFARE_CONTRIBUTION_PCT, 2)
    federation_commission = round(amount * FEDERATION_COMMISSION_PCT, 2)
    worker_payout = round(amount - welfare_contribution - federation_commission, 2)

    payment_count = conn.execute("SELECT COUNT(*) AS c FROM payments").fetchone()["c"]
    invoice_no = f"SHY-{datetime.now().year}-{1001 + payment_count}"

    conn.execute(
        """INSERT INTO payments
           (id, booking_id, amount, method, welfare_contribution,
            federation_commission, worker_payout, invoice_no, created_at)
           VALUES (?, ?, ?, 'Co-op Escrow', ?, ?, ?, ?, ?)""",
        (new_id(), booking_id, amount, welfare_contribution,
         federation_commission, worker_payout, invoice_no, now()),
    )
    conn.execute(
        "UPDATE workers SET welfare_wallet = welfare_wallet + ? WHERE id = ?",
        (welfare_contribution, profile["id"]),
    )
    conn.execute(
        """UPDATE escrow_transactions
           SET status = 'released', released_at = ?, amount = ?
           WHERE booking_id = ?""",
        (now(), amount, booking_id),
    )
    conn.execute(
        "UPDATE bookings SET status = 'completed', price = ?, escrow_status = 'released', completed_at = ? WHERE id = ?",
        (amount, now(), booking_id),
    )
    conn.commit()
    conn.close()

    flash(f"Customer OTP verified! Escrow of Rs.{amount} successfully released: Rs.{worker_payout} direct payout, Rs.{welfare_contribution} to Welfare Wallet. Invoice {invoice_no} issued.", "success")
    return redirect(url_for("worker_dashboard"))


@app.route("/worker/dispute/<booking_id>", methods=["POST"])
def worker_dispute(booking_id):
    redirect_response = require_role("worker")
    if redirect_response:
        return redirect_response

    user = current_user()
    reason = request.form.get("reason", "Customer withholding completion OTP despite finished on-site work.").strip()

    conn = get_connection()
    profile = conn.execute("SELECT * FROM workers WHERE user_id = ?", (user["id"],)).fetchone()
    booking = conn.execute("SELECT * FROM bookings WHERE id = ? AND worker_id = ?", (booking_id, profile["id"])).fetchone()

    if not booking:
        conn.close()
        flash("Booking not found.", "error")
        return redirect(url_for("worker_dashboard"))

    conn.execute("UPDATE bookings SET escrow_status = 'disputed' WHERE id = ?", (booking_id,))
    conn.execute(
        """UPDATE escrow_transactions
           SET status = 'disputed', dispute_reason = ?, dispute_opened_by = 'worker'
           WHERE booking_id = ?""",
        (reason, booking_id),
    )
    conn.commit()
    conn.close()

    flash("Escrow dispute escalated to Federation Conciliation Desk. Officer will inspect work evidence and conciliate.", "info")
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

    # Master & Pending Workers
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

    # Central Fleet Geolocation Pins
    workers_geo = conn.execute(
        """SELECT workers.id, workers.lat, workers.lng, workers.skills, workers.rating,
                  workers.available, workers.verified, workers.retraining_status, users.name, users.phone
           FROM workers
           JOIN users ON users.id = workers.user_id
           WHERE workers.lat IS NOT NULL"""
    ).fetchall()

    worker_pins = [
        {
            "id": w["id"],
            "name": w["name"],
            "phone": w["phone"],
            "lat": w["lat"],
            "lng": w["lng"],
            "skills": [category_label(s) for s in w["skills"].split(",")],
            "rating": w["rating"],
            "available": bool(w["available"]),
            "verified": bool(w["verified"]),
            "retraining_status": w["retraining_status"] if "retraining_status" in w.keys() and w["retraining_status"] else "none"
        }
        for w in workers_geo
    ]

    # Active Job Pins
    active_jobs = conn.execute(
        """SELECT bookings.id, bookings.category, bookings.lat, bookings.lng, bookings.status,
                  bookings.price, users.name as customer_name
           FROM bookings
           JOIN users ON users.id = bookings.customer_id
           WHERE bookings.status IN ('matched', 'accepted') AND bookings.lat IS NOT NULL"""
    ).fetchall()

    active_job_pins = [
        {
            "id": j["id"],
            "category": category_label(j["category"]),
            "lat": j["lat"],
            "lng": j["lng"],
            "status": j["status"],
            "customer_name": j["customer_name"]
        }
        for j in active_jobs
    ]

    # Financial Settlement Ledger
    payments_ledger = conn.execute(
        """SELECT payments.*, bookings.category, customer_users.name AS customer_name,
                  worker_users.name AS worker_name
           FROM payments
           JOIN bookings ON bookings.id = payments.booking_id
           JOIN users AS customer_users ON customer_users.id = bookings.customer_id
           JOIN workers ON workers.id = bookings.worker_id
           JOIN users AS worker_users ON worker_users.id = workers.user_id
           ORDER BY payments.created_at DESC
           LIMIT 50"""
    ).fetchall()

    # 5% Worker Welfare Disbursals Ledger
    welfare_disbursals = conn.execute(
        """SELECT welfare_disbursals.*, users.name AS worker_name, workers.welfare_wallet
           FROM welfare_disbursals
           JOIN workers ON workers.id = welfare_disbursals.worker_id
           JOIN users ON users.id = workers.user_id
           ORDER BY welfare_disbursals.disbursed_at DESC"""
    ).fetchall()

    total_disbursed_row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total_disbursed FROM welfare_disbursals"
    ).fetchone()
    total_disbursed = total_disbursed_row["total_disbursed"] if total_disbursed_row else 0

    # Escrow Vault Statistics & Conciliation Queues
    escrow_held = conn.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM escrow_transactions WHERE status = 'held'").fetchone()["s"]
    escrow_released = conn.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM escrow_transactions WHERE status = 'released'").fetchone()["s"]
    escrow_disputed = conn.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM escrow_transactions WHERE status = 'disputed'").fetchone()["s"]

    disputed_escrows = conn.execute(
        """SELECT escrow_transactions.*, bookings.category, bookings.description, bookings.completion_otp,
                  customer.name AS customer_name, customer.phone AS customer_phone,
                  worker_users.name AS worker_name, worker_users.phone AS worker_phone
           FROM escrow_transactions
           JOIN bookings ON bookings.id = escrow_transactions.booking_id
           JOIN users AS customer ON customer.id = escrow_transactions.customer_id
           LEFT JOIN workers ON workers.id = escrow_transactions.worker_id
           LEFT JOIN users AS worker_users ON worker_users.id = workers.user_id
           WHERE escrow_transactions.status = 'disputed'
           ORDER BY escrow_transactions.held_at DESC"""
    ).fetchall()

    escrow_ledger = conn.execute(
        """SELECT escrow_transactions.*, bookings.category,
                  customer.name AS customer_name,
                  worker_users.name AS worker_name
           FROM escrow_transactions
           JOIN bookings ON bookings.id = escrow_transactions.booking_id
           JOIN users AS customer ON customer.id = escrow_transactions.customer_id
           LEFT JOIN workers ON workers.id = escrow_transactions.worker_id
           LEFT JOIN users AS worker_users ON worker_users.id = workers.user_id
           ORDER BY escrow_transactions.held_at DESC
           LIMIT 50"""
    ).fetchall()

    # NCCT Retraining Candidate Workers (Rating < 4.0 or flagged)
    retraining_workers = conn.execute(
        """SELECT workers.*, users.name AS name, users.phone AS phone
           FROM workers
           JOIN users ON users.id = workers.user_id
           WHERE (workers.retraining_status IS NOT NULL AND workers.retraining_status != 'none')
              OR (workers.rating_count > 0 AND workers.rating < 4.0)
           ORDER BY workers.rating ASC"""
    ).fetchall()

    all_bookings = conn.execute("SELECT category, created_at FROM bookings").fetchall()
    forecast = forecast_demand(all_bookings)

    conn.close()

    net_welfare = round(revenue_row["welfare"] - total_disbursed, 2)
    stats = {
        "total_workers": total_workers,
        "verified_workers": verified_workers,
        "total_customers": total_customers,
        "total_bookings": total_bookings,
        "completed_bookings": completed_bookings,
        "completion_rate": round(completed_bookings / total_bookings * 100) if total_bookings else 0,
        "total_revenue": revenue_row["revenue"],
        "total_welfare": revenue_row["welfare"],
        "total_disbursed": total_disbursed,
        "net_welfare": net_welfare if net_welfare > 0 else 0,
        "total_commission": revenue_row["commission"],
        "avg_rating": round(avg_rating_row["avg_rating"], 2) if avg_rating_row["avg_rating"] else None,
        "total_escrow_held": round(escrow_held, 2),
        "total_escrow_released": round(escrow_released, 2),
        "total_escrow_disputed": round(escrow_disputed, 2),
    }

    return render_template(
        "admin_dashboard.html",
        stats=stats,
        bookings_by_category=bookings_by_category,
        pending_workers=pending_workers,
        all_workers=all_workers,
        forecast=forecast[:12],
        worker_pins=worker_pins,
        active_job_pins=active_job_pins,
        payments_ledger=payments_ledger,
        welfare_disbursals=welfare_disbursals,
        retraining_workers=retraining_workers,
        disputed_escrows=disputed_escrows,
        escrow_ledger=escrow_ledger,
        category_label=category_label,
    )


@app.route("/admin/escrow/resolve/<escrow_id>", methods=["POST"])
def admin_escrow_resolve(escrow_id):
    redirect_response = require_role("admin")
    if redirect_response:
        return redirect_response

    action = request.form.get("action")  # "release_to_worker" or "refund_to_customer"
    notes = request.form.get("resolution_notes", "").strip()

    conn = get_connection()
    escrow = conn.execute("SELECT * FROM escrow_transactions WHERE id = ?", (escrow_id,)).fetchone()
    if not escrow:
        conn.close()
        flash("Escrow record not found.", "error")
        return redirect(url_for("admin_dashboard") + "#welfare")

    booking = conn.execute("SELECT * FROM bookings WHERE id = ?", (escrow["booking_id"],)).fetchone()

    if action == "release_to_worker":
        amount = escrow["amount"]
        welfare_contribution = round(amount * WELFARE_CONTRIBUTION_PCT, 2)
        federation_commission = round(amount * FEDERATION_COMMISSION_PCT, 2)
        worker_payout = round(amount - welfare_contribution - federation_commission, 2)

        payment_count = conn.execute("SELECT COUNT(*) AS c FROM payments").fetchone()["c"]
        invoice_no = f"SHY-{datetime.now().year}-{1001 + payment_count}"

        existing_p = conn.execute("SELECT id FROM payments WHERE booking_id = ?", (escrow["booking_id"],)).fetchone()
        if not existing_p:
            conn.execute(
                """INSERT INTO payments
                   (id, booking_id, amount, method, welfare_contribution,
                    federation_commission, worker_payout, invoice_no, created_at)
                   VALUES (?, ?, ?, 'Conciliated Escrow', ?, ?, ?, ?, ?)""",
                (new_id(), escrow["booking_id"], amount, welfare_contribution,
                 federation_commission, worker_payout, invoice_no, now()),
            )
            if escrow["worker_id"]:
                conn.execute(
                    "UPDATE workers SET welfare_wallet = welfare_wallet + ? WHERE id = ?",
                    (welfare_contribution, escrow["worker_id"]),
                )

        conn.execute(
            """UPDATE escrow_transactions
               SET status = 'released', released_at = ?, resolution_notes = ?
               WHERE id = ?""",
            (now(), f"Conciliation Release: {notes}", escrow_id),
        )
        conn.execute(
            "UPDATE bookings SET status = 'completed', price = ?, escrow_status = 'released', completed_at = ? WHERE id = ?",
            (amount, now(), escrow["booking_id"]),
        )
        conn.commit()
        conn.close()
        flash(f"Dispute resolved: Escrow Rs.{amount} released to worker following federation audit. Invoice {invoice_no} logged.", "success")

    elif action == "refund_to_customer":
        conn.execute(
            """UPDATE escrow_transactions
               SET status = 'refunded', resolution_notes = ?
               WHERE id = ?""",
            (f"Conciliation Refund: {notes}", escrow_id),
        )
        conn.execute(
            "UPDATE bookings SET status = 'cancelled', escrow_status = 'refunded' WHERE id = ?",
            (escrow["booking_id"],),
        )
        conn.commit()
        conn.close()
        flash(f"Dispute resolved: Escrow deposit of Rs.{escrow['amount']} refunded to customer source account.", "info")

    else:
        conn.close()
        flash("Invalid arbitration action.", "error")

    return redirect(url_for("admin_dashboard") + "#welfare")


@app.route("/admin/verify/worker/<worker_id>")
def admin_worker_dossier(worker_id):
    redirect_response = require_role("admin")
    if redirect_response:
        return redirect_response

    conn = get_connection()
    worker = conn.execute(
        """SELECT workers.*, users.name, users.phone, users.address, users.created_at AS user_created_at
           FROM workers
           JOIN users ON users.id = workers.user_id
           WHERE workers.id = ?""",
        (worker_id,),
    ).fetchone()
    conn.close()

    if not worker:
        flash("Worker not found.", "error")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_worker_dossier.html", worker=worker)


@app.route("/admin/verify/worker/<worker_id>/approve", methods=["POST"])
def admin_worker_approve(worker_id):
    redirect_response = require_role("admin")
    if redirect_response:
        return redirect_response

    officer_remarks = request.form.get("officer_remarks", "Field toolkit audit passed at Regional Co-op Office. All 4 pillars accredited.").strip()
    coop_id = f"SHY-COOP-HYD-{worker_id[:5].upper()}"

    conn = get_connection()
    conn.execute(
        """UPDATE workers
           SET verified = 1, certified = 1, verification_status = 'verified',
               tools_verified = 1, officer_remarks = ?,
               coop_id = COALESCE(NULLIF(coop_id, ''), ?),
               verified_at = ?
           WHERE id = ?""",
        (officer_remarks, coop_id, now(), worker_id),
    )
    conn.commit()
    conn.close()
    flash("Worker verified! 4-Pillar Accreditation granted and Cold-Start boost activated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/verify/worker/<worker_id>/reject", methods=["POST"])
def admin_worker_reject(worker_id):
    redirect_response = require_role("admin")
    if redirect_response:
        return redirect_response

    officer_remarks = request.form.get("officer_remarks", "Incomplete verification details. Please update and resubmit.").strip()

    conn = get_connection()
    conn.execute(
        "UPDATE workers SET verification_status = 'rejected', officer_remarks = ? WHERE id = ?",
        (officer_remarks, worker_id),
    )
    conn.commit()
    conn.close()
    flash(f"Worker verification returned for correction: '{officer_remarks}'", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/verify/<worker_id>", methods=["POST"])
def admin_verify(worker_id):
    redirect_response = require_role("admin")
    if redirect_response:
        return redirect_response

    coop_id = f"SHY-COOP-HYD-{worker_id[:5].upper()}"
    conn = get_connection()
    conn.execute(
        """UPDATE workers
           SET verified = 1, certified = 1, verification_status = 'verified',
               tools_verified = 1,
               coop_id = COALESCE(NULLIF(coop_id, ''), ?),
               verified_at = ?
           WHERE id = ?""",
        (coop_id, now(), worker_id),
    )
    conn.commit()
    conn.close()
    flash("Worker verified! 4-Pillar Accreditation granted and Cold-Start boost activated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/welfare/disburse", methods=["POST"])
def admin_welfare_disburse():
    redirect_response = require_role("admin")
    if redirect_response:
        return redirect_response

    worker_id = request.form.get("worker_id")
    grant_type = request.form.get("grant_type", "Healthcare Emergency Assistance").strip()
    amount_raw = request.form.get("amount", "0").strip()
    officer_notes = request.form.get("officer_notes", "").strip()

    try:
        amount = float(amount_raw)
    except ValueError:
        amount = 0.0

    if not worker_id or amount <= 0:
        flash("Please select a valid worker and enter a positive grant amount.", "error")
        return redirect(url_for("admin_dashboard") + "#welfare")

    conn = get_connection()
    worker = conn.execute(
        "SELECT workers.*, users.name FROM workers JOIN users ON users.id = workers.user_id WHERE workers.id = ?",
        (worker_id,)
    ).fetchone()

    if not worker:
        conn.close()
        flash("Worker not found.", "error")
        return redirect(url_for("admin_dashboard") + "#welfare")

    disbursal_id = f"wgrant-{random.randint(1000, 9999)}"
    conn.execute(
        """INSERT INTO welfare_disbursals (id, worker_id, grant_type, amount, officer_notes, disbursed_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (disbursal_id, worker_id, grant_type, amount, officer_notes, now())
    )
    conn.commit()
    conn.close()

    flash(f"Welfare Grant of Rs.{amount} approved for {worker['name']} ({grant_type}). Disbursal receipt logged.", "success")
    return redirect(url_for("admin_dashboard") + "#welfare")


@app.route("/admin/worker/<worker_id>/retrain", methods=["POST"])
def admin_worker_retrain(worker_id):
    redirect_response = require_role("admin")
    if redirect_response:
        return redirect_response

    training_module = request.form.get("module", "NCCT Module 4 - Advanced Trade Standards & Customer Protocol").strip()
    conn = get_connection()
    worker = conn.execute("SELECT workers.*, users.name FROM workers JOIN users ON users.id = workers.user_id WHERE workers.id = ?", (worker_id,)).fetchone()
    if not worker:
        conn.close()
        flash("Worker not found.", "error")
        return redirect(url_for("admin_dashboard") + "#retraining")

    conn.execute(
        "UPDATE workers SET retraining_status = 'assigned' WHERE id = ?",
        (worker_id,)
    )
    conn.commit()
    conn.close()

    flash(f"Worker {worker['name']} assigned to {training_module} at Hyderabad Regional Co-op Institute.", "info")
    return redirect(url_for("admin_dashboard") + "#retraining")


@app.route("/admin/worker/<worker_id>/clear_retrain", methods=["POST"])
def admin_worker_clear_retrain(worker_id):
    redirect_response = require_role("admin")
    if redirect_response:
        return redirect_response

    conn = get_connection()
    worker = conn.execute("SELECT workers.*, users.name FROM workers JOIN users ON users.id = workers.user_id WHERE workers.id = ?", (worker_id,)).fetchone()
    if not worker:
        conn.close()
        flash("Worker not found.", "error")
        return redirect(url_for("admin_dashboard") + "#retraining")

    conn.execute(
        "UPDATE workers SET retraining_status = 'none' WHERE id = ?",
        (worker_id,)
    )
    conn.commit()
    conn.close()

    flash(f"NCCT Refresher Course completed! {worker['name']} recertified for full active dispatch.", "success")
    return redirect(url_for("admin_dashboard") + "#retraining")


# ---------------------------------------------------------------------------
# App startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
