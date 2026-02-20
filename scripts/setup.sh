#!/bin/bash
# First-time setup script for HR Intelligence

set -e

echo "🚀 HR Intelligence — First-Time Setup"
echo "======================================="

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "❌ Docker is required but not installed."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3.12+ is required."; exit 1; }

# Copy env template
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ Created .env from template — please edit with real values"
else
    echo "ℹ️  .env already exists, skipping"
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Start infrastructure
echo "🐘 Starting PostgreSQL & Redis..."
docker compose up -d db redis
sleep 5

# Run migrations
echo "📋 Running database migrations..."
alembic upgrade head

echo ""
echo "✅ Setup complete!"
echo ""
echo "Start the API server:"
echo "  uvicorn backend.main:app --reload --port 8000"
echo ""
echo "Start the frontend (once built):"
echo "  cd frontend && npm install && npm run dev"
