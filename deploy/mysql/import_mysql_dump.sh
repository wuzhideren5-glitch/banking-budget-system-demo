#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DUMP_FILE="${DUMP_FILE:-$SCRIPT_DIR/banking_budget_20260623_full.sql.gz}"

MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3307}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-}"
MYSQL_DATABASE="${MYSQL_DATABASE:-banking_budget}"

if [ ! -f "$DUMP_FILE" ]; then
  echo "Dump file not found: $DUMP_FILE" >&2
  exit 1
fi

mysql_base=(
  --host="$MYSQL_HOST"
  --port="$MYSQL_PORT"
  --user="$MYSQL_USER"
  --default-character-set=utf8mb4
)

if [ -n "$MYSQL_PASSWORD" ]; then
  mysql_base+=(--password="$MYSQL_PASSWORD")
fi

mysql "${mysql_base[@]}" -e "CREATE DATABASE IF NOT EXISTS \`$MYSQL_DATABASE\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
gzip -dc "$DUMP_FILE" | mysql "${mysql_base[@]}" "$MYSQL_DATABASE"

echo "OK imported $DUMP_FILE into $MYSQL_DATABASE"
