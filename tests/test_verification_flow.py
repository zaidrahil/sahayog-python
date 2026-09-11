import requests
from bs4 import BeautifulSoup
import sqlite3

BASE_URL = "http://127.0.0.1:5000"

def test_verification_flow():
    # 0. Setup clean initial state for Mahesh Yadav
    conn = sqlite3.connect("data/sahayog.db")
    conn.execute(
        """UPDATE workers SET verified = 0, certified = 0, verification_status = 'submitted',
           aadhaar_last4 = '4819', cert_type = 'Skill India Digital (SID)', cert_id = 'SID-2026-TS-8910',
           peer_reference = 'Mukhiya Anand Rao', tools_verified = 1
           WHERE user_id = (SELECT id FROM users WHERE phone = '9111111115')"""
    )
    conn.commit()
    conn.row_factory = sqlite3.Row
    worker = conn.execute(
        "SELECT workers.*, users.phone, users.name FROM workers JOIN users ON users.id = workers.user_id WHERE users.phone = '9111111115'"
    ).fetchone()
    print(f"[TEST 1] Initial state of Mahesh Yadav: verified={worker['verified']}, status={worker['verification_status']}, cert_id={worker['cert_id']}")
    conn.close()

    # 2. Login as Mahesh Yadav (phone 9111111115 / worker123)
    s = requests.Session()
    login_res = s.post(f"{BASE_URL}/login", data={"phone": "9111111115", "password": "worker123"}, allow_redirects=True)
    assert login_res.status_code == 200, f"Login failed with status {login_res.status_code}"
    print("[TEST 2] Mahesh Yadav logged in successfully.")

    # 3. Check worker dashboard shows Submitted status
    dash_res = s.get(f"{BASE_URL}/worker")
    assert "4-Pillar Accreditation Under Review" in dash_res.text
    assert "XXXX-XXXX-4819" in dash_res.text
    assert "SID-2026-TS-8910" in dash_res.text
    print("[TEST 3] Worker dashboard displays 4-pillar review stage correctly.")

    # 4. Login as Admin (phone 9000000000 / admin123)
    admin_s = requests.Session()
    admin_login = admin_s.post(f"{BASE_URL}/login", data={"phone": "9000000000", "password": "admin123"}, allow_redirects=True)
    assert admin_login.status_code == 200
    print("[TEST 4] Admin logged in successfully.")

    admin_dash = admin_s.get(f"{BASE_URL}/admin")
    assert "4-Pillar Verification Desk" in admin_dash.text
    assert "Mahesh Yadav" in admin_dash.text
    assert "SID-2026-TS-8910" in admin_dash.text
    print("[TEST 5] Admin dashboard displays Mahesh Yadav with 4-pillar audit indicators.")

    # 5. Admin approves Mahesh Yadav
    worker_id = worker["id"]
    approve_res = admin_s.post(f"{BASE_URL}/admin/verify/{worker_id}", allow_redirects=True)
    assert approve_res.status_code == 200
    assert "Worker verified! 4-Pillar Accreditation granted and Cold-Start boost activated." in approve_res.text
    print("[TEST 6] Admin approved 4-pillar accreditation successfully.")

    # 6. Re-check Mahesh Yadav's dashboard
    dash_after = s.get(f"{BASE_URL}/worker")
    assert "COOPERATIVE ACCREDITATION PASSPORT" in dash_after.text
    assert "Certified Cooperative Master Craftsman" in dash_after.text
    assert "+25% Cold-Start Boost Active" in dash_after.text
    print("[TEST 7] Mahesh Yadav now has Certified Cooperative Craftsman Passport with cold-start boost active!")

    # 7. Test unsubmitted -> submission workflow
    # Let's reset Mahesh back to unsubmitted to test the submit form
    conn = sqlite3.connect("data/sahayog.db")
    conn.execute(
        "UPDATE workers SET verified = 0, certified = 0, verification_status = 'unsubmitted', aadhaar_last4 = NULL, cert_id = NULL WHERE id = ?",
        (worker_id,)
    )
    conn.commit()
    conn.close()

    dash_unsub = s.get(f"{BASE_URL}/worker")
    assert "Complete 4-Pillar Cooperative Accreditation Gate" in dash_unsub.text
    print("[TEST 8] Unsubmitted worker sees interactive 4-pillar credential submission wizard.")

    # Submit the 4-pillar form
    submit_res = s.post(f"{BASE_URL}/worker/verify/submit", data={
        "aadhaar_last4": "5566",
        "cert_type": "NCCT Master Craftsman",
        "cert_id": "NCCT-2026-HYD-5566",
        "peer_reference": "Gopal Verma - Co-op Guild #12",
        "police_declaration": "on",
        "tools_verified": "on"
    }, allow_redirects=True)
    assert submit_res.status_code == 200
    assert "4-Pillar accreditation credentials submitted!" in submit_res.text
    assert "4-Pillar Accreditation Under Review" in submit_res.text
    assert "XXXX-XXXX-5566" in submit_res.text
    assert "NCCT-2026-HYD-5566" in submit_res.text
    print("[TEST 9] Worker 4-pillar submission successfully processed and transitioned to review.")

    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY! [OK]")

if __name__ == "__main__":
    test_verification_flow()
