# Isolated FOSS build qualification

Passive donor intake and build qualification are separate stages.

The passive stage downloads and scans exact source without executing donor code. This stage is only for candidates that survived that review and are worth compiling/testing.

## Boundaries

- Exact public GitHub commit only.
- No secrets are provided to donor code.
- No push/write credentials or third-party repository write operations.
- The donor Git remote is removed immediately after exact-source acquisition.
- Only same-repository PRs or explicit manual runs may execute the qualification jobs.
- Build/test network access may be used where the upstream build itself restores or fetches public dependencies.
- Compiled donor binaries are **not uploaded**. The workflow records hashes/names and test outcomes only.
- A passing donor build does not approve integration into ECO, KOMB or Rig Worker. Target-project integration remains a separate review.

## Batch 1

### llama.cpp Windows Manager

Use the exact upstream Windows CI sequence through vulnerability checking:

1. code-shape check;
2. `.NET 10.0.400` from upstream `global.json`;
3. locked restore/build;
4. tests and coverage;
5. format verification;
6. documentation checks;
7. package vulnerability/currency audit.

Do not publish the application or build/test its installer in this qualification.

### llama.cpp Windows CPU/server

Use the upstream Windows `x64-cpu-static` CMake configuration:

- Windows Server 2025;
- Ninja Multi-Config;
- upstream LLVM x64 Windows toolchain;
- `GGML_NATIVE=OFF`;
- upstream fetched LLVM OpenMP with SHA-256 verification;
- `LLAMA_BUILD_SERVER=ON`;
- `GGML_RPC=ON`;
- static libraries;
- BoringSSL enabled as in upstream Windows CI;
- Release build;
- `ctest -L main -C Release`.

Do not download a model, run inference, package a release, or publish binaries in this stage.
