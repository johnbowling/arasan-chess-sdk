# SixtyFour difficulty evaluation

This directory starts a reproducible answer to a product question: does each
SixtyFour bot difficulty behave like a meaningfully stronger opponent than the
one below it?

The first end-to-end smoke-study results and their interpretation are recorded
in [`PILOT_RESULTS.md`](PILOT_RESULTS.md).

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
- the **Product lane** uses SixtyFour's current 650 ms no-clock response budget,
  plus a 100 ms match-controller margin that prevents host scheduling jitter
  from being scored as a chess loss without granting the engine more search;
- the bundled, CC0-licensed Stockfish `4mvs_+90_+99.epd` suite provides 635
  positions reached after eight plies;
- one thread and 32 MB hash;
- no engine opening book, position learning, or tablebases;
- single-PV search;
- the six limited-strength Elo presets plus unrestricted Maximum.

`run_strength_eval.py` creates six adjacent-level matches in each lane. Every
opening is played twice with colors reversed. The lane, opening seed, engine
binary, settings, and host metadata are recorded in `manifest.json`, along with
SHA-256 hashes of the engine, opening set, and fastchess binary.
After each match, the runner refreshes `summary.json` and `summary.md`. The
summary evaluates the higher preset using fastchess's pentanomial paired-game
scores and a bounded Wilson-style 95% interval. This preserves the
color-swapped opening as the statistical unit instead of pretending its two
games are independent. It also avoids the zero-width interval produced by a
raw plug-in variance when every sampled pair has the same outcome. The report
retains fastchess-style likelihood of superiority (LOS) as a diagnostic but
does not use it as the pass/fail gate. It also audits every PGN termination;
timeouts, abandoned games, illegal moves, unterminated games, and unknown
termination types fail the match regardless of its score.

The Algorithm lane reduces hardware sensitivity; it does not make runs fully
deterministic because Arasan's weaker-move selection is probabilistic. The
Product lane deliberately retains hardware sensitivity because it measures the
behavior users receive within 650 ms.

The outer depth is intentionally not 24 or another effectively unrestricted
value. A ladder-wide pilot showed that six concurrent unrestricted depth-24
searches could spend minutes on the first move of Elite versus Maximum. Depth
16 preserves headroom above every limited preset's internal cap while keeping
Maximum useful in routine evaluation runs.

For each comparison within each lane, interpret the higher preset's paired-game
score this way:

- **pass:** the lower end of its 95% confidence interval is above 50%;
- **fail:** the upper end of its 95% confidence interval is 50% or lower;
- **inconclusive:** the interval spans 50%, so run more paired openings.

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

The Product lane passes `st=0.65` to each engine and `timemargin=100` only to
fastchess's deadline enforcement. A ladder pilot without that margin produced
several false time losses for one- and two-millisecond overruns. Actual search
time and latency remain in the PGN and logs so regressions are still visible.

An Algorithm-lane pass with a Product-lane failure points to the response
budget or runtime performance rather than the intended strength ordering. A
failure in both lanes points more directly to the strength algorithm or preset
spacing.

Neither study proves that a label such as 1900 equals human 1900. They test
relative ordering on one binary and opening distribution. The separate
Stockfish-anchored study below tests numeric labels against a reproducible
engine scale. Human-facing Elo claims ultimately require opt-in games against
appropriately rated people at comparable time controls.

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

## Stockfish-anchored calibration

`run_calibration_eval.py` compares each of the six rated Arasan presets with
Stockfish 19 configured to the same `UCI_Elo`. Maximum is intentionally omitted
because an unrestricted engine has no numeric target. Stockfish 19 is pinned by
its `sf_19` tag and full source revision in `sixtyfour-strength.json`; the
workflow builds that source instead of downloading an unidentified executable.
The manifest hashes the resulting Stockfish, Arasan, fastchess, config, and
opening binaries or files.

This is a **Stockfish-anchored engine calibration**, not human Elo. Stockfish's
pinned source describes its 1320–3190 limited-strength range as approximately
covering CCRL Blitz Elo. The checked-in `120+1` game clock matches Stockfish's
published calibration condition. A shorter clock is useful for plumbing tests,
but it changes the experiment and cannot validate the published scale.

Every selected opening is played with colors reversed. The summary converts
Arasan's paired-opening score to an Elo offset using
`400 * log10(score / (1 - score))`. A ±100 Elo equivalence band is checked this
way:

- **pass:** the entire 95% Elo-offset interval is inside −100 to +100;
- **fail:** the entire interval is below −100 or above +100, or a game has a
  hard termination;
- **inconclusive:** the interval overlaps both acceptable and unacceptable
  values, so more paired openings are needed.

