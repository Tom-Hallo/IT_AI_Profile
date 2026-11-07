$ErrorActionPreference = "Stop"

# Chuyển về thư mục gốc dự án
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " IT TALENT AI PROFILE - SETUP"
Write-Host "========================================" -ForegroundColor Cyan

# 1. Kiểm tra Docker đã được cài đặt
Write-Host "`n[1/6] Checking Docker..."

docker --version

if ($LASTEXITCODE -ne 0) {
    throw "Docker chua duoc cai dat."
}

# 2. Kiểm tra Docker Engine đang hoạt động
Write-Host "`n[2/6] Checking Docker Engine..."

docker info --format '{{.ServerVersion}}'

if ($LASTEXITCODE -ne 0) {
    throw "Docker Engine chua chay. Hay mo Docker Desktop."
}

# 3. Tạo .env nếu chưa có
Write-Host "`n[3/6] Checking environment..."

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example" -ForegroundColor Green
}
else {
    Write-Host ".env already exists. Keeping current configuration."
}

# 4. Kiểm tra cấu hình Docker Compose
Write-Host "`n[4/6] Validating Docker Compose..."

docker compose config --quiet

if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose configuration is invalid."
}

# 5. Build và khởi động toàn bộ service
Write-Host "`n[5/6] Building and starting services..."

docker compose up -d --build --wait

if ($LASTEXITCODE -ne 0) {
    throw "Failed to start services."
}

# 6. Chạy migration database
Write-Host "`n[6/6] Applying database migrations..."

docker compose exec -T backend alembic upgrade head

if ($LASTEXITCODE -ne 0) {
    throw "Database migration failed."
}

Write-Host "`n========================================" -ForegroundColor Green
Write-Host " SETUP COMPLETED SUCCESSFULLY"
Write-Host "========================================" -ForegroundColor Green

docker compose ps

Write-Host "`nFrontend: http://localhost:5173"
Write-Host "Backend:  http://localhost:8000/api/v1/health"