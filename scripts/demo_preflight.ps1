# Windows PowerShell 5.1 / PowerShell 7. Read-only checks except optional ping/tests.
[CmdletBinding()]
param(
    [switch]$FullTests,
    [switch]$WorkerPing,
    [switch]$StrictLogs,
    [switch]$SkipOAuth,
    [switch]$SkipAI,
    [string]$ExpectedBranch = 'master',
    [string]$FrontendUrl,
    [string]$BackendUrl,
    [ValidateRange(1,1440)][int]$LogMinutes = 15
)
$ErrorActionPreference = 'Stop'
$script:Failures = 0
$script:Warnings = 0
$script:Skipped = 0
$script:Passes = 0
function Result([string]$Status, [string]$Name, [string]$Detail = '') {
    $color = switch ($Status) {
        PASS { $script:Passes++; 'Green' }
        FAIL { $script:Failures++; 'Red' }
        WARN { $script:Warnings++; 'Yellow' }
        SKIP { $script:Skipped++; 'DarkYellow' }
    }
    Write-Host "[$Status] $Name $Detail" -ForegroundColor $color
}
function Check([string]$Name, [scriptblock]$Action) {
    try { & $Action; Result PASS $Name } catch { Result FAIL $Name $_.Exception.Message }
}
function Require([bool]$Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function Native([string]$Program, [string[]]$Arguments) {
    # Windows PowerShell 5.1 can treat native stderr as ErrorRecord. Do not infer exit from stderr.
    $ErrorActionPreference = 'Continue'
    if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
        $PSNativeCommandUseErrorActionPreference = $false
    }
    $out = & $Program @Arguments 2>$null
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "$Program exited $code (run command locally for details)" }
    return $out
}
function Dc { Native 'docker' (@('compose','--env-file','.env') + $args) }
function PublishedUrl([string]$Service, [int]$Port) {
    $binding = (Dc port $Service $Port | Select-Object -First 1)
    if ($binding -notmatch ':(\d+)$') { throw "No published port for $Service" }
    return "http://localhost:$($Matches[1])"
}
function Health([string]$Base) {
    $h = Invoke-RestMethod -Uri "$($Base.TrimEnd('/'))/api/v1/health" -TimeoutSec 10
    Require ($h.status -eq 'ok' -and $h.checks.database -eq 'ok' -and $h.checks.redis -eq 'ok') 'Unexpected health body'
}
function PythonCheck([string]$Service, [string]$Code) {
    # stdin avoids PowerShell 5.1 native argument quote rewriting; code is ASCII.
    $ErrorActionPreference = 'Continue'
    if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) { $PSNativeCommandUseErrorActionPreference = $false }
    $output = $Code | & docker compose --env-file .env exec -T $Service python - 2>$null
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) { throw "Python probe in $Service exited $exitCode" }
    $output | ForEach-Object { Write-Host $_ }
}
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    Check 'Git CLI' { $null = Get-Command git -ErrorAction Stop }
    Check 'Docker CLI' { $null = Get-Command docker -ErrorAction Stop }
    Check 'Root files' { Require ((Test-Path .env -PathType Leaf) -and (Test-Path docker-compose.yml -PathType Leaf)) 'Missing .env or docker-compose.yml' }
    if ($script:Failures) { throw 'Prerequisites missing' }
    Check 'Git branch and clean worktree' {
        $branch = (Native git @('branch','--show-current') | Out-String).Trim()
        Require ($branch -eq $ExpectedBranch) "Expected $ExpectedBranch; got $branch"
        Require (-not (Native git @('status','--porcelain'))) 'Uncommitted or untracked files'
        foreach ($marker in @('MERGE_HEAD','CHERRY_PICK_HEAD','REVERT_HEAD','rebase-merge','rebase-apply')) {
            $p = Native git @('rev-parse','--git-path',$marker)
            Require (-not (Test-Path $p)) "Git operation in progress: $marker"
        }
        $sha = Native git @('rev-parse','--short','HEAD'); Write-Host "HEAD: $sha"
    }
    Check 'Git remote comparison (cached origin)' {
        $counts = (Native git @('rev-list','--left-right','--count',"HEAD...origin/$ExpectedBranch") | Out-String).Trim() -split '\s+'
        Require ($counts.Count -eq 2 -and $counts[0] -eq '0' -and $counts[1] -eq '0') 'HEAD differs from cached remote; fetch and review'
    }
    Check 'Docker daemon and Compose' { $null = Native docker @('info','--format','{{.ServerVersion}}'); $null = Native docker @('compose','version') }
    Check 'Compose config' { $null = Dc config --quiet }
    # Stop dependent probes only if Docker/config is unavailable; Git failures still allow diagnostics.
    try { $null = Dc config --quiet; $null = Native docker @('info','--format','{{.ServerVersion}}') } catch { throw 'Docker/config unavailable; dependent checks skipped' }
    foreach ($svc in @('postgres','redis','backend','frontend','worker','maintenance','clamav','migrate')) {
        Check "Container $svc" {
            $ids = @(Dc ps -a -q $svc | Where-Object { $_ })
            Require ($ids.Count -gt 0) 'Container missing'
            foreach ($id in $ids) {
                $s = (Native docker @('inspect','--format','{{json .State}}',$id) | Out-String) | ConvertFrom-Json
                if ($svc -eq 'migrate') { Require ($s.Status -eq 'exited' -and $s.ExitCode -eq 0) 'Migration container did not exit successfully' }
                else {
                    Require ($s.Status -eq 'running' -and -not $s.Restarting) "State: $($s.Status)"
                    if ($s.Health) { Require ($s.Health.Status -eq 'healthy') "Health: $($s.Health.Status)" }
                }
            }
        }
    }
    try {
        if (-not $FrontendUrl) { $FrontendUrl = PublishedUrl frontend 5173 }
        if (-not $BackendUrl) { $BackendUrl = PublishedUrl backend 8000 }
        Check 'Backend direct health' { Health $BackendUrl }
        Check 'Frontend proxy health' { Health $FrontendUrl }
        Check 'Frontend HTTP' {
            $r = Invoke-WebRequest -Uri $FrontendUrl -UseBasicParsing -TimeoutSec 10
            Require ($r.StatusCode -eq 200 -and $r.Content -match '<html') 'Frontend did not return HTML 200'
        }
        if ($SkipOAuth) { Result SKIP 'OAuth readiness' } else {
            Check 'OAuth readiness' {
                $r = Invoke-WebRequest -Uri "$($FrontendUrl.TrimEnd('/'))/api/v1/auth/github/status" -UseBasicParsing -TimeoutSec 10
                Require ($r.StatusCode -eq 204) 'OAuth credentials/key not ready'
            }
        }
    } catch { Result FAIL 'HTTP setup' $_.Exception.Message }
    Check 'Alembic current equals all heads' {
        PythonCheck backend @'
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from app.db.session import engine
heads = set(ScriptDirectory.from_config(Config('alembic.ini')).get_heads())
with engine.connect() as conn:
    conn.exec_driver_sql('SET SESSION search_path TO public')
    current = set(MigrationContext.configure(conn).get_current_heads())
print('current=' + ','.join(sorted(current)) + ' heads=' + ','.join(sorted(heads)))
if not heads or current != heads:
    raise SystemExit(1)
'@
    }
    Check 'ClamAV protocol ping from backend' {
        PythonCheck backend @'
import socket
from app.core.config import settings
with socket.create_connection((settings.cv_scanner_host, settings.cv_scanner_port), timeout=5) as s:
    s.settimeout(5)
    s.sendall(b'zPING\0')
    response = s.recv(1024)
if response.rstrip(b'\0\n') != b'PONG':
    raise SystemExit(1)
'@
    }
    Check 'Worker registered on configured queues' {
        PythonCheck backend @'
from datetime import datetime, timezone
from rq import Worker
from app.core.config import settings
from app.core.redis import get_redis_connection
workers = Worker.all(connection=get_redis_connection())
queues = set()
for worker in workers:
    beat = worker.last_heartbeat
    if beat is None:
        continue
    if beat.tzinfo is None:
        beat = beat.replace(tzinfo=timezone.utc)
    if (datetime.now(timezone.utc) - beat).total_seconds() <= 600:
        queues.update(worker.queue_names())
if not set(settings.worker_queues).issubset(queues):
    raise SystemExit(1)
'@
    }
    if ($WorkerPing) {
        Check 'RQ actual ping job' {
            $ping = (Dc exec -T backend python -m app.workers.enqueue ping --message demo-preflight --wait 30 | Select-Object -Last 1) | ConvertFrom-Json
            Require ($ping.status -eq 'finished' -and $ping.result.pong -eq $true) 'Unexpected RQ ping result'
        }
    } else { Result SKIP 'RQ actual ping job' 'Use -WorkerPing to enqueue a temporary Redis job.' }
    try {
        $logs = @(Dc logs --no-color --since "${LogMinutes}m" --tail 500 backend worker maintenance migrate)
        $suspect = @($logs | Where-Object { $_ -match '(?i)\b(ERROR|CRITICAL|FATAL)\b|Traceback \(most recent call last\)|\bOperationalError\b|\bConnectionError\b' })
        if ($suspect.Count) {
            $status = if ($StrictLogs) { 'FAIL' } else { 'WARN' }
            Result $status 'Recent logs' "$($suspect.Count) matching lines; review locally (not printed to avoid secrets)."
        } else { Result PASS 'Recent logs' 'No matching error lines in sampled window.' }
    } catch { Result FAIL 'Recent logs' $_.Exception.Message }
    if ($SkipAI) { Result SKIP 'AI readiness' } else {
        foreach ($svc in @('backend','worker')) {
            Check "AI readiness from $svc" {
                PythonCheck $svc @'
import json, urllib.request
from app.core.config import settings as s
if s.ai_provider == 'ollama':
    if not s.ai_model:
        raise SystemExit(1)
    with urllib.request.urlopen(s.ai_base_url.rstrip('/') + '/api/tags', timeout=8) as r:
        names = {m.get('name') or m.get('model') for m in json.load(r).get('models', [])}
    if s.ai_model not in names and s.ai_model + ':latest' not in names:
        raise SystemExit(1)
    print('Ollama configured model available; inference not tested')
else:
    if not s.ai_api_key or not s.ai_api_key.get_secret_value().strip():
        raise SystemExit(1)
    print('Cloud AI key present; provider authentication/inference not tested')
'@
            }
        }
        Result WARN 'AI inference' 'Run a real Mentor request before demo; availability/key presence is not inference.'
    }
    if ($FullTests) {
        Check 'Ruff lint' { $null = Dc exec -T backend python -m ruff check . }
        Check 'Ruff format' { $null = Dc exec -T backend python -m ruff format --check . }
        Check 'Backend unit tests (isolated runtime config)' {
            $null = Dc exec -T -e APP_ENV=test -e DATABASE_URL=postgresql+psycopg://ita:test-only@127.0.0.1:5432/it_ai_profile -e REDIS_URL=redis://127.0.0.1:6379/0 -e RUN_INTEGRATION=0 backend python -m pytest -m 'not integration' -q --tb=short
        }
        Check 'Frontend lint' { $null = Dc exec -T frontend npm run lint }
        Check 'Frontend regression scripts' { $null = Dc exec -T frontend npm test }
        Check 'Frontend Dashboard/Mentor/Analysis regressions' {
            $null = Dc exec -T frontend node --test tests/dashboard-github-radar.test.js tests/score-presentation.test.js tests/analysis-feedback.test.js tests/mentor-proposal-controls.test.js
        }
        Check 'Frontend build (includes typecheck)' { $null = Dc exec -T frontend npm run build }
    } else { Result SKIP 'Full regression tests' 'Use -FullTests.' }
} catch { Result FAIL 'Preflight aborted' $_.Exception.Message }
finally { Pop-Location }
Write-Host "PASS=$script:Passes FAIL=$script:Failures WARN=$script:Warnings SKIP=$script:Skipped"
if ($script:Failures -gt 0) { Write-Host 'NOT READY' -ForegroundColor Red; exit 1 }
Write-Host 'AUTOMATED CHECKS PASSED; manual OAuth/AI/UI smoke tests still required.' -ForegroundColor Green
exit 0
