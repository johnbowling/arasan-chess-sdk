# Difficulty evaluation pilot results

## 2026-09-12 dual-lane smoke study

This run exercised every adjacent SixtyFour difficulty pair in both evaluation
lanes. It was deliberately small: 10 paired openings, or 20 color-swapped games,
per matchup. Its purpose was to validate the harness and expose obvious ordering
problems before spending hours on a larger study.

Configuration:

- SDK revision: `b91b3ed4f40d33a3fac78e07980f33c97105eb23`
- host: Apple arm64, 18 logical CPUs, macOS 26.6.2
- native engine SHA-256:
  `41c0a277beb8c3ed6cdac308cc979f2a165f837614be03aba05147d521a1daac`
- fastchess SHA-256:
  `3a1111dcf5eaa7d048598116fc8e18067e726a84078b4ab6941a3209f1c0ffe8`
- opening corpus SHA-256:
  `9b4d9fb7eda778377a36f67c93b6913b67c6b4db9a51e1b7d9bf6bff5cdf8e8e`
- opening seed: `640026`
- one thread, 32 MB hash, six concurrent games
- Algorithm lane: depth 16
- Product lane: 650 ms per move with a 100 ms controller margin

The pilot used the same official Stockfish suite that is now bundled under
`evaluation/openings/`. Its recorded hash differs because the downloaded
upstream EPD used CRLF line endings; Git normalizes the vendored copy to LF
without changing any position.

The score and 95% interval below are for the higher preset. The interval treats
each paired opening as one observation.

| Lane | Matchup | Higher W-D-L | Score (95% CI) | Result |
| --- | --- | ---: | ---: | --- |
| Algorithm | Casual -> Club | 18-1-1 | 92.5% (62.5%-98.9%) | Pass |
| Algorithm | Club -> Strong Club | 13-1-6 | 67.5% (37.5%-87.8%) | Inconclusive |
| Algorithm | Strong Club -> Expert | 17-0-3 | 85.0% (54.1%-96.5%) | Pass |
| Algorithm | Expert -> Master | 14-1-5 | 72.5% (41.9%-90.6%) | Inconclusive |
| Algorithm | Master -> Elite | 8-9-3 | 62.5% (33.3%-84.8%) | Inconclusive |
| Algorithm | Elite -> Maximum | 15-5-0 | 87.5% (56.8%-97.4%) | Pass |
| Product | Casual -> Club | 19-0-1 | 95.0% (65.5%-99.5%) | Pass |
| Product | Club -> Strong Club | 17-1-2 | 87.5% (56.8%-97.4%) | Pass |
| Product | Strong Club -> Expert | 16-0-4 | 80.0% (49.0%-94.3%) | Inconclusive |
| Product | Expert -> Master | 15-4-1 | 85.0% (54.1%-96.5%) | Pass |
| Product | Master -> Elite | 14-2-4 | 75.0% (44.2%-91.9%) | Inconclusive |
| Product | Elite -> Maximum | 16-4-0 | 90.0% (59.6%-98.2%) | Pass |

All 12 matches completed, for 240 games total. Every higher preset scored above
50%; seven comparisons passed the conservative interval gate, five were
inconclusive, and none failed. The retained logs contain the expected warnings
where weakened Arasan play returns a different move from the principal
variation. They contain no time forfeits, illegal moves, crashes, disconnects,
or unsupported-option failures.

This is encouraging evidence that the configured ladder is directionally
correct, not a complete certification. Ten paired openings leave wide intervals.
The next efficient run was therefore limited to the five inconclusive
comparisons, using the same binary, corpus, settings, and seed.

The raw PGNs, logs, manifest, fastchess JSON, and generated summaries are kept
outside Git in the workspace artifact directory
`artifacts/strength-eval-pilot-2026-09-12`.

## Targeted follow-up

The three inconclusive Algorithm matchups were rerun with 100 paired openings
(200 games) each. The two inconclusive Product matchups were rerun with 30
paired openings (60 games) each.

