# Sync ai/docs/wiki/*.md -> github.com/<owner>/<repo>.wiki
# Usage: .\ai\scripts\sync_github_wiki.ps1 [-WikiRepo "https://github.com/mouxangithub/ai.wiki.git"]

param(
    [string]$WikiRepo = "",
    [string]$CommitMessage = "docs: sync OP Agent wiki from ai/docs/wiki"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AiRoot = Resolve-Path (Join-Path $ScriptDir "..")
$WikiSrc = Join-Path $AiRoot "docs\wiki"
if (-not (Test-Path $WikiSrc)) {
    throw "Wiki source not found: $WikiSrc"
}

function Get-RepoSlug {
    if ($env:GITHUB_REPOSITORY) { return $env:GITHUB_REPOSITORY }
    $url = if ($WikiRepo) { $WikiRepo } else { "https://github.com/mouxangithub/ai.wiki.git" }
    if ($url -match 'github\.com[:/]([^/]+)/([^/.]+)') {
        return "$($Matches[1])/$($Matches[2])"
    }
    throw "Cannot resolve repository from WIKI_REPO"
}

function Get-WikiGitUrl([string]$Slug) {
    $owner, $repo = $Slug -split '/', 2
    $token = if ($env:WIKI_SYNC_TOKEN) { $env:WIKI_SYNC_TOKEN } elseif ($env:GITHUB_TOKEN) { $env:GITHUB_TOKEN } else { $null }
    if ($token) {
        return "https://x-access-token:${token}@github.com/${owner}/${repo}.wiki.git"
    }
    return "https://github.com/${owner}/${repo}.wiki.git"
}

function Get-ApiToken {
    if ($env:WIKI_SYNC_TOKEN) { return $env:WIKI_SYNC_TOKEN }
    if ($env:GITHUB_TOKEN) { return $env:GITHUB_TOKEN }
    return $null
}

function Enable-WikiFeature([string]$Slug) {
    $token = Get-ApiToken
    if (-not $token) { return $false }
    $headers = @{
        Authorization = "Bearer $token"
        Accept        = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
    }
    try {
        Invoke-RestMethod -Method Patch -Uri "https://api.github.com/repos/$Slug" -Headers $headers -Body '{"has_wiki":true}' -ContentType "application/json" | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Bootstrap-WikiHome([string]$Slug) {
    $token = Get-ApiToken
    if (-not $token) { return $false }
    $headers = @{
        Authorization = "Bearer $token"
        Accept        = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
    }
    $body = @{
        title  = "Home"
        body   = "OP Agent wiki — source: https://github.com/$Slug/tree/main/docs/wiki"
        format = "markdown"
    } | ConvertTo-Json
    try {
        Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$Slug/wiki/pages" -Headers $headers -Body $body -ContentType "application/json" | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Show-WikiMissingHelp([string]$Slug) {
    Write-Host @"

GitHub Wiki git 仓库不存在: ${Slug}.wiki

一次性修复（仓库管理员）:
  1. 打开 https://github.com/${Slug}/settings
  2. Features → 勾选 Wikis → Save
  3. 重新运行: .\ai\scripts\sync_github_wiki.ps1

源稿: https://github.com/${Slug}/tree/main/docs/wiki
"@ -ForegroundColor Yellow
}

$RepoSlug = Get-RepoSlug
$WikiUrl = Get-WikiGitUrl $RepoSlug
$Masked = "https://github.com/$RepoSlug.wiki.git"
$Tmp = Join-Path $env:TEMP ("ai-wiki-sync-" + [guid]::NewGuid().ToString("n"))
New-Item -ItemType Directory -Path $Tmp | Out-Null

try {
    Write-Host "Cloning $Masked"
    git clone $WikiUrl $Tmp 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Wiki clone failed; trying API bootstrap..."
        [void](Enable-WikiFeature $RepoSlug)
        [void](Bootstrap-WikiHome $RepoSlug)
        Start-Sleep -Seconds 3
        git clone $WikiUrl $Tmp
        if ($LASTEXITCODE -ne 0) {
            Show-WikiMissingHelp $RepoSlug
            if ($env:WIKI_SYNC_SKIP_ON_MISSING -eq "1" -or $env:GITHUB_ACTIONS) {
                Write-Host "SKIP: Wiki not available."
                exit 0
            }
            exit 2
        }
    }

    Push-Location $Tmp
    Get-ChildItem -Path $WikiSrc -Filter "*.md" | ForEach-Object {
        Copy-Item -Force $_.FullName (Join-Path $Tmp $_.Name)
        Write-Host "  copied $($_.Name)"
    }

    git add -A
    $status = git status --porcelain
    if (-not $status) {
        Write-Host "Wiki already up to date."
        exit 0
    }
    git -c user.name="wiki-sync" -c user.email="wiki-sync@local" commit -m $CommitMessage
    git push
    Write-Host "Wiki pushed successfully."
}
finally {
    Pop-Location -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}
