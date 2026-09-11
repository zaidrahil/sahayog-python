"""
utils/geo.py
------------
Distance calculation and worker matching - the "geo-location based service
matching" feature from the SIH26089 problem statement.
"""

import math


def distance_km(lat1, lng1, lat2, lng2):
    """Haversine formula: great-circle distance between two lat/lng points,
    in kilometres. This is the standard formula for 'distance between two
    GPS coordinates on Earth' - the same idea used by ride-hailing and food
    delivery apps for their own matching."""
    if None in (lat1, lng1, lat2, lng2):
        return float("inf")

    R = 6371  # Earth's radius in kilometres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (math.sin(d_phi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def find_best_worker(workers, category, lat, lng, preferred_lang=None):
    """Given a list of worker rows, a required skill category, customer location,
    and optional preferred communication language, return the best match:

    1. Only verified, available workers with the required skill are considered.
    2. If preferred_lang is given, only workers fluent in that language are eligible.
    3. Prefer any worker within 15 km (prioritizing 2-3 km hyper-local zone).
    4. Among those, distance binning (0.5 km steps) with star-rating tiebreaker.

    Returns (worker_row, distance_km) or (None, None) if nobody qualifies.
    """
    eligible = [
        w for w in workers
        if w["verified"] and w["available"] and category in w["skills"].split(",")
    ]
    if not eligible:
        return None, None

    # Requirement 3: Language-gated matching
    if preferred_lang and preferred_lang.lower() not in ("any", ""):
        lang_target = preferred_lang.lower().strip()
        lang_matched = []
        for w in eligible:
            languages = [l.strip().lower() for l in (w["spoken_languages"] or "en,hi").split(",")] if "spoken_languages" in w.keys() else ["en", "hi"]
            if lang_target in languages:
                lang_matched.append(w)
        eligible = lang_matched
        if not eligible:
            return None, None

    scored = []
    for w in eligible:
        d = distance_km(lat, lng, w["lat"], w["lng"])
        scored.append((w, d))

    def sort_key(item):
        worker, d = item
        within_radius = d <= 15
        return (0 if within_radius else 1, round(d / 0.5), -worker["rating"])

    scored.sort(key=sort_key)
    best_worker, best_distance = scored[0]
    return best_worker, round(best_distance, 1)
