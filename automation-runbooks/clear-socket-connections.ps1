<#
.SYNOPSIS
  Clears sticky / hung socket connections for an Azure Web App
  by doing a controlled restart (optionally on a specific slot).

.NOTES
  Intended to run as an Azure Automation Runbook using Managed Identity.
#>

param(
    [Parameter(Mandatory = $true)]
    [string] $SubscriptionId,

    [Parameter(Mandatory = $true)]
    [string] $ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string] $WebAppName,

    [Parameter(Mandatory = $false)]
    [string] $Slot
)

Write-Output "[ClearSockets] Starting runbook for $WebAppName (slot='$Slot') in RG '$ResourceGroupName'"

try {
    # In Azure Automation, this should use the system-assigned managed identity
    Connect-AzAccount -Identity -ErrorAction Stop
    Select-AzSubscription -SubscriptionId $SubscriptionId -ErrorAction Stop
    Write-Output "[ClearSockets] Connected with managed identity and selected subscription $SubscriptionId"
}
catch {
    Write-Error "[ClearSockets] Failed to authenticate or select subscription: $($_.Exception.Message)"
    throw
}

try {
    if ([string]::IsNullOrWhiteSpace($Slot)) {
        Write-Output "[ClearSockets] Restarting Web App '$WebAppName' (no slot)..."
        Restart-AzWebApp -Name $WebAppName -ResourceGroupName $ResourceGroupName -ErrorAction Stop
    }
    else {
        Write-Output "[ClearSockets] Restarting Web App '$WebAppName' slot '$Slot'..."
        Restart-AzWebApp -Name $WebAppName -ResourceGroupName $ResourceGroupName -Slot $Slot -ErrorAction Stop
    }

    Write-Output "[ClearSockets] Restart requested successfully. Existing socket connections will be dropped and re-established."
}
catch {
    Write-Error "[ClearSockets] Failed to restart web app: $($_.Exception.Message)"
    throw
}

Write-Output "[ClearSockets] Runbook completed."
