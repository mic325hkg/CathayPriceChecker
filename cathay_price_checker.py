#!/usr/bin/env python3
import argparse
import os
import cathay_core as core

def main():
    ap = argparse.ArgumentParser(description="Fixed DEST; HUB is transit for feeder origins. Show HUB⇄DEST first, then NEW→HUB→DEST.")
    ap.add_argument("--hub", required=True, help="Transit point / original origin (e.g., HKG)")
    ap.add_argument("--dest", required=True, help="Fixed destination (e.g., LHR)")
    ap.add_argument("--depart", required=True, help="Depart date for HUB→DEST (YYYY-MM-DD)")
    ap.add_argument("--return-date", required=True, help="Return date for DEST→HUB (YYYY-MM-DD)")
    ap.add_argument("--adults", type=int, default=1)
    ap.add_argument("--currency", default="HKD")
    ap.add_argument("--max", type=int, default=20)
    ap.add_argument("--env", choices=["test", "production"], default="test")
    ap.add_argument("--cabin", choices=["ANY", "ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"], default="ANY")
    ap.add_argument("--cx-only", action="store_true")
    ap.add_argument("--regions", nargs="*", default=["China","Singapore","Malaysia","Indonesia","Japan","Korea","Taiwan"])
    ap.add_argument("--nonstop-direct", action="store_true", help="Request nonStop=True for HUB⇄DEST search")

    args = ap.parse_args()

    cid = os.getenv("AMADEUS_CLIENT_ID")
    csec = os.getenv("AMADEUS_CLIENT_SECRET")
    if not cid or not csec:
        raise SystemExit("Missing AMADEUS_CLIENT_ID / AMADEUS_CLIENT_SECRET env vars")

    hostname = "production" if args.env == "production" else None

    hub = args.hub.upper()
    dest = args.dest.upper()

    # 1) HUB ⇄ DEST
    offers = core.search_roundtrip_get(
        client_id=cid, client_secret=csec,
        origin=hub, dest=dest,
        depart_date=args.depart, return_date=args.return_date,
        adults=args.adults, currency=args.currency.upper(),
        max_results=args.max, hostname=hostname,
        travel_class=args.cabin,
        non_stop=args.nonstop_direct
    )
    if args.cx_only:
        offers = [o for o in offers if core.offer_is_all_cx(o)]

    nonstop = [o for o in offers if core.is_roundtrip_nonstop(o)]
    first_block = nonstop if nonstop else offers

    print("\n=== HUB⇄DEST (original direct) ===")
    if not first_block:
        print("No offers found.")
    for i, o in enumerate(first_block[:args.max], 1):
        price = o.get("price", {}).get("grandTotal")
        cur = o.get("price", {}).get("currency", args.currency.upper())
        print(f"{i}. {cur} {price}")

    # 2) NEW_ORIGIN → HUB → DEST → HUB → NEW_ORIGIN
    print("\n=== NEW_ORIGIN→HUB→DEST options ===")
    candidates = core.expand_new_origins(args.regions)[:40]
    collected = []
    seen = set()

    for new_origin in candidates:
        if new_origin in {hub, dest}:
            continue
        for ods in core.build_new_origin_via_hub_bodies(new_origin, hub, dest, args.depart, args.return_date):
            resp = core.search_multicity_post(
                client_id=cid, client_secret=csec,
                origin_destinations=ods,
                adults=args.adults, currency=args.currency.upper(),
                max_results=2, hostname=hostname,
                travel_class=args.cabin
            )
            if args.cx_only:
                resp = [o for o in resp if core.offer_is_all_cx(o)]
            for o in resp:
                key = (new_origin, o.get("id", ""))
                if key in seen:
                    continue
                seen.add(key)
                collected.append((new_origin, o))

    def price_float(offer):
        try:
            return float(offer.get("price", {}).get("grandTotal", "1e18"))
        except Exception:
            return 1e18

    collected.sort(key=lambda x: price_float(x[1]))

    for new_origin, o in collected[:args.max]:
        price = o.get("price", {}).get("grandTotal")
        cur = o.get("price", {}).get("currency", args.currency.upper())
        print(f"- {new_origin} → {hub} → {dest}: {cur} {price}")

if __name__ == "__main__":
    main()