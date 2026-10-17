param([Parameter(Mandatory=$true)][string]$Image)
$ErrorActionPreference='Stop'
# Load only CLI credentials; never execute or print the dotenv file.
$configPath = Join-Path (Split-Path $PSScriptRoot -Parent) '.env'
if (Test-Path -LiteralPath $configPath) {
    foreach ($line in Get-Content -LiteralPath $configPath) {
        if ($line -match '^\s*(AF_TOKEN|AF_PROJECT_ID)\s*=\s*(.*?)\s*$') {
            $key = $Matches[1]
            $value = $Matches[2]
            if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            if (![Environment]::GetEnvironmentVariable($key, 'Process')) {
                [Environment]::SetEnvironmentVariable($key, $value, 'Process')
            }
        }
    }
}
if ($Image -match ':(latest|main)$' -or $Image -notmatch ':') { throw 'Use a public immutable image tag, e.g. ghcr.io/your-team/claimbreaker:release-commit' }
if (!(Get-Command acc -ErrorAction SilentlyContinue)) { throw 'Install @alternatefutures/acc, authenticate, and select your project. See docs/DEPLOYMENT.md.' }
& acc whoami
if ($LASTEXITCODE -ne 0) { throw 'Authenticate the CLI first with acc login, or configure AF_TOKEN and AF_PROJECT_ID privately.' }
& acc services create --kind docker --image $Image --port 8000 --name claimbreaker -y
if ($LASTEXITCODE -ne 0) { throw 'Alternate Clouds rejected the deployment. Inspect the CLI error above.' }
& acc services list
