from pathlib import Path
import hashlib
import sys

path = Path(sys.argv[1])
raw = path.read_bytes()
expected_before = "41be563b28963198547e674aafad2aad42d9d4e81f6661375721bf75361d6793"
expected_after = "3a6c5bbe0f987112a80ee78b3db5a76c72fa1a60019f17d8fe37816f616cf8eb"

actual_before = hashlib.sha256(raw).hexdigest()
if actual_before != expected_before:
    raise SystemExit(f"unexpected runner input SHA-256: {actual_before}")

old1 = (
    b"    $proc = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -Wait -PassThru -NoNewWindow -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath\r\n"
    b"    return [int]$proc.ExitCode\r\n"
)
new1 = (
    b"    $startParams = @{\r\n"
    b"        FilePath = $FilePath\r\n"
    b"        Wait = $true\r\n"
    b"        PassThru = $true\r\n"
    b"        NoNewWindow = $true\r\n"
    b"        RedirectStandardOutput = $StdoutPath\r\n"
    b"        RedirectStandardError = $StderrPath\r\n"
    b"    }\r\n"
    b"    if ($null -ne $ArgumentList -and $ArgumentList.Count -gt 0) {\r\n"
    b"        $startParams['ArgumentList'] = $ArgumentList\r\n"
    b"    }\r\n"
    b"    $proc = Start-Process @startParams\r\n"
    b"    return [int]$proc.ExitCode\r\n"
)
old2 = (
    b"        if (-not ((Get-Content -LiteralPath $stdout -Raw).Contains('runner-self-test'))) { throw 'Native capture output self-test failed' }\r\n"
    b"        $resultDir = Join-Path $tmp 'results'\r\n"
)
new2 = (
    b"        if (-not ((Get-Content -LiteralPath $stdout -Raw).Contains('runner-self-test'))) { throw 'Native capture output self-test failed' }\r\n"
    b"\r\n"
    b"        # Exercise the zero-argument branch used by the mcr-ingest smoke test.\r\n"
    b"        $whoami = Join-Path $env:SystemRoot 'System32\\whoami.exe'\r\n"
    b"        $stdout0 = Join-Path $tmp 'native-zero-args.out.txt'\r\n"
    b"        $stderr0 = Join-Path $tmp 'native-zero-args.err.txt'\r\n"
    b"        $exitCode0 = Invoke-NativeCapture -FilePath $whoami -ArgumentList @() -StdoutPath $stdout0 -StderrPath $stderr0\r\n"
    b"        if ($exitCode0 -ne 0) { throw \"Zero-argument native capture self-test failed: $exitCode0\" }\r\n"
    b"        if ([string]::IsNullOrWhiteSpace((Get-Content -LiteralPath $stdout0 -Raw))) { throw 'Zero-argument native capture output self-test failed' }\r\n"
    b"\r\n"
    b"        $resultDir = Join-Path $tmp 'results'\r\n"
)

if raw.count(old1) != 1 or raw.count(old2) != 1:
    raise SystemExit("expected runner repair targets were not found exactly once")

raw = raw.replace(old1, new1).replace(old2, new2)
actual_after = hashlib.sha256(raw).hexdigest()
if actual_after != expected_after:
    raise SystemExit(f"unexpected patched runner SHA-256: {actual_after}")

path.write_bytes(raw)
print(f"PASS patched runner SHA-256 {actual_after}")
