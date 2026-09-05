$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$source = Join-Path $PSScriptRoot 'build-package.ps1'
$runtime = Join-Path $PSScriptRoot 'build-package-runtime-v3.ps1'
$text = [IO.File]::ReadAllText($source)

$startMarker = '$adversarial = Join-Path $root ''tests\adversarial.rs'''
$endMarker = 'Push-Location $root'
$start = $text.IndexOf($startMarker, [StringComparison]::Ordinal)
if ($start -lt 0) { throw 'Could not find adversarial patch block start.' }
$end = $text.IndexOf($endMarker, $start, [StringComparison]::Ordinal)
if ($end -lt 0) { throw 'Could not find adversarial patch block end.' }

$replacement = @'
$adversarial = Join-Path $root 'tests\adversarial.rs'
$adversarialBefore = Get-Sha256Lower -Path $adversarial
$testText = [IO.File]::ReadAllText($adversarial)
$testNewLine = if ($testText.Contains("`r`n")) { "`r`n" } else { "`n" }
$allow = '#![allow(clippy::field_reassign_with_default)]'
$allowCount = ([regex]::Matches($testText, [regex]::Escape($allow))).Count
if ($allowCount -ne 0) { throw "Expected the original test source to contain no field_reassign_with_default allowance; found $allowCount" }
$testText = $allow + $testNewLine + $testText
[IO.File]::WriteAllText($adversarial, $testText, [Text.UTF8Encoding]::new($false))
$adversarialAfter = Get-Sha256Lower -Path $adversarial
$patches += [pscustomobject]@{
    file = 'tests/adversarial.rs'
    purpose = 'Add one test-only Clippy allowance because these five hostile-policy tests intentionally mutate selected fields after ScanPolicy::default(); runtime behavior is unchanged.'
    occurrences = 1
    before_sha256 = $adversarialBefore
    after_targeted_patch_sha256 = $adversarialAfter
}

Push-Location $root
'@

$patched = $text.Substring(0, $start) + $replacement + $text.Substring($end + $endMarker.Length)
[IO.File]::WriteAllText($runtime, $patched, [Text.UTF8Encoding]::new($false))

& $runtime
