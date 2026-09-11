import requests
import sqlite3

BASE_URL = "http://127.0.0.1:5000"

def test_detailed_verification_suite():
    # 0. Set Mahesh Yadav to initial submitted state
    conn = sqlite3.connect("data/sahayog.db")
    conn.execute(
        """UPDATE workers
           SET verified = 0, certified = 0, verification_status = 'submitted',
               aadhaar_last4 = '4819', aadhaar_name = 'Mahesh Yadav', aadhaar_dob = '1993-08-22',
               cert_type = 'Skill India Digital (SID)', cert_id = 'SID-2026-TS-8910',
               cert_level = 'NSQF Level 4 (Certified Electrician)', cert_issue_year = '2024',
               peer_reference = 'Mukhiya Anand Rao (Fed #102)', peer_phone = '9876501234',
               pcc_number = 'CCTNS-TS-2026-44019',
               toolkit_items = 'Heavy Duty Drill, Pipe Wrench Set, Digital Multimeter, Insulated Cutters, Safety Goggles & Gloves',
               tools_verified = 1, coop_id = 'SHY-COOP-HYD-04819', officer_remarks = NULL
           WHERE user_id = (SELECT id FROM users WHERE phone = '9111111115')"""
    )
    conn.commit()
    conn.row_factory = sqlite3.Row
    worker = conn.execute(
        "SELECT workers.*, users.phone, users.name FROM workers JOIN users ON users.id = workers.user_id WHERE users.phone = '9111111115'"
    ).fetchone()
    worker_id = worker["id"]
    conn.close()

    print(f"[TEST 1] Reset Mahesh Yadav (ID: {worker_id}) to clean submitted state.")

    # 1. Login as Mahesh Yadav (9111111115 / worker123)
    s = requests.Session()
    login_res = s.post(f"{BASE_URL}/login", data={"phone": "9111111115", "password": "worker123"}, allow_redirects=True)
    assert login_res.status_code == 200
    print("[TEST 2] Mahesh Yadav logged in successfully.")

    # 2. Access /worker/verification portal
    portal_res = s.get(f"{BASE_URL}/worker/verification")
    assert portal_res.status_code == 200
    assert "Cooperative Craftsman 4-Pillar Verification Portal" in portal_res.text
    assert "Pillar 1: Government Identity &amp; UIDAI e-KYC" in portal_res.text
    assert "XXXX-XXXX-4819" in portal_res.text
    assert "Pillar 2: NCCT &amp; Technical Trade Certification" in portal_res.text
    assert "SID-2026-TS-8910" in portal_res.text
    assert "Pillar 3: Background &amp; Cooperative Peer Endorsement" in portal_res.text
    assert "Mukhiya Anand Rao (Fed #102)" in portal_res.text
    assert "Pillar 4: Physical Tool-Kit &amp; Safety Equipment Audit" in portal_res.text
    assert "SAHAYOG LABOUR COOPERATIVE FEDERATION" in portal_res.text
    assert "SHY-COOP-HYD-04819" in portal_res.text
    print("[TEST 3] Detailed Worker Verification Portal & Smart Digital ID rendered with all 4 pillars.")

    # 3. Test saving detailed dossier via /worker/verification/save
    save_res = s.post(f"{BASE_URL}/worker/verification/save", data={
        "aadhaar_last4": "4819",
        "aadhaar_name": "Mahesh Kumar Yadav",
        "aadhaar_dob": "1993-08-22",
        "cert_type": "NCCT Master Craftsman",
        "cert_id": "NCCT-HYD-2026-4819",
        "cert_level": "NSQF Level 5 (Master Craftsman)",
        "cert_issue_year": "2025",
        "peer_reference": "Senior Craftsman Bikash Mohanty (#042)",
        "peer_phone": "9848123456",
        "pcc_number": "CCTNS-TS-2026-99012",
        "police_declaration": "on",
        "toolkit_items": "1000V Insulated Screwdriver Set, Digital Clamp Meter, Safety Helmet, Leather Gloves, Heavy Duty Tool Bag",
        "tools_verified": "on"
    }, allow_redirects=True)
    assert save_res.status_code == 200
    assert "Comprehensive 4-Pillar verification saved" in save_res.text
    assert "NCCT-HYD-2026-4819" in save_res.text
    print("[TEST 4] Worker successfully saved and updated detailed 4-pillar verification.")

    # 4. Login as Admin (9000000000 / admin123)
    admin_s = requests.Session()
    admin_login = admin_s.post(f"{BASE_URL}/login", data={"phone": "9000000000", "password": "admin123"}, allow_redirects=True)
    assert admin_login.status_code == 200
    print("[TEST 5] Admin logged in successfully.")

    # 5. Access Admin Verification View: /admin/verify/worker/<worker_id>
    dossier_res = admin_s.get(f"{BASE_URL}/admin/verify/worker/{worker_id}")
    assert dossier_res.status_code == 200
    assert f"4-Pillar Verification: Mahesh Yadav" in dossier_res.text
    assert "NCCT-HYD-2026-4819" in dossier_res.text
    assert "Senior Craftsman Bikash Mohanty" in dossier_res.text
    assert "1000V Insulated Screwdriver Set" in dossier_res.text
    assert "Grant 4-Pillar Accreditation &amp; Issue Passport" in dossier_res.text
    print("[TEST 6] Admin successfully opened and inspected detailed 4-pillar audit dossier.")

    # 6. Admin approves dossier with custom officer remarks
    approve_res = admin_s.post(f"{BASE_URL}/admin/verify/worker/{worker_id}/approve", data={
        "officer_remarks": "In-person toolkit inspection completed at Hyderabad Central Federation on 11-Sep-2026. All 4 pillars verified."
    }, allow_redirects=True)
    assert approve_res.status_code == 200
    assert "Worker verified! 4-Pillar Accreditation granted" in approve_res.text
    print("[TEST 7] Federation Officer approved 4-pillar accreditation.")

    # 7. Re-check Worker Portal as Mahesh Yadav
    worker_after = s.get(f"{BASE_URL}/worker/verification")
    assert "Fully Accredited Master Craftsman" in worker_after.text
    assert "In-person toolkit inspection completed at Hyderabad Central Federation" in worker_after.text
    assert "+25% Cold-Start Boost" in worker_after.text
    print("[TEST 8] Worker portal displays Fully Accredited Master Craftsman status with officer remarks!")

    print("\nALL DETAILED VERIFICATION TESTS PASSED SUCCESSFULLY! [OK]")

if __name__ == "__main__":
    test_detailed_verification_suite()
