#!/bin/sh
# Drive lab_sweep.py for one year until it stops finding new records.
#
# The mirroring session drops at random and the ledger makes a restart free, so
# relaunching is more reliable than trying to make one long run bulletproof.
#
#   ./phone/sweep_year.sh 2024
set -u
YEAR=${1:?usage: sweep_year.sh <year>}
HERE=$(cd "$(dirname "$0")" && pwd)
export PATH="$HOME/.local/bin:$PATH"
# Configuration (HA_ACCOUNT_NAME, DOB_YEAR, paths) lives outside the repo.
[ -f "$HOME/.hago-scraper.env" ] && . "$HOME/.hago-scraper.env"

LEDGER=${LAB_LEDGER:-$HOME/lab_done.json}
export LAB_LEDGER="$LEDGER"

count() {
    python3 - "$LEDGER" <<'PY'
import json, os, sys
f = sys.argv[1]
try:
    print(len(json.load(open(f))))
except Exception:
    print(0)
PY
}

dry=0
for i in $(seq 1 20); do
    before=$(count)
    echo "=== $YEAR attempt $i (ledger=$before) ==="
    # Report the sweeper's own exit status, not tail's, or a crash reads as a
    # clean run and two "unchanged" counts declare the year finished.
    PYTHONUNBUFFERED=1 YEAR="$YEAR" phone-harness < "$HERE/lab_sweep.py" > "$HERE/.sweep.log" 2>&1
    status=$?
    grep -v '^  File \|^    \|^Traceback' "$HERE/.sweep.log" | tail -20
    rm -f "$HERE/.sweep.log"
    [ "$status" -ne 0 ] && echo "  (sweeper exited $status)"
    after=$(count)
    echo "--- ledger $before -> $after ---"
    if [ "$after" = "$before" ]; then
        dry=$((dry + 1))
        [ "$dry" -ge 2 ] && { echo "$YEAR: two dry runs, done"; break; }
    else
        dry=0
    fi
done
echo "$YEAR FINISHED ledger=$(count)"
