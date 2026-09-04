$ErrorActionPreference = 'Stop'

function Test-OriginalEmptyLists {
    $Failures = New-Object -TypeName 'System.Collections.Generic.List[object]'
    $Checks = New-Object -TypeName 'System.Collections.Generic.List[object]'
    try {
        $Result = [ordered]@{
            failures = @($Failures)
            checks = @($Checks)
        }
        $null = $Result | ConvertTo-Json -Depth 4
        return 'ORIGINAL_EMPTY_NO_ERROR'
    }
    catch {
        return ('ORIGINAL_EMPTY_ERROR: ' + $_.Exception.GetType().FullName + ': ' + $_.Exception.Message)
    }
}

function Test-OriginalMixedLists {
    $Failures = New-Object -TypeName 'System.Collections.Generic.List[object]'
    $Checks = New-Object -TypeName 'System.Collections.Generic.List[object]'
    $Checks.Add([pscustomobject]@{ check='hash'; status='PASS' }) | Out-Null
    try {
        $Result = [ordered]@{
            failures = @($Failures)
            checks = @($Checks)
        }
        $null = $Result | ConvertTo-Json -Depth 4
        return 'ORIGINAL_MIXED_NO_ERROR'
    }
    catch {
        return ('ORIGINAL_MIXED_ERROR: ' + $_.Exception.GetType().FullName + ': ' + $_.Exception.Message)
    }
}

function Test-PatchedArrays {
    [object[]]$Failures = @()
    [object[]]$Checks = @()
    $Checks += [pscustomobject]@{ check='hash'; status='PASS' }
    $Result = [ordered]@{
        failures = $Failures
        checks = $Checks
    }
    $json = $Result | ConvertTo-Json -Depth 4
    if ($json -notmatch 'PASS') { throw 'patched JSON serialization failed' }
    return 'PATCHED_ARRAYS_PASS'
}

Write-Host (Test-OriginalEmptyLists)
Write-Host (Test-OriginalMixedLists)
Write-Host (Test-PatchedArrays)
