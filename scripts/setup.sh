#!/usr/bin/env bash
# Cai dat va chay moi truong phat trien (Technical Blueprint, muc 3).
# Chay tu bat ky thu muc nao:  ./scripts/setup.sh
# Script chi la lop boc mong: moi logic chay that nam trong docker-compose.yml.
#   1. Neu chua co .env thi sao chep tu .env.example (KHONG BAO GIO ghi de .env co san).
#   2. Kiem tra Docker dang chay.
#   3. docker compose up -d --build --wait
#   4. In dia chi truy cap va trang thai.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

info() { printf '[setup] %s\n' "$*"; }
fail() { printf '[setup] LOI: %s\n' "$*" >&2; exit 1; }

# Doc gia tri bien tu .env (khong dung 'source' de tranh chay lenh la); mac dinh neu khong co.
env_value() {
  local name="$1" default="$2" value
  value="$(grep -E "^${name}=" .env 2>/dev/null | tail -n 1 | cut -d= -f2- | tr -d '\r' || true)"
  printf '%s' "${value:-$default}"
}

# --- 1. File .env ---
if [ -f .env ]; then
  info ".env da ton tai, giu nguyen (khong ghi de)."
else
  [ -f .env.example ] || fail "Khong thay .env.example o thu muc goc. Ban dang o dung repo chua?"
  cp .env.example .env
  info "Da tao .env tu .env.example. Hay doi mat khau trong .env neu can."
fi

# Canh bao: mat khau mau chi danh cho may dev.
if grep -q '^POSTGRES_PASSWORD=change-me-dev-only' .env && [ "$(env_value APP_ENV development)" != "development" ]; then
  fail "APP_ENV khong phai 'development' nhung van dung mat khau mau. Doi POSTGRES_PASSWORD (hoac dat APP_ENV=development)."
fi

# --- 2. Docker ---
command -v docker >/dev/null 2>&1 || fail "Chua cai Docker. Xem https://docs.docker.com/get-docker/"
docker compose version >/dev/null 2>&1 || fail "Khong tim thay 'docker compose' (can Docker Compose v2)."
docker info >/dev/null 2>&1 || fail "Docker chua chay. Hay mo Docker Desktop (hoac khoi dong dich vu docker) roi chay lai."

# --- 3. Build va khoi dong, doi toi khi tat ca healthy ---
info "Dang build va khoi dong (lan dau co the mat vai phut)..."
if ! docker compose up -d --build --wait; then
  printf '\n' >&2
  docker compose ps >&2 || true
  fail "Co service khong khoi dong duoc hoac khong healthy. Xem log: docker compose logs <service>"
fi

# --- 4. Ket qua ---
FRONTEND_PORT="$(env_value FRONTEND_PORT 5173)"
BACKEND_PORT="$(env_value BACKEND_PORT 8000)"
printf '\n'
docker compose ps
printf '\n'
info "Hoan tat. Dia chi truy cap:"
info "  Giao dien : http://localhost:${FRONTEND_PORT}"
info "  API health: http://localhost:${BACKEND_PORT}/api/v1/health"
info "  Swagger   : http://localhost:${BACKEND_PORT}/api/v1/docs (chi khi APP_ENV=development)"
info "Dung (giu du lieu): docker compose down | Reset (XOA du lieu DB): docker compose down -v"
