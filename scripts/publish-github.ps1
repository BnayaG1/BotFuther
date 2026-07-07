# Push BotFuther to a private GitHub repo (run from repo root).
param(
    [Parameter(Mandatory = $true)]
    [string]$RepoUrl
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
Write-Host "Pushing branch '$branch' to origin..."
git push -u origin $branch
Write-Host "Done. Connect this repo in Railway: New Project -> Deploy from GitHub repo."
