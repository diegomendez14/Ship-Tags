"""
Tag ShipStation orders whose ship-to ZIP is in zips.txt.

Setup:
  pip install requests
  export SHIPSTATION_KEY="your_v1_api_key"
  export SHIPSTATION_SECRET="your_v1_api_secret"

Usage:
  python tag_orders.py --tag-name "Special ZIP"            # dry run (default)
  python tag_orders.py --tag-name "Special ZIP" --apply    # actually tags orders
Optional: --  "orderStatus": a.status, "modifyDateStart": since,
"""
import argparse, os, re, sys, time
from datetime import datetime, timedelta, timezone
import requests

BASE = "https://ssapi.shipstation.com"
auth = (os.environ["SHIPSTATION_KEY"], os.environ["SHIPSTATION_SECRET"])


def call(method, path, **kw):
    """Request with automatic wait/retry on rate limit (429)."""
    while True:
        r = requests.request(method, BASE + path, auth=auth, timeout=60, **kw)
        if r.status_code == 429:
            wait = int(r.headers.get("X-Rate-Limit-Reset", 5)) + 1
            print(f"  rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        # slow down proactively when the window is nearly used up
        if int(r.headers.get("X-Rate-Limit-Remaining", 99)) <= 1:
            time.sleep(int(r.headers.get("X-Rate-Limit-Reset", 5)) + 1)
        return r.json() if r.content else {}


def load_zips(path):
    text = open(path).read()
    return set(re.findall(r"\d{5}", text))


def get_tag_id(name):
    for t in call("GET", "/accounts/listtags"):
        if t["name"].lower() == name.lower():
            return t["tagId"]
    sys.exit(f'Tag "{name}" not found. Create it in ShipStation first '
             f"(Settings > Account > Tags), then re-run.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag-name", default=os.environ.get("TAG_NAME"))
    ap.add_argument("--status", default="awaiting_shipment")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--zips", default="zips.txt")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not a.tag_name:
        sys.exit("Provide --tag-name or set the TAG_NAME environment variable.")

    zips = load_zips(a.zips)
    tag_id = get_tag_id(a.tag_name)
    since = (datetime.now(timezone.utc) - timedelta(days=a.days)).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{len(zips)} ZIPs loaded, tag id {tag_id}, mode: {'APPLY' if a.apply else 'DRY RUN'}")

    page, seen, matched, tagged = 1, 0, 0, 0
    while True:
        data = call("GET", "/orders", params={
            "orderStatus": a.status, "createDateStart": since,
            "page": page, "pageSize": 500})
        for o in data.get("orders", []):
            seen += 1
            zip5 = (o.get("shipTo") or {}).get("postalCode", "")[:5]
            if zip5 not in zips:
                continue
            matched += 1
            if tag_id in (o.get("tagIds") or []):
                continue  # already tagged
            print(f"  order {o['orderNumber']} (id {o['orderId']}) ZIP {zip5}")
            if a.apply:
                call("POST", "/orders/addtag",
                     json={"orderId": o["orderId"], "tagId": tag_id})
                tagged += 1
        if page >= data.get("pages", 1):
            break
        page += 1

    print(f"Done. Checked {seen} orders, {matched} matched, {tagged} newly tagged.")


if __name__ == "__main__":
    main()
