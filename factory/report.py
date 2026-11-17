"""Report vendite da Etsy: aggiorna `state/sales.json` e scrive `reports/<data>.md`."""

from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

from .etsy import Etsy


def _money(m: dict | None) -> float:
    if not m:
        return 0.0
    return m["amount"] / (m.get("divisor") or 100)


def sales_report(client: Etsy, shop_id: int, etsy_state: dict, out_dir: Path,
                 sales_path: Path, days: int = 7) -> Path:
    by_listing = {v["listing_id"]: k for k, v in etsy_state.items() if "listing_id" in v}
    receipts = client.receipts(shop_id)
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)

    totals: dict[str, dict] = defaultdict(lambda: {"orders": 0, "revenue": 0.0})
    week_orders, week_revenue, currency = 0, 0.0, ""
    for r in receipts:
        created = dt.datetime.fromtimestamp(r.get("created_timestamp") or r.get("create_timestamp") or 0,
                                            dt.UTC)
        recent = created >= since
        if recent:
            week_orders += 1
            week_revenue += _money(r.get("grandtotal"))
            currency = (r.get("grandtotal") or {}).get("currency_code", currency)
        for t in r.get("transactions", []):
            key = by_listing.get(t.get("listing_id"), f"altro:{t.get('listing_id')}")
            totals[key]["orders"] += t.get("quantity", 1)
            totals[key]["revenue"] += _money(t.get("price")) * t.get("quantity", 1)

    sales_path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: {"orders": v["orders"], "revenue": round(v["revenue"], 2)}
             for k, v in sorted(totals.items(), key=lambda kv: -kv[1]["orders"])}
    sales_path.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    today = dt.date.today().isoformat()
    lines = [
        f"# Report {today}", "",
        f"- Ordini negli ultimi {days} giorni: **{week_orders}**",
        f"- Incasso lordo negli ultimi {days} giorni: **{week_revenue:.2f} {currency}**",
        f"- Ordini totali registrati: **{len(receipts)}**",
        f"- Inserzioni pubblicate: **{sum(1 for v in etsy_state.values() if v.get('step') == 'done')}**",
        "", "## Prodotti più venduti (da sempre)", "",
        "| Prodotto | Pezzi | Incasso |", "|---|---:|---:|",
    ]
    for k, v in list(clean.items())[:15]:
        lines.append(f"| {k} | {v['orders']} | {v['revenue']:.2f} |")
    if not clean:
        lines.append("| nessuna vendita ancora | | |")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{today}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
