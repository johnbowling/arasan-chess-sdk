# Apple SDK

The Apple target packages Arasan as a static XCFramework for embedding in iOS
applications. The initial support floor is iOS 16.0. It contains an arm64
device slice and arm64 plus x86_64 simulator slices by default.

## Requirements

- macOS with Xcode and the iOS SDK
- CMake 3.20 or newer
- Ninja
- Node.js

Build from the repository root:

```sh
./platforms/apple/build.sh
```

With an iOS simulator booted, exercise the packaged XCFramework from the
included Swift application:

```sh
./platforms/apple/build-smoke.sh
./platforms/apple/run-smoke.sh
```

The smoke application imports the packaged C module from Swift and validates
UCI startup, a three-line MultiPV search, cancellation of an infinite search,
opening-book lookup, shutdown, reinitialization, and a second bounded search.

On Apple Silicon, set `ARASAN_APPLE_X86_64_SIMULATOR=0` to omit the Intel
simulator slice. Set `ARASAN_IOS_DEPLOYMENT_TARGET` to raise (but not lower)
the deployment target.

The package is written to `dist/apple`:

- `Arasan.xcframework` is the static library and public C header.
- `resources/arasan.nnue` is the required network resource.
- `resources/book.bin` is the required opening-book resource.
- `manifest.json` records source/toolchain provenance and SHA-256 checksums.
- `LICENSE` and `PROVENANCE.md` carry redistribution information.

The engine version, upstream source revision, and required network filename are
read from `sdk/upstream.json`. The automated stable-release updater changes that
single baseline before rebuilding and validating this package.

## Host integration

1. Add `Arasan.xcframework` to the application target.
2. Copy `resources/arasan.nnue` and `resources/book.bin` into the application
   bundle without renaming them.
3. Use `import ArasanEngine` in Swift, or include `arasan_embed.h` from
   Objective-C/Objective-C++.
4. Ensure the application links the C++ standard library (`libc++` / `-lc++`).
5. Pass the bundle resource directory to `arasan_embed_initialize`.
6. Exchange normal UCI commands through `arasan_embed_send` and consume
   complete UCI output lines through the callback.
7. Call `arasan_embed_shutdown` before discarding the host integration.

Book play is off by default. Send `setoption name OwnBook value true` to use it
for engine moves, or send `bk` after setting a position to list the available
book moves.

There is one process-wide engine instance. A bounded `go` command runs
synchronously, so invoke it away from the main thread. A second host thread may
send `stop` while a search is active. Do not call shutdown from inside the
output callback. Output may arrive on an engine/search thread; dispatch UI work
to the main actor and make callback state thread-safe.

The Apple build deliberately does not infer an executable or application
bundle path. The explicit resource directory is the stable mobile embedding
contract and keeps filesystem policy in the host application.
