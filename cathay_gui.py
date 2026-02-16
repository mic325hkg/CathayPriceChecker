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

# PyInstaller --onefile extracts bundled data to a temp dir pointed to by sys._MEIPASS. [1](https://stackoverflow.com/questions/51060894/adding-a-data-file-in-pyinstaller-using-the-onefile-option)[2](https://stackoverflow.com/questions/7674790/bundling-data-files-with-pyinstaller-onefile)
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cathay Price Checker (CX) – GUI")
        self.geometry("1100x720")

        self.cfg = load_config()
        self.airports = core.load_airports()

        self._build_ui()
        self._load_defaults()

    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}

        top = ttk.Frame(self)
        top.pack(fill="x", **pad)

        # Inputs row 1
        r1 = ttk.Frame(top)
        r1.pack(fill="x")

        ttk.Label(r1, text="From (IATA):").pack(side="left")
        self.origin_var = tk.StringVar()
        ttk.Entry(r1, textvariable=self.origin_var, width=8).pack(side="left", padx=6)

        ttk.Label(r1, text="To (IATA):").pack(side="left")
        self.dest_var = tk.StringVar()
        ttk.Entry(r1, textvariable=self.dest_var, width=8).pack(side="left", padx=6)

        ttk.Label(r1, text="Date (YYYY-MM-DD):").pack(side="left")
        self.date_var = tk.StringVar()
        ttk.Entry(r1, textvariable=self.date_var, width=14).pack(side="left", padx=6)

        ttk.Label(r1, text="Adults:").pack(side="left")
        self.adults_var = tk.IntVar(value=1)
        ttk.Spinbox(r1, from_=1, to=9, textvariable=self.adults_var, width=4).pack(side="left", padx=6)

        ttk.Label(r1, text="Currency:").pack(side="left")
        self.currency_var = tk.StringVar(value="HKD")
        ttk.Entry(r1, textvariable=self.currency_var, width=6).pack(side="left", padx=6)

        self.cx_only_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(r1, text="CX only", variable=self.cx_only_var).pack(side="left", padx=12)

        # Inputs row 2
        r2 = ttk.Frame(top)
        r2.pack(fill="x")

        ttk.Label(r2, text="Fare type:").pack(side="left")
        self.fare_type_var = tk.StringVar(value="AUTO")
        ttk.Combobox(
            r2, textvariable=self.fare_type_var, width=12,
            values=["AUTO", "LIGHT", "ESSENTIAL", "FLEX", "UNKNOWN"],
            state="readonly"
        ).pack(side="left", padx=6)

        ttk.Label(r2, text="Earnings YAML:").pack(side="left")
        self.earnings_path_var = tk.StringVar()
        ttk.Entry(r2, textvariable=self.earnings_path_var, width=45).pack(side="left", padx=6)
        ttk.Button(r2, text="Browse…", command=self.pick_earnings).pack(side="left")

        ttk.Label(r2, text="Max results:").pack(side="left", padx=(16, 0))
        self.max_var = tk.IntVar(value=20)
        ttk.Spinbox(r2, from_=1, to=100, textvariable=self.max_var, width=5).pack(side="left", padx=6)

        # API keys row
        keys = ttk.LabelFrame(self, text="Amadeus API credentials (stored in your Windows profile)")
        keys.pack(fill="x", **pad)

        kr = ttk.Frame(keys)
        kr.pack(fill="x", padx=8, pady=6)

        ttk.Label(kr, text="Client ID:").pack(side="left")
        self.client_id_var = tk.StringVar()
        ttk.Entry(kr, textvariable=self.client_id_var, width=34).pack(side="left", padx=6)

        ttk.Label(kr, text="Client Secret:").pack(side="left")
        self.client_secret_var = tk.StringVar()
        ttk.Entry(kr, textvariable=self.client_secret_var, width=34, show="•").pack(side="left", padx=6)

        ttk.Button(kr, text="Save credentials", command=self.save_creds).pack(side="left", padx=10)

        # Actions
        actions = ttk.Frame(self)
        actions.pack(fill="x", **pad)

        ttk.Button(actions, text="Search flights", command=self.on_search).pack(side="left")
        ttk.Button(actions, text="Export results to JSON…", command=self.export_json).pack(side="left", padx=8)

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(actions, textvariable=self.status_var).pack(side="left", padx=12)

        # Results table
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, **pad)

        cols = ("#", "Price", "Duration", "Stops", "CXOnly", "FareType", "Est SP", "Est AsiaMiles")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", height=12)
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("#", width=40, anchor="center")
        self.tree.column("Price", width=120)
        self.tree.column("Duration", width=90)
        self.tree.column("Stops", width=60, anchor="center")
        self.tree.column("CXOnly", width=70, anchor="center")
        self.tree.column("FareType", width=90, anchor="center")
        self.tree.column("Est SP", width=80, anchor="center")
        self.tree.column("Est AsiaMiles", width=110, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="left", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self.on_select_offer)

        # Details box
        details = ttk.LabelFrame(self, text="Flight details (segments)")
        details.pack(fill="both", expand=True, **pad)

        self.details_text = tk.Text(details, height=14, wrap="word")
        self.details_text.pack(fill="both", expand=True, padx=8, pady=6)

        self.results = []  # full enriched results in memory

    def _load_defaults(self):
        self.origin_var.set(self.cfg.get("origin", "HKG"))
        self.dest_var.set(self.cfg.get("dest", "NRT"))
        self.date_var.set(self.cfg.get("date", "2026-03-10"))
        self.adults_var.set(self.cfg.get("adults", 1))
        self.currency_var.set(self.cfg.get("currency", "HKD"))
        self.cx_only_var.set(self.cfg.get("cx_only", True))
        self.max_var.set(self.cfg.get("max_results", 20))

        # credentials
        self.client_id_var.set(self.cfg.get("amadeus_client_id", ""))
        self.client_secret_var.set(self.cfg.get("amadeus_client_secret", ""))

        # earnings yaml: prefer bundled default if present
        bundled = resource_path(DEFAULT_EARNINGS)
        if os.path.exists(bundled):
            self.earnings_path_var.set(bundled)
        else:
            self.earnings_path_var.set(self.cfg.get("earnings_yaml", DEFAULT_EARNINGS))

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
        messagebox.showinfo("Saved", f"Saved credentials to:\n{config_path()}")

    def _save_form_fields(self):
        self.cfg.update({
            "origin": self.origin_var.get().strip().upper(),
            "dest": self.dest_var.get().strip().upper(),
            "date": self.date_var.get().strip(),
            "adults": int(self.adults_var.get()),
            "currency": self.currency_var.get().strip().upper(),
            "cx_only": bool(self.cx_only_var.get()),
            "max_results": int(self.max_var.get()),
            "earnings_yaml": self.earnings_path_var.get().strip(),
        })

    def on_search(self):
        self._save_form_fields()
        save_config(self.cfg)

        cid = self.client_id_var.get().strip()
        csec = self.client_secret_var.get().strip()
        if not cid or not csec:
            messagebox.showerror("Missing API keys", "Please enter Amadeus Client ID and Client Secret.")
            return

        # clear old
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.details_text.delete("1.0", "end")
        self.results = []

        self.status_var.set("Searching…")
        t = threading.Thread(target=self._search_worker, daemon=True)
        t.start()

    def _search_worker(self):
        try:
            earning_table = core.load_earning_table(self.earnings_path_var.get().strip())
            offers = core.search_offers(
                self.client_id_var.get().strip(),
                self.client_secret_var.get().strip(),
                self.origin_var.get().strip().upper(),
                self.dest_var.get().strip().upper(),
                self.date_var.get().strip(),
                adults=int(self.adults_var.get()),
                currency=self.currency_var.get().strip().upper(),
                max_results=int(self.max_var.get()),
            )

            cx_only_flag = bool(self.cx_only_var.get())
            if cx_only_flag:
                offers = [o for o in offers if core.offer_is_all_cx(o)]

            enriched = []
            for offer in offers:
                price = offer.get("price", {}).get("grandTotal")
                cur = offer.get("price", {}).get("currency", self.currency_var.get().strip().upper())
                total_min, total_mi, segs = core.compute_offer_metrics(offer, self.airports)

                # fare type
                ft_ui = self.fare_type_var.get().strip().upper()
                if ft_ui == "AUTO":
                    fare_type = core.infer_fare_type_from_offer(offer).upper()
                else:
                    fare_type = ft_ui
                if fare_type not in {"LIGHT", "ESSENTIAL", "FLEX"}:
                    fare_type = "UNKNOWN"

                est_sp, est_am, per_seg = core.estimate_earnings(segs, earning_table, fare_type)
                stops = sum(len(it.get("segments", [])) for it in offer.get("itineraries", [])) - 1

                enriched.append({
                    "price_amount": price,
                    "currency": cur,
                    "total_minutes": total_min,
                    "total_miles_est": total_mi,
                    "stops": stops,
                    "cx_only": core.offer_is_all_cx(offer),
                    "fare_type": fare_type,
                    "estimated_sp": est_sp,
                    "estimated_am": est_am,
                    "segments": segs,
                    "raw_offer": offer,
                    "earning_table_version": earning_table.get("version"),
                })

            self.results = enriched
            self.after(0, self._render_results)

        except Exception as e:
            self.after(0, lambda: self._show_error(str(e)))

    def _render_results(self):
        for idx, r in enumerate(self.results, 1):
            self.tree.insert("", "end", iid=str(idx-1), values=(
                idx,
                f"{r['currency']} {r['price_amount']}",
                core.fmt_minutes(r["total_minutes"]),
                r["stops"],
                "Yes" if r["cx_only"] else "No",
                r["fare_type"],
                r["estimated_sp"] if r["estimated_sp"] is not None else "N/A",
                r["estimated_am"] if r["estimated_am"] is not None else "N/A",
            ))
        self.status_var.set(f"Done. {len(self.results)} options.")

    def on_select_offer(self, _evt=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])  # iid is 0-based string
        r = self.results[idx]

        lines = []
        lines.append(f"Price: {r['currency']} {r['price_amount']}")
        lines.append(f"Duration: {core.fmt_minutes(r['total_minutes'])} | Stops: {r['stops']}")
        lines.append(f"FareType: {r['fare_type']} | Estimated SP: {r['estimated_sp']} | Estimated Asia Miles: {r['estimated_am']}")
        lines.append(f"Earning table version: {r.get('earning_table_version')}")
        lines.append("")
        lines.append("Segments:")
        for i, s in enumerate(r["segments"], 1):
            zone = s["zone"] + (f"-{s['short_type']}" if s.get("short_type") else "")
            dist = f"{(s['distance_mi'] or 0):.0f} mi"
            lines.append(
                f" {i}. {s['flight']}  {s['from']}→{s['to']}  "
                f"{(s['dep_at'] or '')} → {(s['arr_at'] or '')}  "
                f"{core.fmt_minutes(s['duration_min'])}  "
                f"Cabin={s['cabin']}  BkCls={s['booking_class']}  Zone={zone}  Dist~{dist}"
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
    app = App()
    app.mainloop()