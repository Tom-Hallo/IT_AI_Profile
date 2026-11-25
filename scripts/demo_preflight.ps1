#requires -Version 5.1
<#
IT Talent AI Profile - read-only readiness checks for the dev Compose stack.
FullTests runs lint/tests/build (may write build/cache artifacts).
Fetch updates remote-tracking refs only. ProbeAI sends a tiny Ollama request.
Exit 0: ready (warnings allowed unless Strict); exit 1: not ready.
#>
[CmdletBinding()]
param(
    [switch]$FullTests,
    [switch]$Strict,
    [switch]$Fetch,
    [switch]$ProbeAI,
    [ValidateNotNullOrEmpty()][string]$ExpectedBranch = 'master',
    [ValidateRange(1,1440)][int]$LogMinutes = 15,
    [ValidateRange(1,3600)][int]$WorkerHeartbeatSeconds = 180,
    [ValidateRange(5,600)][int]$AiTimeoutSeconds = 120
)
$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 handles native stderr differently from PS 7.
$PSNativeCommandUseErrorActionPreference = $false
$script:Results = New-Object 'System.Collections.Generic.List[object]'
$Root = Split-Path -Parent $PSScriptRoot
$script:ComposeArgs = @('compose','--project-directory',$Root,'--env-file',(Join-Path $Root '.env'),'-f',(Join-Path $Root 'docker-compose.yml'))

function Add-Result([string]$Name,[string]$Status,[string]$Detail) {
    $colors = @{ PASS='Green'; WARN='Yellow'; FAIL='Red'; SKIP='DarkGray' }
    [void]$script:Results.Add([pscustomobject]@{Check=$Name;Status=$Status;Detail=$Detail})
    Write-Host ('[{0}] {1}: {2}' -f $Status,$Name,$Detail) -ForegroundColor $colors[$Status]
}
function Invoke-Native([string]$Exe,[string[]]$Arguments,[string]$InputText) {
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    if ($PSBoundParameters.ContainsKey('InputText')) {
        $output = @($InputText | & $Exe @Arguments 2>&1)
    } else { $output = @(& $Exe @Arguments 2>&1) }
    $code = $LASTEXITCODE
    return [pscustomobject]@{Code=$code;Text=(($output | ForEach-Object { [string]$_ }) -join "`n")}
}
function Invoke-Compose([string[]]$Arguments,[string]$InputText) {
    $allArgs = $script:ComposeArgs + $Arguments
    if ($PSBoundParameters.ContainsKey('InputText')) {
        Invoke-Native -Exe 'docker' -Arguments $allArgs -InputText $InputText
    } else { Invoke-Native -Exe 'docker' -Arguments $allArgs }
}
function Assert-Exit($Result,[string]$Hint) {
    if ($null -eq $Result.Code -or $Result.Code -ne 0) { throw "$Hint (exit $($Result.Code))" }
}
function Check([string]$Name,[scriptblock]$Action) {
    try {
        $detail = & $Action
        Add-Result $Name 'PASS' ($detail -join ' ')
        return $true
    } catch {
        Add-Result $Name 'FAIL' $_.Exception.Message
        return $false
    }
}
function Skip([string]$Name,[string]$Why) { Add-Result $Name 'SKIP' $Why }
function Get-Port([string]$Service,[int]$InternalPort) {
    $r = Invoke-Compose @('port',$Service,[string]$InternalPort)
    Assert-Exit $r "No published port for $Service"
    $match = [regex]::Match($r.Text.Trim(),'(?m):(\d+)\s*$')
    if (-not $match.Success) { throw "Cannot determine published port for $Service" }
    return [int]$match.Groups[1].Value
}
function Assert-Health([string]$Url) {
    try { $h = Invoke-RestMethod -Uri $Url -TimeoutSec 10 -ErrorAction Stop }
    catch { throw "Health HTTP request failed: $Url. Check backend/proxy logs." }
    if ($h.status -ne 'ok' -or $h.service -ne 'backend' -or $h.checks.database -ne 'ok' -or $h.checks.redis -ne 'ok') {
        throw "Unexpected health JSON at $Url (expected status, database and redis = ok)."
    }
    return "$Url - database=ok, redis=ok"
}
function Check-Command([string]$Name,[string[]]$Arguments) {
    [void](Check $Name {
        $r = Invoke-Compose $Arguments
        Assert-Exit $r "Failed: docker compose $($Arguments -join ' ')"
        'Command completed (exit 0)'
    })
}

