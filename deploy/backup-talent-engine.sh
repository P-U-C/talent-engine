#!/usr/bin/env bash
# Nightly snapshot of the talent-engine ledger.
#
# talent_engine.db holds the audit log (which is what makes historical scores
# reproducible), the quarantined applicant contacts, and the cohort decisions
# that allocate funded seats. It had no backup coverage at all.
#
# sqlite3 .backup is used rather than cp: the database runs in WAL mode and a
# plain copy can capture a torn state.
set -euo pipefail

DB=/home/ubuntu/talent-engine-runtime/talent_engine.db
DEST=/home/ubuntu/backups/talent-engine
KEEP=14

mkdir -p "$DEST"
chmod 700 "$DEST"
[ -f "$DB" ] || { echo "$(date -Is) no database at $DB" >&2; exit 1; }

STAMP=$(date -u +%Y%m%d)
OUT="$DEST/talent_engine-$STAMP.db"
/usr/bin/sqlite3 "$DB" ".backup '$OUT'"
gzip -f "$OUT"
chmod 600 "$OUT.gz"

# Keep the most recent N, drop the rest.
ls -1t "$DEST"/talent_engine-*.db.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "$(date -Is) backed up -> $OUT.gz ($(stat -c%s "$OUT.gz") bytes)"
