# SixtyFour difficulty evaluation

This directory starts a reproducible answer to a product question: does each
SixtyFour bot difficulty behave like a meaningfully stronger opponent than the
one below it?

It belongs in the Arasan SDK repository for now because the behavior under test
is the engine's strength-reduction algorithm and SDK build.
SixtyFour should retain its fast integration tests for protocol wiring, legal
moves, and lifecycle behavior. If this grows into a broader product-evaluation
system for explanations, training content, or multiple engines, the manifest
format and runner can be extracted into a dedicated repository without moving
the engine-specific fixtures.

## What the first study proves

`sixtyfour-strength.json` records the exact V1 difficulty contract and two
different questions:

- the **Algorithm lane** uses a fixed outer depth of 16, allowing Arasan's
  lower internal strength caps to govern while giving unrestricted Maximum a
  repeatable, practical ceiling. Depth 16 remains above the highest configured
  limited-strength cap of 11 and its two-ply endgame extension;
- the **Product lane** uses SixtyFour's current 650 ms no-clock response budget;
- one thread and 32 MB hash;
- no engine opening book, position learning, or tablebases;
- single-PV search;
- the six limited-strength Elo presets plus unrestricted Maximum.

`run_strength_eval.py` creates six adjacent-level matches in each lane. Every
opening is played twice with colors reversed. The lane, opening seed, engine
binary, settings, and host metadata are recorded in `manifest.json`, along with
SHA-256 hashes of the engine, opening set, and fastchess binary.

The Algorithm lane reduces hardware sensitivity; it does not make runs fully
deterministic because Arasan's weaker-move selection is probabilistic. The
Product lane deliberately retains hardware sensitivity because it measures the
behavior users receive within 650 ms.

The outer depth is intentionally not 24 or another effectively unrestricted
value. A ladder-wide pilot showed that six concurrent unrestricted depth-24
searches could spend minutes on the first move of Elite versus Maximum. Depth
16 preserves headroom above every limited preset's internal cap while keeping
Maximum useful in routine evaluation runs.

For each pair within each lane, interpret the higher preset's result this way:

- **pass:** its estimated Elo advantage is positive and the lower end of the
  95% confidence interval is above zero;
- **fail:** the upper end of the 95% confidence interval is zero or lower;
- **inconclusive:** the interval spans zero, so run more paired openings.

The checked-in default is a 200-opening-pair pilot, or 400 games per adjacent
comparison. It is a smoke test for ordering, not a permanent sample-size claim.
Use the observed draw rate and uncertainty to size the next run. Crashes,
illegal moves, time losses outside the configured margin, or option failures
are independent failures even if the match score looks reasonable.

The runner does not enable fastchess strict-warning mode. At limited strength,
Arasan intentionally may report the best searched PV and then return a weaker
`bestmove`; fastchess warns about that mismatch even though it is the algorithm
being evaluated. Match logs are retained so unexpected warnings can still be
reviewed.

An Algorithm-lane pass with a Product-lane failure points to the response
budget or runtime performance rather than the intended strength ordering. A
failure in both lanes points more directly to the strength algorithm or preset
spacing.

Neither study proves that a label such as 1900 equals human 1900. They test
relative ordering on one binary and opening distribution. Absolute calibration
requires a pinned reference-engine pool and a joint rating fit. Human-facing
Elo claims ultimately require opt-in games against appropriately rated people
at comparable time controls.

## Why repeated games are necessary

Arasan maps the 1000–3450 `UCI_Elo` range onto integer strength values 0–100.
The current SixtyFour presets therefore reach these internal buckets:

| Preset | Requested Elo | Internal strength | Depth cap | Arasan-reported bucket Elo |
| --- | ---: | ---: | ---: | ---: |
| Casual | 1320 | 13 | 1 | 1318 |
| Club | 1600 | 24 | 3 | 1588 |
| Strong club | 1900 | 36 | 6 | 1882 |
| Expert | 2200 | 48 | 9 | 2176 |
| Master | 2500 | 61 | 9 | 2494 |
| Elite | 2800 | 73 | 11 | 2788 |
| Maximum | unrestricted | 100 | unrestricted | 3450 |

Reduced strength combines a bucket-dependent depth cap with probabilistic
selection of suboptimal root moves. A single position, a short tactical suite,
or an assertion that the UCI option was accepted cannot establish playing
strength. The harness tests parse `src/options.h` and `src/search.cpp` so a
change to the rating range or depth-cap table fails CI until this contract is
reviewed.

## Prerequisites

Build or obtain:

1. a native UCI executable built from the same Arasan source revision and
   release flags as the SixtyFour SDK artifact under test;
2. a pinned fastchess binary;
3. a licensed, versioned EPD opening set with varied, balanced positions.

The opening corpus is deliberately not checked in here until its provenance,
license, and selection policy are documented. Tactical EPD suites in `tests/`
are not a substitute for a match opening set.

## Plan a run

Planning prints the full manifest and commands without requiring the referenced
binaries or opening file to exist:

```sh
python3 evaluation/run_strength_eval.py plan \
  --fastchess /absolute/path/to/fastchess \
  --engine /absolute/path/to/arasanx-64 \
  --openings /absolute/path/to/openings.epd \
  --output-directory /absolute/path/to/results
```

Limit a development run to one adjacent pair with, for example,
`--pair casual:club`. Run the planned matches by replacing `plan` with `run`.
The runner executes pairs sequentially; fastchess controls within-pair
concurrency from the checked-in configuration. Development smoke runs can use
`--opening-pairs`, `--concurrency`, `--opening-seed`, `--depth`, and
`--move-time-ms` overrides; every override is captured in the resulting
manifest. Use `--lane algorithm` or `--lane product` to run only one lane.

## Evaluation ladder

1. **Conformance:** retain SDK and SixtyFour tests for UCI identity, supported
   options, legal moves, cancellation, and lifecycle behavior.
2. **Algorithm monotonicity:** run the fixed-depth paired study on the
   release-native binary. Treat uncertainty as a first-class result.
3. **Product monotonicity:** run the 650 ms paired study on each release backend
   to measure the actual no-clock experience.
4. **Absolute calibration:** add a versioned reference pool, use the same paired
   opening discipline, and fit all ratings jointly with a tool such as Ordo.
   Anchor the scale explicitly; pool-relative engine Elo is not automatically
   human Elo.
5. **Platform parity:** repeat on release Apple, Android, and WebAssembly builds.
   Compare failure rates, latency, NPS, and strength ordering. Time-based search
   is not expected to select identical moves across hardware.
6. **Human validation:** if product copy needs human-rating semantics, collect
   consented games by time control and compare predicted versus observed scores.

Run the harness unit tests with:

```sh
python3 -m unittest discover -s evaluation -p 'test_*.py'
```
