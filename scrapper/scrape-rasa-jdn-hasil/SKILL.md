---
name: scrape-rasa-jdn-hasil
description: "Update the RASA JDN hasil CSV (all apps + Fungsi/Objektif)."
version: 1.1.0
author: sitin, Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [scraping, csv, rasa, jdn, government, inventory, periodic-update]
---

# Scrape RASA JDN Hasil Skill

Scrape the full Malaysian public-sector application inventory from
`https://rasa.jdn.gov.my/carian/hasil` into a CSV, including each app's
**Fungsi** and **Objektif** (the metadata shown when you click a record).
The companion script `scripts/update_rasa_hasil.py` does the fetch, parse,
and write in one shot. Re-run it any time the user asks to refresh the CSV.

## When to Use

- User says "update the hasil / RASA / JDN CSV", "refresh the JDN records",
  or "scrape rasa.jdn.gov.my again".
- User wants a CSV of the public-sector apps with Fungsi and Objektif.

Don't use for: a *search* of the site (the `carian` query box) — this skill
pulls the entire unfiltered inventory. If the user wants a filtered subset,
fetch with `?carian=<term>` instead and re-run the same parser.

## Prerequisites

- `python` on PATH (3.9+). No third-party packages — the script is pure
  stdlib (`urllib`, `csv`, `re`).
- Outbound HTTPS access to `rasa.jdn.gov.my`.
- Script: `scripts/update_rasa_hasil.py` (next to this file).

## How to Run

```bash
# default output: <home>/hasil_rasa_jdn.csv
python "<skill_dir>/scripts/update_rasa_hasil.py"

# explicit output path (pass a NATIVE path, not /c/... on Windows):
python "<skill_dir>/scripts/update_rasa_hasil.py" "C:/Users/<user>/hasil_rasa_jdn.csv"
```

The default output is `hasil_rasa_jdn.csv` in the user's home directory.
Tell the user the final path and row count when done.

## Google Sheets Variant (Apps Script, weekly auto-update)

For "update it on my Google Sheet every week", there is a ready-to-paste
Apps Script at `C:/Users/sitin/RasaHasil_Updater.gs` (JS port of the same
parser + merge logic, tested in Node against the live page). If it's missing
or stale, regenerate it from this skill's knowledge.

- User setup: Sheet → **Extensions → Apps Script** → paste the file → select
  `setup` in the run menu → Run → authorize. `setup()` does the first update
  immediately AND creates the weekly trigger (default Monday 08:00).
- It preserves extra user columns (keyed on Bil), refreshes the 8 scraped
  columns, and drops rows gone from the site — same merge semantics as the
  Python script, so the two variants stay in sync.

**Trigger API gotcha (caused a real `is not a function` error):**
`ClockTriggerBuilder` has **no `.weekly()` method** — use
`.timeBased().everyWeeks(1).onWeekDay(ScriptApp.WeekDay.MONDAY).atHour(8)
.create()`. Note `onWeekDay` is capital-D and takes the `ScriptApp.WeekDay`
enum (MONDAY…SUNDAY), not a number. `.atHour(8)` fires somewhere in the
08:00–08:59 window (Apps Script picks the moment) — fine for weekly jobs.

## Procedure

1. Run the script (above). It prints a summary line: rows, how many have
   Fungsi filled, how many have Objektif filled.
2. Confirm `rows` is close to the number in `Parsed N records (page declares M)`.
   The script already warns if the two diverge by more than ~1%.
3. Report back to the user: record count, filled-metadata counts, and the
   CSV path (as a `MEDIA:` link if they'll want to open it).

## How the Site Works (why no pagination loop)

- The page is **server-rendered**. A single `GET /carian/hasil` returns
  *every* record (~2,480 as of 2026-09) inline — the "pagination" is a
  client-side jQuery DataTable, so there is no server-side page to walk.
  Do NOT try to loop `page=1..N`; it won't help and will just refetch the
  same blob.
- Each record is one `<tr>` with 6 columns:
  `Bil`, `Nama Aplikasi`, `Agensi`, `Pegawai Bertanggungjawab`, `Emel`,
  `No. Telefon`. The app-name cell (`<a href="#myModal-N">`) also embeds a
  Bootstrap `<div class="modal">` whose inner table holds the
  `<th>Fungsi</th><th>Objektif</th>` row and one `<td>` each — that is the
  metadata the user clicks to see.
- **Fungsi/Objektif are genuinely empty for many records** upstream (the
  modal cells are blank). An empty column is a real state, not a parse bug —
  don't "fix" it. ~1,900 of ~2,480 have Fungsi; fewer have Objektif.

## Pitfalls

- **Encoding:** the page declares `charset=UTF-8` but contains a handful of
  stray Windows-1252 bytes. The script decodes with
  `errors="replace"` (a few U+FFFD), which is the correct call. Don't switch
  to strict UTF-8 — it will raise on the stray bytes.
- **Windows paths:** when passing the output path on Windows, use a native
  `C:/Users/<user>/...` path, never the MSYS `/c/Users/...` form — MSYS path
  translation is disabled here and `/c/...` mis-resolves to `C:\c\...`.
- **Don't drop user columns:** if the CSV already has extra columns (notes,
  tags, a `Nota` column), the script preserves them and their values, refreshes
  only the 8 scraped fields, and removes records no longer on the site. Keep
  the same CSV path on each run so history is retained.
- **Record IDs:** identity key is `Bil`. `myModal-N` ids are non-sequential
  and are NOT stable across updates — never use them as a key.
- **Site redesign:** if `Parsed 0 records`, the page layout changed. Re-read
  the current HTML (see below) and adjust `ROW_RE`/`MODAL_RE` in the script,
  then bump `version`.

## Verification

- Script prints `OK` and a row count matching the page's declared total.
- Spot-check: open the CSV and confirm a known app (e.g. Bil 6
  "Sistem Pengurusan Kerjaya Perkhidmatan Sistem Maklumat") has populated
  Fungsi/Objektif, and that a known-empty one (Bil 1) has blank metadata.
- To debug layout drift: fetch the raw HTML
  (`curl -sSL https://rasa.jdn.gov.my/carian/hasil -o page.html`) and inspect
  the first `<tr>` that contains `<a href="#myModal-`.
