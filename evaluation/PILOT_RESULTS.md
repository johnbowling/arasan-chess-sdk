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
The next efficient run should increase the sample only for the five inconclusive
comparisons, using the same binary, corpus, settings, and seed. A release gate
should eventually use the checked-in 200-pair default across the full ladder.

The raw PGNs, logs, manifest, fastchess JSON, and generated summaries are kept
outside Git in the workspace artifact directory
`artifacts/strength-eval-pilot-2026-09-12`.
