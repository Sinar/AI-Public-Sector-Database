#!/usr/bin/env python
"""Scrape RASA JDN (rasa.jdn.gov.my/carian/hasil) into a CSV.

The hasil page is server-rendered: the single GET returns EVERY record
(~2,480+), each as a table row, and each row's app-name cell embeds a
Bootstrap modal holding that app's Fungsi and Objektif. There is no real
server pagination to walk - one fetch is the whole dataset.

Columns: Bil, Nama Aplikasi, Agensi, Pegawai Bertanggungjawab, Emel,
No. Telefon, Fungsi, Objektif.

If an existing CSV is found at the target path, it is treated as the
source of truth: scraped fields are refreshed in place, any extra columns
you added (notes, tags, ...) are preserved, and records removed upstream
are dropped.

Usage:
    python update_rasa_hasil.py [output_csv_path]
"""
import csv
import html as _html
import io
import os
import re
import sys
import urllib.request
from pathlib import Path

URL = "https://rasa.jdn.gov.my/carian/hasil"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ms-MY,ms;q=0.8,en;q=0.6",
}
FIELDS = [
    "Bil",
    "Nama Aplikasi",
    "Agensi",
    "Pegawai Bertanggungjawab",
    "Emel",
    "No. Telefon",
    "Fungsi",
    "Objektif",
]
SCRAPE_FIELDS = set(FIELDS)

# A record row: <td>Bil</td><td><a href="#myModal-N">NAME</a><div modal>...</div></td>
# <td>Agensi</td><td>Pegawai</td><td>Emel</td><td>Phone</td></tr>
ROW_RE = re.compile(
    r"<tr>\s*"
    r"<td>\s*(\d+)\s*</td>\s*"
    r"<td>\s*"
    r'<a href="#myModal-(\d+)"[^>]*>(.*?)</a>'
    r"\s*<!-- start modal -->\s*"
    r'<div class="modal" id="myModal-\2"[^>]*>(.*?)</div>\s*'
    r"<!-- end modal -->\s*"
    r"</td>\s*"
    r"<td>\s*(.*?)\s*</td>\s*"
    r"<td>\s*(.*?)\s*</td>\s*"
    r"<td>\s*(.*?)\s*</td>\s*"
    r"<td>\s*(.*?)\s*</td>\s*"
    r"</tr>",
    re.S,
)
MODAL_RE = re.compile(
    r'<table[^>]*>\s*<tr>\s*<th>Fungsi</th>\s*<th>Objektif</th>\s*</tr>\s*<tr>(.*?)</tr>\s*</table>',
    re.S,
)


def clean(h):
    t = re.sub(r"<[^>]+>", "", h)
    t = _html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def parse_modal(modal_html):
    m = MODAL_RE.search(modal_html)
    if not m:
        return "", ""
    cells = re.findall(r"<td>(.*?)</td>", m.group(1), re.S)
    f = clean(cells[0]) if len(cells) > 0 else ""
    o = clean(cells[1]) if len(cells) > 1 else ""
    return f, o


def fetch():
    req = urllib.request.Request(URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def parse(s):
    """Return (records, declared_total) from the HTML source string."""
    total_m = re.search(r"Hasil carian:\s*(\d+)\s*rekod", s)
    declared = int(total_m.group(1)) if total_m else None
    records = []
    for m in ROW_RE.finditer(s):
        bil, _mid, name_html, modal_html, agensi, pegawai, emel, phone = m.groups()
        fungsi, objektif = parse_modal(modal_html)
        records.append(
            {
                "Bil": int(bil),
                "Nama Aplikasi": clean(name_html),
                "Agensi": clean(agensi),
                "Pegawai Bertanggungjawab": clean(pegawai),
                "Emel": clean(emel),
                "No. Telefon": clean(phone),
                "Fungsi": fungsi,
                "Objektif": objektif,
            }
        )
    return records, declared


def merge(existing_rows, scraped, header):
    """Refresh scraped fields; preserve extra columns and their values.

    Returns (merged_rows, dropped_bils) where merged_rows is a list of dicts
    keyed by the full header.
    """
    by_bil = {}
    for row in existing_rows:
        try:
            bil = int(row.get("Bil", ""))
        except (TypeError, ValueError):
            bil = None
        if bil is not None:
            by_bil[bil] = row

    merged = []
    for rec in scraped:
        base = dict(by_bil.get(rec["Bil"], {}))
        # keep any extra-column values already present
        for k, v in rec.items():
            base[k] = v
        base["Bil"] = str(rec["Bil"])
        merged.append(base)

    scraped_bils = {rec["Bil"] for rec in scraped}
    dropped = sorted(b for b in by_bil if b not in scraped_bils)
    return merged, dropped, header


def main(argv):
    out_path = Path(argv[1]) if len(argv) > 1 else Path.home() / "hasil_rasa_jdn.csv"
    out_path = out_path.expanduser().resolve()

    print(f"Fetching {URL} ...", flush=True)
    raw = fetch()
    # Page is mostly UTF-8 with a handful of stray cp1252 bytes; replace is safe.
    s = raw.decode("utf-8", errors="replace")

    records, declared = parse(s)
    if not records:
        print("ERROR: no records parsed. Page structure may have changed.", file=sys.stderr)
        sys.exit(2)

    print(f"Parsed {len(records)} records" + (f" (page declares {declared})" if declared else ""))
    if declared is not None and abs(declared - len(records)) > max(2, declared * 0.001):
        print(
            f"WARNING: parsed {len(records)} != declared {declared}. "
            "Check that the parser is still matching the page layout.",
            file=sys.stderr,
        )

    # Existing CSV?
    existing_rows, header = [], FIELDS
    if out_path.exists():
        with open(out_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or FIELDS
            existing_rows = list(reader)
        print(f"Found existing CSV ({len(existing_rows)} rows); refreshing in place.")
    else:
        print("No existing CSV; writing fresh.")

    merged, dropped, header = merge(existing_rows, records, header)
    # header keeps existing order; ensure all scrape fields present
    for fld in FIELDS:
        if fld not in header:
            header.append(fld)

    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for row in merged:
            w.writerow({h: row.get(h, "") for h in header})
    os.replace(tmp, out_path)

    n_f = sum(1 for r in records if r["Fungsi"])
    n_o = sum(1 for r in records if r["Objektif"])
    print(f"Wrote {out_path}")
    print(f"  rows: {len(merged)}  |  fungsi filled: {n_f}  |  objektif filled: {n_o}")
    if dropped:
        print(f"  removed from CSV (no longer on site): {len(dropped)} -> Bils {dropped[:10]}{'...' if len(dropped)>10 else ''}")
    print("OK")


if __name__ == "__main__":
    main(sys.argv)
