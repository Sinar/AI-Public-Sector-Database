---
name: scrape-gamma-malaysia
description: "Scrape all GAMMA Malaysia government apps (gamma.malaysia.gov.my) to a CSV with full metadata (Nama, Agensi, Kategori, SDGS, Muat Turun, Penilaian, Keterangan)."
version: 1.0.0
author: sitin, Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [scraping, csv, gamma, malaysia, government, apps, inventory, periodic-update]
    related_skills: [scrape-rasa-jdn-hasil]
---

# Scrape GAMMA Malaysia Apps Skill

Scrape the **entire** Malaysian government mobile-app gallery from
`https://gamma.malaysia.gov.my/app-lists/recents` into one CSV with full
per-app metadata: **Nama, Agensi (full name), Kategori, SDGS, Jumlah Muat
Turun (per store + total), Penilaian (rating), Bil Ulasan, and full
Keterangan (description)**.

The companion script `scripts/scrape_gamma.py` walks the paginated list,
fetches every detail page (cached under `scripts/cache/`), parses, and writes
`gamma_malaysia_apps.csv`. Re-run any time the user asks to refresh; detail
pages are cached so a partial re-run only refetches missing app ids.

## When to Use

- User says "scrape gamma.malaysia.gov.my", "update the GAMMA app list", or
  "get all the Malaysian government apps".
- User wants a CSV of the government apps with downloads, ratings, SDGs,
  and descriptions.

Distinct from `scrape-rasa-jdn-hasil` (that one is `rasa.jdn.gov.my`, a
*different* site with a different parser). Do not confuse the two.

## Prerequisites

- `python` on PATH (3.9+). `requests` is the only third-party import — the
  system `python` may lack `pip`; if `import requests` fails, run
  `python -m ensurepip` first, or install via your package manager. (On this
  host `requests` was already available.)
- Outbound HTTPS access to `gamma.malaysia.gov.my`.
- Script: `scripts/scrape_gamma.py` (next to this file).

## How to Run

```bash
# default output: <home>/gamma_malaysia_apps.csv
python "<skill_dir>/scripts/scrape_gamma.py"

# explicit output (pass a NATIVE C:/... path, never /c/... on Windows):
python "<skill_dir>/scripts/scrape_gamma.py" "C:/Users/<user>/gamma_malaysia_apps.csv"
```

A full first run is ~318 detail fetches throttled 0.3–0.8s apart — a few
minutes. Run it as a **background** terminal task (`background=true,
notify=true`) and wait for completion; it prints progress to stderr and a
single `rows=N` line to stdout. Tell the user the final path and row count.

## Procedure

1. Run the script (above). It logs per-page and per-detail progress, then a
   final `WROTE <path> rows=N missing_details=[...]` line and `rows=N`.
2. Confirm `rows` matches the site's declared **Jumlah Aplikasi** (318 as of
   2026-09; the script stops at the hidden `#last-page` field, so it
   self-adjusts if the app count changes). `missing_details` should be empty
   — if not, re-run once (cached pages are skipped, only gaps refetch).
3. Quick sanity check: the top-downloaded app should be MySejahtera
   (tens of millions), and total per-app downloads sum to roughly 70M+ —
   *not* the portal-wide 101M (that figure is a site-wide stat, not per-app).
4. Report back: row count, the CSV path (as a `MEDIA:` link), and note the
   one or two apps whose Kategori is genuinely empty upstream.

## How the Site Works

- **List** (`/app-lists/recents`): *server-paginated*. 12 cards/page; the
  "Seterusnya" (Next) button just does `$.get(url + "?page=N")` and appends
  the returned `#posts` block. A hidden `<input id="last-page" value="27">`
  gives the total page count. Each card (`class="single-product"`) carries
  the app **id** (`/app-details/<id>`), name, agency **abbreviation** (e.g.
  "DVS"), category, and a rating span (`X.X Penilaian`).
- **Detail** (`/app-details/<id>`): the authoritative source. The
  `product-info` block has the real title + **full agency name**
  (e.g. "Jabatan Perkhidmatan Veterinar"). A run of
  `<span class="detail-label">…</span>: value` gives **Kategori** and
  **SDGS**. A `Jumlah Muat Turun</p>` block lists **three** per-store counts
  in order (Google Play | Apple App Store | Huawei AppGallery). The star
  rating is in the `review` block (count `fas fa-star` filled stars before
  the "Penilaian &amp; Ulasan" anchor). **Keterangan** is the big description
  block after `Keterangan</h4>`, ending at the `Penilaian Pengguna` /
  `item-details` section.
- The portal header shows **site-wide** totals (Pelawat, Jumlah Muat Turun,
  Jumlah Aplikasi, Jumlah Agensi). Ignore those for per-app data — they are
  aggregate figures, not app records.

## Pitfalls

- **Don't treat the 101M "Jumlah Muat Turun" as a per-app number.** It is the
  portal-wide total shown in the header of *every* page. Real per-app counts
  are the three store figures on the detail page (many apps are 0; a handful
  are multi-million).
- **Icon-only rating cards:** a few list cards render stars as
  `lni-star-filled` icons with **no** `X.X Penilaian` span, so the list
  parser returns no rating for them. This is fine — the detail page always
  has the rating, and the script falls back to detail values for
  name/agency/category anyway.
- **Empty Kategori is a real state.** At least one app (eKSS, id 833) has a
  blank Kategori value on the site (`Kategori :</span>` with nothing after).
  Don't "fix" or drop it.
- **Keterangan truncation:** stop the description capture at the
  `Penilaian Pengguna` / `<section class="item-details">` marker. Otherwise
  the rating-widget text leaks into the description field.
- **`requests` import:** the host `python` may not have it (no `pip`). Verify
  `python -c "import requests"` before a long run; bootstrap with
  `python -m ensurepip` if needed.
- **Windows paths:** pass output as a native `C:/Users/<user>/...` path, never
  the MSYS `/c/Users/...` form (MSYS path translation is disabled here).
- **Throttling / politeness:** keep the 0.3–0.8s sleeps. The site has a
  reCAPTCHA; hammering it risks a 403/429. The script backs off on 403/429.
- **Cache:** `scripts/cache/<id>.html` holds detail pages. Safe to delete at
  any time (the script refetches). Do **not** commit a populated cache into
  the skill — it's ~30 MB and regenerable.
- **Site redesign:** if `rows` comes back 0 or `WROTE ... rows=0`, the markup
  changed. Re-fetch a list + a detail page
  (`curl -sSL .../app-lists/recents -o l.html`), inspect the
  `single-product` and `detail-label` blocks, and update `parse_list` /
  `parse_detail`, then bump `version`.

## Verification

- Final `rows=N` matches the declared **Jumlah Aplikasi** (318 as of
  2026-09) and `missing_details=[]`.
- Spot-check: MySejahtera has a multi-million download total; an app like
  "SISTEM IDENTIFIKASI VESEL SIV" has per-store counts summing to its total
  (e.g. 188 | 26 | 15 = 229); a low-usage app has 0 downloads but still a
  populated Keterangan.
- Confirm per-store columns sum to `muat_turun_total` for every row (a cheap
  CSV check) and that `keterangan` contains no "Penilaian Pengguna" text
  (truncation leak).
