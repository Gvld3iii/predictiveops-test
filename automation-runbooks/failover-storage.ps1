<#
.SYNOPSIS
  Triggers a geo-replicated Azure Storage Account failover
  (RA-GRS / GZRS → secondary region becomes primary).

.WARNING
  This is IRREVERSIBLE and should only be used in true outage scenarios
  or controlled demos.

.NOTES
  Intended to run as an Azure Automation Runbook using Managed Identity.
#>

param(
    [Parameter(Mandatory = $true)]
    [string] $SubscriptionId,

    [Parameter(Mandatory = $true)]
    [string] $ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string] $StorageAccountName,

    [Parameter(Mandatory = $false)]
    [switch] $ConfirmFailover
)

Write-Output "[FailoverStorage] Starting failover runbook for '$StorageAccountName' in RG '$ResourceGroupName'"

try {
    Connect-AzAccount -Identity -ErrorAction Stop
    Select-AzSubscription -SubscriptionId $SubscriptionId -ErrorAction Stop
    Write-Output "[FailoverStorage] Connected and subscription selected."
}
catch {
    Write-Error "[FailoverStorage] Auth / subscription error: $($_.Exception.Message)"
    throw
}

try {
    $account = Get-AzStorageAccount -ResourceGroupName $ResourceGroupName -Name $StorageAccountName -ErrorAction Stop
}
catch {
    Write-Error "[FailoverStorage] Storage account not found: $($_.Exception.Message)"
    throw
}

Write-Output "[FailoverStorage] Account kind: $($account.Kind), SKU: $($account.Sku.Name)"
Write-Output "[FailoverStorage] GeoReplication Stats: $($account.GeoReplicationStats) (if available)"

if (-not $ConfirmFailover.IsPresent) {
    Write-Warning "[FailoverStorage] ConfirmFailover switch NOT set. Exiting WITHOUT triggering failover."
    Write-Output "[FailoverStorage] To actually fail over, re-run with -ConfirmFailover."
    return
}

try {
    Write-Warning "[FailoverStorage] Initiating storage account failover for '$StorageAccountName'. This is irreversible."
    Invoke-AzStorageAccountFailover -ResourceGroupName $ResourceGroupName -Name $StorageAccountName -ErrorAction Stop
    Write-Output "[FailoverStorage] Failover requested. It may take time for DNS + replication to settle."
}
catch {
    Write-Error "[FailoverStorage] Failover failed: $($_.Exception.Message)"
    throw
}

Write-Output "[FailoverStorage] Runbook completed."
