# Embedding Arasan

The embedded host preserves UCI as the application boundary. It accepts one UCI
command at a time and delivers every engine response as a complete line through
a C callback. It does not redirect process stdin or stdout and does not modify
the host process's signal handlers or stack limit.

## C interface

The public header is `src/embed/arasan_embed.h`:

```c
typedef void (*arasan_output_callback)(const char *line, void *context);

int arasan_embed_initialize(
    const char *resource_root,
    arasan_output_callback output,
    void *context
);
int arasan_embed_send(const char *uci_command);
int arasan_embed_is_ready(void);
int arasan_embed_is_searching(void);
void arasan_embed_shutdown(void);
```

The first API version intentionally supports one engine instance per process.
The output line is valid only during its callback. Host code should serialize
ordinary commands. A bounded `go` call is synchronous; a second host thread may
submit `stop` during a search. Do not call shutdown from inside the callback.

`resource_root` must be an explicit directory containing the NNUE file recorded
in [PROVENANCE.md](PROVENANCE.md). Embedded initialization does not search the
executable directory or the user's home directory.

Embedded defaults are deliberately conservative:

- one search thread;
- opening-book play and ECO loading disabled by default;
- Syzygy tablebases disabled at runtime;
- position learning disabled; and
- game storage disabled.

Consumers can change supported engine options with normal UCI `setoption`
commands after initialization. The explicit resource root also supplies the
packaged `book.bin`; `setoption name OwnBook value true` enables book play, and
the existing `bk` command lists book moves for the current position.

## WebAssembly host

The web target compiles the same C API and places a raw UCI adapter around it in
a Web Worker. Worker input and output are plain JavaScript strings. See
[WASM.md](WASM.md) for the build, artifact contract, browser test, and required
restart-based cancellation behavior.

## Apple host

The Apple target packages the common C interface as a static XCFramework with
arm64 device and arm64/x86_64 simulator slices. Its public module imports
directly into Swift as `ArasanEngine`. The network is a separate, checksummed
application resource, and the host passes its bundle resource directory to
initialization. See [APPLE.md](APPLE.md) for the build, artifact layout, Swift
acceptance application, and integration contract.

## Android host

The Android target packages the common C interface into a shared library and
wraps it with the small Java `org.arasanchess.sdk.ArasanEngine` API. The AAR
contains ARM64 device and x86_64 emulator libraries. Its Java host verifies and
copies the packaged network to app-private storage before initialization. See
[ANDROID.md](ANDROID.md) for the build, artifact layout, emulator acceptance
application, and integration contract.

## Native build and smoke test

Initialize the required Syzygy source submodule, then build the command-line and
embedded targets. On Apple Silicon:

```sh
git submodule update --init src/syzygy
make -C src clean
make -C src BUILD_TYPE=neon
make -C src BUILD_TYPE=neon embedded-smoke
./bin/arasan-embed-smoke network
```

The smoke test verifies this sequence:

1. initialize from an explicit resource root;
2. `uci` through `uciok`;
3. `isready` through `readyok`;
4. load a FEN;
5. perform `go movetime 100`;
6. receive a legal `bestmove`; and
7. interrupt `go infinite` from another host thread;
8. send `quit` and shut down cleanly.

The outputs are `bin/libarasan_embed.a` and `bin/arasan-embed-smoke`. These are
local proof artifacts, not consumer releases.

## Current limitations

- The Apple device slice is compiled in CI, while physical-device execution
  remains a release-validation step requiring a signed host application.
- The Android ARM64 library is compiled in CI, while physical-device execution
  remains a release-validation step requiring a consumer application.
- The Makefile does not generate header dependencies, so use a clean build after
  changing a public header or build configuration.
- The WebAssembly, Apple, and Android packages are integration artifacts, not
  yet signed releases.
- This first host has a single global engine because Arasan itself has global
  engine state.
