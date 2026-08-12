# Security

This tool handles medical records. Short document, worth reading once.

## What is actually sensitive

The **records** are: the exported PDFs, the database built from them, the CSVs,
the charts, and the generated report. Those carry your name, ID number, date of
birth, hospital numbers, clinicians, diagnoses and results.

The **code** is not sensitive, and is written to stay that way. Everything
identifying — your name, date-of-birth year, paths, hosts — is read from the
environment. If you ever find a diagnosis or a drug name hard-coded in a source
file, that is a bug worth fixing before you share the code.

## Where to keep records

- **Outside the repository.** `.gitignore` blocks `*.pdf`, `*.db`, `*.csv` and
  the record directories, but that is a backstop, not a plan.
- **`chmod 700` the directory, `chmod 600` the files.** On a shared or managed
  Mac, default permissions leave your database readable by other local accounts.
  The pipeline sets `600` on everything it generates; `check_setup.py` will tell
  you if a directory is too open.
- **Encrypt the disk.** FileVault, on every machine that holds a copy.
- **Treat iCloud as a pipe.** It is the only transport that works off the phone,
  but move files to local storage and delete the cloud copy immediately. Don't
  leave records sitting in someone else's storage indefinitely.
- Keep a backup of the **source PDFs**. Everything else can be rebuilt; those
  cannot.

## Serving it

`serve.py` is read-only and GET-only, but where it listens is a real decision.
Set `BIND_MODE`:

| Mode | Listens on | Use when |
|---|---|---|
| `tailscale` (default) | your tailnet address only | you want it on your own devices and nowhere else |
| `localhost` | `127.0.0.1` | you are putting a Cloudflare Tunnel, SSH tunnel or reverse proxy in front |
| `lan` | your LAN address | on a network you control, and you accept everyone on it can reach it |
| `any` | every interface | almost never; requires `ALLOW_ANY_INTERFACE=1` as well |

It **refuses to start** rather than silently choosing something wider than you
asked for. That guard exists because on café or hotel wifi, a `0.0.0.0` bind
publishes your medical records to that network.

### If you expose it beyond your own machine

- **Set `AUTH_TOKEN`.** Then every request needs it, as a `Bearer` header, an
  `ht` cookie, or `?token=…` once. Use a long random value:
  `python3 -c "import secrets;print(secrets.token_urlsafe(32))"`.
- **A Cloudflare Tunnel without Access in front of it is a public URL.** The
  tunnel gives you TLS and hides your IP; it does not authenticate anyone. Put
  Cloudflare Access on it, or rely on `AUTH_TOKEN`, or both.
- Run with `BIND_MODE=localhost` behind the tunnel so nothing else can reach the
  port directly.
- Set `BEHIND_TLS=1` so the auth cookie is marked `Secure`.
- There is no rate limiting and no lockout. It is a personal tool, not a public
  service.

## Sending data to AI models

- **Embeddings are local.** `embed_db.py` uses Ollama on a host you control, so
  document text is not sent to a hosted API. Keep it that way — a hosted
  embedding endpoint would mean uploading every report.
- **Never paste records into a hosted chat model.**
- **Reviewing this code with a cloud model is fine; reviewing your data is not.**
  If you do send code for review, check it first for clinical facts, not just
  identifiers — a diagnosis plus a drug plus an allergy list is medical
  information about you even with your name removed. Grep for diagnoses, drug
  names, allergies, procedures and event dates before sending anything.

## Automation risk

The phone scripts tap through a live logged-in medical app. Consequences worth
knowing:

- They can only read and share; nothing in the flow deletes or amends records.
- A pending confirmation dialog can swallow taps, and a stray tap in an unknown
  state does something you did not intend. If a run dies, look at the screen
  before relaunching.
- Run **one sweep at a time**. Concurrent runs fight over the phone and fail in
  ways that look like app faults.
- Sessions expire after a few hours; log in yourself. Do not attempt to automate
  the login.

## Reporting a problem

Personal tool, no security team. If you find a flaw that would expose records —
a path traversal in `serve.py`, a bind that ignores `BIND_MODE`, records landing
in a commit — treat it as urgent and fix it before running the pipeline again.
