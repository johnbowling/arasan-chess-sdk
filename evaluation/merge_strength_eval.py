#!/usr/bin/env python3
"""Merge independently executed strength-evaluation shards."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MATCH_ID_PATTERN = re.compile(r"^[a-z0-9-]+__[a-z0-9-]+_vs_[a-z0-9-]+$")
MATCH_SUFFIXES = ("fastchess.json", "log", "pgn")
COMPATIBILITY_FIELDS = (
    "schemaVersion",
    "sdkRevision",
    "openingSuite",
    "study",
    "lanes",
    "engineOptions",
    "presets",
)


class MergeError(ValueError):
    """Raised when shard artifacts cannot form one trustworthy study."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise MergeError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise MergeError(f"expected a JSON object in {path}")
    return value


def _input_hashes(manifest: dict[str, Any]) -> dict[str, str]:
    inputs = manifest.get("inputs")
    if not isinstance(inputs, dict):
        raise MergeError("manifest.inputs must be an object")
    hashes = {}
    for name in ("config", "fastchess", "engine", "openings"):
        value = inputs.get(name)
        if not isinstance(value, dict) or not isinstance(value.get("sha256"), str):
            raise MergeError(f"manifest.inputs.{name}.sha256 must be a string")
        hashes[name] = value["sha256"]
    return hashes


def expected_match_ids(manifest: dict[str, Any]) -> list[str]:
    lanes = manifest.get("lanes")
    presets = manifest.get("presets")
    if not isinstance(lanes, list) or not lanes:
        raise MergeError("manifest.lanes must contain at least one lane")
    if not isinstance(presets, list) or len(presets) < 2:
        raise MergeError("manifest.presets must contain at least two presets")
    lane_ids = [lane.get("id") if isinstance(lane, dict) else None for lane in lanes]
    preset_ids = [
        preset.get("id") if isinstance(preset, dict) else None for preset in presets
    ]
    if not all(isinstance(value, str) and value for value in lane_ids + preset_ids):
        raise MergeError("lane and preset ids must be non-empty strings")
    return [
        f"{lane_id}__{lower_id}_vs_{higher_id}"
        for lane_id in lane_ids
        for lower_id, higher_id in zip(preset_ids, preset_ids[1:])
    ]


def _assert_compatible(
    baseline: dict[str, Any], candidate: dict[str, Any], shard: Path
) -> None:
    for field in COMPATIBILITY_FIELDS:
        if candidate.get(field) != baseline.get(field):
            raise MergeError(f"incompatible {field} in {shard / 'manifest.json'}")
    if _input_hashes(candidate) != _input_hashes(baseline):
        raise MergeError(f"incompatible input hashes in {shard / 'manifest.json'}")


def merge_shards(
    output_directory: Path,
    shard_directories: list[Path],
    require_complete_ladder: bool = False,
) -> dict[str, Any]:
    if not shard_directories:
        raise MergeError("at least one shard directory is required")
    if output_directory.exists() and any(output_directory.iterdir()):
        raise MergeError(f"output directory is not empty: {output_directory}")

    baseline: dict[str, Any] | None = None
    matches: dict[str, tuple[Path, dict[str, Any], dict[str, Any]]] = {}
    for shard in shard_directories:
        manifest = _load_json(shard / "manifest.json")
        if baseline is None:
            baseline = manifest
            _input_hashes(baseline)
        else:
            _assert_compatible(baseline, manifest, shard)
        shard_matches = manifest.get("matches")
        if not isinstance(shard_matches, list) or len(shard_matches) != 1:
            raise MergeError(f"shard must contain exactly one match: {shard}")
        match = shard_matches[0]
        match_id = match.get("id") if isinstance(match, dict) else None
        if not isinstance(match_id, str) or not MATCH_ID_PATTERN.fullmatch(match_id):
            raise MergeError(f"invalid match id in {shard / 'manifest.json'}")
        if match_id in matches:
            raise MergeError(f"duplicate match id: {match_id}")
        matches[match_id] = (shard, manifest, match)

    assert baseline is not None
    expected = expected_match_ids(baseline)
    if require_complete_ladder and set(matches) != set(expected):
        missing = sorted(set(expected) - set(matches))
        unexpected = sorted(set(matches) - set(expected))
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if unexpected:
            details.append("unexpected: " + ", ".join(unexpected))
        raise MergeError("incomplete ladder (" + "; ".join(details) + ")")

    ordered_ids = [match_id for match_id in expected if match_id in matches]
    ordered_ids.extend(sorted(set(matches) - set(ordered_ids)))
    output_directory.mkdir(parents=True, exist_ok=True)
    execution_shards = []
    for match_id in ordered_ids:
        shard, manifest, _ = matches[match_id]
        for suffix in MATCH_SUFFIXES:
            source = shard / f"{match_id}.{suffix}"
            if not source.is_file():
                raise MergeError(f"missing shard artifact: {source}")
            shutil.copy2(source, output_directory / source.name)
        console = shard / "console.log"
        if not console.is_file():
            raise MergeError(f"missing shard artifact: {console}")
        shutil.copy2(console, output_directory / f"{match_id}.console.log")
        execution_shards.append(
            {
                "matchId": match_id,
                "generatedAtUtc": manifest.get("generatedAtUtc"),
                "host": manifest.get("host"),
            }
        )

    merged = {
        key: value
        for key, value in baseline.items()
        if key not in {"schemaVersion", "generatedAtUtc", "host", "matches"}
    }
    merged.update(
        {
            "schemaVersion": 2,
            "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
            "execution": {
                "mode": "sharded",
                "shards": execution_shards,
            },
            "matches": [matches[match_id][2] for match_id in ordered_ids],
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
    parser.add_argument(
        "--require-complete-ladder",
        action="store_true",
        help="require every adjacent pair for every selected lane",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        merge_shards(
            args.output_directory.resolve(),
            [path.resolve() for path in args.shard_directories],
            args.require_complete_ladder,
        )
        return 0
    except (MergeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
