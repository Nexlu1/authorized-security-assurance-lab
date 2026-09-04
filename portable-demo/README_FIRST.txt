RIG WORKER LOCAL AI DEMO R1
===========================

WHAT THIS IS
------------
A portable Windows x64 demonstration of a local AI worker assembled from free/open-source components.

It uses:
- llama.cpp official Windows x64 CPU build b10621 / llama.cpp v0.3.0 release family (MIT licence)
- Qwen2.5-0.5B-Instruct GGUF Q4_K_M from the official Qwen Hugging Face repository (Apache-2.0 licence)

HOW TO USE IT
-------------
1. Extract this ZIP to a normal folder.
2. Double-click START_RIG_WORKER_DEMO.cmd
3. On the first run only, it downloads the official ~491 MB demo model and verifies its SHA-256.
4. When the server is ready, your browser opens automatically.
5. Chat with the local model in the browser.
6. Press ENTER in the black console window to stop it.

AFTER THE FIRST DOWNLOAD
------------------------
The AI server is started with llama.cpp offline mode and is bound to 127.0.0.1 only. It does not expose the demo server to your network.

NO INSTALLATION OR ACCOUNT
--------------------------
No Python installation, cloud AI account or paid service is required for this demo.

WHAT THIS DEMONSTRATES
----------------------
- a real local LLM running on Windows;
- a real browser chat interface served from the local machine;
- pinned open-source runtime provenance;
- a pinned, SHA-256-verified local model;
- local-only network binding;
- offline inference after the model has been downloaded.

LIMITATION
----------
The included model choice is deliberately small so the demo is easy to run. It is suitable for proving the local architecture works, not for judging the final Rig Worker model quality.

PINNED MODEL
------------
Repository: Qwen/Qwen2.5-0.5B-Instruct-GGUF
Revision: df5bf01389a39c743ab467d734bf501681e041c5
File: qwen2.5-0.5b-instruct-q4_k_m.gguf
SHA-256: 74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db

PINNED LLAMA.CPP BINARY RELEASE
-------------------------------
Release: b10621
Asset: llama-b10621-bin-win-cpu-x64.zip
Release asset SHA-256: 0e8b65e650e369f70f8307d890508886f171ef4fb00facccddd4a1b7ffdaca51

See LICENSES and SOURCE_PROVENANCE.txt inside this package for attribution and verification details.
