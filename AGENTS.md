# Working on this repo with an AI agent

Read by Codex automatically; `CLAUDE.md` points Claude Code here. If you drive
this tool with an agent, these are the rules that matter — most were learned by
breaking something.

## What you need installed

**For parsing and analysis: nothing special.** `pdftotext`, Python, numpy. Any
agent with shell access can run the whole `parse/` and `analyse/` pipeline. Run
`python3 check_setup.py` first; it tells you what is missing.

**For driving the phone: one skill.**
[phone-harness](https://github.com/ShawnPana/phone-harness) provides screen
capture and tap/type control over iPhone Mirroring, and ships a `SKILL.md` that
Claude Code loads. Codex uses it the same way — it is just a CLI:

```bash
phone-harness <<'PY'
print(screen_info())
PY
```

It needs **Accessibility** and **Screen Recording** granted to the terminal the
agent runs in. Screen Recording only takes effect after that terminal restarts,
and a **tmux server started over ssh does not inherit it** — captures fail with
a misleading `cannot read image` error.

No other skill, plugin or MCP server is required.

## Hard rules

1. **Never send records to a hosted model.** Not the PDFs, not the database, not
   the report. Reviewing the *code* with a cloud model is fine. Before you do,
   grep for clinical facts — diagnoses, drug names, allergies, procedures, event
   dates — not just names and ID numbers. A diagnosis plus a drug plus an
   allergy list is medical information about someone even with the name removed.
2. **Never hard-code anything identifying.** Name, date of birth, paths, hosts
   all come from `~/.hago-scraper.env`. If you need a value, read the
   environment.
3. **One phone sweep at a time.** Check `ps` for `phone_harness.run` and
   `sweep_year` before launching. Concurrent sweeps produce
   `cannot read image window.png` and `cannot select year`, which look like app
   faults and are not.
4. **Never run `organise_hago.py --apply` against the archive directory.** It
   would treat every file as a duplicate of itself and delete all of them. It
   refuses now — do not "fix" that guard.
5. **Never ledger a failed export.** Only `r == "ok"` earns an entry; failures
   belong in the fails file with a retry cap. Marking a failure done retires
   that record permanently.
6. **Do not weaken `serve.py`'s bind guard.** It refuses to start rather than
   listening somewhere wider than asked. On café wifi a `0.0.0.0` bind publishes
   medical records to strangers.
7. **Never clear the transfer folder while a sweep is running.** The sweeper
   ledgers a record the moment it saves, so deleting files mid-run leaves the
   record marked done with no file to show for it — and it will never be
   exported again. Stop the sweep first, then move files out. If it happens,
   remove that key from the ledger so the record is retried.
8. **Do not commit records.** `.gitignore` blocks `*.pdf`, `*.db`, `*.csv`, but
   check `git status` before committing anyway.

## Things that will mislead you

- **The parser is a subset, not a transcript.** It reports what it recognises
  and stays silent about the rest. Never describe its output as complete.
- **`<0.6` is an upper bound, not 0.6.** Do not trend censored values or quote
  one as a maximum.
- **Cumulative sheets repeat up to five previous collect dates**, so exports
  overlap heavily. Deduplicate on content, never filename.
- **`build_db.py` rebuilds from scratch** into a temp file and refuses to
  publish if the new build has far fewer rows than the old one. If it refuses,
  find out why rather than deleting the database.
- **n is small.** 27 draw dates over a decade. `stats_tests.py` applies
  Benjamini-Hochberg across analytes and a permutation test for change-points
  precisely because eyeballing a split and quoting its p-value manufactures
  findings. Use it; do not reintroduce hand-picked comparisons.
- **This is not a medical device.** State what the data show and what to discuss
  with a doctor. Do not give clinical advice.

## Verifying your work

```bash
python3 check_setup.py                    # prerequisites and permissions
python3 analyse/build_db.py               # should report the expected row count
python3 analyse/query.py flags            # spot-check against a source PDF
```

When you change the parser, rebuild and compare the row count against the
previous build. A parser change that silently drops results is the failure mode
that matters most here, and it is invisible unless you look.
