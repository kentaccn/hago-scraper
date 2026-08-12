# hago-scraper

Export your own Hong Kong Hospital Authority medical records off your iPhone,
and turn the resulting PDFs into structured data.

HA GO and 醫健通 (eHealth) let you *view* your records but give you no bulk
export and no API. This drives the apps through iPhone Mirroring, saves each
report as a PDF, then names and parses them.

**It contains no medical data and no personal identifiers** — those live only on
the machine you run it on. Configuration that would identify anyone is read from
the environment.

## Layout

```
phone/   drive the iPhone through eHealth / HA GO and save each report
  lab_sweep.py        sweep every 化驗紀錄 record for one year
  rad_sweep.py        the same for 放射紀錄
  sweep_year.sh       relaunch the sweeper until a year comes back dry twice
  sweep_rad_year.sh   the same, for radiology
  lab_years.py        probe: which years does the filter offer?

parse/   turn the exported PDFs into data
  organise_hago.py    rename exports to YYYY-MM-DD_<type>_<site>.pdf from their own text
  extract_labs.py     read the lab tables into one analyte x collect-date CSV

analyse/ store, search and read the result
  build_db.py         PDFs -> SQLite: documents, quantified lab_results, text chunks
  embed_db.py         embed the chunks locally (Ollama) for semantic search
  query.py            CLI: semantic search, keyword search, one test over time
  analyse.py          write an analysis report + trend/forecast charts
  serve.py            read-only web UI, bound to a Tailscale address only
  analytes.py         what each test is for, English and 繁體中文
  inflammation_timeline.py   wide ESR/CRP/HGB/MCV/PLT/WBC table
```

`phone/` needs [phone-harness](https://github.com/ShawnPana/phone-harness) and a
Mac with iPhone Mirroring paired. `parse/` needs only `pdftotext` (poppler).

## Configuration

Copy `.env.example` to `~/.hago-scraper.env` and fill it in — the sweep drivers
source it automatically. Nothing identifying is stored in the repository.

```bash
export HA_ACCOUNT_NAME="你的名字"   # the signed-in name, filtered out of OCR rows
export DOB_YEAR=1990                # so a date of birth is never read as a collect date
export HAGO_DIR=~/records           # where the renamed PDFs live
export INCOMING_DIR=~/incoming      # where fresh exports arrive
export MEDICAL_DB=~/records/medical.db
export OLLAMA=http://localhost:11434
```

## Running

```bash
YEAR=2024 phone-harness < phone/lab_sweep.py   # one pass
./phone/sweep_year.sh 2024                     # until two dry runs
python3 parse/organise_hago.py "$INCOMING_DIR"           # dry run
python3 parse/organise_hago.py "$INCOMING_DIR" --apply   # move + rename
python3 parse/extract_labs.py > labs.csv

python3 analyse/build_db.py        # -> medical.db
python3 analyse/embed_db.py        # local embeddings for semantic search
python3 analyse/analyse.py         # -> analysis.md + charts/
python3 analyse/query.py ask "gut inflammation"
python3 analyse/serve.py           # read-only web UI on your tailnet address
```

## Your records never enter this repository

`.gitignore` blocks `*.pdf`, `*.db`, `*.csv` and the record directories, and the
code holds no diagnosis, medication or identifier — the clinical summary in the
report is built by searching your own database at runtime. `serve.py` binds to
the Tailscale address only and refuses to start if it cannot find one, rather
than falling back to `0.0.0.0` and exposing records to whatever LAN you are on.

Run **one sweep at a time**. Two at once fight over the same phone and fail with
misleading errors (see below).

## Things that cost a day to learn

- **Never match a Chinese label exactly.** The row parser keyed on 「醫院」 and
  Vision garbles 醫 constantly — 盤院, 馨院, 髷院, 齧院. Every mis-OCR'd row was
  invisible, so the sweeper declared each year finished early and quietly
  skipped **37 records**. Match 「院」 and validate structurally instead.
- **Never run two sweeps concurrently.** They produce
  `cannot read image window.png` and `cannot select year`, which look like app
  or mirroring faults and are neither. Check `ps` before launching.
- **A failed export must not be ledgered.** Marking a record done on failure
  retires it permanently. Record failures separately and give up only after N
  attempts.
- **The lab sheets are cumulative** — one report carries up to five collect
  dates side by side, so exports overlap heavily and most values end up
  confirmed by several independent reports. Deduplicate on content, not
  filename.
- **Parse the PDFs by word coordinates, not whitespace.**
  `pdftotext -bbox-layout` plus nearest-column-centre matching; `-layout`
  shifts every value one column left as soon as a cell is blank.
- **Group rows per page.** A second panel restarts its y coordinates, so
  document-wide grouping splices unrelated tables together.
- **Drop the interpretive prose.** Sentences like
  "Plasma glucose concentration <2.5 or >= 11.1 mmol/L" parse as results, as do
  the lipid "Desirable levels" / "Treatment goals" tables.
- **iCloud Drive is the transport that works.** AirDrop failed every time
  between this iPhone and two Macs on the same Apple ID. Treat iCloud strictly
  as a pipe: move files to local storage and delete the cloud copy.
- **Sessions expire every few hours** and biometric login cannot work over
  mirroring — there is no face at the phone. Expect to log in by hand.
- **Run it over plain ssh, not tmux.** A tmux server started from ssh lacks
  Screen Recording permission and every capture fails silently.

## Licence

MIT.
