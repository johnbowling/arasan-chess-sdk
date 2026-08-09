# Arasan embedding fork

This repository is a neutral integration fork of
[`jdart1/arasan-chess`](https://github.com/jdart1/arasan-chess). Its purpose is
to make Arasan straightforward to embed in applications on Apple platforms,
Android, and the web without coupling the engine to any one product or UI.

The engine, its name, and its original documentation remain Arasan's. This fork
does not currently change evaluation, search, playing strength, or UCI
semantics.

## Branch and release policy

- `master` follows the fork's view of upstream development.
- Integration branches such as `embed/v26.0` start at an exact upstream release
  tag and contain the embedding delta for that release.
- Consumer releases will use immutable downstream tags such as
  `v26.0-embed.1`, with checksums and build metadata.
- The canonical upstream remote is `https://github.com/jdart1/arasan-chess.git`.

No upstream pull requests are planned during the initial implementation. Work
is kept product-neutral and separated into reviewable changes so that generally
useful pieces can be considered for upstream later without making that a
dependency of delivery.

## Current scope

The first increment provides:

- provenance for the upstream source and NNUE network;
- a small, line-oriented C API around Arasan's existing UCI implementation;
- explicit embedded resource paths and conservative embedded defaults;
- a native static-library build and smoke test; and
- unchanged command-line engine behavior.

Platform artifact production is intentionally deferred to subsequent
increments. See [doc/EMBEDDING.md](doc/EMBEDDING.md) and
[doc/UPSTREAM-DELTA.md](doc/UPSTREAM-DELTA.md).
