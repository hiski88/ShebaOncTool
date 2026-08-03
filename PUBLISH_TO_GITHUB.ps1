param(
    [string]$RepositoryUrl = "https://github.com/hiski88/ShebaOncTool.git",
    [string]$Branch = "main",
    [string]$CommitMessage = "Update oncology scheduling prototype"
)

$ErrorActionPreference = "Stop"
$SourceDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$PublishDirectory = Join-Path $env:TEMP ("ShebaOncTool-publish-" + [guid]::NewGuid().ToString("N"))

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "The required command '$Name' is not installed. Install Git for Windows and run the script again."
    }
}

Require-Command "git"
Require-Command "robocopy"

try {
    Write-Host "Cloning $RepositoryUrl ..."
    git clone --branch $Branch $RepositoryUrl $PublishDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "Git clone failed. Confirm that you are signed in to GitHub and have write access to the repository."
    }

    $ExcludedDirectories = @(
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "data",
        "uploads",
        "artifacts"
    )
    $ExcludedFiles = @(
        "*.xls",
        "*.xlsx",
        "*.xlsm",
        "*.ics",
        "*.pyc",
        "secrets.toml",
        ".env"
    )

    Write-Host "Copying safe project files ..."
    $RoboCopyArguments = @(
        $SourceDirectory,
        $PublishDirectory,
        "/E",
        "/PURGE",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/NP",
        "/XD"
    ) + $ExcludedDirectories + @("/XF") + $ExcludedFiles

    & robocopy @RoboCopyArguments | Out-Null
    $RoboCopyExitCode = $LASTEXITCODE
    if ($RoboCopyExitCode -ge 8) {
        throw "Copying the files failed. Robocopy exit code: $RoboCopyExitCode"
    }

    Push-Location $PublishDirectory
    try {
        if (-not (git config user.name)) {
            git config user.name "hiski88"
        }
        if (-not (git config user.email)) {
            git config user.email "85390128+hiski88@users.noreply.github.com"
        }

        git add --all
        git diff --cached --quiet
        if ($LASTEXITCODE -eq 0) {
            Write-Host "No changes were found. The repository is already up to date."
        }
        else {
            git commit -m $CommitMessage
            if ($LASTEXITCODE -ne 0) {
                throw "Git commit failed."
            }

            git push origin $Branch
            if ($LASTEXITCODE -ne 0) {
                throw "Git push failed. Complete the GitHub sign-in window and run the script again."
            }
            Write-Host "The prototype was published successfully to GitHub."
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    if (Test-Path $PublishDirectory) {
        Remove-Item -Path $PublishDirectory -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Repository: https://github.com/hiski88/ShebaOncTool"
