# Android SDK

The Android target packages the common embedded Arasan host as an AAR. It
supports Android API 24 or newer and contains native libraries for
`arm64-v8a` devices and `x86_64` emulators.

## Artifact contract

`dist/android/arasan-chess-sdk-android.aar` contains:

- `org.arasanchess.sdk.ArasanEngine`, a small Java API that preserves UCI as
  the application boundary;
- `libarasan_android.so` for `arm64-v8a` and `x86_64`;
- `assets/arasan/arasan.nnue`, the required checksummed evaluation network;
- `assets/arasan/book.bin`, the required checksummed opening book;
- the Arasan license and source/network provenance; and
- consumer R8 rules that preserve the JNI entry points.

The engine version, upstream source revision, network filename, size, and
checksum come from `sdk/upstream.json`. Android toolchain and support-matrix
versions are pinned in `platforms/android/gradle.properties`.

## Build

Requirements:

- JDK 17;
- Gradle 9.1.0;
- Android SDK platform and build tools 36;
- Android NDK 28.2.13676358;
- CMake 3.22.1;
- Node.js and `unzip`.

After accepting the Android SDK licenses, Gradle can install the pinned NDK and
CMake versions automatically. Build from the repository root:

```sh
./platforms/android/build.sh
```

The build creates the AAR, a debug smoke application, and a distribution
manifest with checksums. With an Android device or emulator visible to `adb`,
run:

```sh
./platforms/android/run-smoke.sh
```

The smoke application validates UCI readiness, a three-line MultiPV search,
cancellation of an infinite search, opening-book lookup, shutdown and
reinitialization, a second bounded search, process recreation, and reuse of the
verified private resource copies.

## Host integration

Add the AAR to the Android application. For an AAR copied into `app/libs`, a
Gradle Kotlin build can use:

```kotlin
dependencies {
    implementation(files("libs/arasan-chess-sdk-android.aar"))
}
```

Open the process-wide engine from a background-aware owner:

```java
Executor callbackExecutor = command -> mainHandler.post(command);
ArasanEngine engine = ArasanEngine.open(
        context,
        callbackExecutor,
        line -> consumeUciLine(line)
);

backgroundExecutor.execute(() -> engine.send("go movetime 250"));
```

`ArasanEngine.open` verifies and copies the bundled NNUE and opening-book assets
into the application's no-backup private directory before calling the native
engine. The consumer does not need to discover or manage resource paths. Book
play is off by default; use the normal `OwnBook` option or `bk` query command.

A bounded `go` command is synchronous and must not run on the Android main
thread. Ordinary commands should be serialized by the host. A second thread
may send `stop` while a search is active. Call `close` from the lifecycle owner
when the engine is no longer needed, but never from inside the output callback.
Callbacks may originate on engine/search threads and are delivered through the
`Executor` supplied by the host.

Only one `ArasanEngine` may be open in a process because this Arasan embedding
line has process-global engine state. Opening a second instance fails rather
than silently sharing state.

## Validation boundary

Hosted CI executes the full smoke suite on an x86_64 emulator and compiles the
ARM64 library in the same AAR. Physical ARM64 execution, app background/restore
behavior, and device-specific memory pressure remain release validation steps
for a signed consumer application.
