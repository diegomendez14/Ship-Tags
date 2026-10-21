"""
Tag ShipStation orders by FedEx Delivery Area Surcharge (DAS) ZIP lists.

  - ZIPs on the FedEx "Contiguous U.S." DAS list       -> tag "DAS FedEx"
  - ZIPs on the FedEx "Contiguous U.S.: Extended" list -> tag "extended residence"

Each tag must already exist in ShipStation with exactly that name.
To rename a tag, change it in the TAGS section below.

Run:
    python tag_fedex_extended.py           # dry run: only shows what it would tag
    python tag_fedex_extended.py --apply   # actually tags orders
"""
import os
import sys
import time
from pathlib import Path

import requests

FEDEX_DIR = Path(__file__).resolve().parent / "fedex"

# Tag name in ShipStation  ->  ZIP list file in the fedex folder
TAGS = {
    "DAS FedEx": "fedex_das_contiguous_zips.txt",
    "extended residence": "fedex_das_extended_zips.txt",
}

ORDER_STATUS = "awaiting_shipment"
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


def load_zip_to_tag():
    """Build one lookup: ZIP -> tag name. Stops if a ZIP is on two lists."""
    zip_to_tag = {}
    for tag_name, filename in TAGS.items():
        path = FEDEX_DIR / filename
        if not path.exists():
            sys.exit(f"Missing {path}. Upload it to the fedex folder.")
        for line in path.read_text().splitlines():
            z = line.strip()
            if not z:
                continue
            if z in zip_to_tag and zip_to_tag[z] != tag_name:
                sys.exit(f"ZIP {z} is on both the '{zip_to_tag[z]}' and '{tag_name}' lists.")
            zip_to_tag[z] = tag_name
    return zip_to_tag


def normalize_zip(postal_code):
    """'1234-5678', '01234-5678' or '1234' -> 5-digit string like '01234'."""
    digits = (postal_code or "").split("-")[0].strip()
    return digits.zfill(5) if digits.isdigit() else ""


def find_tag_ids():
    existing = {t["name"].strip().lower(): t["tagId"] for t in api("GET", "/accounts/listtags")}
    missing = [name for name in TAGS if name.lower() not in existing]
    if missing:
        sys.exit("Tag(s) not found in ShipStation: " + ", ".join(f'"{m}"' for m in missing)
                 + ". Create them first.")
    return {name: existing[name.lower()] for name in TAGS}


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

    apply = "--apply" in sys.argv
    print("Mode:", "APPLY (tagging orders)" if apply else "DRY RUN (no changes)")

    zip_to_tag = load_zip_to_tag()
    tag_ids = find_tag_ids()
    checked = 0
    tagged = {name: 0 for name in TAGS}
    already = {name: 0 for name in TAGS}

    for order in iter_orders():
        checked += 1
        ship_to = order.get("shipTo") or {}
        if (ship_to.get("country") or "US") != "US":
            continue
        tag_name = zip_to_tag.get(normalize_zip(ship_to.get("postalCode")))
        if not tag_name:
            continue
        tag_id = tag_ids[tag_name]
        if tag_id in (order.get("tagIds") or []):
            already[tag_name] += 1
            continue
        if apply:
            api("POST", "/orders/addtag", json={"orderId": order["orderId"], "tagId": tag_id})
        tagged[tag_name] += 1
        print(f"{'Tagged' if apply else 'Would tag'} order {order['orderNumber']} "
              f"(ZIP {ship_to.get('postalCode')}) -> {tag_name}")

    print(f"\nChecked {checked} orders.")
    for name in TAGS:
        verb = "newly tagged" if apply else "would be tagged"
        print(f"  {name}: {tagged[name]} {verb}, {already[name]} already had the tag")


if __name__ == "__main__":
    main()
