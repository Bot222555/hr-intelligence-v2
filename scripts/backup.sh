#!/bin/bash
# Database backup script — runs daily via cron

set -e

BACKUP_DIR=/opt/backups
TIMESTAMP=$(date +%Y-%m-%d_%H%M)

mkdir -p "$BACKUP_DIR"

# PostgreSQL dump
echo "📦 Backing up database..."
docker compose exec -T db pg_dump -U hr_app hr_intelligence | gzip > "$BACKUP_DIR/hr_$TIMESTAMP.sql.gz"

# Keep last 30 days
find "$BACKUP_DIR" -name "hr_*.sql.gz" -mtime +30 -delete

echo "✅ Backup saved: $BACKUP_DIR/hr_$TIMESTAMP.sql.gz"

# Optional: upload to S3
# aws s3 cp "$BACKUP_DIR/hr_$TIMESTAMP.sql.gz" s3://cf-backups/hr/
