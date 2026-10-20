"""
Add the "extended residence" tag to ShipStation orders whose ship-to ZIP
is on FedEx's Contiguous U.S.: Extended delivery area surcharge list.

Setup:
  1. In ShipStation, create a tag named exactly: extended residence
  2. Set environment variables (same API keys your other tag script uses):
       SHIPSTATION_API_KEY
       SHIPSTATION_API_SECRET
  3. Make sure data/fedex_das_extended_zips.txt exists
     (created by scripts/extract_fedex_das_zips.py)

Run:
    pip install requests
    python scripts/tag_fedex_extended.py
"""
import os
import sys
import time
from pathlib import Path

import requests

TAG_NAME = "extended residence"
ORDER_STATUS = "awaiting_shipment"
ZIP_FILE = Path(__file__).resolve().parent / "fedex" / "fedex_das_extended_zips.txt". Click Commit changes. (Or delete the old file and upload the updated one from this chat.)
API_BASE = "https://ssapi.shipstation.com"

session = requests.Session()
session.auth = (os.environ.get("SHIPSTATION_API_KEY", ""), os.environ.get("SHIPSTATION_API_SECRET", ""))


def api(method, path, **kwargs):
    """Call the ShipStation API, waiting and retrying if rate limited."""
    while True:
        resp = session.request(method, API_BASE + path, timeout=60, **kwargs)
        if resp.status_code == 429:
            wait = int(resp.headers.get("X-Rate-Limit-Reset", 30)) + 1
            print(f"Rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json() if resp.content else None


def load_zips():
    if not ZIP_FILE.exists():
        sys.exit(f"Missing {ZIP_FILE}. Run extract_fedex_das_zips.py first.")
    return {line.strip() for line in ZIP_FILE.read_text().splitlines() if line.strip()}


def normalize_zip(postal_code):
    """'1234-5678', '01234-5678' or '1234' -> 5-digit string like '01234'."""
    digits = (postal_code or "").split("-")[0].strip()
    return digits.zfill(5) if digits.isdigit() else ""


def find_tag_id():
    for tag in api("GET", "/accounts/listtags"):
        if tag["name"].strip().lower() == TAG_NAME.lower():
            return tag["tagId"]
    sys.exit(f'Tag "{TAG_NAME}" not found. Create it in ShipStation first.')


def iter_orders():
    page = 1
    while True:
        data = api("GET", "/orders", params={"orderStatus": ORDER_STATUS, "page": page, "pageSize": 500})
        yield from data["orders"]
        if page >= data["pages"]:
            break
        page += 1


def main():
    if not session.auth[0] or not session.auth[1]:
        sys.exit("Set SHIPSTATION_API_KEY and SHIPSTATION_API_SECRET first.")

    extended_zips = load_zips()
    tag_id = find_tag_id()
    checked = tagged = already = 0

    for order in iter_orders():
        checked += 1
        ship_to = order.get("shipTo") or {}
        if (ship_to.get("country") or "US") != "US":
            continue
        if normalize_zip(ship_to.get("postalCode")) not in extended_zips:
            continue
        if tag_id in (order.get("tagIds") or []):
            already += 1
            continue
        api("POST", "/orders/addtag", json={"orderId": order["orderId"], "tagId": tag_id})
        tagged += 1
        print(f"Tagged order {order['orderNumber']} (ZIP {ship_to.get('postalCode')})")

    print(f"\nChecked {checked} orders: {tagged} newly tagged, {already} already had the tag.")


if __name__ == "__main__":
    main()