Write-Host "`n=== IT TALENT AI PROFILE | DEMO PREFLIGHT ===" -ForegroundColor Cyan
Write-Host "Root: $Root | PowerShell $($PSVersionTable.PSVersion)"
Push-Location -LiteralPath $Root
try {
    $gitOk = Check 'Git CLI and repository' {
        if (-not (Get-Command git -CommandType Application -ErrorAction SilentlyContinue)) { throw 'Git CLI is not installed.' }
        $r = Invoke-Native 'git' @('rev-parse','--show-toplevel')
        Assert-Exit $r 'Not a Git working tree'
        if ((Resolve-Path -LiteralPath $r.Text.Trim()).Path -ne (Resolve-Path -LiteralPath $Root).Path) { throw 'Script is not in the expected repository root.' }
        'Git repository found'
    }
    if ($gitOk) {
        [void](Check 'Git branch and commit' {
            $r = Invoke-Native 'git' @('symbolic-ref','--quiet','--short','HEAD')
            Assert-Exit $r 'Detached HEAD; select the approved demo branch'
            if ($r.Text.Trim() -ne $ExpectedBranch) { throw "Expected branch $ExpectedBranch; actual $($r.Text.Trim())" }
            $sha = Invoke-Native 'git' @('rev-parse','--short','HEAD')
            Assert-Exit $sha 'Cannot read commit'
            "$ExpectedBranch @ $($sha.Text.Trim())"
        })
        [void](Check 'Git operation state' {
            foreach ($marker in @('MERGE_HEAD','CHERRY_PICK_HEAD','REVERT_HEAD','rebase-merge','rebase-apply','sequencer','BISECT_START')) {
                $r = Invoke-Native 'git' @('rev-parse','--git-path',$marker)
                Assert-Exit $r 'Cannot resolve Git metadata path'
                if (Test-Path -LiteralPath $r.Text.Trim()) { throw "Unfinished Git operation: $marker" }
            }
            'No merge/rebase/cherry-pick in progress'
        })
        $r = Invoke-Native 'git' @('status','--porcelain','--untracked-files=normal')
        if ($r.Code -ne 0) { Add-Result 'Working tree' 'FAIL' 'git status failed' }
        elseif ($r.Text.Trim()) { Add-Result 'Working tree' 'WARN' 'Uncommitted or untracked files exist. Review git status.' }
        else { Add-Result 'Working tree' 'PASS' 'Clean' }
        $remoteOk = $true
        if ($Fetch) { $remoteOk = Check 'Git fetch' { $r = Invoke-Native 'git' @('fetch','origin'); Assert-Exit $r 'Fetch failed; check network/authentication'; 'Remote refs refreshed' } }
        else { Skip 'Git fetch' 'Not requested; upstream comparison uses cached refs.' }
        if ($remoteOk) {
            $r = Invoke-Native 'git' @('rev-list','--left-right','--count',"HEAD...refs/remotes/origin/$ExpectedBranch")
            if ($r.Code -ne 0 -or $r.Text.Trim() -notmatch '^(\d+)\s+(\d+)$') { Add-Result 'Git upstream' 'WARN' 'Cannot compare against origin; verify the approved demo commit.' }
            elseif ([int]$Matches[1] -ne 0 -or [int]$Matches[2] -ne 0) { Add-Result 'Git upstream' 'WARN' "Ahead=$($Matches[1]), behind=$($Matches[2]); review differences." }
            else { Add-Result 'Git upstream' 'PASS' 'Matches origin ref (cached unless -Fetch)' }
        } else { Skip 'Git upstream' 'Fetch failed' }
    } else { foreach ($n in @('Git branch and commit','Git operation state','Working tree','Git fetch','Git upstream')) { Skip $n 'Git unavailable' } }

    $filesOk = Check 'Compose prerequisites' {
        foreach ($f in @('.env','docker-compose.yml')) { if (-not (Test-Path -LiteralPath (Join-Path $Root $f) -PathType Leaf)) { throw "Missing $f" } }
        'Required files exist'
    }
    $dockerOk = Check 'Docker CLI and Compose v2' {
        if (-not (Get-Command docker -CommandType Application -ErrorAction SilentlyContinue)) { throw 'Docker CLI not installed.' }
        $r = Invoke-Native 'docker' @('compose','version'); Assert-Exit $r 'Docker Compose v2 is unavailable'; $r.Text.Trim()
    }
    $daemonOk = $false
    if ($dockerOk) { $daemonOk = Check 'Docker daemon' { $r = Invoke-Native 'docker' @('info','--format','{{.OSType}}'); Assert-Exit $r 'Start Docker Desktop and check docker context'; if ($r.Text.Trim() -ne 'linux') { throw 'Linux containers are required' }; 'Linux Docker daemon reachable' } }
    else { Skip 'Docker daemon' 'Docker CLI unavailable' }
    $configOk = $false
    if ($filesOk -and $dockerOk) {
        $configOk = Check 'Compose configuration' {
            $r = Invoke-Compose @('config','--quiet')
            Assert-Exit $r 'Invalid Compose/.env; run docker compose config --quiet locally'
            if ($r.Text -match '(?i)variable is not set|defaulting to a blank string') { throw 'A Compose variable is missing; inspect .env locally.' }
            'Compose syntax and required interpolation valid'
        }
    } else { Skip 'Compose configuration' 'Prerequisites missing' }
    $stackOk = $daemonOk -and $configOk
    $running = @{}
    $services = @('postgres','redis','migrate','backend','worker','maintenance','clamav','frontend')
    foreach ($svc in $services) {
        $running[$svc] = $false
        if (-not $stackOk) { Skip "Container $svc" 'Docker/Compose prerequisite failed'; continue }
        $running[$svc] = Check "Container $svc" {
            $r = Invoke-Compose @('ps','-a','-q',$svc); Assert-Exit $r 'Cannot list container'
            $ids = @($r.Text -split '\r?\n' | Where-Object { $_ -match '^[a-f0-9]{12,64}$' })
            if ($ids.Count -ne 1) { throw "Expected one container, found $($ids.Count); run docker compose ps -a" }
            $r = Invoke-Native 'docker' @('inspect','--format','{{json .State}}',$ids[0]); Assert-Exit $r 'docker inspect failed'
            $s = $r.Text | ConvertFrom-Json
            if ($svc -eq 'migrate') {
                if ($s.Status -ne 'exited' -or $s.ExitCode -ne 0) { throw "Migration container: $($s.Status), exit=$($s.ExitCode)" }
                return 'Completed successfully (exited 0)'
            }
            if ($s.Status -ne 'running' -or $s.Restarting -or $s.OOMKilled) { throw "Container state=$($s.Status), OOMKilled=$($s.OOMKilled)" }
            if ($s.Health -and $s.Health.Status -ne 'healthy') { throw "Health=$($s.Health.Status)" }
            if ($svc -in @('postgres','redis','backend','frontend') -and -not $s.Health) { throw 'Expected Docker healthcheck is missing' }
            if ($s.Health) { 'Running, healthy' } else { 'Running; functional checks follow where available' }
        }
    }
    if ($running.backend) {
        [void](Check 'Direct backend health' { $p = Get-Port 'backend' 8000; Assert-Health "http://127.0.0.1:$p/api/v1/health" })
        [void](Check 'Alembic current vs heads' {
            $r = Invoke-Compose @('exec','-T','backend','alembic','heads'); Assert-Exit $r 'Cannot read Alembic heads'
            $heads = @($r.Text -split '\r?\n' | Where-Object { $_ -match '\(head\)\s*$' })
            if ($heads.Count -ne 1) { throw "Expected exactly one migration head; found $($heads.Count)" }
            $r = Invoke-Compose @('exec','-T','backend','alembic','current','--check-heads'); Assert-Exit $r 'Database is not at all heads or migration check failed'
            "Database at latest head: $($heads[0].Trim())"
        })
        [void](Check 'GitHub OAuth configuration' {
            $py = @'
from app.core.config import settings
assert settings.github_oauth_enabled, 'OAuth credentials missing'
assert settings.github_token_encryption_key, 'Encryption key missing'
print('OAuth credentials and encryption key configured')
'@
            $r = Invoke-Compose -Arguments @('exec','-T','backend','python','-') -InputText $py; Assert-Exit $r 'Check GitHub OAuth credentials and encryption key (values not printed)'; 'Credentials configured; callback registration/login still requires manual test'
        })
        [void](Check 'ClamAV from backend' {
            $py = @'
import socket
from app.core.config import settings
with socket.create_connection((settings.cv_scanner_host, settings.cv_scanner_port), timeout=5) as s:
    s.settimeout(5)
    s.sendall(b'zPING\0')
    response = b''
    while b'\0' not in response and len(response) < 64:
        chunk = s.recv(64)
        if not chunk:
            break
        response += chunk
    assert response.strip(b'\0\r\n') == b'PONG'
'@
            $r = Invoke-Compose -Arguments @('exec','-T','backend','python','-') -InputText $py; Assert-Exit $r 'ClamAV did not respond PONG from backend'; 'Scanner responds PONG'
        })
    } else { foreach ($n in @('Direct backend health','Alembic current vs heads','GitHub OAuth configuration','ClamAV from backend')) { Skip $n 'Backend not ready' } }
    if ($running.frontend) {
        [void](Check 'Frontend HTTP' {
            $p = Get-Port 'frontend' 5173
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$p/" -UseBasicParsing -TimeoutSec 10
            if ($r.StatusCode -ne 200 -or $r.Content -notmatch '<html') { throw 'Expected HTML HTTP 200' }; "HTTP 200 HTML on port $p"
        })
        [void](Check 'Frontend API proxy health' { $p = Get-Port 'frontend' 5173; Assert-Health "http://127.0.0.1:$p/api/v1/health" })
    } else { Skip 'Frontend HTTP' 'Frontend not ready'; Skip 'Frontend API proxy health' 'Frontend not ready' }
    if ($running.worker) {
        [void](Check 'RQ worker heartbeat and queues' {
            $py = @"
from datetime import datetime, timezone
from rq import Worker
from app.core.config import settings
from app.core.redis import get_redis_connection
covered = set()
for w in Worker.all(connection=get_redis_connection()):
    hb = w.last_heartbeat
    if hb is None:
        continue
    if hb.tzinfo is None:
        hb = hb.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - hb).total_seconds()
    if -30 <= age <= $WorkerHeartbeatSeconds and w.get_state() in ('idle', 'busy'):
        covered.update(w.queue_names())
assert set(settings.worker_queues) <= covered, 'No fresh worker for required queues'
"@
            $r = Invoke-Compose -Arguments @('exec','-T','worker','python','-') -InputText $py; Assert-Exit $r 'No live registered RQ worker for all configured queues'; "Configured queues covered by fresh worker heartbeat (<= $WorkerHeartbeatSeconds s)"
        })
    } else { Skip 'RQ worker heartbeat and queues' 'Worker not ready' }
    if ($stackOk) {
        foreach ($svc in @('backend','worker','maintenance','clamav')) {
            $r = Invoke-Compose @('logs','--no-color','--since',"${LogMinutes}m",'--tail','500',$svc)
            if ($r.Code -ne 0) { Add-Result "Recent logs $svc" 'FAIL' 'Cannot read service logs'; continue }
            $lines = @($r.Text -split '\r?\n' | Where-Object { $_ -match '\S' })
            $hits = @($lines | Where-Object { $_ -match '(?i)\b(ERROR|CRITICAL|FATAL|PANIC)\b|Traceback \(most recent call last\)|\bOOMKilled\b|\bHTTP/\d(?:\.\d)?[" ]+5\d\d\b' })
            if ($hits.Count -gt 0) { Add-Result "Recent logs $svc" 'WARN' "$($hits.Count) suspect lines; inspect docker compose logs --since ${LogMinutes}m $svc locally" }
            elseif ($lines.Count -ge 500) { Add-Result "Recent logs $svc" 'WARN' 'No matches but log sample may be truncated (500-line cap)' }
            else { Add-Result "Recent logs $svc" 'PASS' "No matched error patterns in $($lines.Count) sampled lines" }
        }
    } else { Skip 'Recent logs' 'Docker/Compose prerequisite failed' }

    $aiConfig = @{}
    foreach ($svc in @('backend','worker')) {
        if (-not $running[$svc]) { Skip "AI readiness $svc" 'Container not ready'; continue }
        $probe = if ($ProbeAI) { 'True' } else { 'False' }
        $py = @"
import json, urllib.request
from app.core.config import settings
provider, model = settings.ai_provider, settings.ai_model
assert model, 'AI_MODEL missing'
result = {'provider': provider, 'model': model, 'probe': False}
if provider == 'ollama':
    base = settings.ai_base_url.rstrip('/')
    with urllib.request.urlopen(base + '/api/tags', timeout=10) as r:
        tags = json.load(r)
    names = {m.get('name') or m.get('model') for m in tags.get('models', [])}
    wanted = model if ':' in model.rsplit('/', 1)[-1] else model + ':latest'
    assert model in names or wanted in names, 'Configured Ollama model not installed'
    if $probe:
        data = json.dumps({'model': model, 'prompt': 'Reply OK', 'stream': False, 'options': {'num_predict': 8}}).encode()
        req = urllib.request.Request(base + '/api/generate', data=data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=$AiTimeoutSeconds) as r:
            answer = json.load(r)
        assert answer.get('done') is True and str(answer.get('response', '')).strip(), 'Empty or incomplete inference'
        result['probe'] = True
else:
    assert settings.ai_api_key and settings.ai_api_key.get_secret_value().strip(), 'AI_API_KEY missing'
print(json.dumps(result))
"@
        try {
            $r = Invoke-Compose -Arguments @('exec','-T',$svc,'python','-') -InputText $py
            Assert-Exit $r 'AI settings, endpoint, model, key or inference invalid; inspect effective configuration locally'
            $a = $r.Text | ConvertFrom-Json
            $aiConfig[$svc] = $a
            if ($a.provider -eq 'ollama') {
                $detail = if ($a.probe) { 'Model listed and inference returned non-empty response' } else { 'Endpoint reachable and configured model listed; inference not requested' }
                Add-Result "AI readiness $svc" 'PASS' $detail
            } else { Add-Result "AI readiness $svc" 'WARN' "Cloud provider $($a.provider): key/model configured; remote inference not verified" }
        } catch { Add-Result "AI readiness $svc" 'FAIL' $_.Exception.Message }
    }
    if ($aiConfig.ContainsKey('backend') -and $aiConfig.ContainsKey('worker')) {
        if ($aiConfig.backend.provider -ne $aiConfig.worker.provider -or $aiConfig.backend.model -ne $aiConfig.worker.model) { Add-Result 'AI configuration consistency' 'FAIL' 'Backend and worker provider/model differ' }
        else { Add-Result 'AI configuration consistency' 'PASS' 'Backend and worker use the same provider/model' }
    } else { Skip 'AI configuration consistency' 'AI configuration not available for both services' }

    if ($FullTests) {
        if ($running.backend) {
            Check-Command 'Backend Ruff lint' @('exec','-T','backend','python','-m','ruff','check','.')
            Check-Command 'Backend Ruff format' @('exec','-T','backend','python','-m','ruff','format','--check','.')
            Check-Command 'Backend non-integration pytest' @('exec','-T','backend','python','-m','pytest','-m','not integration','-q','--tb=short')
        } else { Skip 'Backend tests' 'Backend not ready' }
        if ($running.frontend) {
            Check-Command 'Frontend ESLint' @('exec','-T','frontend','npm','run','lint')
            Check-Command 'Frontend regression tests' @('exec','-T','frontend','npm','run','test')
            Check-Command 'Frontend production build' @('exec','-T','frontend','npm','run','build')
        } else { Skip 'Frontend tests' 'Frontend not ready' }
    } else { Skip 'FullTests' 'Not requested; use -FullTests for lint, tests and build' }
} catch {
    Add-Result 'Unexpected preflight error' 'FAIL' $_.Exception.Message
} finally { Pop-Location }

$pass = @($script:Results | Where-Object Status -eq 'PASS').Count
$warn = @($script:Results | Where-Object Status -eq 'WARN').Count
$fail = @($script:Results | Where-Object Status -eq 'FAIL').Count
$skip = @($script:Results | Where-Object Status -eq 'SKIP').Count
Write-Host "`n=== SUMMARY ===" -ForegroundColor Cyan
Write-Host "PASS=$pass WARN=$warn FAIL=$fail SKIP=$skip"
if ($fail -gt 0 -or ($Strict -and $warn -gt 0)) {
    Write-Host 'NOT READY - resolve failures (and warnings in Strict mode).' -ForegroundColor Red
    exit 1
}
if ($warn -gt 0) { Write-Host 'READY WITH WARNINGS - review before demo.' -ForegroundColor Yellow }
else { Write-Host 'PREFLIGHT READY - automated checks passed.' -ForegroundColor Green }
Write-Host 'Manual smoke test still required: OAuth -> Sync -> Analyze -> Dashboard -> Roadmap -> JD -> CV -> Share -> Mentor.'
exit 0
