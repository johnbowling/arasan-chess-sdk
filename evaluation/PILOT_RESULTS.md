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

## 2026-09-13 calibration mechanism smoke

The new Stockfish-anchored runner was exercised end to end with Casual against
Stockfish 19 at a matching requested Elo of 1320. This deliberately used only
five paired openings and a short `2+0.02` clock. It validates process startup,
UCI options, paired colors, artifact capture, score orientation, Elo
conversion, and termination auditing. It is **not calibration evidence**: the
clock differs from the checked-in `120+1` calibration condition and the sample
is far too small.

Stockfish won all 10 games. The report correctly remained inconclusive: the
paired Wilson score interval was 0.0%–43.4%, corresponding to an Arasan Elo
offset interval from unbounded below to −45.8. That interval overlaps the
acceptable ±100 band, so neither equivalence nor a mismatch was established.
All 10 PGNs had normal terminations and no hard failures.

The local-only artifacts are kept at
`artifacts/calibration-smoke-sf19-short`. The earlier interrupted `120+1` smoke
is retained separately for diagnostics and is not a completed result.

## 2026-09-13 Stockfish-anchored calibration baseline

The first hosted calibration baseline compared all six rated SixtyFour presets
with Stockfish 19 configured to the same requested Elo. Each match used 50
paired openings, or 100 color-swapped games, at the checked-in `120+1` clock.
This measures agreement with Stockfish's approximate CCRL Blitz scale, not
human Elo.

Reproducibility inputs:

- SDK revision: `e98b9a7e294ba9b33b94528fdd77fd653e4ff91f`
- config SHA-256:
  `a8fb5ed3f552111123309524d6850fab69ee2b4b69d448b3cb2ac2ae793ad6b9`
- Arasan SHA-256:
  `cd3b1eeec0fdff9bb04e1c7e711583253096d90c7b62d710611c0ceb2683d355`
- Stockfish 19 revision: `edb0d9db6731067ec50ce619ff372b463bc4dd5d`
- Stockfish SHA-256:
  `ee4d3dd006770a083f635a75af8e74402cc4a7489be3f3353f4728ba2b2a1e5f`
- fastchess SHA-256:
  `6c872a7d9143c6d49ef06fe149af032ca07440606f1d7256c2544c788e39c561`
- opening corpus SHA-256:
  `13f1637882d3631fc6919c2c8ab95989d1e6d620a335feccc727ea1d3d63e317`
- opening seed: `640026`
- one thread and 32 MB hash per engine, four concurrent games per shard
- six parallel GitHub-hosted Ubuntu x86-64 shards

The score and Elo delta below are from Arasan's perspective. A pass requires
the complete 95% Elo-delta interval to fit inside the configured +/-100 Elo
equivalence band.

| Preset | Target | Arasan W-D-L | Score (95% CI) | Elo delta (95% CI) | Anchored estimate (95% CI) | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Casual | 1320 | 2-0-98 | 2.0% (0.4%-10.5%) | -676.1 (-979.8 to -372.3) | 643.9 (340.2 to 947.7) | Fail |
| Club | 1600 | 10-0-90 | 10.0% (4.3%-21.4%) | -381.7 (-537.0 to -226.4) | 1218.3 (1063.0 to 1373.6) | Fail |
| Strong Club | 1900 | 18-1-81 | 18.5% (10.1%-31.4%) | -257.6 (-379.1 to -136.1) | 1642.4 (1520.9 to 1763.9) | Fail |
| Expert | 2200 | 39-5-56 | 41.5% (28.9%-55.3%) | -59.6 (-156.1 to +36.8) | 2140.4 (2043.9 to 2236.8) | Inconclusive |
| Master | 2500 | 83-4-13 | 85.0% (72.6%-92.4%) | +301.3 (+169.7 to +433.0) | 2801.3 (2669.7 to 2933.0) | Fail |
| Elite | 2800 | 65-16-19 | 73.0% (59.4%-83.3%) | +172.8 (+66.0 to +279.6) | 2972.8 (2866.0 to 3079.6) | Inconclusive |

