<#
.SYNOPSIS
    打包 ADP 发布归档（与 deploy/deploy-blue-green.sh 的输入约定一致）。

.DESCRIPTION
    先把工作区复制到临时 staging 目录（robocopy 精确排除运行时/构建产物），再打成 tar.gz，
    因此归档不会混入 node_modules、dist、.venv、deepseek-harness 等。
    注意：不要用 tar 的 --exclude=scripts 之类按名字匹配的排除方式——它会把
    backend/scripts/ 一起排除，发布时会因缺少 reconcile_enterprise_data.py 失败。

.EXAMPLE
    pwsh tools/build_release_archive.ps1 -OutFile D:\tmp\adp-r3.tgz
#>
param(
    [string]$Repository = (Split-Path -Parent $PSScriptRoot),
    [string]$OutFile = "$env:TEMP\adp-release.tgz",
    [string]$StageDir = "$env:TEMP\adp-release-stage"
)

$ErrorActionPreference = 'Stop'
$required = @(
    'backend/requirements.txt',
    'backend/app.py',
    'backend/scripts/reconcile_enterprise_data.py',
    'frontend/package.json',
    'frontend/package-lock.json',
    'database/migrations',
    'deploy/adp-next.service',
    'deploy/deploy-blue-green.sh',
    'api-docs/openapi.json'
)

if (Test-Path $StageDir) { Remove-Item $StageDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null

# 只排除明确的本地/生成物；根目录 scripts/ 与 docs/manual-test 属于本地手工测试资料。
$excludeDirs = @(
    (Join-Path $Repository '.git'),
    (Join-Path $Repository '.local'),
    (Join-Path $Repository '.agent-teams'),
    (Join-Path $Repository '.worktrees'),
    (Join-Path $Repository '.pytest_cache'),
    (Join-Path $Repository 'htmlcov'),
    (Join-Path $Repository 'scripts'),
    (Join-Path $Repository 'repair'),
    (Join-Path $Repository 'uat-evidence'),
    (Join-Path $Repository 'adp_phone'),
    (Join-Path $Repository 'docs\manual-test'),
    (Join-Path $Repository 'frontend\release'),
    'node_modules',
    '.venv',
    'dist',
    '__pycache__',
    'deepseek-harness',
    'playwright-report',
    'test-results'
)
$excludeFiles = @('*.log', '*.pyc', '.coverage', 'coverage-*.json', '*.tgz')

$robocopyArgs = @($Repository, $StageDir, '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/R:1', '/W:1', '/XD') + $excludeDirs + @('/XF') + $excludeFiles
robocopy @robocopyArgs | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }

foreach ($path in $required) {
    if (-not (Test-Path (Join-Path $StageDir $path))) { throw "release is missing required path: $path" }
}

if (Test-Path $OutFile) { Remove-Item $OutFile -Force }
& tar -czf $OutFile -C $StageDir .
if ($LASTEXITCODE -ne 0) { throw "tar failed with exit code $LASTEXITCODE" }

$sha = (Get-FileHash -Algorithm SHA256 -Path $OutFile).Hash.ToLowerInvariant()
[pscustomobject]@{
    Archive = $OutFile
    SizeMB  = [math]::Round((Get-Item $OutFile).Length / 1MB, 2)
    Sha256  = $sha
} | Format-List
