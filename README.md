# Cathay Price Checker (GUI)

Windows desktop app to:
- Search Cathay Pacific (CX) flight prices
- Show duration, segments, aircraft
- Estimate Asia Miles and Status Points
- Export results to JSON

## Requirements
- Python 3.10+
- Amadeus API credentials

## Setup
```bash
pip install -r requirements.txt

python cathay_gui.py

## Build EXE
pyinstaller --clean --noconfirm --onefile --windowed --name CathayPriceChecker --collect-data airportsdata --add-data "cathay_earnings.yaml;." cathay_gui.py

## Run Command Line
python cathay_price_checker.py --from HKG --to NRT --date 2026-02-18 --currency HKD --adults 1