All six match jobs completed successfully. All 600 games were present as 300
complete color-swapped opening pairs at `120+1`; every PGN termination was
normal, and the report recorded no hard failures. The merger verified the SDK
revision and config, Arasan, Stockfish, fastchess, and opening hashes across all
six shards. The workflow's final report job failed intentionally because the
statistical `--require-pass` gate observed an overall calibration failure, not
because of an infrastructure or engine-process failure. Total workflow time was
2 hours 31 minutes 44 seconds.

This establishes that the ladder is ordered but is not calibrated to the
pinned Stockfish scale at the current requested values. Casual, Club, and
Strong Club were clearly weaker than their anchors, while Master was clearly
stronger. Expert and Elite need more evidence to prove equivalence or mismatch;
neither passed this strict equivalence test.

The next efficient experiment is not a larger rerun of the four clear
mismatches. It is a bracketed search that holds each Stockfish target fixed,
varies the Arasan `UCI_Elo` input, and jointly fits a monotone lookup curve.
After choosing a candidate mapping, the checked-in 200-pair calibration should
confirm every level. Product difficulty values remain unchanged until that
mapping is reviewed.

The GitHub Actions run is
[`34735840276`](https://github.com/johnbowling/arasan-chess-sdk/actions/runs/34735840276).
Its combined report is retained by GitHub for 90 days. A downloaded copy is
kept outside Git at `artifacts/calibration-ci-34735840276`.

## 2026-09-13 calibration bracket-search pilot

The first bracket search held each Stockfish target fixed and tested two
candidate Arasan `UCI_Elo` inputs selected from the baseline. Each candidate
used 25 paired openings, or 50 color-swapped games, at `120+1`.

Reproducibility inputs:

- SDK revision: `7ff637f2518a2b9b9bf72439079b70d159826b67`
- config SHA-256:
  `8965e21f53a837096fd1dad7860c69da990d5f26da037a2ad225c1c9e147f352`
- Arasan SHA-256:
  `96feb3fc968d0be9a2606262dde2a92d4b1ca421781c895c6daa1a5b7649b9cf`
- Stockfish 19 revision: `edb0d9db6731067ec50ce619ff372b463bc4dd5d`
- Stockfish SHA-256:
  `ee4d3dd006770a083f635a75af8e74402cc4a7489be3f3353f4728ba2b2a1e5f`
- fastchess SHA-256:
  `6c872a7d9143c6d49ef06fe149af032ca07440606f1d7256c2544c788e39c561`
- opening corpus SHA-256:
  `13f1637882d3631fc6919c2c8ab95989d1e6d620a335feccc727ea1d3d63e317`
- opening seed: `640026`
- one thread and 32 MB hash per engine, four concurrent games per shard

The Elo delta and interval are from Arasan's perspective. `Bracketed` means the
candidate point estimates straddled zero; it does not mean either candidate
passed the equivalence gate.

| Preset target | Arasan input | Arasan W-D-L | Elo delta (95% CI) | Search finding |
| --- | ---: | ---: | ---: | --- |
| Casual 1320 | 1600 | 18-1-31 | -92.5 (-229.9 to +45.0) | Bracketed with 1750 |
| Casual 1320 | 1750 | 24-3-23 | +6.9 (-126.0 to +139.9) | Suggested input 1740 |
| Club 1600 | 1800 | 9-0-41 | -263.4 (-433.8 to -93.1) | Too weak |
| Club 1600 | 1950 | 17-1-32 | -107.5 (-246.6 to +31.5) | Expand higher |
| Strong Club 1900 | 1975 | 10-0-40 | -240.8 (-404.9 to -76.8) | Too weak |
| Strong Club 1900 | 2125 | 18-0-32 | -100.0 (-238.1 to +38.2) | Expand higher |
| Expert 2200 | 2150 | 13-1-36 | -172.8 (-321.6 to -24.0) | Bracketed with 2300 |
| Expert 2200 | 2300 | 47-1-2 | +511.5 (+230.7 to +792.3) | Suggested input 2188 |
| Master 2500 | 2275 | 39-5-6 | +275.5 (+101.5 to +449.4) | Too strong |
| Master 2500 | 2425 | 38-4-8 | +240.8 (+76.8 to +404.9) | Expand lower |
| Elite 2800 | 2425 | 16-9-25 | -63.2 (-198.3 to +71.8) | Too weak |
| Elite 2800 | 2575 | 18-10-22 | -27.9 (-161.2 to +105.5) | Expand higher |

All 12 match jobs succeeded. All 600 games were present as 300 complete
color-swapped pairs at `120+1`; all PGN terminations were normal, and no hard
failures were recorded. The merger verified identical config, Arasan,
Stockfish, fastchess, and opening hashes across every shard. The workflow took
1 hour 21 minutes 51 seconds. Its red status is the expected
`--require-ready` signal that a complete mapping was not yet bracketed, not an
infrastructure failure.

The original workflow report called Master's small point-estimate decrease
non-monotonic even though the two wide confidence intervals overlap. Commit
`50867148` corrected that rule: only a statistically separated decrease is now
called non-monotonic. Regenerating the report classifies Master as
`expand-lower` and the overall search as `expand-brackets`.

This run also exposed a device-control issue useful beyond this pilot. The 12
candidates ran independently across nine AMD EPYC 7763 hosts, two AMD EPYC
9V74 hosts, and one Intel Xeon Platinum 8573C host. Each individual match is
internally controlled because both engines share its host, but interpolating
between candidates on different CPUs adds avoidable variance. Commit
`50867148` changes future searches to run both candidates for a target
sequentially on one host.

The next bracket set should be:

| Preset | Next Arasan inputs | Reason |
| --- | ---: | --- |
| Casual | 1600, 1750 | Repeat the existing crossing on one host |
| Club | 1950, 2100 | Extend above two weak candidates |
| Strong Club | 2125, 2250 | Extend above two weak candidates |
| Expert | 2150, 2300 | Repeat the existing crossing on one host |
| Master | 2150, 2275 | Extend below two strong candidates |
| Elite | 2575, 2800 | Extend to the baseline's stronger point |

The Strong Club and Expert ranges intentionally overlap around Arasan's
depth-cap transition. The next report must reject the proposed mapping if these
targets cannot produce strictly increasing inputs and internal buckets. No
product difficulty value has changed.

The GitHub Actions run is
[`34771071016`](https://github.com/johnbowling/arasan-chess-sdk/actions/runs/34771071016).
Its combined report is retained by GitHub for 90 days. A downloaded and
post-fix-regenerated copy is kept outside Git at
`artifacts/calibration-search-ci-34771071016`.

## 2026-09-13 same-host bracket follow-up

The expanded bracket search reran two candidates for every target. Unlike the
first pilot, each target's candidates executed sequentially in one job on one
host, removing CPU differences from its interpolation.

Reproducibility inputs:

- SDK revision: `c1b35b04a3d20259011a08b624d6db54947bb8be`
- config SHA-256:
  `f54f9a581ad996a24a73deab4ef44737e569ca128a8320f400449409b3547996`
- Arasan SHA-256:
  `bf9309d96718db9910308b11d824ba3dda8974d3e17f3ac05a0948d5ed8843c8`
- Stockfish 19 revision: `edb0d9db6731067ec50ce619ff372b463bc4dd5d`
- Stockfish SHA-256:
  `ee4d3dd006770a083f635a75af8e74402cc4a7489be3f3353f4728ba2b2a1e5f`
- fastchess SHA-256:
  `6c872a7d9143c6d49ef06fe149af032ca07440606f1d7256c2544c788e39c561`
- opening corpus SHA-256:
  `13f1637882d3631fc6919c2c8ab95989d1e6d620a335feccc727ea1d3d63e317`
- opening seed: `640026`
- 25 paired openings per candidate at `120+1`
- one thread and 32 MB hash per engine, four concurrent games

| Preset target | Arasan input | Arasan W-D-L | Elo delta (95% CI) | Search use |
| --- | ---: | ---: | ---: | --- |
| Casual 1320 | 1600 | 13-0-37 | -181.7 (-332.2 to -31.2) | Lower candidate |
| Casual 1320 | 1750 | 21-2-27 | -41.9 (-175.7 to +92.0) | In-band candidate |
| Club 1600 | 1950 | 19-0-31 | -85.0 (-221.8 to +51.7) | Lower candidate |
| Club 1600 | 2100 | 22-0-28 | -41.9 (-175.7 to +92.0) | In-band candidate |
| Strong Club 1900 | 2125 | 20-2-28 | -56.1 (-190.7 to +78.5) | In-band candidate |
| Strong Club 1900 | 2250 | 48-1-1 | +603.9 (+262.4 to +945.3) | Upper candidate |
| Expert 2200 | 2150 | 10-0-40 | -240.8 (-404.9 to -76.8) | Lower bracket |
| Expert 2200 | 2300 | 47-1-2 | +511.5 (+230.7 to +792.3) | Upper bracket |
| Master 2500 | 2150 | 9-2-39 | -240.8 (-404.9 to -76.8) | Lower bracket |
| Master 2500 | 2275 | 39-4-7 | +263.4 (+93.1 to +433.8) | Upper bracket |
| Elite 2800 | 2575 | 20-13-17 | +20.9 (-112.3 to +154.0) | In-band candidate |
| Elite 2800 | 2800 | 37-5-8 | +230.2 (+68.8 to +391.5) | Upper candidate |

All six match jobs succeeded. All 600 games were present as 300 complete
color-swapped pairs at `120+1`; every PGN termination was normal, with no hard
failures. The two candidates for each target record the same CPU model and
logical CPU count. The merger verified identical config, Arasan, Stockfish,
fastchess, and opening hashes across all 12 shards. The workflow took 2 hours
38 minutes 56 seconds.

The report job failed before analysis because Elite's candidate input `2800`
equals its product target. The runner correctly used the canonical match ID
`calibration__elite`, while the search completeness check incorrectly expected
`calibration__elite__a2800`. Commit `f8cc2108` fixes that ID rule and adds a
regression test. The retained diagnostic shards merge successfully with the
fix; no games needed to be repeated.

Commit `eb5898d8` also aligns exploratory search with the declared +/-100 Elo
equivalence goal. A tested candidate whose point estimate is already inside
the band is now selected for confirmation even when its 25-pair confidence
interval is too wide to pass. Requiring an exact zero crossing would spend more
games optimizing beyond the product's stated tolerance. The candidate is still
not called calibrated until its confirmation interval passes.

The recovered search is **ready for confirmation** with this strictly
increasing proposal:

| Preset target | Proposed Arasan input | Internal bucket | Basis |
| --- | ---: | ---: | --- |
| Casual 1320 | 1750 | 30 | Observed point estimate inside band |
| Club 1600 | 2100 | 44 | Observed point estimate inside band |
| Strong Club 1900 | 2125 | 45 | Observed point estimate inside band |
| Expert 2200 | 2198 | 48 | Interpolated zero crossing |
| Master 2500 | 2210 | 49 | Interpolated zero crossing |
| Elite 2800 | 2575 | 64 | Observed point estimate inside band |

The close Club-through-Master inputs reflect Arasan's nonlinear weakening
behavior and make confirmation especially important. These are evaluation-only
hypotheses; no SixtyFour product value changed.

The GitHub Actions run is
[`34776431949`](https://github.com/johnbowling/arasan-chess-sdk/actions/runs/34776431949).
Its failed-run diagnostic shards are retained by GitHub for 90 days. The
recovered combined report is kept outside Git at
`artifacts/calibration-search-ci-34776431949/combined`.

## 2026-09-14 proposed-mapping confirmation

The full confirmation tested the six strictly increasing inputs selected by
the same-host bracket follow-up. Each preset used 200 distinct color-swapped
opening pairs at `120+1`. To remain within hosted-job limits, the workflow split
each preset across four sequential 50-pair blocks starting at opening indices
1, 51, 101, and 151, then verified and combined the block statistics and PGNs.

Reproducibility inputs:

- SDK revision: `a3629bdf71681d18b9b2a91940087532da805047`
- config SHA-256:
  `698b23eeba3b7a52bbf41be67409bd3e7f9c2d333e61753f01f03eac0de1771b`
- Arasan SHA-256:
  `e750919a82bd70288f556b621e05b018137f7edfc9a509cf11596d3a0fa7ba63`
- Stockfish 19 revision: `edb0d9db6731067ec50ce619ff372b463bc4dd5d`
- Stockfish SHA-256:
  `ee4d3dd006770a083f635a75af8e74402cc4a7489be3f3353f4728ba2b2a1e5f`
- fastchess SHA-256:
  `6c872a7d9143c6d49ef06fe149af032ca07440606f1d7256c2544c788e39c561`
- opening corpus SHA-256:
  `13f1637882d3631fc6919c2c8ab95989d1e6d620a335feccc727ea1d3d63e317`
- 200 paired openings per preset at `120+1`
- one thread and 32 MB hash per engine, four concurrent games per block

| Preset target | Arasan input | Arasan W-D-L | Elo delta (95% CI) | Status |
| --- | ---: | ---: | ---: | --- |
| Casual 1320 | 1750 | 208-9-183 | +21.7 (-26.3 to +69.8) | Pass |
| Club 1600 | 2100 | 199-7-194 | +4.3 (-43.7 to +52.3) | Pass |
| Strong Club 1900 | 2125 | 162-12-226 | -56.1 (-104.7 to -7.5) | Inconclusive |
| Expert 2200 | 2198 | 203-13-184 | +16.5 (-31.5 to +64.6) | Pass |
| Master 2500 | 2210 | 159-15-226 | -58.7 (-107.4 to -10.1) | Inconclusive |
| Elite 2800 | 2575 | 166-93-141 | +21.7 (-26.3 to +69.8) | Pass |

All 24 match jobs succeeded. All 2,400 games were present as 1,200 complete
paired observations, and every PGN termination was normal. The merger accepted
exactly the four configured non-overlapping blocks for every preset. All hosts
exposed four logical CPUs, but the hosted pool assigned four CPU models across
the 24 blocks. Strong Club's four blocks all ran on AMD EPYC 7763 hosts;
Master's blocks spanned AMD EPYC 7763, AMD EPYC 9V74, and Intel Xeon Platinum
8573C hosts. Supported-device parity remains a separate product-lane question.
The workflow took 4 hours 57 minutes 36 seconds.

The combined calibration status is **inconclusive**, not fail. Four inputs pass
the strict requirement that their entire 95% interval fit inside the +/-100
Elo band. Strong Club and Master have point estimates inside the band, but their
lower interval bounds extend only 4.7 and 7.4 Elo beyond it. The report job is
red solely because `--require-pass` correctly rejects those two inconclusive
results; it is not an operational workflow failure and is not evidence of an
Arasan defect.

The next efficient step is to add 100 new, disjoint paired openings for Strong
Club 2125 and Master 2210 only, using indices 201 through 300, and combine them
with the retained 200-pair samples. If the observed centers and variances stay
similar, ordinary inverse-square-root interval scaling projects roughly
40-Elo half-widths at 300 pairs: about -95.8 to -16.4 for Strong Club and -98.5
to -19.0 for Master. Those are planning projections, not results. A stable
300-pair interval that still crosses the boundary would justify refining the
input; a statistically clear discontinuity or inability to keep distinct
monotonic buckets would justify investigating Arasan's weakening algorithm.
No SixtyFour product difficulty value has changed.

The GitHub Actions run is
[`34785759770`](https://github.com/johnbowling/arasan-chess-sdk/actions/runs/34785759770).
Its combined report is retained by GitHub for 90 days. A downloaded copy is
kept outside Git at `artifacts/calibration-confirmation-ci-34785759770`.
