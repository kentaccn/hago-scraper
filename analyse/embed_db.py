"""Embed the document chunks locally and store the vectors in medical.db.

Embeddings come from Ollama on the Mac Mini (nomic-embed-text, 768-d). These
are medical records, so nothing is sent to a hosted embedding API -- the whole
pipeline stays on Kenta's own machines.

Vectors live in the same SQLite file as everything else. For a corpus this size
(hundreds of chunks) an exact numpy dot-product beats an approximate index on
both accuracy and dependency count; search_db.py does that. If the corpus ever
grows past ~50k chunks, swap in sqlite-vec without changing the schema.
"""
import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path

import numpy as np

# Load ~/.hago-scraper.env so every stage sees the same paths. Without this
# only the shell wrappers read it, and one stage writes where the next never
# looks.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config                              # noqa: E402
config.load()

DB = Path(os.environ.get("MEDICAL_DB",
                         Path(__file__).parent / "medical.db"))
HOST = os.environ.get("OLLAMA", "http://localhost:11434")
MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
BATCH = 16


def embed(texts):
    req = urllib.request.Request(
        f"{HOST}/api/embed",
        data=json.dumps({"model": MODEL, "input": texts}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["embeddings"]


def main():
    con = sqlite3.connect(DB)
    other = con.execute("SELECT DISTINCT model FROM embeddings WHERE model != ?",
                        (MODEL,)).fetchall()
    if other:
        sys.exit(f"database already holds vectors from {[o[0] for o in other]}; "
                 f"mixing models makes search meaningless. Delete the embeddings "
                 f"table and re-embed with {MODEL}.")
    todo = con.execute(
        "SELECT c.id, c.text FROM chunks c "
        "LEFT JOIN embeddings e ON e.chunk_id = c.id "
        "WHERE e.chunk_id IS NULL ORDER BY c.id").fetchall()
    if not todo:
        print("nothing to embed; all chunks already have vectors")
        return
    print(f"embedding {len(todo)} chunks with {MODEL} ...")
    done = 0
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        try:
            vecs = embed([t for _, t in batch])
        except Exception as e:                       # noqa: BLE001
            print(f"  ! batch at {i}: {e}", file=sys.stderr)
            continue
        for (cid, _), v in zip(batch, vecs):
            arr = np.asarray(v, dtype=np.float32)
            arr /= (np.linalg.norm(arr) or 1.0)      # store unit vectors so
            con.execute(                             # search is a plain dot
                "INSERT OR REPLACE INTO embeddings (chunk_id, model, dim, vec)"
                " VALUES (?,?,?,?)",
                (cid, MODEL, arr.size, arr.tobytes()))
        con.commit()
        done += len(batch)
        print(f"  {done}/{len(todo)}", end="\r", flush=True)
    n = con.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    if not n:
        # every batch failed -- say so instead of crashing on a missing row
        sys.exit(f"\nno chunks were embedded. Is Ollama reachable at {HOST} "
                 f"and is {MODEL} pulled?")
    dim = con.execute("SELECT dim FROM embeddings LIMIT 1").fetchone()[0]
    print(f"\n{n} chunks embedded ({MODEL}, {dim}-d)")
    con.close()


if __name__ == "__main__":
    main()
