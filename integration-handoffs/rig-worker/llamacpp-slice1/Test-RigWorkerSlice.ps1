[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifestPath = Join-Path $root 'INTEGRATION.json'
$buildPath = Join-Path $root 'Build-RigWorkerLlamaCpp.ps1'
$managePath = Join-Path $root 'Manage-RigWorkerLlamaServer.ps1'
$expectedSha = '0ef4d560e12c1a46470265c1abd31dd47c777d23'

function Assert-True {
    param(
        [Parameter(Mandatory = $true)][bool]$Condition,
        [Parameter(Mandatory = $true)][string]$Message
    )
    if (-not $Condition) {
        throw $Message
    }
}

function Assert-NoParseErrors {
    param([Parameter(Mandatory = $true)][string]$Path)

    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors) | Out-Null
    if ($errors.Count -gt 0) {
        $details = ($errors | ForEach-Object { $_.Message }) -join '; '
        throw "PowerShell syntax errors in ${Path}: $details"
    }
}

foreach ($path in @($buildPath, $managePath, $MyInvocation.MyCommand.Path)) {
    Assert-True (Test-Path -LiteralPath $path -PathType Leaf) "Required script is missing: $path"
    Assert-NoParseErrors $path
}
Assert-True (Test-Path -LiteralPath $manifestPath -PathType Leaf) "Integration manifest is missing: $manifestPath"

$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
Assert-True ($manifest.schema_version -eq 1) 'Unexpected integration manifest schema.'
Assert-True ($manifest.target_project -eq 'Rig Worker') 'Integration target drifted away from Rig Worker.'
Assert-True ($manifest.integration_mode -eq 'external supervised engine') 'Integration mode changed unexpectedly.'
Assert-True ($manifest.donor.repository -eq 'ggml-org/llama.cpp') 'Donor repository changed unexpectedly.'
Assert-True ($manifest.donor.commit_sha -eq $expectedSha) 'Qualified llama.cpp commit changed without requalification.'
Assert-True ($manifest.donor.license -eq 'MIT') 'Donor licence record changed unexpectedly.'
Assert-True ($manifest.qualification.status -eq 'PASS') 'Donor no longer records a PASS qualification.'
Assert-True ($manifest.runtime_policy.bind_host -eq '127.0.0.1') 'Runtime must remain loopback-only in Slice 1.'
Assert-True ($manifest.runtime_policy.offline_runtime -eq $true) 'Runtime must remain offline in Slice 1.'
Assert-True ($manifest.runtime_policy.web_ui -eq $false) 'Web UI must remain disabled in Slice 1.'
Assert-True ($manifest.runtime_policy.automatic_model_download -eq $false) 'Automatic model downloads are forbidden in Slice 1.'
Assert-True ($manifest.boundaries.api_key_is_not_written_to_disk -eq $true) 'API key disk boundary changed.'
Assert-True ($manifest.boundaries.api_key_is_not_put_on_process_command_line -eq $true) 'API key command-line boundary changed.'
Assert-True ($manifest.boundaries.pid_is_verified_against_executable_before_stop -eq $true) 'PID/executable verification boundary changed.'

$buildSource = Get-Content -LiteralPath $buildPath -Raw -Encoding utf8
$manageSource = Get-Content -LiteralPath $managePath -Raw -Encoding utf8

Assert-True ($buildSource.Contains($expectedSha)) 'Build script is not pinned to the qualified donor SHA.'
Assert-True ($buildSource.Contains('GGML_NATIVE=OFF')) 'Qualified GGML_NATIVE build setting is missing.'
Assert-True ($buildSource.Contains('GGML_OPENMP_FETCH=ON')) 'Qualified OpenMP build setting is missing.'
Assert-True ($buildSource.Contains('LLAMA_BUILD_SERVER=ON')) 'llama-server build setting is missing.'
Assert-True ($buildSource.Contains('BUILD_SHARED_LIBS=OFF')) 'Qualified static-build setting is missing.'
Assert-True ($buildSource.Contains('LLAMA_BUILD_BORINGSSL=ON')) 'Qualified BoringSSL build setting is missing.'
Assert-True ($buildSource.Contains('remote remove origin')) 'Donor Git remote removal control is missing.'
Assert-True ($buildSource.Contains('RIG_WORKER_LLAMA_SOURCE.json')) 'Owned-source marker control is missing.'

Assert-True ($manageSource.Contains("'--host', '127.0.0.1'")) 'Server launcher is not explicitly loopback-only.'
Assert-True ($manageSource.Contains("'--offline'")) 'Server launcher is not explicitly offline.'
Assert-True ($manageSource.Contains("'--no-webui'")) 'Server launcher does not explicitly disable the upstream Web UI.'
Assert-True ($manageSource.Contains("'--cors-origins', 'localhost'")) 'Server launcher does not restrict CORS to localhost.'
Assert-True ($manageSource.Contains('RIG_WORKER_API_KEY')) 'Rig Worker API key input is missing.'
Assert-True ($manageSource.Contains('LLAMA_API_KEY')) 'Child environment authentication binding is missing.'
Assert-True (-not $manageSource.Contains("'--api-key'")) 'API key must not be passed on the child process command line.'
Assert-True (-not $manageSource.Contains('--api-key-file')) 'Slice 1 must not write/read an API-key file.'
Assert-True (-not $manageSource.Contains('--model-url')) 'Slice 1 must not enable URL model downloads.'
Assert-True (-not $manageSource.Contains('--hf-repo')) 'Slice 1 must not enable Hugging Face model downloads.'
Assert-True ($manageSource.Contains('Get-VerifiedStateProcess')) 'Verified PID/executable management control is missing.'
Assert-True ($manageSource.Contains('Refusing to manage it')) 'PID-reuse refusal path is missing.'
Assert-True ($manageSource.Contains("[System.IO.Path]::GetExtension(`$resolvedModel) -ne '.gguf'")) 'Local GGUF-only input guard is missing.'

Write-Host 'Rig Worker llama.cpp Slice 1 static safety checks passed.'
