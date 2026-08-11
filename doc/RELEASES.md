# Release candidates

The SDK uses one cross-platform release-candidate workflow before any Git tag
or GitHub release is created. This keeps the ordinary maintenance path simple:
one manual run proves that Native, Apple, Android, and WebAssembly all pass at
the same fork commit, then assembles their output into one checksummed candidate.

The candidate workflow is deliberately non-publishing. It does not create a
tag, GitHub release, pull request, package-registry entry, or commit. A second
manual workflow may promote the exact retained bytes to a GitHub prerelease so
consumer CI has a durable coordinate. Stable publication remains a separate,
explicit owner decision after physical-device validation.

## Build a candidate

Open **Actions → Release candidate → Run workflow** and select the exact branch
or tag to validate. The optional version must use the downstream form
`v<arasan-version>-embed.<release>-rc.<candidate>`, for example:

```text
v26.0-embed.1-rc.1
```

If the version is omitted, the assembler uses `v<arasan-version>-embed.1-rc.1`.
The label describes the candidate artifact and is not initially a Git tag. It
becomes a tag only if an owner explicitly promotes that successful run through
the prerelease workflow.

The workflow calls the repository's existing validation workflows rather than
maintaining a second build implementation. Assembly begins only after:

- the native embedded and upstream unit suites pass;
- the Apple XCFramework passes its simulator lifecycle suite;
- the Android AAR passes its emulator lifecycle suite; and
- the WebAssembly package passes its browser suite.

## Candidate contract

The retained `arasan-chess-sdk-release-candidate-*` Actions artifact contains:

```text
apple/                 validated Apple package and manifest
android/               validated Android package and manifest
wasm/                  validated WebAssembly package and manifest
LICENSE                Arasan MIT license
PROVENANCE.md          pinned source and network provenance
README.md              these instructions
SHA256SUMS             checksums for every file above
release-manifest.json  normalized cross-platform candidate metadata
```

The assembler rejects the candidate unless all platform manifests identify the
same engine version, upstream source commit, fork source commit, NNUE network,
and opening book. It also checks each declared payload checksum, requires each
consumer package to expose the opening-book capability, and requires every
package to report a clean source checkout.

Actions retains the dry-run candidate for 90 days. Consumers must not depend on
that expiring URL.

## Publish a consumer prerelease

After a candidate passes and a consumer needs stable downloads, open
**Actions → Publish SDK prerelease → Run workflow** on `main`. Supply the
successful candidate workflow run ID and its exact candidate version. The
workflow:

1. confirms the referenced run is a successful **Release candidate** run;
2. downloads its retained unified artifact without rebuilding source;
3. matches the requested tag, workflow commit, release manifest, and clean-tree
   marker;
4. verifies every entry in `SHA256SUMS`;
5. refuses to overwrite an existing tag or release; and
6. creates a GitHub prerelease with unified and per-platform archives.

Prerelease tags retain the `-rc.N` suffix. They are durable consumer
coordinates, not stable-release approval, and publish nothing to CocoaPods,
Maven, npm, or another registry.

## Promotion gates

Before promoting a candidate to a stable tag such as `v26.0-embed.1`:

1. run the packaged Apple SDK on a physical ARM64 iPhone or iPad;
2. run the packaged Android SDK on a physical ARM64 Android device;
3. validate background/restore, cancellation, shutdown, and memory pressure in
   a signed consumer application;
4. verify the candidate's `SHA256SUMS` and legal notices; and
5. record the physical-device results with the release.

Do not rebuild a different commit during promotion. If source or packaging
changes, produce a new release candidate and repeat the gates.

No Maven, CocoaPods, npm, or server package is part of this process. Those
distribution channels should be added only after a demonstrated consumer need.
