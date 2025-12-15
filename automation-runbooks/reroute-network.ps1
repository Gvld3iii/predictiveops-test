<#
.SYNOPSIS
  Reroutes traffic between two Azure Traffic Manager endpoints
  (e.g., primary vs secondary region).

.DESCRIPTION
  Enables the target endpoint and disables the other, so all new
  traffic flows to the desired region / service.

.NOTES
  Intended to run as an Azure Automation Runbook using Managed Identity.
#>

param(
    [Parameter(Mandatory = $true)]
    [string] $SubscriptionId,

    [Parameter(Mandatory = $true)]
    [string] $ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string] $TrafficManagerProfileName,

    [Parameter(Mandatory = $true)]
    [string] $PrimaryEndpointName,

    [Parameter(Mandatory = $true)]
    [string] $SecondaryEndpointName,

    [Parameter(Mandatory = $true)]
    [ValidateSet("primary", "secondary")]
    [string] $RouteTo
)

Write-Output "[RerouteNetwork] Starting reroute for Traffic Manager profile '$TrafficManagerProfileName'. Target='$RouteTo'"

try {
    Connect-AzAccount -Identity -ErrorAction Stop
    Select-AzSubscription -SubscriptionId $SubscriptionId -ErrorAction Stop
    Write-Output "[RerouteNetwork] Connected and subscription selected."
}
catch {
    Write-Error "[RerouteNetwork] Auth / subscription error: $($_.Exception.Message)"
    throw
}

try {
    $profile = Get-AzTrafficManagerProfile `
        -Name $TrafficManagerProfileName `
        -ResourceGroupName $ResourceGroupName `
        -ErrorAction Stop
    Write-Output "[RerouteNetwork] Loaded Traffic Manager profile. RoutingMethod = $($profile.TrafficRoutingMethod)"
}
catch {
    Write-Error "[RerouteNetwork] Failed to load profile: $($_.Exception.Message)"
    throw
}

# Helper to get an endpoint
function Get-TmEndpoint {
    param(
        [string] $EndpointName
    )

    return Get-AzTrafficManagerEndpoint `
        -Name $EndpointName `
        -ProfileName $TrafficManagerProfileName `
        -ResourceGroupName $ResourceGroupName `
        -Type AzureEndpoints `
        -ErrorAction Stop
}

try {
    $primaryEp   = Get-TmEndpoint -EndpointName $PrimaryEndpointName
    $secondaryEp = Get-TmEndpoint -EndpointName $SecondaryEndpointName
}
catch {
    Write-Error "[RerouteNetwork] Failed to retrieve endpoints: $($_.Exception.Message)"
    throw
}

if ($RouteTo -eq "primary") {
    Write-Output "[RerouteNetwork] Routing to PRIMARY: enabling '$PrimaryEndpointName', disabling '$SecondaryEndpointName'"

    $primaryEp.EndpointStatus   = "Enabled"
    $secondaryEp.EndpointStatus = "Disabled"
}
else {
    Write-Output "[RerouteNetwork] Routing to SECONDARY: enabling '$SecondaryEndpointName', disabling '$PrimaryEndpointName'"

    $primaryEp.EndpointStatus   = "Disabled"
    $secondaryEp.EndpointStatus = "Enabled"
}

try {
    Set-AzTrafficManagerEndpoint -TrafficManagerEndpoint $primaryEp -ErrorAction Stop | Out-Null
    Set-AzTrafficManagerEndpoint -TrafficManagerEndpoint $secondaryEp -ErrorAction Stop | Out-Null

    Write-Output "[RerouteNetwork] Endpoint statuses updated successfully."
    Write-Output "[RerouteNetwork] Primary:   $($primaryEp.Name)   Status=$($primaryEp.EndpointStatus)"
    Write-Output "[RerouteNetwork] Secondary: $($secondaryEp.Name) Status=$($secondaryEp.EndpointStatus)"
}
catch {
    Write-Error "[RerouteNetwork] Failed to update endpoints: $($_.Exception.Message)"
    throw
}

Write-Output "[RerouteNetwork] Runbook completed."
