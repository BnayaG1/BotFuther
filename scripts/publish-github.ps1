# Push BotFuther to GitHub (run from repo root in an interactive terminal).
param(
    [string]$RepoUrl = "https://github.com/BnayaG1/BotFuther.git",
    [switch]$ForceMain
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "Checking secrets are not tracked..."
$tracked = git ls-files | Select-String -Pattern "^\.env$|^coupons\.db$"
if ($tracked) {
    throw "Refusing to push: .env or coupons.db is tracked. Fix .gitignore and git rm --cached first."
}

if (-not (git rev-parse --verify HEAD 2>$null)) {
    throw "No commits yet. Run: git add -A && git commit -m 'Prepare Railway deployment'"
}

if (git remote get-url origin 2>$null) {
    git remote set-url origin $RepoUrl
} else {
    git remote add origin $RepoUrl
}

$branch = git branch --show-current
Write-Host "Local branch: $branch"

git fetch origin 2>$null
$hasMain = git rev-parse --verify origin/main 2>$null

if ($hasMain -and -not $ForceMain) {
    Write-Host "Remote 'main' exists (old nested layout). Re-run with -ForceMain to replace it."
    Write-Host "  .\scripts\publish-github.ps1 -ForceMain"
    exit 1
}

$pushArgs = @("push", "-u", "origin", "${branch}:main")
if ($ForceMain) {
    $pushArgs = @("push", "-u", "origin", "${branch}:main", "--force")
    Write-Host "Force-pushing to main (replaces old BotFuther/ nested layout)..."
} else {
    Write-Host "Pushing to main..."
}

& git @pushArgs
Write-Host "Done. Next: Railway -> New Project -> Deploy from GitHub -> select BotFuther"
