import requests

BASE_URL = "http://127.0.0.1:5000"

def test_customer_tabs_live():
    s = requests.Session()
    # 1. Login as Priya Sharma (Customer)
    login_res = s.post(f"{BASE_URL}/login", data={"phone": "9333333331", "password": "customer123"}, allow_redirects=True)
    assert login_res.status_code == 200, f"Login failed: {login_res.status_code}"
    print("[PASS] Priya Sharma logged in successfully.")

    # 2. Check customer dashboard for tabs
    dash_res = s.get(f"{BASE_URL}/customer")
    assert dash_res.status_code == 200
    html = dash_res.text

    assert "customer-tabs-nav" in html, "customer-tabs-nav not found"
    assert 'id="tab-btn-book"' in html, "tab-btn-book not found"
    assert 'id="tab-btn-bookings"' in html, "tab-btn-bookings not found"
    assert 'id="pane-book"' in html, "pane-book not found"
    assert 'id="pane-bookings"' in html, "pane-bookings not found"
    assert "switchCustomerTab" in html, "switchCustomerTab not found"
    assert "booking-studio-grid" in html, "booking-studio-grid not found"
    assert "bookings-tracker-wrapper" in html, "bookings-tracker-wrapper not found"
    print("[PASS] Customer dashboard contains modern tab navigation and balanced studio.")

    # 3. Test booking redirect has #bookings hash
    book_res = s.post(
        f"{BASE_URL}/customer/book",
        data={
            "category": "electrician",
            "description": "Switchboard sparkling test with tabbed interface",
            "lat": "17.4450",
            "lng": "78.3950",
            "preferred_lang": "en"
        },
        allow_redirects=False
    )
    assert book_res.status_code == 302, f"Expected 302 redirect, got {book_res.status_code}"
    location = book_res.headers.get("Location", "")
    assert location.endswith("/customer#bookings"), f"Location does not end with /customer#bookings: {location}"
    print(f"[PASS] Booking correctly redirected to {location} with #bookings hash.")

if __name__ == "__main__":
    test_customer_tabs_live()
    print("ALL TESTS PASSED!")
