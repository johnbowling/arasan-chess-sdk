# Arasan embedding fork

`arasan-chess-sdk` is a neutral integration fork of
[`jdart1/arasan-chess`](https://github.com/jdart1/arasan-chess). Its purpose is
to make Arasan straightforward to embed in applications on Apple platforms,
Android, and the web without coupling the engine to any one product or UI.

The engine, its name, and its original documentation remain Arasan's. This fork
does not currently change evaluation, search, playing strength, or UCI
semantics.

## Branch and release policy

- `main` is the maintained downstream SDK line. Its current engine baseline is
  the exact upstream `v26.0` source commit recorded in provenance.
- Short-lived branches such as `platform/wasm-v26.0` isolate reviewable SDK
  increments before they merge into `main`.
- Consumer releases will use immutable downstream tags such as
  `v26.0-embed.1`, with checksums and build metadata.
- The canonical upstream remote is `https://github.com/jdart1/arasan-chess.git`.
- Upstream development is observed through the local `upstream/master` remote
  tracking reference. The fork does not publish a redundant mirror branch.

No upstream pull requests are planned during the initial implementation. Work
is kept product-neutral and separated into reviewable changes so that generally
useful pieces can be considered for upstream later without making that a
dependency of delivery.

## Current scope

The maintained SDK currently provides:

- provenance for the upstream source and NNUE network;
- a small, line-oriented C API around Arasan's existing UCI implementation;
- explicit embedded resource paths and conservative embedded defaults;
- a native static-library build and smoke test;
- a single-threaded, SIMD WebAssembly build with a raw UCI Worker host;
- an iOS XCFramework for arm64 devices and arm64/x86_64 simulators;
- a Swift simulator acceptance application for the packaged Apple artifact;
- an Android AAR for arm64-v8a devices and x86_64 emulators;
- a Java/JNI host with verified private NNUE extraction and emulator acceptance; and
- unchanged command-line engine behavior.

See [doc/EMBEDDING.md](doc/EMBEDDING.md), [doc/APPLE.md](doc/APPLE.md),
[doc/ANDROID.md](doc/ANDROID.md), [doc/WASM.md](doc/WASM.md), and
[doc/UPSTREAM-DELTA.md](doc/UPSTREAM-DELTA.md).
Stable upstream updates are handled by the lightweight process in
[doc/UPSTREAM-UPDATES.md](doc/UPSTREAM-UPDATES.md). Unified, non-publishing
release candidates are documented in [doc/RELEASES.md](doc/RELEASES.md).
