# MySQL Fresh-DB Deployment Package Notes

This package is delivered for the MySQL runtime architecture. It intentionally does not ship the large runtime database files as the main data carrier.

## Deployment Flow

1. Install dependencies on the target server.

```bash
npm install --include=optional
python3 -m venv apps/api/.venv
apps/api/.venv/bin/pip install -r apps/api/requirements.txt
```

2. Edit `apps/api/.env` to point at the target MySQL server and database.

Required keys:

```bash
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3307
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=banking_budget
```

3. Create the configured MySQL database and initialize all system tables.

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/create_mysql_database.py
```

4. Start the system.

```bash
bash start.sh
```

5. Upload/import the latest business data through the application entry points.

Recommended validation after deployment:

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/verify_mysql_inventory.py
curl http://127.0.0.1:8009/api/health
```

## Important Boundary

- Runtime database: MySQL.
- `var/data/*.db`: no longer the authoritative delivery data source for this package.
- Business data should be imported after deployment, using the current product upload/import flow.
- `apps/api/.env` is included because it carries the runtime MySQL connection shape; change host/port/password on the target server as needed.
