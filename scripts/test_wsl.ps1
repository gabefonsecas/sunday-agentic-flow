param(
    [string]$TestTarget = "discover -s tests -v"
)

$ErrorActionPreference = "Stop"
$distribution = "Ubuntu"

Write-Host "Installing an ephemeral Ubuntu distribution for the WSL 2 gate"
& wsl.exe --install --distribution $distribution --web-download --no-launch
if ($LASTEXITCODE -ne 0) {
    throw "Unable to install Ubuntu in the GitHub-hosted WSL environment"
}

$distributionList = ((& wsl.exe --list --verbose | Out-String) -replace "`0", "")
Write-Host $distributionList
if ($distributionList -notmatch "Ubuntu\s+(?:Stopped|Running)\s+2") {
    throw "Ubuntu was not installed as a WSL 2 distribution"
}

$linuxPath = (& wsl.exe --distribution $distribution -- wslpath -a $env:GITHUB_WORKSPACE).Trim()
if (-not $linuxPath) {
    throw "Unable to resolve the GitHub workspace inside WSL 2"
}

$command = "cd '$linuxPath' && python3 -m unittest $TestTarget"
& wsl.exe --distribution $distribution -- bash -lc $command
if ($LASTEXITCODE -ne 0) {
    throw "Sunday tests failed inside WSL 2"
}
