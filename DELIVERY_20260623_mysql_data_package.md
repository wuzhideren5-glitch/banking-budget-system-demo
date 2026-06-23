# MySQL Data-Included Runtime Package Notes

This package is for internal handover. It includes the current application code, frontend build output, runtime `.env`, and a compressed MySQL data snapshot.

## Included Database Snapshot

- Dump file: `deploy/mysql/banking_budget_20260623_full.sql.gz`
- Import helper: `deploy/mysql/import_mysql_dump.sh`
- Source database: `banking_budget`
- Export mode: `mysqldump --single-transaction --routines --triggers --events --set-gtid-purged=OFF`

The package does not use SQLite `.db` files as the runtime database carrier. The runtime database is MySQL.

## Restore on Target Server

1. Install dependencies.

```bash
npm install --include=optional
python3 -m venv apps/api/.venv
apps/api/.venv/bin/pip install -r apps/api/requirements.txt
```

2. Edit `apps/api/.env` to match the target MySQL host, port, user, password, and database.

3. Import the packaged MySQL snapshot.

```bash
MYSQL_HOST=127.0.0.1 \
MYSQL_PORT=3307 \
MYSQL_USER=root \
MYSQL_PASSWORD='' \
MYSQL_DATABASE=banking_budget \
bash deploy/mysql/import_mysql_dump.sh
```

4. Start the system.

```bash
bash start.sh
```

5. Validate.

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/verify_mysql_inventory.py \
  --host "$MYSQL_HOST" \
  --port "$MYSQL_PORT" \
  --user "$MYSQL_USER" \
  --password "$MYSQL_PASSWORD" \
  --database "$MYSQL_DATABASE"

curl http://127.0.0.1:8009/api/health
```

## Sensitive Package

This package includes `.env` and database data. Treat it as an internal sensitive delivery artifact.
