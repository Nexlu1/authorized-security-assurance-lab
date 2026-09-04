# Rig Worker llama.cpp Slice 1

This is the first integration-ready Rig Worker slice built from a qualified free/open-source donor rather than from scratch.

## What is being reused

The inference engine remains the upstream MIT-licensed `ggml-org/llama.cpp` project at exact commit:

`0ef4d560e12c1a46470265c1abd31dd47c777d23`

That exact revision was independently configured, compiled and tested on a GitHub Windows 2025 runner before this integration slice was written. The qualified Windows x64 CPU/server build completed successfully and the upstream `main` CTest suite passed.

We deliberately do **not** vendor thousands of llama.cpp source files into this repository. The integration keeps llama.cpp as an exact, externally supervised engine and adds only the Rig Worker glue we need. This reduces duplicated code and future maintenance while preserving exact provenance.

## Slice 1 scope

Included:

- exact-SHA llama.cpp source acquisition;
- refusal to build reused donor source if Git reports tracked, staged, extra untracked, or ignored worktree changes;
- Windows x64 CPU/static `llama-server` + `llama-cli` build using the already-qualified configuration;
- upstream `main` CTest execution by default;
- local build receipt with SHA-256 hashes;
- localhost-only server launch;
- API-key authentication through the child environment, not a command-line argument;
- process launch through a real argument vector so paths containing spaces remain intact;
- offline runtime mode;
- Web UI disabled;
- localhost-only CORS;
- PID/log/state tracking;
- verified executable-path check before stopping a recorded PID;
- no automatic model download.

Not included yet:

- CUDA/Vulkan/other GPU build qualification;
- automatic GGUF acquisition;
- model catalogue/downloader;
- multi-model orchestration;
- service installation;
- final Rig Worker GUI;
- movement into a dedicated Rig Worker repository.

Those are later slices and should reuse qualified FOSS components rather than be recreated blindly.

## Prerequisites

Windows x64 with these tools available in `PATH`:

- Git
- CMake
- Ninja
- LLVM/Clang
- CTest

The build stage needs network access to fetch the exact public llama.cpp commit and upstream build dependencies such as the SHA-256-verified LLVM OpenMP runtime. The runtime stage is started with llama.cpp `--offline` and does not download a model.

## Build

From this directory:

```powershell
.\Build-RigWorkerLlamaCpp.ps1 -Workspace 'D:\RigWorker'
```

To rebuild only the known build directory:

```powershell
.\Build-RigWorkerLlamaCpp.ps1 -Workspace 'D:\RigWorker' -CleanBuild
```

The script refuses to reuse an existing `llama.cpp-source` directory unless it contains a valid Rig Worker ownership marker, is still on the exact pinned commit, has no Git remote, and has no worktree differences except that marker. It does not silently reset or discard local files.

The local receipt is written to:

`D:\RigWorker\build-receipt.json`

Local executable hashes are recorded there. They are not required to equal the reference CI hashes because compiler and build-environment differences can legitimately change binary bytes.

## Prepare an API key

Generate a strong key in the current PowerShell process without typing a literal secret into the command history:

```powershell
$env:RIG_WORKER_API_KEY = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant()
```

The controller places that value directly into the new child process environment as `LLAMA_API_KEY`. It does not modify the parent process's `LLAMA_API_KEY`, write the key into the runtime state file, or place the key on the child command line.

## Start

You must already have a local `.gguf` model:

```powershell
.\Manage-RigWorkerLlamaServer.ps1 `
  -Action Start `
  -Workspace 'D:\RigWorker' `
  -ModelPath 'F:\Models\example.gguf' `
  -Port 8080
```

Slice 1 starts `llama-server` with:

- `--host 127.0.0.1`
- `--offline`
- `--no-webui`
- `--cors-origins localhost`
- authentication through child-environment `LLAMA_API_KEY`

The process is launched with `System.Diagnostics.ProcessStartInfo.ArgumentList`, so model and log paths remain single arguments even when they contain spaces.

No GPU backend or GPU-layer count is forced in this slice.

## Status

```powershell
.\Manage-RigWorkerLlamaServer.ps1 -Action Status -Workspace 'D:\RigWorker'
```

Status is returned as JSON. A recorded PID is considered manageable only if the live process executable path still matches the path stored when the server was launched.

## Stop

```powershell
.\Manage-RigWorkerLlamaServer.ps1 -Action Stop -Workspace 'D:\RigWorker'
```

The controller refuses to stop a PID that now belongs to a different executable.

## Runtime files

Under `<Workspace>\runtime`:

- `llama-server-state.json` — PID, paths, hashes and launch metadata; no API key;
- `llama-server.log` — upstream server log;
- `last-stop.json` — stop receipt.

## Current disposition

This slice is staged in the FOSS control repository because there is not yet a dedicated Rig Worker GitHub repository available through the connected account. It is intentionally isolated from ECO, KOMB, Daybreak, MCR and other unrelated repositories. Once a dedicated Rig Worker repository exists, this directory can be moved as one controlled handoff rather than reconstructed from chat history.