Requiring the whole interval to fit inside the band prevents a noisy point
estimate near zero from being called calibrated. Conversely, a result is not
called mismatched unless the data place the full interval outside one side of
the band. The checked-in study uses 200 opening pairs per preset. The manual
workflow defaults to 50 as a less expensive first pass; rerun inconclusive
presets with 200 or more.

Plan a local calibration without requiring the binaries to exist:

```sh
python3 evaluation/run_calibration_eval.py plan \
  --fastchess /absolute/path/to/fastchess \
  --arasan /absolute/path/to/arasanx-64 \
  --reference /absolute/path/to/stockfish-19 \
  --output-directory /absolute/path/to/calibration-results
```

Replace `plan` with `run` to execute it. Use `--preset club` to run one target.
Development-only overrides include `--opening-pairs`, `--concurrency`,
`--opening-seed`, `--time-control`, and `--tolerance-elo`; all are captured in
the manifest. Regenerate or gate a report with:

```sh
python3 evaluation/summarize_calibration_eval.py \
  --require-pass /absolute/path/to/calibration-results
```

The `Stockfish-anchored calibration` workflow builds all three executables once
and runs the six presets on separate hosts. Its final job refuses missing,
duplicated, or input-incompatible shards before producing the combined report.
The reference and match shards expire after one day; the combined report,
manifests, PGNs, and logs are retained for 90 days.

## Prerequisites

Build or obtain:

1. a native UCI executable built from the same Arasan source revision and
   release flags as the SixtyFour SDK artifact under test;
2. a pinned fastchess binary.

Local calibration also needs Stockfish built from the revision pinned under
`calibration.reference`. The manual workflow performs and verifies that build
automatically.

The default opening suite is checked in under `evaluation/openings/`, together
with its CC0 license, pinned upstream revision, and checksums. It is match input,
not an Arasan runtime book. Pass `--openings` only to evaluate an explicitly
chosen alternative corpus; the manifest records its path and hash. Tactical EPD
suites in `tests/` are not a substitute for a match opening set.

## Plan a run

Planning prints the full manifest and commands without requiring the referenced
binaries or opening file to exist:

```sh
python3 evaluation/run_strength_eval.py plan \
  --fastchess /absolute/path/to/fastchess \
  --engine /absolute/path/to/arasanx-64 \
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
4. **Stockfish-anchored calibration:** run each numeric preset against the
   matching pinned Stockfish 19 `UCI_Elo` and require its confidence interval to
   fit inside the declared equivalence band. Add a multi-engine reference pool
   and a joint Ordo fit if one reference implementation proves too brittle.
5. **Platform parity:** repeat on release Apple, Android, and WebAssembly builds.
   Compare failure rates, latency, NPS, and strength ordering. Time-based search
   is not expected to select identical moves across hardware.
6. **Human validation:** if product copy needs human-rating semantics, collect
   consented games by time control and compare predicted versus observed scores.

Run the harness unit tests with:

```sh
python3 -m unittest discover -s evaluation -p 'test_*.py'
```

Regenerate a summary for an existing or interrupted run with:

```sh
python3 evaluation/summarize_strength_eval.py /absolute/path/to/results
```

Add `--require-pass` when using the summary as a gate. The command returns a
nonzero status for failed, incomplete, or inconclusive studies:

```sh
python3 evaluation/summarize_strength_eval.py \
  --require-pass /absolute/path/to/results
```

The `Evaluation harness` workflow keeps contract tests lightweight on ordinary
pushes and pull requests. A manual run enables the full 200-pair Algorithm lane
by default. The six adjacent matches run in parallel from one uploaded engine
and fastchess build, so every shard uses identical binaries. A final job rejects
missing, duplicated, partial, or configuration-incompatible shards before it
applies the statistical gate. The merged manifest records the host used for
each match.

The Release candidate workflow requires that full lane to pass and retains its
merged manifest, machine-readable summary, Markdown report, PGNs, match logs,
and per-match console output for 90 days. Temporary binary and match-shard
artifacts expire after one day. Fastchess is built from the pinned commit
recorded in the workflow.

Downloaded shards can be merged and checked with:

```sh
python3 evaluation/merge_strength_eval.py \
  --require-complete-ladder \
  /absolute/path/to/combined \
  /absolute/path/to/shards/*
python3 evaluation/summarize_strength_eval.py \
  --require-pass /absolute/path/to/combined
```

Use the calibration-specific merger for downloaded reference-match shards:

```sh
python3 evaluation/merge_calibration_eval.py \
  --require-complete-calibration \
  /absolute/path/to/combined \
  /absolute/path/to/shards/*
python3 evaluation/summarize_calibration_eval.py \
  --require-pass /absolute/path/to/combined
```
