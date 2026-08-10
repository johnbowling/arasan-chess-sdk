# Embedded distribution provenance

This file explains the inputs pinned for the current embedding line. The
machine-readable source of truth used by builds and update automation is
[`sdk/upstream.json`](../sdk/upstream.json).

## Upstream source

| Item | Value |
| --- | --- |
| Repository | `https://github.com/jdart1/arasan-chess.git` |
| Upstream tag | `v26.0` |
| Annotated tag object | `7482a6cc77f099d7d13421fdd0eb3ebfdf8829c6` |
| Source commit | `d8613aca11b3db15ce7f5c6d54da4dc4b31f63f8` |
| Maintained branch | `main` |
| Initial integration branch | `embed/v26.0` |

The upstream `LICENSE` grants the MIT license for the source and the contents
of the `network` directory. Redistributions must preserve its copyright and
permission notice.

## Required NNUE network

| Item | Value |
| --- | --- |
| File | `network/arasanv8-20260622.nnue` |
| Size | `25,024,576` bytes |
| SHA-256 | `b42f9e13a37debb4af425d2ca74b5edff1d8034a616806bccdb67b79530201ac` |

Embedded artifacts must use that file unless the engine version, manifest, and
checksum are deliberately updated together. The opening book, GUI assets,
fonts, and tablebase data are not part of the embedded distribution.

The WebAssembly package renames the unchanged network payload to
`arasan.nnue`. Its package manifest must retain the same byte size and SHA-256.
The Apple package uses the same name, byte size, and checksum and carries the
network as an explicit application resource beside the XCFramework.
The Android AAR uses the same name, byte size, and checksum under
`assets/arasan`; its Java host verifies the payload before copying it to
app-private storage.

For reference, the upstream `book/book.bin` file at this commit has SHA-256
`21c7938d90d5247f3d916e5b11d7efc6b6a863b2b1f9fa63104e87d0a996b209`,
but embedded mode disables and does not package it.

## Original v26.0 baseline reproduction

The first clean build was reproduced on Apple Silicon with:

- macOS 26.6.1 (`25G76`), ARM64;
- Xcode 26.6 (`17F113`);
- Apple clang 21.0.0 (`clang-2100.1.1.101`); and
- GNU Make 3.81.

The upstream Makefile requires `BUILD_TYPE=neon` on ARM64. The unchanged
command-line engine completed `uci`, `isready`, and `go movetime 100`, returning
a legal `bestmove`.

The Apple SDK baseline was reproduced with the same Xcode installation and iOS
26.5 SDK at a minimum deployment target of iOS 16.0. It produced:

- an arm64 iOS device static library;
- arm64 and x86_64 iOS simulator static libraries;
- a combined XCFramework with a Swift-importable C module; and
- a successful arm64 simulator run covering UCI readiness, MultiPV, bounded and
  cancelled searches, shutdown, and reinitialization.

The Android SDK baseline targets API 24 or newer, uses NDK 28.2.13676358 and
CMake 3.22.1, and produces `arm64-v8a` and `x86_64` shared libraries. Hosted
validation compiles both ABIs and runs the common UCI smoke behavior on an
x86_64 Android emulator. Physical ARM64 execution remains a consumer release
validation step.
