param(
    [Parameter(Mandatory = $true)]
    [string] $ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string] $AppServiceName
)

Write-Output "[PredictiveOps] Restarting App Service '$AppServiceName' in RG '$ResourceGroupName'..."

# Ensure Az module is available
if (-not (Get-Module -ListAvailable -Name Az.Accounts)) {
    Write-Output "[PredictiveOps] Importing Az modules..."
    Import-Module Az.Accounts -ErrorAction Stop
    Import-Module Az.Websites -ErrorAction Stop
}

# Use the managed identity / automation connection for auth in real Azure
try {
    Write-Output "[PredictiveOps] Connecting to Azure (Run As / Managed Identity context)..."
    Connect-AzAccount -Identity | Out-Null
}
catch {
    Write-Warning "[PredictiveOps] Failed to authenticate with managed identity: $($_.Exception.Message)"
    throw
}

try {
    Write-Output "[PredictiveOps] Issuing restart command..."
    Restart-AzWebApp -Name $AppServiceName -ResourceGroupName $ResourceGroupName -ErrorAction Stop

    Write-Output "[PredictiveOps] Restart command submitted successfully."
}
catch {
    Write-Error "[PredictiveOps] Failed to restart App Service: $($_.Exception.Message)"
    throw
}
