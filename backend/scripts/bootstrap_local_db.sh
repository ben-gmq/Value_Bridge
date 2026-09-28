#!/usr/bin/env bash
# LOCAL DEVELOPMENT ONLY. Creates the two roles (§6.6) and the dev + test databases, and
# writes their connection strings to backend/.env (gitignored). Passwords are generated
# here, written only to .env, and never printed. In Azure the admin does this (§15.2).
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=.env
if [[ -f $ENV_FILE ]] && grep -q '^DATABASE_URL=.\+' "$ENV_FILE"; then
  echo ".env already has DATABASE_URL — not overwriting. Delete it to re-bootstrap."; exit 1
fi
: "${VB_EMAIL_DOMAINS:?Set VB_EMAIL_DOMAINS to the FTC email domain(s), e.g. VB_EMAIL_DOMAINS=fortience.com}"
gen() { python3 -c 'import secrets; print(secrets.token_urlsafe(32))'; }
OWNER_PW=$(gen); APP_PW=$(gen); JWT=$(gen)$(gen)
psql -v ON_ERROR_STOP=1 -d postgres -q <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='vb_owner') THEN CREATE ROLE vb_owner LOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='vb_app')   THEN CREATE ROLE vb_app LOGIN;   END IF;
END \$\$;
ALTER ROLE vb_owner PASSWORD '${OWNER_PW}';
ALTER ROLE vb_app   PASSWORD '${APP_PW}';
SQL
for db in vb_db vb_test_db; do
  psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 \
    || psql -v ON_ERROR_STOP=1 -d postgres -qc "CREATE DATABASE $db OWNER vb_owner"
  psql -v ON_ERROR_STOP=1 -d "$db" -qc "REVOKE ALL ON DATABASE $db FROM PUBLIC; GRANT CONNECT ON DATABASE $db TO vb_app; ALTER SCHEMA public OWNER TO vb_owner;"
done
umask 077
cat > "$ENV_FILE" <<ENV
DATABASE_URL=postgresql+psycopg://vb_app:${APP_PW}@localhost:5432/vb_db
MIGRATION_DATABASE_URL=postgresql+psycopg://vb_owner:${OWNER_PW}@localhost:5432/vb_db
TEST_DATABASE_URL=postgresql+psycopg://vb_app:${APP_PW}@localhost:5432/vb_test_db
TEST_MIGRATION_DATABASE_URL=postgresql+psycopg://vb_owner:${OWNER_PW}@localhost:5432/vb_test_db
JWT_SECRET_KEY=${JWT}
FRONTEND_URL=http://localhost:5180
ALLOWED_EMAIL_DOMAINS=${VB_EMAIL_DOMAINS}
ENV
echo "Created roles vb_owner, vb_app; databases vb_db, vb_test_db; wrote $ENV_FILE (mode 600)."
