# Cai dat va chay moi truong phat trien (Technical Blueprint, muc 3) - Windows PowerShell.
# Chay:  .\scripts\setup.ps1
# Neu bi chan boi Execution Policy:  powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
# Script chi la lop boc mong: moi logic chay that nam trong docker-compose.yml.
#   1. Neu chua co .env thi sao chep tu .env.example (KHONG BAO GIO ghi de .env co san).
#   2. Kiem tra Docker dang chay.
#   3. docker compose up -d --build --wait
#   4. In dia chi truy cap va trang thai.
# Giu file nay chi chua ky tu ASCII (Windows PowerShell 5.1 doc sai file UTF-8 khong co BOM).

$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

function Write-Info($Message) { Write-Host "[setup] $Message" }
function Stop-Setup($Message) {
    [Console]::Error.WriteLine("[setup] LOI: $Message")
    exit 1
}

# Doc gia tri bien tu .env (khong thuc thi gi); tra ve mac dinh neu khong co.
function Get-EnvValue($Name, $Default) {
    if (Test-Path '.env') {
        $line = Select-String -Path '.env' -Pattern "^$Name=" | Select-Object -Last 1
        if ($line) {
            $value = $line.Line.Substring($Name.Length + 1).Trim()
            if ($value) { return $value }
        }
    }
    return $Default
}

# --- 1. File .env ---
if (Test-Path '.env') {
    Write-Info '.env da ton tai, giu nguyen (khong ghi de).'
}
else {
    if (-not (Test-Path '.env.example')) { Stop-Setup 'Khong thay .env.example o thu muc goc. Ban dang o dung repo chua?' }
    Copy-Item '.env.example' '.env'
    Write-Info 'Da tao .env tu .env.example. Hay doi mat khau trong .env neu can.'
}

# Canh bao: mat khau mau chi danh cho may dev.
if ((Get-EnvValue 'POSTGRES_PASSWORD' '') -eq 'change-me-dev-only' -and (Get-EnvValue 'APP_ENV' 'development') -ne 'development') {
    Stop-Setup "APP_ENV khong phai 'development' nhung van dung mat khau mau. Doi POSTGRES_PASSWORD (hoac dat APP_ENV=development)."
}

# --- 2. Docker ---
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Stop-Setup 'Chua cai Docker. Xem https://docs.docker.com/get-docker/'
}
docker compose version *> $null
if ($LASTEXITCODE -ne 0) { Stop-Setup "Khong tim thay 'docker compose' (can Docker Compose v2)." }
docker info *> $null
if ($LASTEXITCODE -ne 0) { Stop-Setup 'Docker chua chay. Hay mo Docker Desktop roi chay lai script.' }

# --- 3. Build va khoi dong, doi toi khi tat ca healthy ---
Write-Info 'Dang build va khoi dong (lan dau co the mat vai phut)...'
docker compose up -d --build --wait
if ($LASTEXITCODE -ne 0) {
    docker compose ps
    Stop-Setup 'Co service khong khoi dong duoc hoac khong healthy. Xem log: docker compose logs <service>'
}

# --- 4. Ket qua ---
$FrontendPort = Get-EnvValue 'FRONTEND_PORT' '5173'
$BackendPort = Get-EnvValue 'BACKEND_PORT' '8000'
Write-Host ''
docker compose ps
Write-Host ''
Write-Info 'Hoan tat. Dia chi truy cap:'
Write-Info "  Giao dien : http://localhost:$FrontendPort"
Write-Info "  API health: http://localhost:$BackendPort/api/v1/health"
Write-Info "  Swagger   : http://localhost:$BackendPort/api/v1/docs (chi khi APP_ENV=development)"
Write-Info 'Dung (giu du lieu): docker compose down | Reset (XOA du lieu DB): docker compose down -v'
