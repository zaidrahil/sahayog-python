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


def find_best_worker(workers, category, lat, lng):
    """Given a list of worker rows, a required skill category, and the
    customer's location, return the best match:

    1. Only verified, available workers with the required skill are considered.
    2. Prefer any worker within 15 km.
    3. Among those, prefer the nearest one - unless two are within 0.5 km of
       each other, in which case prefer the higher-rated worker (a tiebreaker
       so a slightly-further but much-better-rated worker can still win).

    Returns (worker_row, distance_km) or (None, None) if nobody qualifies.
    """
    eligible = [
        w for w in workers
        if w["verified"] and w["available"] and category in w["skills"].split(",")
    ]
    if not eligible:
        return None, None

    scored = []
    for w in eligible:
        d = distance_km(lat, lng, w["lat"], w["lng"])
        scored.append((w, d))

    def sort_key(item):
        worker, d = item
        within_radius = d <= 15
        # Python sorts tuples left-to-right: this puts "within radius" workers
        # first, then breaks ties by distance/rating as described above.
        return (0 if within_radius else 1, round(d / 0.5), -worker["rating"])

    scored.sort(key=sort_key)
    best_worker, best_distance = scored[0]
    return best_worker, round(best_distance, 1)
