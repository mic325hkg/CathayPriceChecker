# cathay_core.py
import math
import re
import os
import sys
import yaml
import airportsdata
from amadeus import Client, ResponseError

ISO_DUR_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")

TYPE2_COUNTRIES = {"JP", "ID", "LK", "NP", "BD", "IN"}  # per Cathay Short-Type2 grouping concept

ZONE_BANDS = [
    ("ULTRA_SHORT", 1, 750),
    ("SHORT", 751, 2750),
    ("MEDIUM", 2751, 5000),
    ("LONG", 5001, 7500),
    ("ULTRA_LONG", 7501, 10**9),
]

def parse_iso_duration(dur: str) -> int:
    m = ISO_DUR_RE.match(dur or "")
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mi = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 60 + mi + (1 if s >= 30 else 0)

def fmt_minutes(m: int) -> str:
    h = m // 60
    mi = m % 60
    if h and mi:
        return f"{h}h {mi}m"
    if h:
        return f"{h}h"
    return f"{mi}m"

def haversine_miles(lat1, lon1, lat2, lon2) -> float:
    R = 3958.7613
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def classify_zone(segment_miles: float, origin_cc: str, dest_cc: str):
    for name, lo, hi in ZONE_BANDS:
        if lo <= segment_miles <= hi:
            if name == "SHORT":
                if (origin_cc in TYPE2_COUNTRIES) or (dest_cc in TYPE2_COUNTRIES):
                    return ("SHORT", "TYPE2")
                return ("SHORT", "TYPE1")
            return (name, None)
    return ("UNKNOWN", None)

def infer_cabin(travel_class: str) -> str:
    tc = (travel_class or "").upper()
    if tc in {"ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"}:
        return tc
    return "UNKNOWN"

def infer_fare_type_from_offer(offer: dict) -> str:
    for tp in offer.get("travelerPricings", []):
        for fds in tp.get("fareDetailsBySegment", []):
            bf = (fds.get("brandedFare") or fds.get("fareFamilyName") or "").upper()
            if "FLEX" in bf:
                return "FLEX"
            if "ESSENTIAL" in bf:
                return "ESSENTIAL"
            if "LIGHT" in bf:
                return "LIGHT"
    return "UNKNOWN"

def load_earning_table(path: str) -> dict:
    if not path or not os.path.exists(path):
        return {"version": None, "rules": []}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"version": None, "rules": []}

def find_earning_rule(table: dict, zone: str, short_type, cabin: str, fare_type: str, booking_class: str):
    for r in table.get("rules", []):
        if (r.get("zone") or "").upper() != zone:
            continue
        st = r.get("short_type")
        if (st is None and short_type is not None) or (st is not None and (st or "").upper() != (short_type or "").upper()):
            continue
        if (r.get("cabin") or "").upper() != cabin:
            continue
        if (r.get("fare_type") or "").upper() != fare_type:
            continue
        bcs = [x.upper() for x in (r.get("booking_classes") or [])]
        if booking_class.upper() in bcs:
            return r
    return None

def estimate_earnings(seg_rows, earning_table, fare_type):
    total_sp = 0
    total_am = 0
    per_seg = []
    for s in seg_rows:
        bc = (s.get("booking_class") or "?").upper()
        rule = find_earning_rule(
            earning_table,
            zone=s["zone"],
            short_type=s["short_type"],
            cabin=s["cabin"],
            fare_type=fare_type,
            booking_class=bc
        )
        if rule:
            sp = int(rule.get("status_points", 0))
            am = int(rule.get("asia_miles", 0))
            total_sp += sp
            total_am += am
        else:
            sp = None
            am = None
        per_seg.append({"segment": s, "status_points": sp, "asia_miles": am})
    return total_sp, total_am, per_seg

def amadeus_client(client_id: str, client_secret: str, hostname: str = None):
    kwargs = {"client_id": client_id, "client_secret": client_secret}
    if hostname:
        kwargs["hostname"] = hostname
    return Client(**kwargs)

def search_offers(client_id: str, client_secret: str, origin: str, dest: str, date: str,
                 adults: int = 1, currency: str = "HKD", max_results: int = 20, hostname: str = None):
    am = amadeus_client(client_id, client_secret, hostname)
    try:
        resp = am.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=dest,
            departureDate=date,
            adults=adults,
            currencyCode=currency,
            max=max_results,
        )
        return resp.data
    except ResponseError as e:
        raise RuntimeError(f"Amadeus API error: {e}")

def offer_is_all_cx(offer: dict) -> bool:
    for it in offer.get("itineraries", []):
        for seg in it.get("segments", []):
            if (seg.get("carrierCode") or "").upper() != "CX":
                return False
    return True

def compute_offer_metrics(offer: dict, airports):
    total_minutes = 0
    total_miles = 0.0
    seg_rows = []

    seg_fare = {}
    for tp in offer.get("travelerPricings", []):
        for fds in tp.get("fareDetailsBySegment", []):
            sid = fds.get("segmentId")
            if sid:
                seg_fare[sid] = (
                    (fds.get("class") or "").upper(),  # booking class
                    (fds.get("cabin") or fds.get("travelClass") or "")  # cabin/travel class
                )

    for it in offer.get("itineraries", []):
        total_minutes += parse_iso_duration(it.get("duration", ""))
        for seg in it.get("segments", []):
            dep = seg.get("departure", {})
            arr = seg.get("arrival", {})
            o = dep.get("iataCode")
            d = arr.get("iataCode")

            orec = airports.get(o)
            drec = airports.get(d)

            if orec and drec:
                seg_mi = haversine_miles(orec["lat"], orec["lon"], drec["lat"], drec["lon"])
                origin_cc = orec.get("country")
                dest_cc = drec.get("country")
                zone, short_type = classify_zone(seg_mi, origin_cc, dest_cc)
            else:
                seg_mi = None
                origin_cc = None
                dest_cc = None
                zone, short_type = ("UNKNOWN", None)

            total_miles += (seg_mi or 0.0)

            seg_id = seg.get("id")
            booking_class, travel_class = seg_fare.get(seg_id, ("", ""))
            cabin = infer_cabin(travel_class)

            seg_rows.append({
                "segment_id": seg_id,
                "from": o,
                "to": d,
                "dep_at": dep.get("at"),
                "arr_at": arr.get("at"),
                "flight": f"{seg.get('carrierCode','')}{seg.get('number','')}",
                "aircraft": (seg.get("aircraft") or {}).get("code", ""),
                "duration_min": parse_iso_duration(seg.get("duration", "")),
                "distance_mi": seg_mi,
                "zone": zone,
                "short_type": short_type,
                "booking_class": booking_class or "?",
                "cabin": cabin,
                "origin_country": origin_cc,
                "dest_country": dest_cc,
            })

    return total_minutes, total_miles, seg_rows

def load_airports():
    return airportsdata.load("IATA")