#!/bin/zsh
# Drive lab_sweep.py for one year until it stops finding new records.
# The mirroring session drops at random; the ledger makes a restart free, so
# just relaunch rather than trying to make one long run bulletproof.
YEAR=$1
export PATH=$HOME/.local/bin:$PATH
# HA_ACCOUNT_NAME / DOB_YEAR live here, outside the repo
[ -f "$HOME/.hago-scraper.env" ] && . "$HOME/.hago-scraper.env"
count() { python3 -c "import json;print(len(json.load(open(\"$HOME/lab_done.json\"))))"; }
dry=0
for i in $(seq 1 20); do
  before=$(count)
  echo "=== $YEAR attempt $i (ledger=$before) ==="
  PYTHONUNBUFFERED=1 YEAR=$YEAR phone-harness < ~/lab_sweep.py 2>&1 | grep -v "^  File \|^    \|^Traceback" | tail -20
  after=$(count)
  echo "--- ledger $before -> $after ---"
  if [ "$after" = "$before" ]; then
    dry=$((dry+1))
    [ $dry -ge 2 ] && { echo "$YEAR: two dry runs, done"; break; }
  else
    dry=0
  fi
done
echo "$YEAR FINISHED ledger=$(count)"
