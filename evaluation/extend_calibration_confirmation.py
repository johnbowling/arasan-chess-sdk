#!/usr/bin/env python3
"""Extend selected calibration matches with new disjoint opening blocks."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from merge_calibration_confirmation import STAT_FIELDS, _one_stats, _write_joined
from merge_calibration_eval import (
    MATCH_SUFFIXES,
    MergeError,
    _assert_compatible,
    _input_hashes,
    _load_json,
    expected_id_for_match,
)
from summarize_calibration_eval import SummaryError, build_summary


def _extension_plan(
    manifest: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    calibration = manifest.get("calibration")
    extension = (
        calibration.get("confirmationExtension")
        if isinstance(calibration, dict)
        else None
    )
    if not isinstance(extension, dict):
        raise MergeError("manifest.calibration.confirmationExtension must be an object")
    integer_fields = (
        "baseRunId",
        "baseOpeningPairs",
        "openingPairs",
        "pairsPerShard",
    )
    if any(
        not isinstance(extension.get(field), int) or extension[field] <= 0
        for field in integer_fields
    ):
        raise MergeError("confirmation extension counts and run id must be positive")
    if extension.get("openingOrder") != "sequential":
        raise MergeError("confirmation extension opening order must be sequential")
    starts = extension.get("openingStarts")
    if not isinstance(starts, list) or not starts or not all(
        isinstance(start, int) and start > 0 for start in starts
    ):
        raise MergeError("confirmation extension opening starts are invalid")
    expected_starts = list(
        range(
            extension["baseOpeningPairs"] + 1,
            extension["openingPairs"] + 1,
            extension["pairsPerShard"],
        )
    )
    if starts != expected_starts:
        raise MergeError("confirmation extension blocks must follow the base sample")
    opening_suite = manifest.get("openingSuite")
    positions = opening_suite.get("positions") if isinstance(opening_suite, dict) else None
    if isinstance(positions, int) and extension["openingPairs"] > positions:
        raise MergeError("confirmation extension exceeds the configured opening suite")

    base_hashes = extension.get("baseInputHashes")
    required_hashes = {"config", "fastchess", "arasan", "reference", "openings"}
    if not isinstance(base_hashes, dict) or set(base_hashes) != required_hashes or any(
        not isinstance(base_hashes[name], str) for name in required_hashes
    ):
        raise MergeError("confirmation extension base input hashes are incomplete")
    if not isinstance(extension.get("baseSdkRevision"), str):
        raise MergeError("confirmation extension base SDK revision is missing")

    presets = manifest.get("presets")
    if not isinstance(presets, list):
        raise MergeError("manifest.presets must be a list")
    target_by_preset = {
        preset.get("id"): preset.get("requestedElo")
        for preset in presets
        if isinstance(preset, dict) and isinstance(preset.get("requestedElo"), int)
    }
    confirmation = calibration.get("confirmation")
    confirmation_mapping = (
        confirmation.get("mapping") if isinstance(confirmation, dict) else None
    )
    if not isinstance(confirmation_mapping, list):
        raise MergeError("base confirmation mapping is missing")
    confirmed_input_by_preset = {
        entry.get("preset"): entry.get("arasanElo")
        for entry in confirmation_mapping
        if isinstance(entry, dict)
    }

    mapping = extension.get("mapping")
    if not isinstance(mapping, list) or not mapping:
        raise MergeError("confirmation extension mapping must contain entries")
    plan = []
    seen_presets = set()
    for entry in mapping:
        if not isinstance(entry, dict):
            raise MergeError("confirmation extension mapping entry must be an object")
        preset = entry.get("preset")
        arasan_elo = entry.get("arasanElo")
        target_elo = target_by_preset.get(preset)
        if (
            not isinstance(preset, str)
            or not isinstance(arasan_elo, int)
            or not isinstance(target_elo, int)
        ):
            raise MergeError("confirmation extension mapping entry is malformed")
        if preset in seen_presets:
            raise MergeError(f"duplicate confirmation extension preset: {preset}")
        if confirmed_input_by_preset.get(preset) != arasan_elo:
            raise MergeError(f"extension changes the confirmed input for {preset}")
        seen_presets.add(preset)
        match = {
            "preset": preset,
            "requestedElo": target_elo,
            "referenceElo": target_elo,
            "arasanElo": arasan_elo,
        }
        plan.append({**match, "id": expected_id_for_match(match)})
    return extension, plan


def _validate_base(
    base_directory: Path,
    base: dict[str, Any],
    supplement: dict[str, Any],
    extension: dict[str, Any],
    plan: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if (
        base.get("schemaVersion") != 2
        or base.get("evaluationType") != "stockfish-anchored-calibration"
    ):
        raise MergeError("base results must be a merged calibration manifest")
    if base.get("sdkRevision") != extension["baseSdkRevision"]:
        raise MergeError("base SDK revision does not match extension configuration")
    if _input_hashes(base) != extension["baseInputHashes"]:
        raise MergeError("base input hashes do not match extension configuration")
    if base.get("openingSuite") != supplement.get("openingSuite"):
        raise MergeError("base and supplemental opening suites differ")
    for field in ("arasanRatingModel", "engineOptions", "presets"):
        if base.get(field) != supplement.get(field):
            raise MergeError(f"base and supplemental {field} differ")
    base_calibration = base.get("calibration")
    supplemental_calibration = supplement.get("calibration")
    if not isinstance(base_calibration, dict) or not isinstance(
        supplemental_calibration, dict
    ):
        raise MergeError("calibration configuration is missing")
    for field in (
        "timeControl",
        "equivalenceToleranceElo",
        "reference",
        "confirmation",
    ):
        if base_calibration.get(field) != supplemental_calibration.get(field):
            raise MergeError(f"base and supplemental calibration {field} differ")
    if base_calibration.get("openingPairs") != extension["baseOpeningPairs"]:
        raise MergeError("base opening pair count does not match extension")
    selection = base.get("openingSelection")
    if (
        not isinstance(selection, dict)
        or selection.get("order") != "sequential"
        or selection.get("start") != 1
        or selection.get("pairs") != extension["baseOpeningPairs"]
    ):
        raise MergeError("base opening selection is incompatible with extension")

    base_matches = base.get("matches")
    if not isinstance(base_matches, list):
        raise MergeError("base manifest matches are missing")
    base_match_by_id = {
        match.get("id"): match for match in base_matches if isinstance(match, dict)
    }
    summary = build_summary(base_directory)
    result_by_id = {match["id"]: match["result"] for match in summary["matches"]}
    selected_ids = {entry["id"] for entry in plan}
    for match_id, result in result_by_id.items():
        if match_id in selected_ids:
            if result["status"] not in {"pass", "inconclusive"}:
                raise MergeError(f"base result cannot be extended: {match_id}")
        elif result["status"] != "pass":
            raise MergeError(f"unselected base result has not passed: {match_id}")
    for expected in plan:
        base_match = base_match_by_id.get(expected["id"])
        if not isinstance(base_match, dict):
            raise MergeError(f"base result is missing {expected['id']}")
        for field in ("preset", "requestedElo", "referenceElo", "arasanElo"):
            if base_match.get(field) != expected[field]:
                raise MergeError(f"base match disagrees with extension: {expected['id']}")
    return base_match_by_id, result_by_id


def extend_confirmation(
    output_directory: Path,
    base_directory: Path,
    shard_directories: list[Path],
) -> dict[str, Any]:
    if not shard_directories:
        raise MergeError("at least one supplemental shard is required")
    if output_directory.exists() and any(output_directory.iterdir()):
        raise MergeError(f"output directory is not empty: {output_directory}")

    base = _load_json(base_directory / "manifest.json")
    supplement: dict[str, Any] | None = None
    extension: dict[str, Any] = {}
    plan: list[dict[str, Any]] = []
    blocks: dict[str, dict[int, tuple[Path, dict[str, Any], dict[str, Any]]]] = (
        defaultdict(dict)
    )
    for shard in shard_directories:
        manifest = _load_json(shard / "manifest.json")
        if manifest.get("evaluationType") != "stockfish-anchored-calibration":
            raise MergeError(f"not a calibration shard: {shard / 'manifest.json'}")
        if supplement is None:
            supplement = manifest
            if supplement.get("schemaVersion") != 1:
                raise MergeError("supplemental shards must use manifest schema version 1")
            _input_hashes(supplement)
            extension, plan = _extension_plan(supplement)
        else:
            _assert_compatible(supplement, manifest, shard)

        current_hashes = _input_hashes(manifest)
        for name in ("fastchess", "arasan", "reference", "openings"):
            if current_hashes[name] != extension["baseInputHashes"][name]:
                raise MergeError(f"supplemental {name} hash differs from the base run")
        selection = manifest.get("openingSelection")
        if not isinstance(selection, dict):
            raise MergeError(f"missing opening selection in {shard / 'manifest.json'}")
        opening_start = selection.get("start")
        if (
            selection.get("order") != "sequential"
            or selection.get("pairs") != extension["pairsPerShard"]
            or manifest["calibration"].get("openingPairs")
            != extension["pairsPerShard"]
            or opening_start not in extension["openingStarts"]
        ):
            raise MergeError(f"invalid supplemental opening block in {shard}")

        matches = manifest.get("matches")
        if not isinstance(matches, list) or len(matches) != 1:
            raise MergeError(f"supplemental shard must contain one match: {shard}")
        match = matches[0]
        match_id = match.get("id") if isinstance(match, dict) else None
        expected_by_id = {entry["id"]: entry for entry in plan}
        if match_id not in expected_by_id or match_id != expected_id_for_match(match):
            raise MergeError(f"unexpected supplemental match in {shard}")
        for field in ("preset", "requestedElo", "referenceElo", "arasanElo"):
            if match.get(field) != expected_by_id[match_id][field]:
                raise MergeError(f"supplemental mapping disagrees in {shard}")
        if opening_start in blocks[match_id]:
            raise MergeError(
                f"duplicate supplemental block for {match_id}: start {opening_start}"
            )
        blocks[match_id][opening_start] = (shard, manifest, match)

    assert supplement is not None
    base_match_by_id, _ = _validate_base(
        base_directory, base, supplement, extension, plan
    )
    for expected in plan:
        observed = sorted(blocks[expected["id"]])
        if observed != extension["openingStarts"]:
            raise MergeError(
                f"incomplete extension for {expected['id']} "
                f"(expected starts {extension['openingStarts']}, observed {observed})"
            )

    output_directory.mkdir(parents=True, exist_ok=True)
    combined_matches = []
    execution_shards = []
    base_execution = base.get("execution")
    base_shards = (
        base_execution.get("shards") if isinstance(base_execution, dict) else None
    )
    if not isinstance(base_shards, list):
        raise MergeError("base execution shard records are missing")

    for expected in plan:
        match_id = expected["id"]
        base_match = base_match_by_id[match_id]
        base_json_path = base_directory / f"{match_id}.fastchess.json"
        aggregate_fastchess, stats_name, combined_stats = _one_stats(base_json_path)
        if aggregate_fastchess.get("rounds") != extension["baseOpeningPairs"]:
            raise MergeError(f"base fastchess rounds disagree for {match_id}")
        combined_stats = copy.deepcopy(combined_stats)
        pgn_paths = [base_directory / f"{match_id}.pgn"]
        log_paths = [base_directory / f"{match_id}.log"]
        console_paths = [base_directory / f"{match_id}.console.log"]
        for path in [*pgn_paths, *log_paths, *console_paths]:
            if not path.is_file():
                raise MergeError(f"missing base artifact: {path}")
        for shard_record in base_shards:
            if isinstance(shard_record, dict) and shard_record.get("matchId") == match_id:
                execution_shards.append(
                    {**copy.deepcopy(shard_record), "sourceRunId": extension["baseRunId"]}
                )

        for opening_start in extension["openingStarts"]:
            shard, manifest, _ = blocks[match_id][opening_start]
            for suffix in MATCH_SUFFIXES:
                path = shard / f"{match_id}.{suffix}"
                if not path.is_file():
                    raise MergeError(f"missing supplemental artifact: {path}")
            console = shard / "console.log"
            if not console.is_file():
                raise MergeError(f"missing supplemental artifact: {console}")
            fastchess, current_name, stats = _one_stats(
                shard / f"{match_id}.fastchess.json"
            )
            opening = fastchess.get("opening")
            if (
                current_name != stats_name
                or fastchess.get("rounds") != extension["pairsPerShard"]
                or not isinstance(opening, dict)
                or opening.get("start") != opening_start
            ):
                raise MergeError(f"supplemental fastchess block disagrees in {shard}")
            for field in STAT_FIELDS:
                combined_stats[field] += stats[field]
            pgn_paths.append(shard / f"{match_id}.pgn")
            log_paths.append(shard / f"{match_id}.log")
            console_paths.append(console)
            execution_shards.append(
                {
                    "matchId": match_id,
                    "openingStart": opening_start,
                    "openingPairs": extension["pairsPerShard"],
                    "generatedAtUtc": manifest.get("generatedAtUtc"),
                    "host": manifest.get("host"),
                }
            )

        aggregate_fastchess["rounds"] = extension["openingPairs"]
        aggregate_fastchess["stats"] = {stats_name: combined_stats}
        (output_directory / f"{match_id}.fastchess.json").write_text(
            json.dumps(aggregate_fastchess, indent=2) + "\n", encoding="utf-8"
        )
        _write_joined(pgn_paths, output_directory / f"{match_id}.pgn")
        _write_joined(log_paths, output_directory / f"{match_id}.log")
        _write_joined(
            console_paths, output_directory / f"{match_id}.console.log"
        )
        combined_match = copy.deepcopy(base_match)
        combined_match["aggregation"] = {
            "openingPairs": extension["openingPairs"],
            "pairsPerShard": extension["pairsPerShard"],
            "openingStarts": list(
                range(1, extension["openingPairs"] + 1, extension["pairsPerShard"])
            ),
            "baseRunId": extension["baseRunId"],
        }
        combined_matches.append(combined_match)

    merged = {
        key: value
        for key, value in supplement.items()
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
    merged["calibration"]["openingPairs"] = extension["openingPairs"]
    merged.update(
        {
            "schemaVersion": 2,
            "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
            "openingSelection": {
                "order": "sequential",
                "start": 1,
                "pairs": extension["openingPairs"],
                "extended": True,
            },
            "execution": {
                "mode": "extended-sharded-opening-blocks",
                "baseRunId": extension["baseRunId"],
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
    parser.add_argument("base_directory", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("shard_directories", type=Path, nargs="+")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        extend_confirmation(
            args.output_directory.resolve(),
            args.base_directory.resolve(),
            [path.resolve() for path in args.shard_directories],
        )
        return 0
    except (MergeError, SummaryError, OSError, KeyError, TypeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
