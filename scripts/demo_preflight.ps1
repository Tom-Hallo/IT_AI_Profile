# IT Talent AI Profile — kiểm tra trước demo (không thay đổi mã/DB)
# Chạy tại D:\AI_talent\IT_AI_Profile bằng PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\scripts\demo_preflight.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\demo_preflight.ps1 -FullTests
param([switch]$FullTests)
$ErrorActionPreference = 'Continue'

function Step([string]$Name) {
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
}
if (-not (Test-Path '.env')) {
    Write-Host 'THIẾU .env ở thư mục gốc. Hãy cấu hình trước khi chạy Docker.' -ForegroundColor Red
    exit 1
}
Step 'Trạng thái git và Docker'
git status -sb
docker compose --env-file .env ps -a
Step 'Health Backend qua frontend proxy'
try {
    $h = Invoke-RestMethod 'http://localhost:5173/api/v1/health' -TimeoutSec 10
    $h | ConvertTo-Json -Depth 8
} catch { Write-Host "LỖI HEALTH: $($_.Exception.Message)" -ForegroundColor Red }
Step 'HTTP Frontend'
try {
    $r = Invoke-WebRequest 'http://localhost:5173/#about' -UseBasicParsing -TimeoutSec 10
    Write-Host "HTTP $($r.StatusCode) — cần xác nhận giao diện Pixel Studio bằng trình duyệt"
} catch { Write-Host "LỖI FRONTEND: $($_.Exception.Message)" -ForegroundColor Red }
Step 'Alembic revision hiện tại'
docker compose --env-file .env exec -T backend alembic current
Step 'Các dòng log lỗi backend/worker gần nhất'
docker compose --env-file .env logs --tail 40 backend worker maintenance
Step 'Kiểm tra Ollama trên máy (nếu AI_PROVIDER=ollama)'
try {
    $r=Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 5
    $r.models | Select-Object name
} catch { Write-Host 'Ollama chưa phản hồi: AI Mentor/CV Generate có thể lỗi nếu cấu hình dùng Ollama.' -ForegroundColor Yellow }
if ($FullTests) {
    Step 'Backend Ruff'
    docker compose --env-file .env exec -T backend python -m ruff check .
    docker compose --env-file .env exec -T backend python -m ruff format --check .
    Step 'Backend pytest'
    docker compose --env-file .env exec -T backend python -m pytest -m 'not integration' -q --tb=short
    Step 'Frontend ESLint và build'
    docker compose --env-file .env exec -T frontend npm run lint
    docker compose --env-file .env exec -T frontend npm run build
}
Write-Host "`nKiểm tra thủ công: OAuth GitHub → Sync → Analyze → Dashboard → Roadmap → JD → CV → Share → Mentor." -ForegroundColor Green
