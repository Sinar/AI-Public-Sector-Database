#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Scrape the full GAMMA Malaysia government-app gallery into one CSV.

Site: https://gamma.malaysia.gov.my/app-lists/recents  (318 apps as of 2026-09)
Pipeline:
  1. Walk the server-paginated list (12 cards/page, `?page=N`) -> app id, name,
     agency, category, rating.
  2. Fetch every /app-details/<id> page (cached under cache/) -> full metadata:
     agency full name, kategori, SDGS, per-store download counts, rating,
     review count, and the full `keterangan` (description) text.
  3. Write gamma_apps.csv (UTF-8 with BOM so Excel shows Malay correctly).

Pure stdlib + `requests`. Re-run any time to refresh; detail pages are cached,
so a re-run after a partial failure only re-fetches missing ids.

Usage:
    python scrape_gamma.py [OUTPUT_CSV]
Default output: <user_home>/gamma_malaysia_apps.csv
"""
import re, csv, os, sys, time, random, html as htmlmod
import requests

BASE = "https://gamma.malaysia.gov.my"
HDRS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124 Safari/537.36"),
    "Accept-Language": "ms-MY,ms;q=0.9,en;q=0.8",
}
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)
sess = requests.Session(); sess.headers.update(HDRS)


def get(url, tries=4):
    for a in range(tries):
        try:
            r = sess.get(url, timeout=30)
            if r.status_code == 200:
                return r.text
            if r.status_code in (403, 429):
                time.sleep(3 * (a + 1)); continue
            print(f"  HTTP {r.status_code} {url}", file=sys.stderr)
        except Exception as e:
            print(f"  ERR {url}: {e}", file=sys.stderr)
        time.sleep(1.5 * (a + 1))
    return None


def clean(s):
    if s is None: return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = htmlmod.unescape(s).replace("\u200b", "")
    return re.sub(r"\s+", " ", s).strip()


def norm_label(s):
    s = htmlmod.unescape(s).replace("\u200b", "")
    return re.sub(r"[\s\u00a0]+", " ", s).strip().lower()


# ---------------- LIST PAGES ----------------
def parse_list(html):
    apps = []
    for p in html.split('class="single-product"')[1:]:
        p = p[:2000]
        m = re.search(r'app-details/(\d+)', p)
        if not m: continue
        name = re.search(r'<h4 class="title">\s*<a[^>]*>(.*?)</a>', p, re.S)
        cat = re.search(r'<span class="category">(.*?)</span>', p, re.S)
        ag = re.search(r'<h6 class="agensi[^"]*">(.*?)</h6>', p, re.S)
        rt = re.search(r'<span>([\d.]+) Penilaian</span>', p)  # icon-only cards -> None
        apps.append({"id": m.group(1),
                     "nama": clean(name.group(1)) if name else "",
                     "agensi": clean(ag.group(1)) if ag else "",
                     "kategori": clean(cat.group(1)) if cat else "",
                     "penilaian": rt.group(1) if rt else ""})
    return apps


def scrape_lists(last_page=40):
    apps, seen = [], set()
    for pg in range(1, last_page + 1):
        url = f"{BASE}/app-lists/recents" + (f"?page={pg}" if pg > 1 else "")
        h = get(url)
        if h is None:
            print(f"!! page {pg} failed", file=sys.stderr); continue
        lp = re.search(r'id="last-page"\s+value="(\d+)"', h)
        lp = int(lp.group(1)) if lp else last_page
        items = parse_list(h)
        new = 0
        for it in items:
            if it["id"] not in seen:
                seen.add(it["id"]); apps.append(it); new += 1
        print(f"page {pg}/{lp}: {len(items)} cards, {new} new, total {len(apps)}", file=sys.stderr)
        if pg >= lp: break
        time.sleep(random.uniform(0.4, 1.0))
    return apps


# ---------------- DETAIL PAGES ----------------
def parse_detail(aid, h):
    d = {"id": aid}
    pi = h.find('<div class="product-info">')
    seg = h[pi: pi + 3000] if pi != -1 else h
    mt = re.search(r'<h2 class="title">(.*?)</h2>', seg, re.S)
    d["nama"] = clean(mt.group(1)) if mt else ""
    ma = re.search(r'<h6 class="category">(.*?)</h6>', seg, re.S)
    d["agensi"] = clean(ma.group(1)) if ma else ""
    d["kategori"] = d["sdgs"] = ""
    for lb in re.finditer(r'<span class="detail-label">(.*?)</span>\s*:\s*(.*?)(?:</p>|<a)', h, re.S):
        key, val = norm_label(lb.group(1)), clean(lb.group(2))
        if key == "kategori": d["kategori"] = val
        elif key in ("sdgs", "sdg"): d["sdgs"] = val
    # per-store downloads (Play | App Store | Huawei)
    i = h.find('Jumlah Muat Turun</p>')
    gp = as_ = hw = ""
    if i != -1:
        blk = h[i: i + 1400]; end = blk.find('</p>', 50)
        nums = re.findall(r'>(\d[\d,]*)\s*<', blk[:end] if end != -1 else blk)
        if len(nums) >= 1: gp = nums[0]
        if len(nums) >= 2: as_ = nums[1]
        if len(nums) >= 3: hw = nums[2]
    def toint(x):
        try: return int(x.replace(",", ""))
        except: return 0
    d["muat_turun_play"], d["muat_turun_appstore"], d["muat_turun_huawei"] = gp, as_, hw
    d["muat_turun_total"] = toint(gp) + toint(as_) + toint(hw)
    # rating from stars in the review block + review count
    j = h.find('Penilaian &amp; Ulasan')
    filled = half = 0
    if j != -1:
        seg2 = h[max(0, j - 2000): j + 40]
        filled = seg2.count('fas fa-star'); half = seg2.count('fa-star-half')
        mc = re.search(r'<span>(\d+) Penilaian', seg2)
        d["bil_ulasan"] = mc.group(1) if mc else ""
    else:
        d["bil_ulasan"] = ""
    d["penilaian"] = f"{(filled + 0.5 * half):.1f}" if (filled or half or d["bil_ulasan"]) else "0.0"
    # keterangan: from "Keterangan</h4>" to the Penilaian Pengguna / item-details section
    k = h.find('Keterangan</h4>'); ket = ""
    if k != -1:
        after = h[k: k + 60000].find('</h4>')
        chunk = h[k + after + 5: k + after + 5 + 60000]
        for marker in ['<section class="item-details">', 'Penilaian Pengguna', '<span class="hr']:
            mm = chunk.find(marker)
            if mm != -1: chunk = chunk[:mm]
        ket = clean(chunk)
    d["keterangan"] = ket
    return d


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), "gamma_malaysia_apps.csv")
    apps = scrape_lists()
    print(f"\n{len(apps)} unique apps from lists", file=sys.stderr)
    rows, missing = [], []
    for idx, a in enumerate(apps, 1):
        cf = os.path.join(CACHE, f'{a["id"]}.html')
        if os.path.exists(cf) and os.path.getsize(cf) > 5000:
            h = open(cf, encoding="utf-8").read()
        else:
            h = get(f'{BASE}/app-details/{a["id"]}')
            if h:
                open(cf, "w", encoding="utf-8").write(h)
        if h is None:
            missing.append(a["id"]); continue
        d = parse_detail(a["id"], h)
        # fall back to list values if detail title/agency missing
        if not d["nama"]: d["nama"] = a["nama"]
        if not d["agensi"]: d["agensi"] = a["agensi"]
        if not d["kategori"]: d["kategori"] = a["kategori"]
        rows.append(d)
        if idx % 20 == 0 or idx == len(apps):
            print(f"  details {idx}/{len(apps)}", file=sys.stderr)
        time.sleep(random.uniform(0.3, 0.8))

    cols = ["id", "nama", "agensi", "kategori", "sdgs",
            "muat_turun_total", "muat_turun_play", "muat_turun_appstore", "muat_turun_huawei",
            "penilaian", "bil_ulasan", "keterangan"]
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    print(f"\nWROTE {out} rows={len(rows)} missing_details={missing}", file=sys.stderr)
    print(f"rows={len(rows)}")  # single stdout line for the caller


if __name__ == "__main__":
    main()
