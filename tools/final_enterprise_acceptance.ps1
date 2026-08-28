param(
    [string]$Server = "root@1.14.148.15",
    [string]$SshKey = "$env:USERPROFILE\.ssh\adp_server_ed25519",
    [string]$Release = "",
    [string]$PublicBaseUrl = "https://1.14.148.15",
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
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE" }
}

function Invoke-SshStep {
    param([string]$Name, [string]$RemoteCommand)
    Invoke-Step $Name {
        ssh -i $SshKey -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 $Server $RemoteCommand
    }
}

function Invoke-MySqlTests {
    if (-not (Test-Path -LiteralPath $MySqlClient)) { throw "MySQL client not found: $MySqlClient" }
    $systemDatabases = @("information_schema", "mysql", "performance_schema", "sys")
    $databases = & $MySqlClient --protocol=tcp --host=127.0.0.1 --port=$MySqlPort --user=root --batch --skip-column-names --execute="SHOW DATABASES"
    if ($LASTEXITCODE -ne 0) { throw "Disposable MySQL is unavailable" }
    if (@($databases | Where-Object { $_ -notin $systemDatabases })) { throw "Disposable MySQL contains non-system databases" }
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
        foreach ($name in @("ADP_TEST_MYSQL_ALLOW_DISPOSABLE", "ADP_TEST_MYSQL_CLIENT", "ADP_TEST_MYSQL_HOST", "ADP_TEST_MYSQL_PORT", "ADP_TEST_MYSQL_USER", "ADP_TEST_MYSQL_PASSWORD")) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
    }
    $databases = & $MySqlClient --protocol=tcp --host=127.0.0.1 --port=$MySqlPort --user=root --batch --skip-column-names --execute="SHOW DATABASES"
    if ($LASTEXITCODE -ne 0) { throw "Cannot verify disposable MySQL cleanup" }
    if (@($databases | Where-Object { $_ -notin $systemDatabases })) { throw "MySQL tests left databases behind" }
}

if ([string]::IsNullOrWhiteSpace($Release)) {
    $Release = (ssh -i $SshKey -o BatchMode=yes -o ConnectTimeout=10 $Server 'basename $(readlink -f /opt/adp/slots/green)').Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Release)) { throw "Cannot resolve active release from cloud" }
}
if ($Release -notmatch '^[A-Za-z0-9._-]+$') { throw "Invalid release id" }
$serverHost = (($Server -split '@')[-1] -split ':')[0]
$publicUri = [Uri]$PublicBaseUrl
if ($publicUri.Scheme -ne "https" -or $publicUri.Host -ne $serverHost) { throw "PublicBaseUrl must target the SSH server over HTTPS" }

$report = Get-Content -Raw -LiteralPath "docs/audits/final-enterprise-acceptance.md"
if ($report -notmatch '(Final result:\s*PASS|最终结果[：:]\s*PASS)') { throw "Acceptance report is not marked PASS" }
$trackedDirty = git status --porcelain --untracked-files=no
if ($LASTEXITCODE -ne 0 -or $trackedDirty) { throw "Tracked implementation worktree must be clean before acceptance" }

Invoke-MySqlTests
Invoke-Step "Dependency security audit" { npm --prefix frontend audit --audit-level=low --registry=https://registry.npmjs.org }
Invoke-Step "Frontend unit tests" { npm --prefix frontend run test:unit }
Invoke-Step "Frontend production build" { npm --prefix frontend run build }
Remove-Item Env:NO_COLOR -ErrorAction SilentlyContinue
Invoke-Step "Seven-role browser flows" { npm --prefix frontend run test:e2e }

$reconciliation = Join-Path ([System.IO.Path]::GetTempPath()) "adp-final-reconciliation.json"
$env:MYSQL_HOST = "127.0.0.1"; $env:MYSQL_PORT = "3308"; $env:MYSQL_USER = "root"; $env:MYSQL_PASSWORD = ""
try {
    Invoke-Step "Local production rehearsal reconciliation" { python backend/scripts/reconcile_enterprise_data.py --database adp_final_acceptance --output $reconciliation }
}
finally {
    foreach ($name in @("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD")) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
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
Invoke-SshStep "Release evidence" "test -f $state/release.env && grep -F 'release_id=$Release' $state/release.env && grep -E '^release_sha256=[a-f0-9]{64}$' $state/release.env && grep -E '^database=[A-Za-z0-9_]+$' $state/release.env"
Invoke-SshStep "Backup checksums" "cd $backup && sha256sum -c SHA256SUMS"
Invoke-SshStep "ACME webroot" "test -d /var/lib/adp-acme && grep -F 'root /var/lib/adp-acme;' /etc/nginx/conf.d/adp-auth.conf"

$reconciliationCheck = 'set -e; found=0; for f in ' + $state + '/*-reconciliation.json; do test -f "$f" || exit 1; grep -q ''"ok": true'' "$f" || exit 1; grep -q ''"total_issues": 0'' "$f" || exit 1; found=1; done; test "$found" = 1'
ssh -i $SshKey -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 $Server $reconciliationCheck
if ($LASTEXITCODE -ne 0) { throw "Cloud reconciliation evidence is unavailable or reports issues" }

foreach ($path in @("/healthz", "/api/v1/health", "/api-docs/", "/workbench")) {
    Invoke-Step "Public $path" { curl.exe --fail --silent --show-error --connect-timeout 10 --max-time 30 --output NUL "$PublicBaseUrl$path" }
}
$trackedDirty = git status --porcelain --untracked-files=no
if ($LASTEXITCODE -ne 0 -or $trackedDirty) { throw "Acceptance changed tracked implementation files" }
Write-Host "FINAL_ENTERPRISE_ACCEPTANCE=PASS release=$Release"
