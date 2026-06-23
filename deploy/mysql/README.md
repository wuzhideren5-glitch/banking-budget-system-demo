# MySQL Data Package

This directory contains the MySQL runtime data snapshot for the banking budget system.

## Files

- `banking_budget_20260623_full.sql.gz`: compressed MySQL dump exported from the `banking_budget` runtime database.
- `import_mysql_dump.sh`: helper script to create a target database and import the compressed dump.

## Import

```bash
MYSQL_HOST=127.0.0.1 \
MYSQL_PORT=3307 \
MYSQL_USER=root \
MYSQL_PASSWORD='' \
MYSQL_DATABASE=banking_budget \
bash deploy/mysql/import_mysql_dump.sh
```

After import, start the application:

```bash
bash start.sh
```

Then validate:

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/verify_mysql_inventory.py \
  --host "$MYSQL_HOST" \
  --port "$MYSQL_PORT" \
  --user "$MYSQL_USER" \
  --password "$MYSQL_PASSWORD" \
  --database "$MYSQL_DATABASE"
```
