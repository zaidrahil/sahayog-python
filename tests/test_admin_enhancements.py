import requests
import sqlite3
from bs4 import BeautifulSoup

BASE_URL = "http://127.0.0.1:5000"

def test_admin_enhancements_live():
    s = requests.Session()

    # 1. Login as Federation Admin
    login_res = s.post(f"{BASE_URL}/login", data={"phone": "9000000000", "password": "admin123"}, allow_redirects=True)
    assert login_res.status_code == 200, f"Login failed: {login_res.status_code}"
    print("[PASS] Federation Admin logged in successfully.")

    # 2. Inspect Admin Dashboard HTML
    dash_res = s.get(f"{BASE_URL}/admin")
    assert dash_res.status_code == 200
    html = dash_res.text
    soup = BeautifulSoup(html, "html.parser")

    # Check 3 Streamlined Tabs
    expected_tabs = [
        "tab-btn-telemetry",
        "tab-btn-verification",
        "tab-btn-welfare"
    ]
    for tab_id in expected_tabs:
        btn = soup.select_one(f"#{tab_id}")
        assert btn is not None, f"Tab button {tab_id} not found!"

    # Check 3 Tab Panes
    expected_panes = [
        "pane-telemetry",
        "pane-verification",
        "pane-welfare"
    ]
    for pane_id in expected_panes:
        pane = soup.select_one(f"#{pane_id}")
        assert pane is not None, f"Tab pane {pane_id} not found!"

    # Check Central Fleet Map
    fleet_map = soup.select_one("#admin-fleet-map")
    assert fleet_map is not None, "admin-fleet-map element not found!"
    assert "initAdminFleetMap" in html, "initAdminFleetMap JS function not found!"

    # Check Welfare Desk and Ledger
    assert "welfare-disburse-card" in html, "welfare-disburse-card not found!"
    assert "Complete Financial Settlement Ledger" in html, "Financial settlement ledger heading not found!"
    print("[PASS] Admin Dashboard contains 3 clean command tabs, fleet map container, and welfare ledger.")

    # 3. Test Welfare Grant Disbursal
    conn = sqlite3.connect("data/sahayog.db")
    conn.row_factory = sqlite3.Row
    worker = conn.execute("SELECT workers.id, users.name FROM workers JOIN users ON users.id = workers.user_id LIMIT 1").fetchone()
    worker_id = worker["id"]
    conn.close()

    grant_res = s.post(
        f"{BASE_URL}/admin/welfare/disburse",
        data={
            "worker_id": worker_id,
            "grant_type": "Children Education & Books Grant",
            "amount": "1200",
            "officer_notes": "Approved test education grant for technician dependent."
        },
        allow_redirects=False
    )
    assert grant_res.status_code == 302, f"Expected 302 redirect, got {grant_res.status_code}"
    assert grant_res.headers.get("Location", "").endswith("/admin#welfare")
    print("[PASS] Welfare grant disbursal processed and redirected to /admin#welfare.")

    # Verify grant in database
    conn = sqlite3.connect("data/sahayog.db")
    conn.row_factory = sqlite3.Row
    logged_grant = conn.execute(
        "SELECT * FROM welfare_disbursals WHERE worker_id = ? ORDER BY disbursed_at DESC LIMIT 1",
        (worker_id,)
    ).fetchone()
    conn.close()
    assert logged_grant is not None
    assert logged_grant["amount"] == 1200.0
    assert logged_grant["grant_type"] == "Children Education & Books Grant"
    print("[PASS] Welfare grant verified in SQLite database.")

    # 4. Test NCCT Retraining Assignment
    retrain_res = s.post(
        f"{BASE_URL}/admin/worker/{worker_id}/retrain",
        data={"module": "NCCT Module 4 - Advanced Trade Standards & Customer Protocol"},
        allow_redirects=False
    )
    assert retrain_res.status_code == 302
    assert retrain_res.headers.get("Location", "").endswith("/admin#retraining")

    conn = sqlite3.connect("data/sahayog.db")
    conn.row_factory = sqlite3.Row
    w_after = conn.execute("SELECT retraining_status FROM workers WHERE id = ?", (worker_id,)).fetchone()
    conn.close()
    assert w_after["retraining_status"] == "assigned"
    print("[PASS] Worker assigned to NCCT retraining successfully.")

    # 5. Test NCCT Retraining Clearance / Recertification
    clear_res = s.post(
        f"{BASE_URL}/admin/worker/{worker_id}/clear_retrain",
        allow_redirects=False
    )
    assert clear_res.status_code == 302
    assert clear_res.headers.get("Location", "").endswith("/admin#retraining")

    conn = sqlite3.connect("data/sahayog.db")
    conn.row_factory = sqlite3.Row
    w_cleared = conn.execute("SELECT retraining_status FROM workers WHERE id = ?", (worker_id,)).fetchone()
    conn.close()
    assert w_cleared["retraining_status"] == "none"
    print("[PASS] Worker recertified and retraining cleared successfully.")

if __name__ == "__main__":
    test_admin_enhancements_live()
    print("\nALL ADMIN ENHANCEMENT TESTS PASSED! [OK]")
