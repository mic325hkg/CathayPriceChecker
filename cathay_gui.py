# cathay_gui.py
import os
import sys
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import cathay_core as core

APP_NAME = "CathayPriceChecker"
DEFAULT_EARNINGS = "cathay_earnings.yaml"


def appdata_dir():
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def config_path():
    return os.path.join(appdata_dir(), "config.json")


def load_config():
    p = config_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(cfg: dict):
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Fixed Destination; Hub is Transit for feeder origins")
        self.geometry("1320x820")

        self.cfg = load_config()
        self.airports = core.load_airports()

        self._build_ui()
        self._load_defaults()

    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}

        top = ttk.Frame(self)
        top.pack(fill="x", **pad)

        r1 = ttk.Frame(top)
        r1.pack(fill="x")

        ttk.Label(r1, text="HUB (Transit Point / Original Origin):").pack(side="left")
        self.hub_var = tk.StringVar()
        ttk.Entry(r1, textvariable=self.hub_var, width=8).pack(side="left", padx=6)

        ttk.Label(r1, text="DEST (Fixed Destination):").pack(side="left")
        self.dest_var = tk.StringVar()
        ttk.Entry(r1, textvariable=self.dest_var, width=8).pack(side="left", padx=6)

        ttk.Label(r1, text="Depart HUB→DEST (YYYY-MM-DD):").pack(side="left")
        self.depart_var = tk.StringVar()
        ttk.Entry(r1, textvariable=self.depart_var, width=14).pack(side="left", padx=6)

        ttk.Label(r1, text="Return DEST→HUB (YYYY-MM-DD):").pack(side="left")
        self.return_var = tk.StringVar()
        ttk.Entry(r1, textvariable=self.return_var, width=14).pack(side="left", padx=6)

        ttk.Label(r1, text="Adults:").pack(side="left")
        self.adults_var = tk.IntVar(value=1)
        ttk.Spinbox(r1, from_=1, to=9, textvariable=self.adults_var, width=4).pack(side="left", padx=6)

        ttk.Label(r1, text="Currency:").pack(side="left")
        self.currency_var = tk.StringVar(value="HKD")
        ttk.Entry(r1, textvariable=self.currency_var, width=6).pack(side="left", padx=6)

        self.strict_cx_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(r1, text="CX only (strict)", variable=self.strict_cx_var).pack(side="left", padx=12)

        r2 = ttk.Frame(top)
        r2.pack(fill="x")

        ttk.Label(r2, text="Cabin/Class:").pack(side="left")
        self.cabin_var = tk.StringVar(value="ANY")
        ttk.Combobox(
            r2, textvariable=self.cabin_var, width=18,
            values=["ANY", "ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"],
            state="readonly"
        ).pack(side="left", padx=6)

        ttk.Label(r2, text="Prefer non-stop for HUB⇄DEST:").pack(side="left", padx=(16, 0))
        self.nonstop_direct_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(r2, text="Non-stop", variable=self.nonstop_direct_var).pack(side="left", padx=6)

        ttk.Label(r2, text="Earnings YAML:").pack(side="left", padx=(16, 0))
        self.earnings_path_var = tk.StringVar()
        ttk.Entry(r2, textvariable=self.earnings_path_var, width=45).pack(side="left", padx=6)
        ttk.Button(r2, text="Browse…", command=self.pick_earnings).pack(side="left")

        ttk.Label(r2, text="Max results:").pack(side="left", padx=(16, 0))
        self.max_var = tk.IntVar(value=25)
        ttk.Spinbox(r2, from_=5, to=100, textvariable=self.max_var, width=5).pack(side="left", padx=6)

        region_box = ttk.LabelFrame(top, text="NEW ORIGINS to try (they will fly via HUB)")
        region_box.pack(fill="x", padx=8, pady=6)

        self.enable_feeders_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(region_box, text="Enable NEW_ORIGIN→HUB→DEST search", variable=self.enable_feeders_var)\
            .pack(side="left", padx=8)

        self.region_vars = {}
        for region in ["China", "Singapore", "Malaysia", "Indonesia", "Japan", "Korea", "Taiwan"]:
            v = tk.BooleanVar(value=True)
            self.region_vars[region] = v
            ttk.Checkbutton(region_box, text=region, variable=v).pack(side="left", padx=6)

        keys = ttk.LabelFrame(self, text="Amadeus API credentials")
        keys.pack(fill="x", **pad)

        kr = ttk.Frame(keys)
        kr.pack(fill="x", padx=8, pady=6)

        ttk.Label(kr, text="Client ID:").pack(side="left")
        self.client_id_var = tk.StringVar()
        ttk.Entry(kr, textvariable=self.client_id_var, width=34).pack(side="left", padx=6)

        ttk.Label(kr, text="Client Secret:").pack(side="left")
        self.client_secret_var = tk.StringVar()
        ttk.Entry(kr, textvariable=self.client_secret_var, width=34, show="•").pack(side="left", padx=6)

        ttk.Label(kr, text="Environment:").pack(side="left", padx=(16, 0))
        self.env_var = tk.StringVar(value="test")
        ttk.Combobox(kr, textvariable=self.env_var, width=10,
                     values=["test", "production"], state="readonly").pack(side="left", padx=6)

        ttk.Button(kr, text="Save", command=self.save_creds).pack(side="left", padx=10)

        actions = ttk.Frame(self)
        actions.pack(fill="x", **pad)
        ttk.Button(actions, text="Search (HUB⇄DEST direct first, then feeder origins via HUB)", command=self.on_search)\
            .pack(side="left")
        ttk.Button(actions, text="Export JSON…", command=self.export_json).pack(side="left", padx=8)
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(actions, textvariable=self.status_var).pack(side="left", padx=12)

        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, **pad)

        cols = ("Type", "NewOrigin", "ViaHub", "Price", "Total Duration", "Stops", "CabinFilter", "CXOnly", "EstSP", "EstMiles")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", height=14)
        for c in cols:
            self.tree.heading(c, text=c)

        self.tree.column("Type", width=90, anchor="center")
        self.tree.column("NewOrigin", width=90, anchor="center")
        self.tree.column("ViaHub", width=80, anchor="center")
        self.tree.column("Price", width=120)
        self.tree.column("Total Duration", width=110)
        self.tree.column("Stops", width=70, anchor="center")
        self.tree.column("CabinFilter", width=100, anchor="center")
        self.tree.column("CXOnly", width=70, anchor="center")
        self.tree.column("EstSP", width=70, anchor="center")
        self.tree.column("EstMiles", width=90, anchor="center")

        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select_offer)

        details = ttk.LabelFrame(self, text="Details")
        details.pack(fill="both", expand=True, **pad)
        self.details_text = tk.Text(details, height=12, wrap="word")
        self.details_text.pack(fill="both", expand=True, padx=8, pady=6)

        self.results = []

    def _load_defaults(self):
        self.hub_var.set(self.cfg.get("hub", "HKG"))
        self.dest_var.set(self.cfg.get("dest", "NRT"))
        self.depart_var.set(self.cfg.get("depart_date", "2026-03-10"))
        self.return_var.set(self.cfg.get("return_date", "2026-03-15"))
        self.adults_var.set(self.cfg.get("adults", 1))
        self.currency_var.set(self.cfg.get("currency", "HKD"))
        self.max_var.set(self.cfg.get("max_results", 25))
        self.cabin_var.set(self.cfg.get("cabin", "ANY"))
        self.env_var.set(self.cfg.get("env", "test"))
        self.strict_cx_var.set(self.cfg.get("strict_cx", False))
        self.enable_feeders_var.set(self.cfg.get("enable_feeders", True))
        self.nonstop_direct_var.set(self.cfg.get("nonstop_direct", True))

        regions = self.cfg.get("regions", {})
        for k, v in self.region_vars.items():
            v.set(bool(regions.get(k, True)))

        self.client_id_var.set(self.cfg.get("amadeus_client_id", ""))
        self.client_secret_var.set(self.cfg.get("amadeus_client_secret", ""))

        bundled = resource_path(DEFAULT_EARNINGS)
        self.earnings_path_var.set(bundled if os.path.exists(bundled) else self.cfg.get("earnings_yaml", DEFAULT_EARNINGS))

    def _save_form_fields(self):
        self.cfg.update({
            "hub": self.hub_var.get().strip().upper(),
            "dest": self.dest_var.get().strip().upper(),
            "depart_date": self.depart_var.get().strip(),
            "return_date": self.return_var.get().strip(),
            "adults": int(self.adults_var.get()),
            "currency": self.currency_var.get().strip().upper(),
            "max_results": int(self.max_var.get()),
            "earnings_yaml": self.earnings_path_var.get().strip(),
            "cabin": self.cabin_var.get().strip().upper(),
            "env": self.env_var.get().strip().lower(),
            "strict_cx": bool(self.strict_cx_var.get()),
            "enable_feeders": bool(self.enable_feeders_var.get()),
            "nonstop_direct": bool(self.nonstop_direct_var.get()),
            "regions": {k: bool(v.get()) for k, v in self.region_vars.items()},
        })

    def pick_earnings(self):
        p = filedialog.askopenfilename(
            title="Select cathay_earnings.yaml",
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")]
        )
        if p:
            self.earnings_path_var.set(p)

    def save_creds(self):
        self.cfg["amadeus_client_id"] = self.client_id_var.get().strip()
        self.cfg["amadeus_client_secret"] = self.client_secret_var.get().strip()
        self._save_form_fields()
        save_config(self.cfg)
        messagebox.showinfo("Saved", f"Saved to:\n{config_path()}")

    def on_search(self):
        self._save_form_fields()
        save_config(self.cfg)

        cid = self.client_id_var.get().strip()
        csec = self.client_secret_var.get().strip()
        if not cid or not csec:
            messagebox.showerror("Missing API keys", "Please enter Amadeus Client ID and Client Secret.")
            return

        if not self.hub_var.get().strip() or not self.dest_var.get().strip():
            messagebox.showerror("Missing inputs", "HUB and DEST are required.")
            return

        if not self.depart_var.get().strip() or not self.return_var.get().strip():
            messagebox.showerror("Dates required", "Depart and Return dates are required.")
            return

        for i in self.tree.get_children():
            self.tree.delete(i)
        self.details_text.delete("1.0", "end")
        self.results = []
        self.status_var.set("Searching…")
        threading.Thread(target=self._search_worker, daemon=True).start()

    def _search_worker(self):
        try:
            earning_table = core.load_earning_table(self.earnings_path_var.get().strip())
            env = self.env_var.get().strip().lower()
            hostname = "production" if env == "production" else None

            hub = self.hub_var.get().strip().upper()
            dest = self.dest_var.get().strip().upper()
            depart_date = self.depart_var.get().strip()
            return_date = self.return_var.get().strip()
            adults = int(self.adults_var.get())
            currency = self.currency_var.get().strip().upper()
            travel_class = self.cabin_var.get().strip().upper()
            max_results = int(self.max_var.get())
            strict_cx = bool(self.strict_cx_var.get())
            nonstop_direct = bool(self.nonstop_direct_var.get())

            # 1) HUB ⇄ DEST (direct first)
            hubdest_offers = core.search_roundtrip_get(
                client_id=self.client_id_var.get().strip(),
                client_secret=self.client_secret_var.get().strip(),
                origin=hub,
                dest=dest,
                depart_date=depart_date,
                return_date=return_date,
                adults=adults,
                currency=currency,
                max_results=max_results,
                hostname=hostname,
                travel_class=travel_class,
                non_stop=nonstop_direct
            )

            if strict_cx:
                hubdest_offers = [o for o in hubdest_offers if core.offer_is_all_cx(o)]

            # Prefer true nonstop RT offers at top; otherwise show whatever returned
            hubdest_nonstop = [o for o in hubdest_offers if core.is_roundtrip_nonstop(o)]
            direct_list = hubdest_nonstop if hubdest_nonstop else hubdest_offers

            enriched = []

            def add_offer(kind, new_origin, via_hub, offer):
                price = offer.get("price", {}).get("grandTotal")
                cur = offer.get("price", {}).get("currency", currency)
                total_min, total_miles, segs = core.compute_offer_metrics(offer, self.airports)

                fare_type = core.infer_fare_type_from_offer(offer).upper()
                if fare_type not in {"LIGHT", "ESSENTIAL", "FLEX"}:
                    fare_type = "UNKNOWN"

                est_sp, est_am, _ = core.estimate_earnings(segs, earning_table, fare_type)
                stops = core.count_stops_all_itineraries(offer)

                enriched.append({
                    "type": kind,
                    "new_origin": new_origin,
                    "via_hub": via_hub,
                    "price_amount": price,
                    "currency": cur,
                    "total_minutes": total_min,
                    "stops": stops,
                    "travel_class_filter": travel_class,
                    "cx_only": core.offer_is_all_cx(offer),
                    "estimated_sp": est_sp,
                    "estimated_am": est_am,
                    "segments": segs,
                    "raw_offer": offer
                })

            # Add HUB⇄DEST first
            for o in direct_list[:max_results]:
                add_offer("HUB⇄DEST", hub, "-", o)

            # 2) NEW_ORIGIN → HUB → DEST → HUB → NEW_ORIGIN
            if bool(self.enable_feeders_var.get()):
                selected_regions = [k for k, v in self.region_vars.items() if v.get()]
                candidate_origins = core.expand_new_origins(selected_regions)

                # Bound the search (can be increased)
                candidate_origins = candidate_origins[:40]

                feeder_collected = []
                seen = set()

                for new_origin in candidate_origins:
                    if new_origin in {hub, dest}:
                        continue

                    bodies = core.build_new_origin_via_hub_bodies(new_origin, hub, dest, depart_date, return_date)

                    for ods in bodies:
                        offers = core.search_multicity_post(
                            client_id=self.client_id_var.get().strip(),
                            client_secret=self.client_secret_var.get().strip(),
                            origin_destinations=ods,
                            adults=adults,
                            currency=currency,
                            max_results=3,
                            hostname=hostname,
                            travel_class=travel_class
                        )
                        if strict_cx:
                            offers = [o for o in offers if core.offer_is_all_cx(o)]
                        for o in offers:
                            oid = o.get("id", "")
                            key = (new_origin, oid)
                            if key in seen:
                                continue
                            seen.add(key)
                            feeder_collected.append((new_origin, o))

                # Sort feeder options by price (best effort)
                def price_float(offer):
                    try:
                        return float(offer.get("price", {}).get("grandTotal", "1e18"))
                    except Exception:
                        return 1e18

                feeder_collected.sort(key=lambda x: price_float(x[1]))

                for new_origin, o in feeder_collected[:max_results]:
                    add_offer("NEW→HUB→DEST", new_origin, hub, o)

            self.results = enriched
            self.after(0, self._render_results)

        except Exception as e:
            self.after(0, lambda: self._show_error(str(e)))

    def _render_results(self):
        for idx, r in enumerate(self.results):
            self.tree.insert("", "end", iid=str(idx), values=(
                r["type"],
                r["new_origin"],
                r["via_hub"],
                f"{r['currency']} {r['price_amount']}",
                core.fmt_minutes(r["total_minutes"]),
                r["stops"],
                r.get("travel_class_filter", "ANY"),
                "Yes" if r["cx_only"] else "No",
                r["estimated_sp"] if r["estimated_sp"] is not None else "N/A",
                r["estimated_am"] if r["estimated_am"] is not None else "N/A",
            ))
        self.status_var.set(f"Done. Results: {len(self.results)}")

    def on_select_offer(self, _evt=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        r = self.results[idx]

        lines = []
        lines.append(f"Type: {r['type']} | NewOrigin: {r['new_origin']} | ViaHub: {r['via_hub']}")
        lines.append(f"Price: {r['currency']} {r['price_amount']} | Duration: {core.fmt_minutes(r['total_minutes'])} | Stops: {r['stops']}")
        lines.append(f"Cabin filter: {r.get('travel_class_filter')} | CX only: {r['cx_only']}")
        lines.append(f"Est SP: {r['estimated_sp']} | Est Asia Miles: {r['estimated_am']}")
        lines.append("")
        lines.append("Segments:")
        for i, s in enumerate(r["segments"], 1):
            lines.append(
                f" {i}. {s['flight']} {s['from']}→{s['to']} "
                f"{(s['dep_at'] or '')} → {(s['arr_at'] or '')} "
                f"{core.fmt_minutes(s['duration_min'])} cabin={s['cabin']} bk={s['booking_class']}"
            )
        self.details_text.delete("1.0", "end")
        self.details_text.insert("1.0", "\n".join(lines))

    def export_json(self):
        if not self.results:
            messagebox.showinfo("No results", "Run a search first.")
            return
        p = filedialog.asksaveasfilename(
            title="Save results JSON",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")]
        )
        if not p:
            return
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("Saved", f"Saved:\n{p}")

    def _show_error(self, msg: str):
        self.status_var.set("Error.")
        messagebox.showerror("Error", msg)


if __name__ == "__main__":
    App().mainloop()