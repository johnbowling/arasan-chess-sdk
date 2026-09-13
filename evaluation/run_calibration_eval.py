#!/usr/bin/env python3
"""Plan or run SixtyFour's Stockfish-anchored Elo calibration matches.

Each rated Arasan preset plays a pinned Stockfish release. Baseline matches use
the same UCI_Elo for both engines; bracket-search matches hold the Stockfish
target fixed while varying Arasan's UCI_Elo. The resulting score estimates the
preset's offset from that reference scale; it does not establish human playing
strength.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_strength_eval import (
    DEFAULT_CONFIG,
    ConfigError,
    bucket_rating,
    file_record,
    git_revision,
    host_record,
    load_config,
    require_file,
    sha256,
    strength_bucket,
)
from summarize_calibration_eval import SummaryError, write_summary


def _render_option(value: Any) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


def _engine_arguments(
    engine_path: Path,
    engine_directory: Path,
    name: str,
    time_control: str,
    options: dict[str, Any],
    requested_elo: int,
) -> list[str]:
    arguments = [
        f"cmd={engine_path}",
        f"dir={engine_directory}",
        f"name={name}",
        "proto=uci",
        "restart=on",
        f"tc={time_control}",
    ]
    for option_name, value in options.items():
        arguments.append(f"option.{option_name}={_render_option(value)}")
    arguments.extend(
        [
            "option.UCI_LimitStrength=true",
            f"option.UCI_Elo={requested_elo}",
        ]
    )
    return arguments


def match_id(preset: dict[str, Any], arasan_elo: int | None = None) -> str:
    target_elo = preset["requestedElo"]
    if arasan_elo is None or arasan_elo == target_elo:
        return f"calibration__{preset['id']}"
    return f"calibration__{preset['id']}__a{arasan_elo}"


def build_fastchess_command(
    fastchess_path: Path,
    arasan_path: Path,
    arasan_directory: Path,
    reference_path: Path,
    reference_directory: Path,
    openings_path: Path,
    output_directory: Path,
    config: dict[str, Any],
    preset: dict[str, Any],
    arasan_elo: int | None = None,
) -> list[str]:
    calibration = config["calibration"]
    reference = calibration["reference"]
    target_elo = preset["requestedElo"]
    if target_elo is None:
        raise ConfigError("the unrestricted preset cannot be calibrated to a numeric anchor")
    arasan_elo = target_elo if arasan_elo is None else arasan_elo
    run_id = match_id(preset, arasan_elo)
    command = [str(fastchess_path), "-engine"]
    command.extend(
        _engine_arguments(
            arasan_path,
            arasan_directory,
            f"Arasan-{preset['id']}",
            calibration["timeControl"],
            config["engineOptions"],
            arasan_elo,
        )
    )
    command.append("-engine")
    command.extend(
        _engine_arguments(
            reference_path,
            reference_directory,
            f"{reference['id']}-{target_elo}",
            calibration["timeControl"],
            reference["engineOptions"],
            target_elo,
        )
    )
    command.extend(
        [
            "-openings",
            f"file={openings_path}",
            "format=epd",
            "order=random",
            "-srand",
            str(calibration["openingSeed"]),
            "-rounds",
            str(calibration["openingPairs"]),
            "-repeat",
            "-concurrency",
            str(calibration["concurrency"]),
            "-maxmoves",
            str(calibration["maxMoves"]),
            "-recover",
            "-config",
            f"outname={output_directory / (run_id + '.fastchess.json')}",
            "-event",
            f"{calibration['name']}: {preset['label']} target {target_elo}, "
            f"Arasan input {arasan_elo}",
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


def select_presets(
    presets: list[dict[str, Any]], requested: list[str]
) -> list[dict[str, Any]]:
    rated = [preset for preset in presets if preset["requestedElo"] is not None]
    available = {preset["id"]: preset for preset in rated}
    if not requested:
        return rated
    unknown = sorted(set(requested) - set(available))
    if unknown:
        raise ConfigError(
            "unknown or unrestricted preset(s): "
            + ", ".join(unknown)
            + "; valid presets: "
            + ", ".join(available)
        )
    return [available[preset_id] for preset_id in requested]


def build_manifest(
    args: argparse.Namespace,
    config: dict[str, Any],
    commands: list[dict[str, Any]],
    include_hashes: bool,
) -> dict[str, Any]:
    model = config["arasanRatingModel"]
    enriched_presets = []
    for preset in config["presets"]:
        if preset["requestedElo"] is None:
            continue
        bucket = strength_bucket(preset["requestedElo"], model)
        enriched_presets.append(
            {
                **preset,
                "internalStrengthBucket": bucket,
                "bucketElo": bucket_rating(bucket, model),
            }
        )
    return {
        "schemaVersion": 1,
        "evaluationType": "stockfish-anchored-calibration",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "sdkRevision": git_revision(Path(__file__).resolve().parent.parent),
        "host": host_record(),
        "inputs": {
            "config": file_record(args.config, include_hashes),
            "fastchess": file_record(args.fastchess, include_hashes),
            "arasan": file_record(args.arasan, include_hashes),
            "arasanDirectory": str(args.arasan_directory),
            "reference": file_record(args.reference, include_hashes),
            "referenceDirectory": str(args.reference_directory),
            "openings": file_record(args.openings, include_hashes),
        },
        "openingSuite": (
            config["openingSuite"]
            if args.uses_configured_openings
            else {"id": "custom", "format": "epd"}
        ),
        "calibration": config["calibration"],
        "arasanRatingModel": model,
        "engineOptions": {
            "arasan": config["engineOptions"],
            "reference": config["calibration"]["reference"]["engineOptions"],
        },
        "presets": enriched_presets,
        "matches": commands,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "run"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--fastchess", type=Path, required=True)
    parser.add_argument("--arasan", type=Path, required=True)
    parser.add_argument("--arasan-directory", type=Path)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--reference-directory", type=Path)
    parser.add_argument(
        "--openings",
        type=Path,
        help="EPD opening suite (defaults to the suite pinned by --config)",
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--opening-pairs", type=int, help="override the pair count")
    parser.add_argument("--concurrency", type=int, help="override the concurrency")
    parser.add_argument("--opening-seed", type=int, help="override the opening seed")
    parser.add_argument(
        "--time-control",
        help="override BASE+INCREMENT seconds (for example 120+1)",
    )
    parser.add_argument(
        "--tolerance-elo",
        type=int,
        help="override the symmetric equivalence tolerance",
    )
    parser.add_argument(
        "--preset",
        action="append",
        default=[],
        help="run only the named rated preset; may be supplied more than once",
    )
    parser.add_argument(
        "--arasan-elo",
        type=int,
        help="override Arasan's UCI_Elo for one selected preset while keeping its reference target fixed",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    args.config = args.config.resolve()
    args.fastchess = args.fastchess.resolve()
    args.arasan = args.arasan.resolve()
    args.reference = args.reference.resolve()
    if args.openings is not None:
        args.openings = args.openings.resolve()
    args.output_directory = args.output_directory.resolve()
    args.arasan_directory = (
        args.arasan_directory.resolve() if args.arasan_directory else args.arasan.parent
    )
    args.reference_directory = (
        args.reference_directory.resolve()
        if args.reference_directory
        else args.reference.parent
    )

    try:
        require_file(args.config, "config")
        config = load_config(args.config)
        calibration = config["calibration"]
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
            ("tolerance_elo", "equivalenceToleranceElo"),
        ):
            override = getattr(args, argument_name)
            if override is not None:
                if override <= 0:
                    raise ConfigError(f"--{argument_name.replace('_', '-')} must be positive")
                calibration[config_name] = override
        if args.time_control is not None:
            if not re.fullmatch(r"\d+(?:\.\d+)?\+\d+(?:\.\d+)?", args.time_control):
                raise ConfigError("--time-control must use BASE+INCREMENT seconds")
            calibration["timeControl"] = args.time_control
        presets = select_presets(config["presets"], args.preset)
        if args.arasan_elo is not None:
            if len(presets) != 1:
                raise ConfigError("--arasan-elo requires exactly one --preset")
            rating_model = config["arasanRatingModel"]
            if not (
                rating_model["minimumElo"]
                <= args.arasan_elo
                <= rating_model["maximumElo"]
            ):
                raise ConfigError("--arasan-elo is outside Arasan's Elo range")

        if args.mode == "run":
            require_file(args.fastchess, "fastchess", executable=True)
            require_file(args.arasan, "Arasan", executable=True)
            require_file(args.reference, "reference engine", executable=True)
            require_file(args.openings, "openings")
            if args.uses_configured_openings:
                expected_openings_hash = config["openingSuite"]["sha256"]
                if sha256(args.openings) != expected_openings_hash:
                    raise ConfigError(
                        "configured opening suite hash does not match the pinned configuration"
                    )
            if not args.arasan_directory.is_dir():
                raise ConfigError(
                    f"Arasan directory does not exist: {args.arasan_directory}"
                )
            if not args.reference_directory.is_dir():
                raise ConfigError(
                    "reference engine directory does not exist: "
                    f"{args.reference_directory}"
                )

        commands = []
        for preset in presets:
            command = build_fastchess_command(
                args.fastchess,
                args.arasan,
                args.arasan_directory,
                args.reference,
                args.reference_directory,
                args.openings,
                args.output_directory,
                config,
                preset,
                args.arasan_elo,
            )
            target_elo = preset["requestedElo"]
            arasan_elo = target_elo if args.arasan_elo is None else args.arasan_elo
            commands.append(
                {
                    "id": match_id(preset, arasan_elo),
                    "preset": preset["id"],
                    "requestedElo": target_elo,
                    "arasanElo": arasan_elo,
                    "referenceElo": target_elo,
                    "argv": command,
                }
            )

        manifest = build_manifest(
            args, config, commands, include_hashes=args.mode == "run"
        )
        if args.mode == "plan":
            json.dump(manifest, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 0

        args.output_directory.mkdir(parents=True, exist_ok=True)
        (args.output_directory / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        for match in commands:
            print(f"Running {match['id']}...", flush=True)
            try:
                result = subprocess.run(match["argv"], check=False)
            except KeyboardInterrupt:
                print(
                    f"\nCalibration interrupted during {match['id']}; "
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
        print(f"Calibration complete: {args.output_directory}")
        return 0
    except (ConfigError, SummaryError, json.JSONDecodeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
