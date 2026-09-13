#!/usr/bin/env python3
"""Combine disjoint opening blocks for a full calibration confirmation."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from merge_calibration_eval import (
    MATCH_SUFFIXES,
    MergeError,
    _assert_compatible,
    _input_hashes,
    _load_json,
    expected_id_for_match,
)


STAT_FIELDS = (
    "wins",
    "losses",
    "draws",
    "penta_WW",
    "penta_WD",
    "penta_WL",
    "penta_DD",
    "penta_LD",
    "penta_LL",
)


def _confirmation_plan(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int]:
    calibration = manifest.get("calibration")
    confirmation = (
        calibration.get("confirmation") if isinstance(calibration, dict) else None
    )
    if not isinstance(confirmation, dict):
        raise MergeError("manifest.calibration.confirmation must be an object")
    total_pairs = confirmation.get("openingPairs")
    pairs_per_shard = confirmation.get("pairsPerShard")
    if (
        not isinstance(total_pairs, int)
        or not isinstance(pairs_per_shard, int)
        or total_pairs <= 0
        or pairs_per_shard <= 0
        or total_pairs % pairs_per_shard != 0
    ):
        raise MergeError("confirmation pair counts must be positive and evenly sharded")
    if confirmation.get("openingOrder") != "sequential":
        raise MergeError("confirmation opening order must be sequential")
    opening_suite = manifest.get("openingSuite")
    positions = opening_suite.get("positions") if isinstance(opening_suite, dict) else None
    if isinstance(positions, int) and total_pairs > positions:
        raise MergeError("confirmation requires more openings than the suite contains")

    presets = manifest.get("presets")
    if not isinstance(presets, list):
        raise MergeError("manifest.presets must be a list")
    target_by_preset = {
        preset.get("id"): preset.get("requestedElo")
        for preset in presets
        if isinstance(preset, dict)
    }
    mapping = confirmation.get("mapping")
    if not isinstance(mapping, list) or not mapping:
        raise MergeError("confirmation mapping must contain entries")
    plan = []
    seen_presets = set()
    for entry in mapping:
        if not isinstance(entry, dict):
            raise MergeError("confirmation mapping entry must be an object")
        preset = entry.get("preset")
        arasan_elo = entry.get("arasanElo")
        target_elo = target_by_preset.get(preset)
        if not isinstance(preset, str) or not isinstance(arasan_elo, int):
            raise MergeError("confirmation mapping entry is malformed")
        if not isinstance(target_elo, int):
            raise MergeError(f"confirmation preset is not rated: {preset}")
        if preset in seen_presets:
            raise MergeError(f"duplicate confirmation preset: {preset}")
        seen_presets.add(preset)
        match = {
            "preset": preset,
            "requestedElo": target_elo,
            "referenceElo": target_elo,
            "arasanElo": arasan_elo,
        }
        plan.append({**match, "id": expected_id_for_match(match)})
    return plan, total_pairs, pairs_per_shard


def _one_stats(path: Path) -> tuple[dict[str, Any], str, dict[str, int]]:
    fastchess = _load_json(path)
    stats_by_match = fastchess.get("stats")
    if not isinstance(stats_by_match, dict) or len(stats_by_match) != 1:
        raise MergeError(f"expected one stats entry in {path}")
    name, stats = next(iter(stats_by_match.items()))
    if not isinstance(name, str) or not isinstance(stats, dict):
        raise MergeError(f"invalid stats entry in {path}")
    normalized = {}
    for field in STAT_FIELDS:
        value = stats.get(field)
        if not isinstance(value, int) or value < 0:
            raise MergeError(f"invalid fastchess stat {field} in {path}")
        normalized[field] = value
    return fastchess, name, normalized


def _write_joined(paths: list[Path], destination: Path, binary: bool = False) -> None:
    mode = "wb" if binary else "w"
    kwargs = {} if binary else {"encoding": "utf-8"}
    with destination.open(mode, **kwargs) as output:
        for index, path in enumerate(paths):
            if index:
                output.write(b"\n" if binary else "\n")
            if binary:
                output.write(path.read_bytes())
            else:
                output.write(path.read_text(encoding="utf-8"))


def merge_confirmation(
    output_directory: Path, shard_directories: list[Path]
) -> dict[str, Any]:
    if not shard_directories:
        raise MergeError("at least one shard directory is required")
    if output_directory.exists() and any(output_directory.iterdir()):
        raise MergeError(f"output directory is not empty: {output_directory}")

    baseline: dict[str, Any] | None = None
    plan: list[dict[str, Any]] = []
    total_pairs = 0
    pairs_per_shard = 0
    blocks: dict[str, dict[int, tuple[Path, dict[str, Any], dict[str, Any]]]] = (
        defaultdict(dict)
    )
    for shard in shard_directories:
        manifest = _load_json(shard / "manifest.json")
        if manifest.get("evaluationType") != "stockfish-anchored-calibration":
            raise MergeError(f"not a calibration shard: {shard / 'manifest.json'}")
        if baseline is None:
            baseline = manifest
            if baseline.get("schemaVersion") != 1:
                raise MergeError("calibration shards must use manifest schema version 1")
            _input_hashes(baseline)
            plan, total_pairs, pairs_per_shard = _confirmation_plan(baseline)
        else:
            _assert_compatible(baseline, manifest, shard)

        selection = manifest.get("openingSelection")
        if not isinstance(selection, dict):
            raise MergeError(f"missing opening selection in {shard / 'manifest.json'}")
        if selection.get("order") != "sequential":
            raise MergeError("confirmation shards must traverse openings sequentially")
        opening_start = selection.get("start")
        if (
            not isinstance(opening_start, int)
            or selection.get("pairs") != pairs_per_shard
            or manifest["calibration"].get("openingPairs") != pairs_per_shard
        ):
            raise MergeError(f"invalid opening block in {shard / 'manifest.json'}")

        shard_matches = manifest.get("matches")
        if not isinstance(shard_matches, list) or len(shard_matches) != 1:
            raise MergeError(f"shard must contain exactly one match: {shard}")
        match = shard_matches[0]
        match_id = match.get("id") if isinstance(match, dict) else None
        expected_by_id = {entry["id"]: entry for entry in plan}
        if match_id not in expected_by_id or match_id != expected_id_for_match(match):
            raise MergeError(f"unexpected confirmation match in {shard / 'manifest.json'}")
        expected_match = expected_by_id[match_id]
        for field in ("preset", "requestedElo", "referenceElo", "arasanElo"):
            if match.get(field) != expected_match[field]:
                raise MergeError(
                    f"confirmation mapping disagrees with {shard / 'manifest.json'}"
                )
        if opening_start in blocks[match_id]:
            raise MergeError(
                f"duplicate opening block for {match_id}: start {opening_start}"
            )
        blocks[match_id][opening_start] = (shard, manifest, match)

    assert baseline is not None
    expected_starts = list(range(1, total_pairs + 1, pairs_per_shard))
    for match in plan:
        observed = sorted(blocks[match["id"]])
        if observed != expected_starts:
            raise MergeError(
                f"incomplete confirmation for {match['id']} "
                f"(expected starts {expected_starts}, observed {observed})"
            )

    output_directory.mkdir(parents=True, exist_ok=True)
    combined_matches = []
    execution_shards = []
    for expected_match in plan:
        match_id = expected_match["id"]
        ordered = [blocks[match_id][start] for start in expected_starts]
        combined_stats = {field: 0 for field in STAT_FIELDS}
        aggregate_fastchess = None
        stats_name = None
        pgn_paths = []
        log_paths = []
        console_paths = []
        for shard, manifest, match in ordered:
            for suffix in MATCH_SUFFIXES:
                path = shard / f"{match_id}.{suffix}"
                if not path.is_file():
                    raise MergeError(f"missing shard artifact: {path}")
            console = shard / "console.log"
            if not console.is_file():
                raise MergeError(f"missing shard artifact: {console}")
            fastchess, current_name, stats = _one_stats(
                shard / f"{match_id}.fastchess.json"
            )
            if aggregate_fastchess is None:
                aggregate_fastchess = copy.deepcopy(fastchess)
                stats_name = current_name
            elif current_name != stats_name:
                raise MergeError(f"incompatible stats name in {shard}")
            for field in STAT_FIELDS:
                combined_stats[field] += stats[field]
            start = manifest["openingSelection"]["start"]
            pgn_paths.append(shard / f"{match_id}.pgn")
            log_paths.append(shard / f"{match_id}.log")
            console_paths.append(console)
            execution_shards.append(
                {
                    "matchId": match_id,
                    "openingStart": start,
                    "openingPairs": pairs_per_shard,
                    "generatedAtUtc": manifest.get("generatedAtUtc"),
                    "host": manifest.get("host"),
                }
            )

        assert aggregate_fastchess is not None and stats_name is not None
        aggregate_fastchess["rounds"] = total_pairs
        aggregate_fastchess["stats"] = {stats_name: combined_stats}
        if isinstance(aggregate_fastchess.get("opening"), dict):
            aggregate_fastchess["opening"]["start"] = 1
        (output_directory / f"{match_id}.fastchess.json").write_text(
            json.dumps(aggregate_fastchess, indent=2) + "\n", encoding="utf-8"
        )
        _write_joined(pgn_paths, output_directory / f"{match_id}.pgn")
        _write_joined(log_paths, output_directory / f"{match_id}.log")
        _write_joined(
            console_paths, output_directory / f"{match_id}.console.log"
        )
        combined_match = copy.deepcopy(ordered[0][2])
        combined_match["aggregation"] = {
            "openingPairs": total_pairs,
            "pairsPerShard": pairs_per_shard,
            "openingStarts": expected_starts,
        }
        combined_matches.append(combined_match)

    merged = {
        key: value
        for key, value in baseline.items()
        if key
        not in {
            "schemaVersion",
            "generatedAtUtc",
            "host",
            "openingSelection",
            "matches",
        }
    }
    merged["calibration"] = copy.deepcopy(merged["calibration"])
    merged["calibration"]["openingPairs"] = total_pairs
    merged.update(
        {
            "schemaVersion": 2,
            "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
            "openingSelection": {
                "order": "sequential",
                "start": 1,
                "pairs": total_pairs,
                "sharded": True,
            },
            "execution": {
                "mode": "sharded-opening-blocks",
                "shards": execution_shards,
            },
            "matches": combined_matches,
        }
    )
    (output_directory / "manifest.json").write_text(
        json.dumps(merged, indent=2) + "\n", encoding="utf-8"
    )
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("shard_directories", type=Path, nargs="+")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        merge_confirmation(
            args.output_directory.resolve(),
            [path.resolve() for path in args.shard_directories],
        )
        return 0
    except (MergeError, OSError, KeyError, TypeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
