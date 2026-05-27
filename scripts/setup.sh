#!/bin/bash
set -e

echo "=== PriceWatch Setup ==="

# Copy env files
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local

echo "→ Generated .env files (edit backend/.env with your settings)"

# Start containers
docker compose up -d postgres redis
echo "→ Waiting for PostgreSQL..."
sleep 5

# Run migrations
docker compose run --rm backend alembic upgrade head
echo "→ Database migrated"

echo ""
echo "✅ Setup complete! Run: docker compose up"
echo "   Frontend: http://localhost:3000"
echo "   Backend:  http://localhost:8000/docs"
