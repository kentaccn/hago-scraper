<p align="center">
  <img src="docs/assets/hago-icon.webp" alt="HA Go" height="64">
  &nbsp;&nbsp;
  <img src="docs/assets/ehealth-logo.png" alt="醫健通 eHealth" height="64">
</p>

<h1 align="center">hago-scraper</h1>

<p align="center">
  Export your own Hong Kong Hospital Authority records, parse the PDFs, and
  search them locally.
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="SECURITY.md">Security</a> ·
  <a href="#limitations">Limitations</a> ·
  <a href="ANDROID.md">Android</a> ·
  <a href="AGENTS.md">AI agents</a>
</p>

<p align="center">
  <img src="docs/assets/screenshot-overview.png" alt="Overview: latest draw, overdue tests, trend charts" width="49%">
  <img src="docs/assets/screenshot-test.png" alt="One test over time, with trend and next-test estimate" width="49%">
</p>
<p align="center"><sub>Sample data only: an invented diabetes patient from
<code>demo/make_demo_db.py</code>.</sub></p>

---

HA Go and 醫健通 (eHealth) show you your records but have no export and no API.
This drives the app through iPhone Mirroring, saves each report as a PDF, then
names, parses and indexes them.

The phone scripts need macOS, iPhone Mirroring and
[phone-harness](https://github.com/ShawnPana/phone-harness). The parser and
database tools run anywhere with Python and `pdftotext`.

This repository holds no records and nothing identifying. Your name,
date-of-birth year and paths come from a config file you create.

## Quick start

```bash
git clone https://github.com/<you>/hago-scraper.git && cd hago-scraper
brew install poppler && pip3 install numpy scipy matplotlib

cp .env.example ~/.hago-scraper.env && chmod 600 ~/.hago-scraper.env
$EDITOR ~/.hago-scraper.env          # HAGO_DIR, MEDICAL_DB, DOB_YEAR

python3 check_setup.py               # says what is missing

./phone/sweep_year.sh 2024           # log into the app by hand first
python3 parse/organise_hago.py "$INCOMING_DIR"           # dry run
python3 parse/organise_hago.py "$INCOMING_DIR" --apply
python3 analyse/build_db.py

python3 analyse/query.py lab ESR
python3 analyse/serve.py
```

To look around without any records, build a synthetic database:

```bash
python3 demo/make_demo_db.py
MEDICAL_DB=demo/demo.db MEDICAL_OUT=/tmp/demo BIND_MODE=localhost python3 analyse/serve.py
```

## What it does

```
phone/    drive eHealth / HA GO and save each report
          lab_sweep.py, rad_sweep.py, sweep_year.sh, sweep_rad_year.sh
parse/    organise_hago.py renames exports from their own text
          extract_labs.py reads the lab tables
analyse/  build_db.py    PDFs -> SQLite
          embed_db.py    local embeddings through Ollama
          query.py       ask / find / lab / on / flags / sql
          analyse.py     report and trend charts
          serve.py       read-only web UI
          analytes.py    what each test is for, English and 繁體中文
          stats_tests.py Theil-Sen, Mann-Kendall, BH correction, change-points
```

## Configuration

Everything comes from `~/.hago-scraper.env`, which the sweep drivers source.

```bash
export HA_ACCOUNT_NAME="你的名字"   # your name as the app prints it
export DOB_YEAR=1990
export HAGO_DIR="$HOME/records"
export INCOMING_DIR="$HOME/incoming"
export MEDICAL_DB="$HOME/records/medical.db"
export OLLAMA="http://localhost:11434"
```

Your name is in the app header and OCRs as if it were a table row, so
`HA_ACCOUNT_NAME` is used to filter it out.

Keep records outside the checkout, in a directory only you can read:

```bash
mkdir -p ~/records && chmod 700 ~/records
```

`.gitignore` blocks `*.pdf`, `*.db` and `*.csv`, but do not rely on it.

## Serving it

```bash
BIND_MODE=tailscale python3 analyse/serve.py    # default, tailnet only
BIND_MODE=localhost python3 analyse/serve.py    # behind a tunnel or proxy
BIND_MODE=lan       python3 analyse/serve.py    # anyone on your network
BIND=192.0.2.10     python3 analyse/serve.py
```

It exits rather than binding somewhere wider than you asked for. `BIND_MODE=any`
also needs `ALLOW_ANY_INTERFACE=1`. Anything past loopback or a tailnet needs
`AUTH_TOKEN` or it refuses to start.

Behind a Cloudflare Tunnel, the tunnel gives you TLS but authenticates nobody:

```bash
export AUTH_TOKEN=$(python3 -c "import secrets;print(secrets.token_urlsafe(32))")
export BEHIND_TLS=1
BIND_MODE=localhost python3 analyse/serve.py
cloudflared tunnel --url http://127.0.0.1:8137
```

Open `https://…/?token=<token>` once and it moves into a cookie.
See [SECURITY.md](SECURITY.md).

## Things that cost me a day

The row parser matched 「醫院」. Vision garbles 醫 into 盤, 馨, 髷, 齧, so those
rows were invisible and each year finished early. That silently skipped 37
records. Match 「院」 and check the structure instead.

Two sweeps at once fail with `cannot read image window.png` and
`cannot select year`. Those look like mirroring faults. Check `ps` first.

A failed export must not go in the ledger. Marking it done retires that record
permanently.

Running the organiser on its own destination deleted everything, because every
file matched itself as a duplicate. It refuses now.

Lab sheets are cumulative: one report reprints up to five earlier collect dates.
Exports overlap heavily, so deduplicate on content rather than filename.

Parse with `pdftotext -bbox-layout` and match columns by x coordinate. With
`-layout`, one blank cell shifts every later value a column left.

Group rows per page. A second panel restarts its y coordinates.

Drop the footnotes. "Plasma glucose concentration <2.5 or >= 11.1 mmol/L" and
the lipid "Desirable levels" tables both parse as results.

AirDrop failed every time between the phone and two Macs on the same Apple ID.
iCloud Drive is the only transport that worked.

Sessions expire after a few hours and Face ID cannot work over mirroring. Log in
by hand.

Run it from a terminal or plain ssh. A tmux server started over ssh has no
Screen Recording permission and every capture fails.

## Limitations

The parser reports what it recognises and is quiet about the rest, so treat the
database as a subset of your records and keep the PDFs.

One value per date and test. Two draws on the same day cannot both be stored.

Titres (`1:80`), scientific notation, negative numbers and free text such as
`No growth` are skipped.

`<0.6` is stored as 0.6 with a `comparator` field. It means below 0.6, so do not
trend it.

A value seen only on a single-date sheet has no reference range.

Radiology images are not downloaded, only reports.

Do not use any of this for medical decisions.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `cannot read image window.png` | mirroring dropped, or tmux without Screen Recording. Quit and reopen iPhone Mirroring |
| `cannot select year` | a second sweep is running, or a 確認 dialog is swallowing taps |
| taps do nothing, state says `ready` | the mirroring session died. Restart it |
| `iPhone in Use` | lock the phone |
| a year finishes suspiciously fast | a row parser matching a garbled label |
| `no embeddings for <model>` | run `embed_db.py`, or you changed model and must re-embed |
| `refusing to publish` | the new build has far fewer rows than the old one |

## Works with

| App | Publisher | iOS | Android |
|---|---|---|---|
| HA Go | Hospital Authority | [App Store](https://apps.apple.com/hk/app/ha-go/id1489096699) | [`hk.org.ha.hago`](https://play.google.com/store/apps/details?id=hk.org.ha.hago) |
| 醫健通 eHealth | eHealth, HKSAR Government | [App Store](https://apps.apple.com/hk/app/%E9%86%AB%E5%81%A5%E9%80%9Aehealth/id1514742468) | [Google Play](https://play.google.com/store/apps/details?id=hk.gov.ehealth.ehr) |

Not affiliated with or endorsed by the Hospital Authority or the HKSAR
Government. Their names and marks are used only to say which apps this reads.
It automates your own account and does nothing you could not do by tapping
through the apps yourself.

## Licence

MIT, see [LICENSE](LICENSE).
