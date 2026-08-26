param(
    [string]$Server = "root@1.14.148.15",
    [string]$SshKey = "$env:USERPROFILE\.ssh\adp_server_ed25519",
    [string]$Release = "20260817-732c247ecde1",
    [string]$MySqlClient = "C:\Program Files\MySQL\MySQL Server 9.7\bin\mysql.exe",
    [int]$MySqlPort = 33307
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location (Split-Path -Parent $PSScriptRoot)

function Invoke-Step {
    param([string]$Name, [scriptblock]$Action)
    Write-Host "[RUN] $Name"
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

function Invoke-SshStep {
    param([string]$Name, [string]$RemoteCommand)
    Invoke-Step $Name {
        ssh -i $SshKey -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 $Server $RemoteCommand
    }
}

function Invoke-MySqlTests {
    if (-not (Test-Path -LiteralPath $MySqlClient)) {
        throw "MySQL client not found: $MySqlClient"
    }
    $systemDatabases = @("information_schema", "mysql", "performance_schema", "sys")
    $databases = & $MySqlClient --protocol=tcp --host=127.0.0.1 --port=$MySqlPort --user=root --batch --skip-column-names --execute="SHOW DATABASES"
    if ($LASTEXITCODE -ne 0) { throw "Disposable MySQL is unavailable" }
    $unexpected = @($databases | Where-Object { $_ -notin $systemDatabases })
    if ($unexpected) { throw "Disposable MySQL contains non-system databases: $unexpected" }

    try {
        $env:ADP_TEST_MYSQL_ALLOW_DISPOSABLE = "1"
        $env:ADP_TEST_MYSQL_CLIENT = $MySqlClient
        $env:ADP_TEST_MYSQL_HOST = "127.0.0.1"
        $env:ADP_TEST_MYSQL_PORT = "$MySqlPort"
        $env:ADP_TEST_MYSQL_USER = "root"
        $env:ADP_TEST_MYSQL_PASSWORD = ""
        $output = python -m pytest -q backend/tests -rs 2>&1
        $testExit = $LASTEXITCODE
        $output | ForEach-Object { Write-Host $_ }
        if ($testExit -ne 0) { throw "Backend and MySQL tests failed" }
        if (($output -join "`n") -match "\bskipped\b") { throw "Backend tests contain skipped checks" }
    }
    finally {
        Remove-Item Env:ADP_TEST_MYSQL_ALLOW_DISPOSABLE -ErrorAction SilentlyContinue
        Remove-Item Env:ADP_TEST_MYSQL_CLIENT -ErrorAction SilentlyContinue
        Remove-Item Env:ADP_TEST_MYSQL_HOST -ErrorAction SilentlyContinue
        Remove-Item Env:ADP_TEST_MYSQL_PORT -ErrorAction SilentlyContinue
        Remove-Item Env:ADP_TEST_MYSQL_USER -ErrorAction SilentlyContinue
        Remove-Item Env:ADP_TEST_MYSQL_PASSWORD -ErrorAction SilentlyContinue
    }
    $databases = & $MySqlClient --protocol=tcp --host=127.0.0.1 --port=$MySqlPort --user=root --batch --skip-column-names --execute="SHOW DATABASES"
    if ($LASTEXITCODE -ne 0) { throw "Cannot verify disposable MySQL cleanup" }
    $unexpected = @($databases | Where-Object { $_ -notin $systemDatabases })
    if ($unexpected) { throw "MySQL tests left databases behind: $unexpected" }
}

$reportPath = "docs/audits/final-enterprise-acceptance.md"
$report = Get-Content -Raw -LiteralPath $reportPath
foreach ($marker in @(
    "Final result: PASS",
    $Release,
    "f629a90372b19b06790b175d5885e4b66a2905827982434214f8dd27f1484835",
    "236 passed",
    "87 passed",
    "12 passed",
    "14 类检查均为 0"
)) {
    if (-not $report.Contains($marker)) {
        throw "Final report is incomplete: $marker"
    }
}

$dirty = git status --porcelain
if ($LASTEXITCODE -ne 0 -or $dirty) {
    throw "Implementation worktree must be clean before acceptance"
}

Write-Host "[RUN] Backend and MySQL tests"
Invoke-MySqlTests
Invoke-Step "Dependency security audit" { npm --prefix frontend audit --audit-level=low --registry=https://registry.npmjs.org }
Invoke-Step "Frontend unit tests" { npm --prefix frontend run test:unit }
Invoke-Step "Frontend production build" { npm --prefix frontend run build }
Remove-Item Env:NO_COLOR -ErrorAction SilentlyContinue
Invoke-Step "Seven-role browser flows" { npm --prefix frontend run test:e2e }

$reconciliation = Join-Path ([System.IO.Path]::GetTempPath()) "adp-final-reconciliation.json"
$env:MYSQL_HOST = "127.0.0.1"
$env:MYSQL_PORT = "3308"
$env:MYSQL_USER = "root"
$env:MYSQL_PASSWORD = ""
try {
    Invoke-Step "Local production rehearsal reconciliation" {
        python backend/scripts/reconcile_enterprise_data.py --database adp_final_acceptance_20260817 --output $reconciliation
    }
}
finally {
    Remove-Item Env:MYSQL_HOST -ErrorAction SilentlyContinue
    Remove-Item Env:MYSQL_PORT -ErrorAction SilentlyContinue
    Remove-Item Env:MYSQL_USER -ErrorAction SilentlyContinue
    Remove-Item Env:MYSQL_PASSWORD -ErrorAction SilentlyContinue
}
Invoke-Step "Strict source audit" { python tools/audit_source.py --root . --strict }

$state = "/var/lib/adp/deployments/$Release"
$backup = "/opt/adp/backups/$Release-blue-green"
Invoke-SshStep "Old service health" "systemctl is-active adp-auth.service"
Invoke-SshStep "New service health" "systemctl is-active adp-next.service"
Invoke-SshStep "Nginx configuration" "nginx -t"
Invoke-SshStep "Old API health" "curl --fail --silent http://127.0.0.1:5001/api/v1/health"
Invoke-SshStep "New API health" "curl --fail --silent http://127.0.0.1:5002/api/v1/health"
Invoke-SshStep "Active release root" "grep -F '/opt/adp/releases/$Release/frontend/dist' /etc/nginx/conf.d/adp-auth.conf"
Invoke-SshStep "Active API upstream" "grep -F 'proxy_pass http://127.0.0.1:5002;' /etc/nginx/conf.d/adp-auth.conf"
Invoke-SshStep "Release evidence" "test -f $state/release.env"
Invoke-SshStep "Backup checksums" "cd $backup && sha256sum -c SHA256SUMS"

$remoteReconciliation = ssh -i $SshKey -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 $Server "cat $state/*-reconciliation.json"
if ($LASTEXITCODE -ne 0) {
    throw "Cloud reconciliation evidence is unavailable"
}
$okCount = [regex]::Matches(($remoteReconciliation -join "`n"), '"ok": true').Count
if ($okCount -ne 2) {
    throw "Both cloud reconciliation reports must be ok"
}
$zeroCount = [regex]::Matches(($remoteReconciliation -join "`n"), '"total_issues": 0').Count
if ($zeroCount -ne 2) {
    throw "Both cloud reconciliation reports must have zero issues"
}

foreach ($path in @("/healthz", "/api/v1/health", "/api-docs/", "/workbench")) {
    Invoke-Step "Public $path" {
        curl.exe --fail --silent --show-error --connect-timeout 10 --max-time 30 --output NUL "https://1.14.148.15$path"
    }
}

$dirty = git status --porcelain
if ($LASTEXITCODE -ne 0 -or $dirty) {
    throw "Acceptance changed the implementation worktree"
}

Write-Host "FINAL_ENTERPRISE_ACCEPTANCE=PASS"
