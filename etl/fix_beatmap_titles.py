"""Fix beatmap titles by fetching beatmapset data from osu! API."""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
from osu_api import _get
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import psycopg2
DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME", "osuanalytics"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

conn = psycopg2.connect(**DB_CONFIG)
cur  = conn.cursor()

cur.execute("SELECT beatmap_id FROM beatmaps WHERE artist = '' OR title = version ORDER BY beatmap_id")
beatmap_ids = [r[0] for r in cur.fetchall()]
print(f"Fixing {len(beatmap_ids)} beatmaps...")

BATCH = 50
fixed = 0
for i in range(0, len(beatmap_ids), BATCH):
    batch = beatmap_ids[i:i+BATCH]
    params = "&".join(f"ids[]={bid}" for bid in batch)
    try:
        data = _get(f"/beatmaps?{params}")
        if not data or "beatmaps" not in data:
            time.sleep(1)
            continue
        for bm in data["beatmaps"]:
            bms = bm.get("beatmapset") or {}
            title  = bms.get("title") or bm.get("version", "")
            artist = bms.get("artist", "")
            cur.execute(
                "UPDATE beatmaps SET title=%s, artist=%s WHERE beatmap_id=%s",
                (title, artist, bm["id"])
            )
            fixed += 1
        conn.commit()
        print(f"  {min(i+BATCH, len(beatmap_ids))}/{len(beatmap_ids)} done ({fixed} updated)")
    except Exception as e:
        print(f"  Error on batch {i}: {e}")
        time.sleep(2)
    time.sleep(0.5)

cur.close()
conn.close()
print(f"Done! Fixed {fixed} beatmaps.")
