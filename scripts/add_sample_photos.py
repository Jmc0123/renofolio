"""Fill empty project photos without resetting accounts, projects or activity.

Usage: python scripts/add_sample_photos.py --db sample_demo.db
Creates a SQLite backup before changes; existing non-empty photo URLs are kept.
"""
from datetime import datetime
from contextlib import closing
from pathlib import Path
import argparse
import json
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.common.sample_photos import SAMPLE_PHOTOS, photo_for_category  # noqa: E402


# Gives projects without a photo the sample photo for their room type, after backing up the file.
def backfill_photos(db_path):
    path = Path(db_path).resolve(strict=True)
    for url in SAMPLE_PHOTOS.values():
        if not (ROOT/"app"/url.lstrip("/")).is_file():
            raise FileNotFoundError(f"Sample photo asset missing: {url}")
    with closing(sqlite3.connect(path.as_uri()+"?mode=rw", uri=True, timeout=15)) as conn, conn:
        rows = conn.execute(
            "SELECT p.idp_id,c.name FROM interior_design_projects p "
            "JOIN project_categories c ON c.category_id=p.category_id "
            "WHERE TRIM(COALESCE(p.photo_url,''))=''"
        ).fetchall()
        updates = [(photo_for_category(name), project) for project,name in rows if photo_for_category(name)]
        if not updates:
            return {"updated":0,"skipped_unmatched":len(rows),"backup_path":None}
        backup_dir = path.parent/"database-backups"
        backup_dir.mkdir(exist_ok=True)
        backup = backup_dir/f"{path.stem}-before-photos-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
        with closing(sqlite3.connect(backup)) as target:
            conn.backup(target)
        cursor = conn.executemany(
            "UPDATE interior_design_projects SET photo_url=? WHERE idp_id=? AND TRIM(COALESCE(photo_url,''))=''",
            updates,
        )
        changed = cursor.rowcount
    return {"updated":changed,"skipped_unmatched":len(rows)-len(updates),"backup_path":str(backup)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    print(json.dumps(backfill_photos(args.db), indent=2))