| Lane | Matchup | Higher W-D-L | Score (95% CI) | Result |
| --- | --- | ---: | ---: | --- |
| Algorithm | Club -> Strong Club | 165-8-27 | 84.5% (76.1%-90.3%) | Pass |
| Algorithm | Expert -> Master | 157-13-30 | 81.8% (73.1%-88.1%) | Pass |
| Algorithm | Master -> Elite | 125-49-26 | 74.8% (65.4%-82.2%) | Pass |
| Product | Strong Club -> Expert | 48-2-10 | 81.7% (64.5%-91.6%) | Pass |
| Product | Master -> Elite | 41-13-6 | 79.2% (61.8%-89.9%) | Pass |

All five follow-up comparisons passed, with no hard failures in 720 follow-up
games. Combined with the seven pilot passes, every adjacent difficulty
transition now has a passing result in both the depth-controlled Algorithm lane
and the 650 ms Product lane.

The follow-up used the same seed, so each larger sample contains the pilot's
first 10 opening pairs. The runs must not be pooled as independent samples; the
follow-up result replaces the smaller result for each repeated comparison.

The follow-up artifacts are kept outside Git in:

- `artifacts/strength-eval-followup-algorithm-2026-09-12`
- `artifacts/strength-eval-followup-product-2026-09-12`

This establishes monotonic ordering for this engine binary, opening corpus,
host, and the two tested search controls. A release gate should still use the
checked-in 200-pair default across the full ladder, and platform-parity runs are
still required for time-based behavior on other release backends.

## 2026-09-13 release-gate baseline

The published release gate ran the complete Algorithm ladder at its checked-in
200-pair setting on SDK revision `944902681c71f7820dae0d8f669cce942e6c50e0`.
It built Arasan and fastchess once, then used that identical uploaded binary
bundle across six parallel Ubuntu x86-64 jobs with four logical CPUs each.

Reproducibility inputs:

- config SHA-256:
  `de9a7dcc21d1533adcc74392530e40081b59fd111dcd3d1352e8ea20acea3a4a`
- engine SHA-256:
  `d080dee79cefd90fb2c97c1d6333e76d506c40a326a24b715fe3e951388e767a`
- fastchess SHA-256:
  `3e5eb69cf14c255a69072272cb37cc9ac3280bf70d3daf339287b29926e6ae24`
- opening corpus SHA-256:
  `13f1637882d3631fc6919c2c8ab95989d1e6d620a335feccc727ea1d3d63e317`
- opening seed: `640026`

| Matchup | Higher W-D-L | Score (95% CI) | Result |
| --- | ---: | ---: | --- |
| Casual -> Club | 359-24-17 | 92.8% (88.3%-95.6%) | Pass |
| Club -> Strong Club | 331-22-47 | 85.5% (80.0%-89.7%) | Pass |
| Strong Club -> Expert | 351-7-42 | 88.6% (83.5%-92.3%) | Pass |
| Expert -> Master | 329-33-38 | 86.4% (80.9%-90.4%) | Pass |
| Master -> Elite | 259-83-58 | 75.1% (68.7%-80.6%) | Pass |
| Elite -> Maximum | 332-68-0 | 91.5% (86.8%-94.6%) | Pass |

All six comparisons passed. All 2,400 games were present and had a normal PGN
termination; no hard failures were recorded. The merger verified one SDK
revision and one config, engine, fastchess, and opening hash across all shards
before the gate evaluated the combined report.

The parallel workflow completed in 58 minutes 23 seconds. The preceding
sequential baseline took 1 hour 53 minutes 2 seconds, so sharding removed 54
minutes 39 seconds, or 48% of wall-clock time, without reducing the sample.

The successful GitHub Actions run is
[`34732430557`](https://github.com/johnbowling/arasan-chess-sdk/actions/runs/34732430557).
Its combined report is retained by GitHub for 90 days. A downloaded copy is
kept outside Git at
`artifacts/strength-eval-ci-parallel-34732430557`.
