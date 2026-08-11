$ErrorActionPreference = "Stop"

$botRoot = "D:\Proyectos\discord-wow-dungeon-matchmaking"
$websiteRoot = "D:\Proyectos\WIP-hub\raid-report-hub"

$websiteUrl = "http://localhost:3000"
$raidSignupsApiUrl = "http://localhost:3000/api/raid-signups"
$dashboardUrl = "http://127.0.0.1:8081"

function Stop-ExistingLocalProcesses {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -like "*local-dev-with-api.mjs*" -or
            $_.CommandLine -like "*main.py*" -or
            $_.CommandLine -like "*npm run dev:api*" -or
            $_.CommandLine -like "*vercel dev --listen 3000*"
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
}

function Start-WebsiteApi {
    Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList "/c npm run dev:api > local-dev-api.log 2> local-dev-api.err.log" `
        -WorkingDirectory $websiteRoot `
        -WindowStyle Hidden
}

function Start-WipyBot {
    Start-Process `
        -FilePath "python" `
        -ArgumentList "main.py" `
        -WorkingDirectory $botRoot `
        -RedirectStandardOutput "$botRoot\bot-local.log" `
        -RedirectStandardError "$botRoot\bot-local.err.log" `
        -WindowStyle Hidden
}

function Wait-ForUrl($url, $headers = @{}) {
    for ($attempt = 1; $attempt -le 20; $attempt++) {
        try {
            Invoke-WebRequest -Uri $url -Headers $headers -UseBasicParsing -TimeoutSec 2 | Out-Null
            return $true
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    return $false
}

Write-Host "Stopping existing local bot/API processes..."
Stop-ExistingLocalProcesses

Write-Host "Starting website/API..."
Start-WebsiteApi

$apiReady = Wait-ForUrl $raidSignupsApiUrl @{ "x-api-key" = "local-dev-secret" }
if (-not $apiReady) {
    Write-Warning "Website API did not respond yet. Check $websiteRoot\local-dev-api.err.log"
}

Write-Host "Starting WipyBot..."
Start-WipyBot

Start-Sleep -Seconds 5

Write-Host ""
Write-Host "Local services started:"
Write-Host "Website:      $websiteUrl"
Write-Host "Raid API:     $raidSignupsApiUrl"
Write-Host "Bot dashboard:$dashboardUrl"
Write-Host ""
Write-Host "Logs:"
Write-Host "Website: $websiteRoot\local-dev-api.log"
Write-Host "Bot:     $botRoot\bot-local.log"
