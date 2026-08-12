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

$workspace = $env:GITHUB_WORKSPACE
if ($workspace -notmatch '^(?<drive>[A-Za-z]):\\(?<path>.+)$') {
    throw "Unable to parse the GitHub workspace path: $workspace"
}
$drive = $Matches["drive"].ToLowerInvariant()
$relativePath = $Matches["path"].Replace('\', '/')
$linuxPath = "/mnt/$drive/$relativePath"

$command = @"
set -e
cd '$linuxPath'
if ! command -v python3.11 >/dev/null 2>&1; then
  if ! command -v curl >/dev/null 2>&1; then
    apt-get update
    apt-get install -y ca-certificates curl
  fi
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="`$HOME/.local/bin:`$PATH"
  uv python install 3.11
fi
python3.11 -m unittest $TestTarget
"@
$command = $command.Replace("`r`n", "`n").Trim()
& wsl.exe --distribution $distribution -- bash -lc $command
if ($LASTEXITCODE -ne 0) {
    throw "Sunday tests failed inside WSL 2"
}
