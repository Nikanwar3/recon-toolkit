#!/usr/bin/env python3
"""Generate synthetic multi-source order data with deliberate discrepancies.

Simulates four systems that each hold their own copy of the same orders
(ERP, Warehouse, Finance, Billing) plus a legacy HTML reporting portal,
the way real reconciliation targets rarely agree cleanly across systems.
"""
import argparse
import json
import random
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

random.seed(42)

CUSTOMERS = ["Acme Corp", "Globex", "Initech", "Umbrella LLC", "Soylent Inc",
             "Hooli", "Stark Industries", "Wayne Enterprises"]
STATUSES = ["PENDING", "SHIPPED", "DELIVERED", "CANCELLED"]


def build_base_orders(n):
    orders = []
    for i in range(1, n + 1):
        orders.append({
            "order_id": f"ORD-{i:05d}",
            "customer": random.choice(CUSTOMERS),
            "amount": round(random.uniform(50, 5000), 2),
            "status": random.choice(STATUSES),
            "date": f"2026-0{random.randint(1, 9)}-{random.randint(1, 28):02d}",
        })
    return orders


def perturb(orders, source, drop_rate=0.0, amount_noise_rate=0.0, status_flip_rate=0.0):
    out = []
    for o in orders:
        if random.random() < drop_rate:
            continue
        rec = dict(o)
        if random.random() < amount_noise_rate:
            rec["amount"] = round(rec["amount"] + random.choice([-1, 1]) * random.uniform(1, 250), 2)
        if random.random() < status_flip_rate:
            rec["status"] = random.choice(STATUSES)
        rec["source"] = source
        out.append(rec)
    return out


def write_json(orders, path):
    Path(path).write_text(json.dumps(orders, indent=2))


def write_xml(orders, path):
    root = ET.Element("orders")
    for o in orders:
        el = ET.SubElement(root, "order")
        for k, v in o.items():
            child = ET.SubElement(el, k)
            child.text = str(v)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def write_csv(orders, path):
    pd.DataFrame(orders).to_csv(path, index=False)


def write_xlsx(orders, path):
    pd.DataFrame(orders).to_excel(path, index=False)


def write_html(orders, path):
    rows = "\n".join(
        f"<tr><td>{o['order_id']}</td><td>{o['customer']}</td>"
        f"<td>{o['amount']}</td><td>{o['status']}</td><td>{o['date']}</td></tr>"
        for o in orders
    )
    html = f"""<html><body>
<h1>Legacy Order Report</h1>
<table id="orders-table">
<tr><th>Order ID</th><th>Customer</th><th>Amount</th><th>Status</th><th>Date</th></tr>
{rows}
</table>
</body></html>"""
    Path(path).write_text(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="data/sample")
    ap.add_argument("--count", type=int, default=200)
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    base = build_base_orders(args.count)

    write_json(perturb(base, "erp"), out / "erp_orders.json")
    write_xml(perturb(base, "warehouse", drop_rate=0.05, status_flip_rate=0.08), out / "warehouse_orders.xml")
    write_csv(perturb(base, "finance", amount_noise_rate=0.10), out / "finance_orders.csv")
    write_xlsx(perturb(base, "billing", drop_rate=0.03, amount_noise_rate=0.05), out / "billing_orders.xlsx")
    write_html(
        perturb(base, "legacy_portal", drop_rate=0.07, status_flip_rate=0.05),
        out / "legacy_report.html",
    )

    print(f"Generated {args.count} base orders across 5 sources in {out}/")


if __name__ == "__main__":
    main()
