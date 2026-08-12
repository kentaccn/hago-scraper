# Security

## What is sensitive

The exported PDFs, the database, the CSVs, the charts and the generated report.
They carry your name, ID number, date of birth, hospital numbers, clinicians,
diagnoses and results.

The code is not sensitive and is written to stay that way. Names, the
date-of-birth year, paths and hosts come from the environment. If you find a
diagnosis or a drug name hard-coded in a source file, that is a bug.

## Storing the files

Keep PDFs, databases, CSVs and reports outside the repository, in a directory
only your account can read:

```bash
chmod 700 ~/records
chmod 600 ~/records/*
```

The pipeline sets `600` on what it generates, and `check_setup.py` warns if a
directory is readable by others.

Turn on FileVault on any Mac that stores the files.

iCloud Drive is the only transport that works off the phone. Delete the iCloud
copy once the file is local.

Keep a backup of the source PDFs. Everything else can be rebuilt from them.

`.gitignore` only catches mistakes. The repository is still the wrong place
to keep records.

## Serving it

`serve.py` is read-only and GET-only. Set `BIND_MODE`:

| Mode | Listens on | Use when |
|---|---|---|
| `tailscale` (default) | your tailnet address | your own devices, nowhere else |
| `localhost` | `127.0.0.1` | behind a Cloudflare Tunnel, SSH tunnel or proxy |
| `lan` | your LAN address | a network you control |
| `any` | every interface | almost never, and needs `ALLOW_ANY_INTERFACE=1` |

It exits rather than binding wider than you asked for. On café or hotel wifi a
`0.0.0.0` bind would put your records on that network.

Past loopback or a tailnet it refuses to start without `AUTH_TOKEN`. Generate
one:

```bash
python3 -c "import secrets;print(secrets.token_urlsafe(32))"
```

Requests then need it as a `Bearer` header, an `ht` cookie, or `?token=…` once.
Set `BEHIND_TLS=1` behind a TLS proxy so the cookie is marked `Secure`.

The `?token=` form puts the secret in a URL, so it reaches browser history and
any proxy or CDN log before the redirect moves it into a cookie. Prefer the
`Bearer` header where you can. The cookie stores a value derived from the token
rather than the token itself, so a stolen cookie cannot be replayed as a Bearer
credential.

A Cloudflare Tunnel provides TLS and hides your IP. It does not authenticate
anyone. Put Cloudflare Access in front of it, or use `AUTH_TOKEN`, or both, and
run with `BIND_MODE=localhost` so nothing else can reach the port.

There is no rate limiting and no lockout.

## Hosted AI services

`embed_db.py` uses Ollama on a host you control, so report text is not sent to
an external embedding API. A hosted endpoint would mean uploading every report.

Do not paste records into a hosted chat model.

Reviewing the code with a cloud model is fine. Before sending it, check for
diagnoses, drug names, allergies, procedures and event dates, not only names and
ID numbers. A diagnosis plus a drug plus an allergy list identifies someone even
without a name attached. That mistake has already been made once in this
project.

## Automating a live medical app

The scripts tap through a logged-in app. They only read and share; nothing in
the flow deletes or amends a record.

Run one sweep at a time. Two fight over the phone and fail in ways that look
like app faults.

Move exported files out only when no sweep is running. A record is ledgered the
moment it saves, so clearing the folder mid-run marks it done with no file to
show for it.

If a run dies, look at the screen before relaunching. A pending dialog swallows
taps, and a tap in an unexpected state does something you did not intend.

Sessions expire after a few hours. Log in yourself; do not automate the login.

## Reporting a problem

There is no security team. If you find something that would expose records, a
path traversal in `serve.py`, a bind that ignores `BIND_MODE`, records reaching
a commit, fix it before running the pipeline again.
