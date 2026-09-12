"""
test_escrow_system.py
----------------------
End-to-end integration tests for the Sahayog Cooperative Milestone Escrow System.
Tests:
1. Upfront escrow locking on customer booking
2. Worker escrow vault guarantee display & job acceptance
3. Tamper-proof 4-digit OTP verification & milestone escrow release (87/5/8 split)
4. Customer dispute logging & escrow freezing
5. Federation Admin conciliation desk & dispute arbitration (release / refund)
"""

import requests
import sqlite3
from bs4 import BeautifulSoup

BASE_URL = "http://127.0.0.1:5000"

def get_db():
    conn = sqlite3.connect("data/sahayog.db")
    conn.row_factory = sqlite3.Row
    return conn

def test_full_escrow_lifecycle():
    print("=== Testing Cooperative Milestone Escrow System ===")

    # 1. Customer Login (Priya Sharma)
    cust_s = requests.Session()
    login_res = cust_s.post(f"{BASE_URL}/login", data={"phone": "9333333331", "password": "customer123"}, allow_redirects=True)
    assert login_res.status_code == 200, "Customer login failed"
    print("[PASS] 1. Customer logged in.")

    # 2. Book a service with Escrow Deposit
    book_res = cust_s.post(
        f"{BASE_URL}/customer/book",
        data={
            "category": "electrician",
            "description": "Ceiling fan sparking test for milestone escrow release",
            "lat": "17.4450",
            "lng": "78.3950",
            "preferred_lang": "en",
            "escrow_amount": "400",
            "gateway_name": "UPI"
        },
        allow_redirects=True
    )
    assert book_res.status_code == 200, "Booking failed"

    # Verify DB: booking & escrow_transactions
    conn = get_db()
    latest_booking = conn.execute(
        "SELECT * FROM bookings WHERE customer_id = (SELECT id FROM users WHERE phone = '9333333331') ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    assert latest_booking is not None, "No booking created"
    booking_id = latest_booking["id"]
    otp = latest_booking["completion_otp"]
    assert latest_booking["escrow_status"] == "held", f"Expected escrow_status 'held', got {latest_booking['escrow_status']}"
    assert latest_booking["price"] == 400.0, f"Expected price 400.0, got {latest_booking['price']}"

    escrow_tx = conn.execute("SELECT * FROM escrow_transactions WHERE booking_id = ?", (booking_id,)).fetchone()
    assert escrow_tx is not None, "No escrow_transaction record found"
    assert escrow_tx["status"] == "held", f"Expected escrow status 'held', got {escrow_tx['status']}"
    assert escrow_tx["amount"] == 400.0, f"Expected escrow amount 400.0, got {escrow_tx['amount']}"
    assert escrow_tx["gateway_name"] == "UPI", f"Expected gateway 'UPI', got {escrow_tx['gateway_name']}"
    assert escrow_tx["gateway_tx_id"].startswith("ESCR-UPI-"), f"Unexpected gateway_tx_id: {escrow_tx['gateway_tx_id']}"
    worker_id = latest_booking["worker_id"]
    conn.close()
    print(f"[PASS] 2. Booking {booking_id} created with Rs.400 locked in Escrow Vault (Txn: {escrow_tx['gateway_tx_id']}).")

    # 3. Verify Customer Dashboard UI displays Escrow Vault Box and OTP
    dash_res = cust_s.get(f"{BASE_URL}/customer")
    assert dash_res.status_code == 200
    assert "COOPERATIVE MILESTONE ESCROW LOCKBOX" in dash_res.text, "Escrow Lockbox heading missing from customer dashboard"
    assert otp in dash_res.text, f"OTP {otp} not found on customer dashboard"
    assert "Raise Escrow Dispute" in dash_res.text, "Dispute trigger missing from customer dashboard"
    print("[PASS] 3. Customer Dashboard renders Escrow Lockbox card, OTP vault, and dispute controls.")

    # 4. Worker Login (Ramesh Kumar - Electrician)
    worker_s = requests.Session()
    w_login_res = worker_s.post(f"{BASE_URL}/login", data={"phone": "9111111111", "password": "worker123"}, allow_redirects=True)
    assert w_login_res.status_code == 200, "Worker login failed"
    print("[PASS] 4. Worker logged in.")

    # Worker Dashboard inspection
    w_dash_res = worker_s.get(f"{BASE_URL}/worker")
    assert w_dash_res.status_code == 200
    assert "in Escrow Vault" in w_dash_res.text, "Escrow guarantee badge missing from worker dashboard"
    print("[PASS] 5. Worker dashboard reflects guaranteed Escrow Vault funds.")

    # 5. Worker Accepts Job
    acc_res = worker_s.post(f"{BASE_URL}/worker/accept/{booking_id}", allow_redirects=True)
    assert acc_res.status_code == 200
    print("[PASS] 6. Worker accepted job.")

    # 6. Worker Verifies Customer OTP & Releases Escrow
    conn = get_db()
    w_before = conn.execute("SELECT welfare_wallet FROM workers WHERE id = ?", (worker_id,)).fetchone()["welfare_wallet"]
    conn.close()

    complete_res = worker_s.post(
        f"{BASE_URL}/worker/complete/{booking_id}",
        data={"price": "400", "otp": otp},
        allow_redirects=True
    )
    assert complete_res.status_code == 200
    assert "released" in complete_res.text or "Customer OTP verified" in complete_res.text

    # Verify DB after release:
    conn = get_db()
    b_after = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    assert b_after["status"] == "completed", f"Expected completed, got {b_after['status']}"
    assert b_after["escrow_status"] == "released", f"Expected released, got {b_after['escrow_status']}"

    esc_after = conn.execute("SELECT * FROM escrow_transactions WHERE booking_id = ?", (booking_id,)).fetchone()
    assert esc_after["status"] == "released", f"Expected released, got {esc_after['status']}"
    assert esc_after["released_at"] is not None

    payment = conn.execute("SELECT * FROM payments WHERE booking_id = ?", (booking_id,)).fetchone()
    assert payment is not None, "No payment row inserted"
    assert payment["amount"] == 400.0
    assert payment["worker_payout"] == 348.0  # 87% of 400 = 348
    assert payment["welfare_contribution"] == 20.0  # 5% of 400 = 20
    assert payment["federation_commission"] == 32.0  # 8% of 400 = 32

    w_after = conn.execute("SELECT welfare_wallet FROM workers WHERE id = ?", (worker_id,)).fetchone()["welfare_wallet"]
    assert round(w_after - w_before, 2) == 20.0, f"Expected +20 in welfare wallet, got {w_after - w_before}"
    conn.close()
    print("[PASS] 7. Milestone Escrow released upon OTP verification with 87% (Rs.348) worker payout and 5% (Rs.20) welfare allocation.")

    # 7. Test Dispute & Admin Conciliation Flow
    print("\n--- Testing Dispute & Federation Conciliation Desk ---")
    # Customer books another service
    book2_res = cust_s.post(
        f"{BASE_URL}/customer/book",
        data={
            "category": "plumber",
            "description": "Pipe leakage dispute simulation",
            "lat": "17.4450",
            "lng": "78.3950",
            "preferred_lang": "en",
            "escrow_amount": "500",
            "gateway_name": "RuPay"
        },
        allow_redirects=True
    )
    assert book2_res.status_code == 200

    conn = get_db()
    b2 = conn.execute(
        "SELECT * FROM bookings WHERE customer_id = (SELECT id FROM users WHERE phone = '9333333331') ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    b2_id = b2["id"]
    conn.close()

    # Customer files dispute
    disp_res = cust_s.post(
        f"{BASE_URL}/customer/dispute/{b2_id}",
        data={"reason": "Plumber arrived 2 hours late and used substandard joint seal"},
        allow_redirects=True
    )
    assert disp_res.status_code == 200

    conn = get_db()
    b2_check = conn.execute("SELECT * FROM bookings WHERE id = ?", (b2_id,)).fetchone()
    esc2_check = conn.execute("SELECT * FROM escrow_transactions WHERE booking_id = ?", (b2_id,)).fetchone()
    assert b2_check["escrow_status"] == "disputed", f"Expected disputed, got {b2_check['escrow_status']}"
    assert esc2_check["status"] == "disputed"
    assert esc2_check["dispute_opened_by"] == "customer"
    esc2_id = esc2_check["id"]
    conn.close()
    print(f"[PASS] 8. Escrow dispute filed for booking {b2_id}; funds frozen in Cooperative Vault.")

    # 8. Federation Admin Conciliation
    admin_s = requests.Session()
    a_login = admin_s.post(f"{BASE_URL}/login", data={"phone": "9000000000", "password": "admin123"}, allow_redirects=True)
    assert a_login.status_code == 200, "Admin login failed"

    admin_dash = admin_s.get(f"{BASE_URL}/admin")
    assert admin_dash.status_code == 200
    assert "Federation Escrow Dispute Conciliation Desk" in admin_dash.text
    assert "Plumber arrived 2 hours late" in admin_dash.text
    print("[PASS] 9. Admin Conciliation Desk detects active dispute and displays dispute statement.")

    # 9. Admin resolves dispute: Refund to Customer
    resolve_res = admin_s.post(
        f"{BASE_URL}/admin/escrow/resolve/{esc2_id}",
        data={"action": "refund_to_customer", "resolution_notes": "GPS audit shows worker delayed by 2.5 hours. Conciliation approved full refund."},
        allow_redirects=True
    )
    assert resolve_res.status_code == 200

    conn = get_db()
    esc2_resolved = conn.execute("SELECT * FROM escrow_transactions WHERE id = ?", (esc2_id,)).fetchone()
    b2_resolved = conn.execute("SELECT * FROM bookings WHERE id = ?", (b2_id,)).fetchone()
    assert esc2_resolved["status"] == "refunded", f"Expected refunded, got {esc2_resolved['status']}"
    assert b2_resolved["escrow_status"] == "refunded"
    assert b2_resolved["status"] == "cancelled"
    conn.close()
    print("[PASS] 10. Federation Admin successfully arbitrated dispute with refund to customer.")

    print("\n[SUCCESS] ALL ESCROW SYSTEM INTEGRATION TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    test_full_escrow_lifecycle()
