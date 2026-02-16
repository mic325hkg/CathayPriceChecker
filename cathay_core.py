# cathay_core.py
import math
import re
import os
import yaml
import airportsdata
from datetime import datetime, timedelta
from amadeus import Client, ResponseError

ISO_DUR_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")

ALLOWED_TRAVEL_CLASSES = {"ANY", "ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"}

# Candidate NEW ORIGINS by region (editable)
NEW_ORIGIN_POOLS = {
    "China": ["PEK", "PKX", "PVG", "SHA", "CAN", "SZX", "CTU", "XIY", "WUH", "KMG"],
    "Singapore": ["SIN"],
    "Malaysia": ["KUL", "PEN", "BKI"],
    "Indonesia": ["CGK", "DPS", "SUB"],
    "Japan": ["NRT", "HND", "KIX", "NGO", "FUK", "CTS"],
    "Korea": ["ICN", "GMP", "PUS"],
    "Taiwan": ["TPE", "KHH"],
}


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
        if (r.get("zone") or "").upper() != (zone or "").upper():
            continue
        st = r.get("short_type")
        if (st is None and short_type is not None) or (
            st is not None and (st or "").upper() != (short_type or "").upper()
        ):
            continue
        if (r.get("cabin") or "").upper() != (cabin or "").upper():
            continue
        if (r.get("fare_type") or "").upper() != (fare_type or "").upper():
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
            zone=s.get("zone", "UNKNOWN"),
            short_type=s.get("short_type"),
            cabin=s.get("cabin", "UNKNOWN"),
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
        kwargs["hostname"] = hostname  # "production"
    return Client(**kwargs)


def load_airports():
    return airportsdata.load("IATA")


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
                    (fds.get("class") or "").upper(),
                    (fds.get("cabin") or fds.get("travelClass") or "")
                )

    for it in offer.get("itineraries", []) or []:
        total_minutes += parse_iso_duration(it.get("duration", ""))
        for seg in it.get("segments", []) or []:
            dep = seg.get("departure", {})
            arr = seg.get("arrival", {})
            o = dep.get("iataCode")
            d = arr.get("iataCode")

            orec = airports.get(o)
            drec = airports.get(d)

            if orec and drec:
                seg_mi = haversine_miles(orec["lat"], orec["lon"], drec["lat"], drec["lon"])
            else:
                seg_mi = None

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
                "duration_min": parse_iso_duration(seg.get("duration", "")),
                "distance_mi": seg_mi,
                "booking_class": booking_class or "?",
                "cabin": cabin,
            })

    return total_minutes, total_miles, seg_rows


def count_stops_all_itineraries(offer: dict) -> int:
    stops = 0
    for it in offer.get("itineraries", []) or []:
        segs = it.get("segments", []) or []
        stops += max(0, len(segs) - 1)
    return stops


def offer_is_all_cx(offer: dict) -> bool:
    for it in offer.get("itineraries", []) or []:
        for seg in it.get("segments", []) or []:
            if (seg.get("carrierCode") or "").upper() != "CX":
                return False
    return True


def is_roundtrip_nonstop(offer: dict) -> bool:
    # For a typical round-trip from GET with returnDate, offers usually have 2 itineraries.
    its = offer.get("itineraries", []) or []
    if len(its) < 2:
        return False
    return all(len(it.get("segments", []) or []) == 1 for it in its[:2])


def search_roundtrip_get(
    client_id: str,
    client_secret: str,
    origin: str,
    dest: str,
    depart_date: str,
    return_date: str,
    adults: int,
    currency: str,
    max_results: int,
    hostname: str = None,
    travel_class: str = "ANY",
    non_stop: bool = False,
):
    """
    Round-trip GET search using returnDate (round-trip if returnDate is included). [1](https://central.ballerina.io/ballerinax/amadeus.flightofferssearch/latest)[2](https://stackoverflow.com/questions/68506468/restrict-amadeus-flight-search-to-max-5-non-stop-economy-return-flights)
    Can request nonStop=True for direct/non-stop filtering. [2](https://stackoverflow.com/questions/68506468/restrict-amadeus-flight-search-to-max-5-non-stop-economy-return-flights)
    """
    am = amadeus_client(client_id, client_secret, hostname)

    tc = (travel_class or "ANY").upper()
    if tc not in ALLOWED_TRAVEL_CLASSES:
        tc = "ANY"

    params = dict(
        originLocationCode=origin,
        destinationLocationCode=dest,
        departureDate=depart_date,
        returnDate=return_date,
        adults=adults,
        currencyCode=currency,
        max=max_results
    )
    if tc != "ANY":
        params["travelClass"] = tc
    if non_stop:
        params["nonStop"] = True

    try:
        resp = am.shopping.flight_offers_search.get(**params)
        return resp.data
    except ResponseError as e:
        raise RuntimeError(f"Amadeus API error: {e}")


