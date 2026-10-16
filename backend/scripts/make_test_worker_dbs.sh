#!/usr/bin/env bash
# LOCAL DEVELOPMENT ONLY. Creates one test database per pytest-xdist worker — <test db>_gw0 … _gw<N-1> — next to the
# test database named in backend/.env (TEST_DATABASE_URL), owned by vb_owner with the same grants as
# bootstrap_local_db.sh. Existing ones are left alone. Usage, from backend/:  ./scripts/make_test_worker_dbs.sh 4
#
# Optional, for speed, on THROWAWAY TEST databases only (never vb_db or any dev / demo / UAT database):
#   psql -d postgres -c "ALTER DATABASE <test db>_gw0 SET synchronous_commit = off"   (one per worker database)
set -euo pipefail
cd "$(dirname "$0")/.."
N="${1:-4}"
url=$(grep '^TEST_DATABASE_URL=' .env | cut -d= -f2-)
base="${url##*/}"
case "$base" in
  *test*) ;;
  *) echo "TEST_DATABASE_URL does not name a test database ($base) — refusing."; exit 1 ;;
esac
for ((i = 0; i < N; i++)); do
  db="${base}_gw${i}"
  psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 \
    || psql -v ON_ERROR_STOP=1 -d postgres -qc "CREATE DATABASE $db OWNER vb_owner"
  psql -v ON_ERROR_STOP=1 -d "$db" -qc "REVOKE ALL ON DATABASE $db FROM PUBLIC; GRANT CONNECT ON DATABASE $db TO vb_app; ALTER SCHEMA public OWNER TO vb_owner;"
  echo "$db ready"
done
