# Downstream change inventory

This inventory explains the maintained difference from upstream Arasan 26.0.
It should be updated whenever the integration branch changes.

| Area | Downstream change | Why it exists | Possible upstream value |
| --- | --- | --- | --- |
| Protocol input | Adds `Protocol::dispatchCommand` and an option to disable stdin polling | Lets an in-process host reuse Arasan's UCI parser and search-time command handling | High; general embedded use |
| Protocol output | Routes engine protocol output through a configurable stream that defaults to `std::cout` | Delivers complete UCI lines without replacing host stdout | High; general library integration |
| Lifecycle | Allows global initialization without desktop process stack configuration | Avoids mutating a containing mobile or browser process | High; general embedding safety |
| Lifecycle cleanup | Clears owned global pointers and NNUE initialization state | Supports deterministic teardown and later reinitialization | Medium; general robustness |
| C API | Adds the single-instance API in `src/embed` | Provides a stable primitive ABI for Swift, JNI/Dart FFI, and WASM | High; general embedding use |
| Embedded profile | Disables book, ECO, tablebases, learning, and game storage by default | Avoids undeclared files and writes in app sandboxes | Medium; profile is policy-sensitive |
| Native build | Adds static-library and smoke-test Make targets | Proves the common host before platform packaging | Medium |
| Embedded CMake | Adds a reusable embedded-library source target | Gives platform builds an explicit target without changing the upstream CLI target | High; general build reuse |
| Web portability | Disables stdin polling, process path discovery, process stack tuning, and extra search threads under Emscripten | Matches the single-threaded Worker runtime and browser sandbox | Medium; browser-specific policy |
| Optional tablebases | Guards CECP tablebase options when Syzygy is not compiled | Allows deliberately tablebase-free targets to link cleanly | High; generic optional-feature correctness |
| Web package | Adds Emscripten exports, raw UCI Worker glue, demo, smoke suite, manifest, and CI | Produces a reproducible browser integration artifact | Low; maintained downstream platform distribution |
| Apple portability | Avoids executable-path discovery in the sandboxed embedded Apple target | Makes the host-provided resource directory authoritative without changing macOS CLI behavior | Medium; useful for Apple embedding, but platform-policy specific |
| Apple package | Adds device/simulator CMake builds, XCFramework assembly, Swift module metadata, smoke app, manifest, and CI | Produces a reproducible iOS integration artifact | Low; maintained downstream platform distribution |
| Android portability | Uses `posix_memalign` where API 24 does not expose C++17 `aligned_alloc` | Preserves Arasan's required hash-table alignment on the declared Android floor | High; generic Android build correctness |
| Android package | Adds ARM64/x86_64 CMake builds, AAR assembly, Java/JNI lifecycle and resource hosting, smoke app, manifest, and CI | Produces a reproducible Android integration artifact | Low; maintained downstream platform distribution |
| Documentation | Adds fork, provenance, embedding, and delta documents | Makes source and artifacts reproducible | High |

No engine evaluation, search, or strength code is intentionally changed. No
upstream pull requests are being opened during the initial implementation.

Likely long-term downstream-only work includes signed release artifacts,
XCFramework/AAR packaging, JavaScript Worker glue, and consumer-specific release
automation. Generic lifecycle, portability, API, tests, and build fixes may be
reasonable upstream candidates later, but upstream acceptance is not required.
