# Sahayog (Python Edition) — Cooperative Gig Services Platform

A working prototype for **SIH26089** (Ministry of Cooperation / National Council for
Cooperative Training), rewritten in **Python (Flask) with SQLite** for readability and
to make the codebase approachable if you're learning full-stack development.

This does the exact same thing as the Node.js version — worker registration & verification,
geo-matched bookings, digital payments with an automatic worker welfare-wallet contribution,
ratings, an admin/federation dashboard, AI-style demand forecasting, and English/Hindi
multilingual support — but in about 500 lines of very plain Python, with a real SQL database
you can open and inspect directly.

---

> 📘 **Project Documentation & Hackathon Deliverables:**  
> - **[PROJECT_DESCRIPTION.md](PROJECT_DESCRIPTION.md)**: Master project architecture, database schemas, ER diagrams, route catalog, and maintenance protocols.
> - **[FAIR_WORKER_ALLOCATION_SYSTEM.md](FAIR_WORKER_ALLOCATION_SYSTEM.md)**: Detailed design specification for Aadhaar verification, fatigue limits, cold-start boost, 2-3km geofencing, escrow settlement, 22-language matching, and NCCT retraining.
> - **[sahayog_sih_presentation.pptx](sahayog_sih_presentation.pptx)**: Official 16:9 SIH PowerPoint presentation with custom visuals and embedded speaker notes.
> - **[PRESENTATION_NOTES.md](PRESENTATION_NOTES.md)**: Full slide-by-slide presenter script, timing blueprint, and jury viva defense guide.

---

## Why this version is easier to read

- **One route = one function.** Every URL in the app (`/customer/book`, `/worker/accept/<id>`,
  etc.) is a single Python function in `app.py` you can read top to bottom.
- **Plain SQL, no ORM.** `database.py` uses Python's built-in `sqlite3` module with visible
  `SELECT`/`INSERT`/`UPDATE` statements — no SQLAlchemy models or hidden query generation.
  If you know basic SQL, you can follow exactly what every function does.
- **Server-rendered pages, minimal JavaScript.** Forms POST directly to Flask routes and the
  page reloads with the result (the classic, simplest web-app pattern) — there's no separate
  frontend build step, no API client, no token management to reason about.
- **A real, inspectable database file.** `data/sahayog.db` is a single SQLite file. You can
  open it with any SQLite browser (e.g. "DB Browser for SQLite") and literally look at the
  tables and rows while the app runs.

---

## Quick start

Requirements: **Python 3.8+**

```bash
cd sahayog-python
pip install -r requirements.txt   # installs Flask - that's the only dependency
python seed.py                     # creates data/sahayog.db with demo data
python app.py                       # starts the server
```

Then open **http://localhost:5000** in your browser.

### Demo accounts

| Role | Phone | Password | Notes |
|---|---|---|---|
| Admin (federation office) | `9000000000` | `admin123` | |
| Worker | `9111111111` | `worker123` | Ramesh Kumar — verified electrician |
| Worker | `9111111115` | `worker123` | Mahesh Yadav — unverified, try verifying him as admin |
| Customer | `9333333331` | `customer123` | Priya Sharma |

When booking as a customer, use latitude/longitude around **17.44, 78.40** (Hyderabad) to
match the seeded workers.

---

## Project structure

```
sahayog-python/
├── app.py                  Main Flask application - every route lives here
├── database.py               SQLite schema + connection helper
├── seed.py                     Populates demo data
├── translations.py               English/Hindi text dictionary
├── requirements.txt
├── utils/
│   ├── geo.py                    Haversine distance + nearest-worker matching
│   └── forecast.py                Demand forecasting model
├── templates/                  Jinja2 HTML templates (server-rendered)
│   ├── base.html                 Shared layout: nav, flash messages, footer
│   ├── index.html                  Landing page + login/register forms
│   ├── customer_dashboard.html
│   ├── worker_dashboard.html
│   └── admin_dashboard.html
├── static/
│   └── css/style.css              Shared design system
└── data/
    └── sahayog.db                 Created by seed.py - the actual database file
```

---

## How each problem-statement requirement is implemented

| PS requirement | Where |
|---|---|
| Service provider registration & verification | `register()` in `app.py`; new workers start `verified = 0` until an admin clicks "Verify worker" (`admin_verify()`) |
| Worker skill profiling & certification | `workers.skills` column; `certified` flag set together with `verified` |
| Customer booking & scheduling | `customer_book()` |
| Geo-location based service matching | `utils/geo.py` — haversine distance, nearest verified worker with the right skill wins, rating breaks near-ties |
| Digital payments & invoicing | `customer_pay()` — generates an invoice number, splits the payment |
| Rating & feedback | `customer_rate()` — updates the worker's running average |
| Worker welfare & insurance integration | Every payment automatically adds 5% to `workers.welfare_wallet` |
| Emergency / on-demand booking | `bookings.urgent` flag, shown as a badge everywhere |
| Cooperative federation admin dashboard | `admin_dashboard()` — stats, pending verifications, category breakdown |
| Multilingual application | `translations.py` + `t()` helper used in every template; toggle in the nav bar |
| AI-based demand forecasting | `utils/forecast.py` — computes expected bookings per category/time-slot from real history |

### The cooperative payment split (the core idea of the pitch, in code)

```python
FEDERATION_COMMISSION_PCT = 0.08   # 8% retained by the cooperative federation
WELFARE_CONTRIBUTION_PCT = 0.05   # 5% auto-contributed to the worker's welfare wallet
```

These live as named constants at the top of `app.py` — not hidden logic — so a federation
admin could change them for a real deployment without hunting through the codebase.

---

## Moving toward production

- Swap SQLite for PostgreSQL (only `database.py` would need to change — every route calls
  `get_connection()` and plain SQL, so the rest of the app stays the same).
- Replace the mock payment logic in `customer_pay()` with a real gateway (Razorpay/UPI PSP).
- Replace the manual "Verify worker" button with real Aadhaar e-KYC + DigiLocker integration.
- Use `flask run` behind a production WSGI server (gunicorn/uWSGI) instead of the Flask
  development server started by `python app.py`.

---

## License

MIT — built as a Smart India Hackathon prototype for SIH26089. Not an official government
service.
