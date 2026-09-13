#!/usr/bin/env python3
"""Plan or run SixtyFour's Arasan difficulty monotonicity matches.

The runner intentionally delegates chess rules, clocks, paired openings, and
PGN output to fastchess. It owns the SixtyFour-specific configuration and the
reproducibility manifest around each run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from summarize_strength_eval import SummaryError, write_summary


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = SCRIPT_DIR / "sixtyfour-strength.json"
DEFAULT_OPENINGS = SCRIPT_DIR / "openings/4mvs_+90_+99.epd"


class ConfigError(ValueError):
    """Raised when an evaluation configuration is invalid."""


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    if config.get("schemaVersion") != 1:
        raise ConfigError("schemaVersion must be 1")

    study = config.get("study")
    if not isinstance(study, dict):
        raise ConfigError("study must be an object")
    for key in ("openingPairs", "openingSeed", "concurrency", "maxMoves"):
        if not isinstance(study.get(key), int) or study[key] <= 0:
            raise ConfigError(f"study.{key} must be a positive integer")

    opening_suite = config.get("openingSuite")
    if not isinstance(opening_suite, dict):
        raise ConfigError("openingSuite must be an object")
    for key in (
        "id",
        "file",
        "format",
        "sha256",
        "sourceRepository",
        "sourceRevision",
        "sourceArchiveSha256",
        "license",
    ):
        if not isinstance(opening_suite.get(key), str) or not opening_suite[key]:
            raise ConfigError(f"openingSuite.{key} must be a non-empty string")
    for key in ("positions", "plies"):
        if not isinstance(opening_suite.get(key), int) or opening_suite[key] <= 0:
            raise ConfigError(f"openingSuite.{key} must be a positive integer")
    if opening_suite["format"] != "epd":
        raise ConfigError("openingSuite.format must be epd")

    lanes = config.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        raise ConfigError("lanes must contain at least one entry")
    seen_lane_ids: set[str] = set()
    for index, lane in enumerate(lanes):
        if not isinstance(lane, dict):
            raise ConfigError(f"lanes[{index}] must be an object")
        lane_id = lane.get("id")
        if not isinstance(lane_id, str) or not lane_id:
            raise ConfigError(f"lanes[{index}].id must be a non-empty string")
        if lane_id in seen_lane_ids:
            raise ConfigError(f"duplicate lane id: {lane_id}")
        seen_lane_ids.add(lane_id)
        if not isinstance(lane.get("label"), str) or not lane["label"]:
            raise ConfigError(f"lanes[{index}].label must be a non-empty string")
        search = lane.get("search")
        if not isinstance(search, dict):
            raise ConfigError(f"lanes[{index}].search must be an object")
        search_type = search.get("type")
        if search_type == "depth":
            value = search.get("value")
        elif search_type == "movetime":
            value = search.get("milliseconds")
            margin = search.get("marginMilliseconds")
            if not isinstance(margin, int) or margin < 0:
                raise ConfigError(
                    f"lanes[{index}].search.marginMilliseconds must be a non-negative integer"
                )
        else:
            raise ConfigError(f"unsupported lane search type: {search_type}")
        if not isinstance(value, int) or value <= 0:
            raise ConfigError(f"lanes[{index}] search limit must be a positive integer")

    rating_model = config.get("arasanRatingModel")
    if not isinstance(rating_model, dict):
        raise ConfigError("arasanRatingModel must be an object")
    minimum = rating_model.get("minimumElo")
    maximum = rating_model.get("maximumElo")
    minimum_strength = rating_model.get("minimumStrength")
    maximum_strength = rating_model.get("maximumStrength")
    if not all(
        isinstance(value, int)
        for value in (minimum, maximum, minimum_strength, maximum_strength)
    ):
        raise ConfigError("Arasan rating model values must be integers")
    if minimum >= maximum or minimum_strength != 0 or maximum_strength <= 0:
        raise ConfigError("Arasan rating model range is invalid")

    engine_options = config.get("engineOptions")
    if not isinstance(engine_options, dict) or not engine_options:
        raise ConfigError("engineOptions must be a non-empty object")

    calibration = config.get("calibration")
    if not isinstance(calibration, dict):
        raise ConfigError("calibration must be an object")
    for key in ("name", "timeControl"):
        if not isinstance(calibration.get(key), str) or not calibration[key]:
            raise ConfigError(f"calibration.{key} must be a non-empty string")
    if not re.fullmatch(r"\d+(?:\.\d+)?\+\d+(?:\.\d+)?", calibration["timeControl"]):
        raise ConfigError("calibration.timeControl must use BASE+INCREMENT seconds")
    for key in (
        "openingPairs",
        "openingSeed",
        "concurrency",
        "maxMoves",
        "equivalenceToleranceElo",
    ):
        if not isinstance(calibration.get(key), int) or calibration[key] <= 0:
            raise ConfigError(f"calibration.{key} must be a positive integer")
    reference = calibration.get("reference")
    if not isinstance(reference, dict):
        raise ConfigError("calibration.reference must be an object")
    for key in (
        "id",
        "name",
        "repository",
        "tag",
        "revision",
        "license",
        "ratingScale",
    ):
        if not isinstance(reference.get(key), str) or not reference[key]:
            raise ConfigError(f"calibration.reference.{key} must be a non-empty string")
    if not re.fullmatch(r"[0-9a-f]{40}", reference["revision"]):
        raise ConfigError("calibration.reference.revision must be a full Git commit hash")
    reference_minimum = reference.get("minimumElo")
    reference_maximum = reference.get("maximumElo")
    if (
        not isinstance(reference_minimum, int)
        or not isinstance(reference_maximum, int)
        or reference_minimum >= reference_maximum
    ):
        raise ConfigError("calibration reference Elo range is invalid")
    reference_options = reference.get("engineOptions")
    if not isinstance(reference_options, dict) or not reference_options:
        raise ConfigError("calibration.reference.engineOptions must be a non-empty object")

    presets = config.get("presets")
    if not isinstance(presets, list) or len(presets) < 2:
        raise ConfigError("presets must contain at least two entries")
    seen_ids: set[str] = set()
    rated_preset_ids: set[str] = set()
    last_rating: int | None = None
    maximum_seen = False
    for index, preset in enumerate(presets):
        if not isinstance(preset, dict):
            raise ConfigError(f"presets[{index}] must be an object")
        preset_id = preset.get("id")
        if not isinstance(preset_id, str) or not preset_id:
            raise ConfigError(f"presets[{index}].id must be a non-empty string")
        if preset_id in seen_ids:
            raise ConfigError(f"duplicate preset id: {preset_id}")
        seen_ids.add(preset_id)
        if not isinstance(preset.get("label"), str) or not preset["label"]:
            raise ConfigError(f"presets[{index}].label must be a non-empty string")

        rating = preset.get("requestedElo")
        expected_depth_cap = preset.get("expectedDepthCap")
        if rating is None:
            if index != len(presets) - 1:
                raise ConfigError("the unrestricted preset must be last")
            if expected_depth_cap is not None:
                raise ConfigError("the unrestricted preset cannot have a depth cap")
            maximum_seen = True
            continue
        if maximum_seen or not isinstance(rating, int):
            raise ConfigError(f"presets[{index}].requestedElo must be an integer or final null")
        if rating < minimum or rating > maximum:
            raise ConfigError(f"preset {preset_id} is outside Arasan's Elo range")
        if rating < reference_minimum or rating > reference_maximum:
            raise ConfigError(f"preset {preset_id} is outside the calibration reference Elo range")
        if last_rating is not None and rating <= last_rating:
            raise ConfigError("rated presets must be strictly increasing")
        if not isinstance(expected_depth_cap, int) or expected_depth_cap <= 0:
            raise ConfigError(f"preset {preset_id} must have a positive expectedDepthCap")
        rated_preset_ids.add(preset_id)
        last_rating = rating

    search = calibration.get("search")
    if not isinstance(search, dict):
        raise ConfigError("calibration.search must be an object")
    if not isinstance(search.get("name"), str) or not search["name"]:
        raise ConfigError("calibration.search.name must be a non-empty string")
    if not isinstance(search.get("openingPairs"), int) or search["openingPairs"] <= 0:
        raise ConfigError("calibration.search.openingPairs must be a positive integer")
    candidates = search.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ConfigError("calibration.search.candidates must contain entries")
    search_preset_ids: set[str] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ConfigError(f"calibration.search.candidates[{index}] must be an object")
        preset_id = candidate.get("preset")
        if preset_id not in rated_preset_ids:
            raise ConfigError(
                f"calibration.search.candidates[{index}].preset must name a rated preset"
            )
        if preset_id in search_preset_ids:
            raise ConfigError(f"duplicate calibration search preset: {preset_id}")
        search_preset_ids.add(preset_id)
        elo_candidates = candidate.get("arasanEloCandidates")
        if not isinstance(elo_candidates, list) or len(elo_candidates) < 2:
            raise ConfigError(
                f"calibration.search.candidates[{index}].arasanEloCandidates "
                "must contain at least two integers"
            )
        if any(
            not isinstance(value, int) or value < minimum or value > maximum
            for value in elo_candidates
        ):
            raise ConfigError(
                f"calibration.search.candidates[{index}] is outside Arasan's Elo range"
            )
        if any(
            lower >= higher
            for lower, higher in zip(elo_candidates, elo_candidates[1:])
        ):
            raise ConfigError(
                f"calibration.search.candidates[{index}].arasanEloCandidates "
                "must be strictly increasing"
            )
    if search_preset_ids != rated_preset_ids:
        missing = sorted(rated_preset_ids - search_preset_ids)
        raise ConfigError(
            "calibration.search.candidates must cover every rated preset; missing: "
            + ", ".join(missing)
        )


def strength_bucket(requested_elo: int | None, rating_model: dict[str, int]) -> int:
    """Mirror Options::getStrength in src/options.h."""
    if requested_elo is None:
        return rating_model["maximumStrength"]
    minimum = rating_model["minimumElo"]
    maximum = rating_model["maximumElo"]
    maximum_strength = rating_model["maximumStrength"]
    raw = maximum_strength * (requested_elo - minimum) // (maximum - minimum)
    return max(0, min(maximum_strength, raw))


def bucket_rating(bucket: int, rating_model: dict[str, int]) -> int:
    """Mirror Options::getRating in src/options.h."""
    minimum = rating_model["minimumElo"]
    maximum = rating_model["maximumElo"]
    maximum_strength = rating_model["maximumStrength"]
    return minimum + bucket * (maximum - minimum) // maximum_strength


def adjacent_pairs(presets: list[dict[str, Any]]) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
    return zip(presets, presets[1:])


def engine_arguments(
    engine_path: Path,
    engine_directory: Path,
    lane: dict[str, Any],
    preset: dict[str, Any],
    config: dict[str, Any],
) -> list[str]:
    arguments = [
        f"cmd={engine_path}",
        f"dir={engine_directory}",
        f"name=Arasan-{lane['id']}-{preset['id']}",
        "proto=uci",
        "restart=on",
    ]
    search = lane["search"]
    if search["type"] == "depth":
        arguments.append(f"plies={search['value']}")
    else:
        move_time_seconds = search["milliseconds"] / 1000
        arguments.append(f"st={move_time_seconds:g}")
        arguments.append(f"timemargin={search['marginMilliseconds']}")
    for name, value in config["engineOptions"].items():
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        arguments.append(f"option.{name}={rendered}")

    requested_elo = preset["requestedElo"]
    arguments.append(f"option.UCI_LimitStrength={'false' if requested_elo is None else 'true'}")
    if requested_elo is not None:
        arguments.append(f"option.UCI_Elo={requested_elo}")
    return arguments


def pair_id(
    lane: dict[str, Any], lower: dict[str, Any], higher: dict[str, Any]
) -> str:
    return f"{lane['id']}__{lower['id']}_vs_{higher['id']}"


def build_fastchess_command(
    fastchess_path: Path,
    engine_path: Path,
    engine_directory: Path,
    openings_path: Path,
    output_directory: Path,
    config: dict[str, Any],
    lane: dict[str, Any],
    lower: dict[str, Any],
    higher: dict[str, Any],
) -> list[str]:
    study = config["study"]
    run_id = pair_id(lane, lower, higher)
    command = [str(fastchess_path), "-engine"]
    command.extend(engine_arguments(engine_path, engine_directory, lane, lower, config))
    command.append("-engine")
    command.extend(engine_arguments(engine_path, engine_directory, lane, higher, config))
    command.extend(
        [
            "-openings",
            f"file={openings_path}",
            "format=epd",
            "order=random",
            "-srand",
            str(study["openingSeed"]),
            "-rounds",
            str(study["openingPairs"]),
            "-repeat",
            "-concurrency",
            str(study["concurrency"]),
            "-maxmoves",
            str(study["maxMoves"]),
            "-recover",
            "-config",
            f"outname={output_directory / (run_id + '.fastchess.json')}",
            "-event",
            f"{study['name']} ({lane['label']}): {lower['label']} vs {higher['label']}",
            "-pgnout",
            f"file={output_directory / (run_id + '.pgn')}",
            "notation=san",
            "append=false",
            "nodes=true",
            "seldepth=true",
            "nps=true",
            "hashfull=true",
            "latency=true",
            "-log",
            f"file={output_directory / (run_id + '.log')}",
            "level=info",
            "append=false",
            "engine=false",
        ]
    )
    return command


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path, include_hash: bool) -> dict[str, Any]:
    record: dict[str, Any] = {"path": str(path)}
    if include_hash:
        record["sha256"] = sha256(path)
    return record


def git_revision(repository: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def cpu_model() -> str:
    """Return a useful CPU description without requiring platform-specific tools."""
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        try:
            for line in cpuinfo.read_text(encoding="utf-8").splitlines():
                if line.lower().startswith("model name") and ":" in line:
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    if platform.system() == "Darwin":
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return platform.processor() or platform.machine() or "unknown"


def host_record() -> dict[str, Any]:
    record: dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpuModel": cpu_model(),
        "cpuCount": os.cpu_count(),
    }
    if os.environ.get("GITHUB_ACTIONS") == "true":
        record["ci"] = {
            "provider": "GitHub Actions",
            "runnerOs": os.environ.get("RUNNER_OS"),
            "runnerArch": os.environ.get("RUNNER_ARCH"),
            "runnerEnvironment": os.environ.get("RUNNER_ENVIRONMENT"),
        }
    return record


def build_manifest(
    args: argparse.Namespace,
    config: dict[str, Any],
    commands: list[dict[str, Any]],
    include_hashes: bool,
) -> dict[str, Any]:
    model = config["arasanRatingModel"]
    presets = []
    for preset in config["presets"]:
        bucket = strength_bucket(preset["requestedElo"], model)
        presets.append(
            {
                **preset,
                "internalStrengthBucket": bucket,
                "bucketElo": bucket_rating(bucket, model),
                "limited": preset["requestedElo"] is not None,
            }
        )
    return {
        "schemaVersion": 1,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "sdkRevision": git_revision(SCRIPT_DIR.parent),
        "host": host_record(),
        "inputs": {
            "config": file_record(args.config, include_hashes),
            "fastchess": file_record(args.fastchess, include_hashes),
            "engine": file_record(args.engine, include_hashes),
            "engineDirectory": str(args.engine_directory),
            "openings": file_record(args.openings, include_hashes),
        },
        "openingSuite": (
            config["openingSuite"]
            if args.uses_configured_openings
            else {"id": "custom", "format": "epd"}
        ),
        "study": config["study"],
        "lanes": config["lanes"],
        "engineOptions": config["engineOptions"],
        "presets": presets,
        "matches": commands,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "run"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--fastchess", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--engine-directory", type=Path)
    parser.add_argument(
        "--openings",
        type=Path,
        help="EPD opening suite (defaults to the suite pinned by --config)",
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--opening-pairs", type=int, help="override the configured pair count")
    parser.add_argument("--concurrency", type=int, help="override the configured concurrency")
    parser.add_argument("--opening-seed", type=int, help="override the configured opening seed")
    parser.add_argument("--depth", type=int, help="override every selected depth lane")
    parser.add_argument(
        "--move-time-ms", type=int, help="override every selected movetime lane"
    )
    parser.add_argument(
        "--lane",
        action="append",
        default=[],
        help="run only the named lane; may be supplied more than once",
    )
    parser.add_argument(
        "--pair",
        action="append",
        default=[],
        metavar="LOWER:HIGHER",
        help="run only one adjacent pair; may be supplied more than once",
    )
    return parser.parse_args(argv)


def select_pairs(
    presets: list[dict[str, Any]], requested: list[str]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs = list(adjacent_pairs(presets))
    if not requested:
        return pairs
    available = {f"{lower['id']}:{higher['id']}": (lower, higher) for lower, higher in pairs}
    unknown = sorted(set(requested) - set(available))
    if unknown:
        raise ConfigError(
            "unknown or non-adjacent pair(s): "
            + ", ".join(unknown)
            + "; valid pairs: "
            + ", ".join(available)
        )
    return [available[pair] for pair in requested]


def select_lanes(
    lanes: list[dict[str, Any]], requested: list[str]
) -> list[dict[str, Any]]:
    if not requested:
        return lanes
    available = {lane["id"]: lane for lane in lanes}
    unknown = sorted(set(requested) - set(available))
    if unknown:
        raise ConfigError(
            "unknown lane(s): "
            + ", ".join(unknown)
            + "; valid lanes: "
            + ", ".join(available)
        )
    return [available[lane_id] for lane_id in requested]


def require_file(path: Path, label: str, executable: bool = False) -> None:
    if not path.is_file():
        raise ConfigError(f"{label} does not exist or is not a file: {path}")
    if executable and not os.access(path, os.X_OK):
        raise ConfigError(f"{label} is not executable: {path}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    args.config = args.config.resolve()
    args.fastchess = args.fastchess.resolve()
    args.engine = args.engine.resolve()
    if args.openings is not None:
        args.openings = args.openings.resolve()
    args.output_directory = args.output_directory.resolve()
    args.engine_directory = (
        args.engine_directory.resolve() if args.engine_directory else args.engine.parent
    )

    try:
        require_file(args.config, "config")
        config = load_config(args.config)
        args.uses_configured_openings = args.openings is None
        if args.uses_configured_openings:
            configured_openings = Path(config["openingSuite"]["file"])
            if not configured_openings.is_absolute():
                configured_openings = args.config.parent / configured_openings
            args.openings = configured_openings.resolve()
        for argument_name, config_name in (
            ("opening_pairs", "openingPairs"),
            ("concurrency", "concurrency"),
            ("opening_seed", "openingSeed"),
        ):
            override = getattr(args, argument_name)
            if override is not None:
                if override <= 0:
                    raise ConfigError(f"--{argument_name.replace('_', '-')} must be positive")
                config["study"][config_name] = override
        for argument_name in ("depth", "move_time_ms"):
            override = getattr(args, argument_name)
            if override is not None and override <= 0:
                raise ConfigError(f"--{argument_name.replace('_', '-')} must be positive")
        lanes = select_lanes(config["lanes"], args.lane)
        config["lanes"] = lanes
        for lane in lanes:
            search = lane["search"]
            if search["type"] == "depth" and args.depth is not None:
                search["value"] = args.depth
            elif search["type"] == "movetime" and args.move_time_ms is not None:
                search["milliseconds"] = args.move_time_ms
        pairs = select_pairs(config["presets"], args.pair)
        if args.mode == "run":
            require_file(args.fastchess, "fastchess", executable=True)
            require_file(args.engine, "engine", executable=True)
            require_file(args.openings, "openings")
            if args.uses_configured_openings:
                expected_openings_hash = config["openingSuite"]["sha256"]
                actual_openings_hash = sha256(args.openings)
                if actual_openings_hash != expected_openings_hash:
                    raise ConfigError(
                        "configured opening suite hash does not match the pinned configuration"
                    )
            if not args.engine_directory.is_dir():
                raise ConfigError(f"engine directory does not exist: {args.engine_directory}")

        commands = []
        for lane in lanes:
            for lower, higher in pairs:
                command = build_fastchess_command(
                    args.fastchess,
                    args.engine,
                    args.engine_directory,
                    args.openings,
                    args.output_directory,
                    config,
                    lane,
                    lower,
                    higher,
                )
                commands.append(
                    {
                        "id": pair_id(lane, lower, higher),
                        "lane": lane["id"],
                        "lowerPreset": lower["id"],
                        "higherPreset": higher["id"],
                        "argv": command,
                    }
                )

        manifest = build_manifest(args, config, commands, include_hashes=args.mode == "run")
        if args.mode == "plan":
            json.dump(manifest, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 0

        args.output_directory.mkdir(parents=True, exist_ok=True)
        manifest_path = args.output_directory / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        for match in commands:
            print(f"Running {match['id']}...", flush=True)
            try:
                result = subprocess.run(match["argv"], check=False)
            except KeyboardInterrupt:
                print(
                    f"\nEvaluation interrupted during {match['id']}; "
                    f"partial artifacts remain in {args.output_directory}",
                    file=sys.stderr,
                )
                return 130
            if result.returncode != 0:
                print(
                    f"{match['id']} failed with exit code {result.returncode}; "
                    f"partial artifacts remain in {args.output_directory}",
                    file=sys.stderr,
                )
                return result.returncode
            write_summary(args.output_directory)
        print(f"Evaluation complete: {args.output_directory}")
        return 0
    except (ConfigError, SummaryError, json.JSONDecodeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
