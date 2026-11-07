#!/usr/bin/env bash

set -euo pipefail

# Chuyển về thư mục gốc dự án
cd "$(dirname "$0")/.."

echo "========================================"
echo " IT TALENT AI PROFILE - SETUP"
echo "========================================"

echo "[1/6] Checking Docker..."
docker --version

echo "[2/6] Checking Docker Engine..."
docker info --format '{{.ServerVersion}}' > /dev/null

echo "[3/6] Checking environment..."

if [ ! -f ".env" ]; then
    cp ".env.example" ".env"
    echo "Created .env from .env.example"
else
    echo ".env already exists."
fi

echo "[4/6] Validating Docker Compose..."
docker compose config --quiet

echo "[5/6] Building and starting services..."
docker compose up -d --build --wait

echo "[6/6] Applying database migrations..."
docker compose exec -T backend alembic upgrade head

echo "========================================"
echo " SETUP COMPLETED SUCCESSFULLY"
echo "========================================"

docker compose ps

echo "Frontend: http://localhost:5173"
echo "Backend:  http://localhost:8000/api/v1/health"