def _date_add(date_str: str, days: int) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return (d + timedelta(days=days)).isoformat()


def search_multicity_post(
    client_id: str,
    client_secret: str,
    origin_destinations: list,
    adults: int,
    currency: str,
    max_results: int,
    hostname: str = None,
    travel_class: str = "ANY",
):
    """
    Multi-city search via POST with originDestinations/travelers/sources. [3](https://github.com/amadeus4dev/developer-guides/blob/master/docs/resources/flights.md)[5](https://stackoverflow.com/questions/65418028/how-to-make-a-post-query-for-multi-city-flight-offers-search-with-amadeus-ruby-g)[4](https://developers.amadeus.com/self-service/apis-docs/guides/developer-guides/resources/flights/)
    """
    am = amadeus_client(client_id, client_secret, hostname)

    tc = (travel_class or "ANY").upper()
    if tc not in ALLOWED_TRAVEL_CLASSES:
        tc = "ANY"

    body = {
        "currencyCode": currency,
        "originDestinations": origin_destinations,
        "travelers": [{"id": str(i + 1), "travelerType": "ADULT"} for i in range(adults)],
        "sources": ["GDS"],
        "searchCriteria": {}
    }

    # Keep cabin filter simple: rely on travelClass on GET results for consistency;
    # some configurations may still return results without explicit cabinRestrictions.
    # If you want strict cabinRestrictions per OD, we can add it later.
    if tc != "ANY":
        body["searchCriteria"]["travelClass"] = tc

    try:
        resp = am.shopping.flight_offers_search.post(body)
        data = resp.data or []
        return data[:max_results]
    except ResponseError as e:
        raise RuntimeError(f"Amadeus API error: {e}")


def build_new_origin_via_hub_bodies(new_origin: str, hub: str, dest: str, hub_depart_date: str, hub_return_date: str):
    """
    You input:
      HUB -> DEST depart date (hub_depart_date)
      DEST -> HUB return date (hub_return_date)

    We build a 4-leg multi-city:
      1) NEW_ORIGIN -> HUB    (hub_depart_date - 1 or same day)
      2) HUB -> DEST          (hub_depart_date)
      3) DEST -> HUB          (hub_return_date)
      4) HUB -> NEW_ORIGIN    (hub_return_date or +1)

    This makes HUB the mandatory transit point.
    """
    bodies = []
    for feeder_offset in [-1, 0]:
        for back_offset in [0, 1]:
            ods = [
                {"id": "1", "originLocationCode": new_origin, "destinationLocationCode": hub,
                 "departureDateTimeRange": {"date": _date_add(hub_depart_date, feeder_offset)}},

                {"id": "2", "originLocationCode": hub, "destinationLocationCode": dest,
                 "departureDateTimeRange": {"date": hub_depart_date}},

                {"id": "3", "originLocationCode": dest, "destinationLocationCode": hub,
                 "departureDateTimeRange": {"date": hub_return_date}},

                {"id": "4", "originLocationCode": hub, "destinationLocationCode": new_origin,
                 "departureDateTimeRange": {"date": _date_add(hub_return_date, back_offset)}},
            ]
            bodies.append(ods)
    return bodies


def expand_new_origins(selected_regions: list) -> list:
    airports = []
    for r in selected_regions:
        airports.extend(NEW_ORIGIN_POOLS.get(r, []))
    return sorted(set(airports))