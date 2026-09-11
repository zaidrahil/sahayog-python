"""
utils/forecast.py
------------------
"AI-based demand forecasting and workforce allocation" - the last feature
in the problem statement's expected-solution list.

This uses a simple, transparent statistical model (not a black-box neural
network) so it's easy to explain in a viva/demo: count how many bookings
happened in each 3-hour time slot for each category, then project a 10%
growth buffer as the "expected" demand for that slot next time, and
recommend enough workers to cover it (roughly one worker per two bookings
in a slot). A production system would replace this function with a proper
time-series model (e.g. Prophet or an LSTM, as described in the pitch
deck's Technical Approach) - the rest of the application would not need to
change, since this function's inputs/outputs would stay the same.
"""

from datetime import datetime
from collections import defaultdict

from database import SERVICE_CATEGORIES


def forecast_demand(bookings):
    """bookings: list of sqlite3.Row objects with 'category' and 'created_at'.
    Returns a list of dicts, sorted by expected demand descending.
    """
    # Count bookings per (category, hour-of-day)
    counts = defaultdict(int)
    for b in bookings:
        created = datetime.fromisoformat(b["created_at"])
        counts[(b["category"], created.hour)] += 1

    results = []
    for category_id, label in SERVICE_CATEGORIES:
        for slot_start in range(0, 24, 3):  # eight 3-hour slots per day
            total = sum(counts.get((category_id, h), 0) for h in range(slot_start, slot_start + 3))
            if total == 0:
                continue
            expected = round(total * 1.1, 1)          # 10% growth buffer
            recommended_workers = max(1, -(-expected // 2))  # ceil(expected / 2)
            results.append({
                "category": category_id,
                "label": label,
                "slot": f"{slot_start:02d}:00-{slot_start + 3:02d}:00",
                "observed": total,
                "expected": expected,
                "recommended_workers": int(recommended_workers),
            })

    results.sort(key=lambda r: r["expected"], reverse=True)
    return results
