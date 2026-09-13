#!/usr/bin/env python3
"""Summarize an exploratory Arasan-to-Stockfish calibration bracket search."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_strength_eval import bucket_rating, strength_bucket
from summarize_calibration_eval import SummaryError, write_summary


READY_TARGET_STATUSES = {"candidate-passes", "bracketed"}


def _signed_delta(result: dict[str, Any]) -> float:
    delta = result.get("eloDelta")
    if isinstance(delta, (int, float)):
        return float(delta)
    score = result.get("arasanScore")
    if score == 0:
        return -math.inf
    if score == 1:
        return math.inf
    raise SummaryError("complete search result is missing its Elo delta")


def _recommendation(
    lower: dict[str, Any],
    upper: dict[str, Any],
    rating_model: dict[str, int],
) -> dict[str, Any]:
    lower_elo = lower["arasanElo"]
    upper_elo = upper["arasanElo"]
    lower_delta = _signed_delta(lower["result"])
    upper_delta = _signed_delta(upper["result"])
    if math.isfinite(lower_delta) and math.isfinite(upper_delta):
        denominator = upper_delta - lower_delta
        estimate = (
            (lower_elo + upper_elo) / 2
            if denominator == 0
            else lower_elo + (-lower_delta / denominator) * (upper_elo - lower_elo)
        )
        method = "linear interpolation of Elo-delta point estimates"
    else:
        estimate = (lower_elo + upper_elo) / 2
        method = "bracket midpoint because an Elo endpoint is unbounded"
    arasan_elo = round(estimate)
    bucket = strength_bucket(arasan_elo, rating_model)
    return {
        "arasanElo": arasan_elo,
        "internalStrengthBucket": bucket,
        "bucketElo": bucket_rating(bucket, rating_model),
        "method": method,
        "bracket": [lower_elo, upper_elo],
    }


def _candidate_record(
    match: dict[str, Any], rating_model: dict[str, int]
) -> dict[str, Any]:
    arasan_elo = match["arasanElo"]
    result = match["result"]
    bucket = strength_bucket(arasan_elo, rating_model)
    record = {
        "arasanElo": arasan_elo,
        "internalStrengthBucket": bucket,
        "bucketElo": bucket_rating(bucket, rating_model),
        "status": result["status"],
        "complete": result["complete"],
        "games": result["games"],
        "expectedGames": result["expectedGames"],
    }
    for key in (
        "arasanWins",
        "draws",
        "arasanLosses",
        "arasanScore",
        "arasanScoreCi95",
        "eloDelta",
        "eloDeltaCi95",
        "terminationAudit",
    ):
        if key in result:
            record[key] = result[key]
    return record


def _clearly_decreases(lower: dict[str, Any], higher: dict[str, Any]) -> bool:
    """Return true only when confidence intervals establish a decreasing curve."""
    lower_interval = lower["result"].get("eloDeltaCi95")
    higher_interval = higher["result"].get("eloDeltaCi95")
    if isinstance(lower_interval, dict) and isinstance(higher_interval, dict):
        lower_bound = lower_interval.get("lower")
        higher_bound = higher_interval.get("upper")
        if isinstance(lower_bound, (int, float)) and isinstance(
            higher_bound, (int, float)
        ):
            return higher_bound < lower_bound
    return _signed_delta(higher["result"]) < _signed_delta(lower["result"])


def analyze_target(
    preset: str,
    target_elo: int,
    matches: list[dict[str, Any]],
    rating_model: dict[str, int],
) -> dict[str, Any]:
    ordered = sorted(matches, key=lambda match: match["arasanElo"])
    candidates = [_candidate_record(match, rating_model) for match in ordered]
    analysis: dict[str, Any] = {
        "preset": preset,
        "targetElo": target_elo,
        "candidates": candidates,
        "status": "incomplete",
        "recommendation": None,
    }
    if any(not candidate["complete"] for candidate in candidates):
        return analysis
    if any(
        candidate.get("terminationAudit", {}).get("hardFailures")
        for candidate in candidates
    ):
        analysis["status"] = "hard-failure"
        return analysis

    deltas = [_signed_delta(match["result"]) for match in ordered]
    if any(
        _clearly_decreases(lower, higher)
        for lower, higher in zip(ordered, ordered[1:])
    ):
        analysis["status"] = "non-monotonic"
        return analysis

    passing = [
        match for match in ordered if match["result"].get("status") == "pass"
    ]
    if passing:
        selected = min(passing, key=lambda match: abs(_signed_delta(match["result"])))
        bucket = strength_bucket(selected["arasanElo"], rating_model)
        analysis["status"] = "candidate-passes"
        analysis["recommendation"] = {
            "arasanElo": selected["arasanElo"],
            "internalStrengthBucket": bucket,
            "bucketElo": bucket_rating(bucket, rating_model),
            "method": "observed candidate passed the equivalence gate",
            "bracket": [selected["arasanElo"], selected["arasanElo"]],
        }
        return analysis

    for lower, upper in zip(ordered, ordered[1:]):
        lower_delta = _signed_delta(lower["result"])
        upper_delta = _signed_delta(upper["result"])
        if lower_delta <= 0 <= upper_delta:
            analysis["status"] = "bracketed"
            analysis["recommendation"] = _recommendation(
                lower, upper, rating_model
            )
            return analysis

    if all(delta < 0 for delta in deltas):
        analysis["status"] = "expand-higher"
    elif all(delta > 0 for delta in deltas):
        analysis["status"] = "expand-lower"
    else:
        analysis["status"] = "non-monotonic"
    return analysis


def build_search_summary(
    manifest: dict[str, Any], calibration_summary: dict[str, Any]
) -> dict[str, Any]:
    if manifest.get("evaluationType") != "stockfish-anchored-calibration":
        raise SummaryError("manifest is not a Stockfish-anchored calibration")
    calibration = manifest.get("calibration")
    search = calibration.get("search") if isinstance(calibration, dict) else None
    configured = search.get("candidates") if isinstance(search, dict) else None
    if not isinstance(configured, list) or not configured:
        raise SummaryError("manifest does not define a calibration search")
    rating_model = manifest.get("arasanRatingModel")
    if not isinstance(rating_model, dict):
        raise SummaryError("manifest does not record Arasan's rating model")

    presets = manifest.get("presets")
    if not isinstance(presets, list):
        raise SummaryError("manifest.presets must be a list")
    target_by_preset = {
        preset.get("id"): preset.get("requestedElo")
        for preset in presets
        if isinstance(preset, dict) and preset.get("requestedElo") is not None
    }

    matches_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for match in calibration_summary["matches"]:
        key = (match["preset"], match["arasanElo"])
        if key in matches_by_key:
            raise SummaryError(f"duplicate calibration search result: {key}")
        matches_by_key[key] = match

    expected_keys = {
        (candidate["preset"], arasan_elo)
        for candidate in configured
        for arasan_elo in candidate["arasanEloCandidates"]
    }
    unexpected = sorted(set(matches_by_key) - expected_keys)
    if unexpected:
        raise SummaryError(f"unexpected calibration search result(s): {unexpected}")

    targets = []
    for candidate in configured:
        preset = candidate["preset"]
        target_elo = target_by_preset.get(preset)
        if not isinstance(target_elo, int):
            raise SummaryError(f"search target is not a rated preset: {preset}")
        matches = []
        for arasan_elo in candidate["arasanEloCandidates"]:
            match = matches_by_key.get((preset, arasan_elo))
            if match is None:
                match = {
                    "preset": preset,
                    "requestedElo": target_elo,
                    "arasanElo": arasan_elo,
                    "referenceElo": target_elo,
                    "result": {
                        "status": "incomplete",
                        "complete": False,
                        "games": 0,
                        "expectedGames": 2 * calibration["openingPairs"],
                    },
                }
            elif match["referenceElo"] != target_elo:
                raise SummaryError(f"search reference target changed for {preset}")
            matches.append(match)
        targets.append(analyze_target(preset, target_elo, matches, rating_model))

    target_statuses = {target["status"] for target in targets}
    recommendations = [target["recommendation"] for target in targets]
    if "hard-failure" in target_statuses:
        status = "fail"
    elif "incomplete" in target_statuses:
        status = "incomplete"
    elif "non-monotonic" in target_statuses:
        status = "review"
    elif any(value.startswith("expand-") for value in target_statuses):
        status = "expand-brackets"
    elif target_statuses <= READY_TARGET_STATUSES:
        arasan_elos = [value["arasanElo"] for value in recommendations]
        buckets = [value["internalStrengthBucket"] for value in recommendations]
        if all(lower < higher for lower, higher in zip(arasan_elos, arasan_elos[1:])) and all(
            lower < higher for lower, higher in zip(buckets, buckets[1:])
        ):
            status = "ready-for-confirmation"
        else:
            status = "review"
    else:
        status = "review"

    return {
        "schemaVersion": 1,
        "evaluationType": "stockfish-anchored-calibration-search-summary",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "reference": calibration_summary["reference"],
        "method": {
            "timeControl": calibration["timeControl"],
            "openingPairsPerCandidate": calibration["openingPairs"],
            "search": "fixed Stockfish targets with varied Arasan UCI_Elo inputs",
            "recommendation": "linear interpolation between Elo-delta point estimates that straddle zero",
            "scope": "exploratory Stockfish-anchored engine mapping; not human Elo",
            "confirmation": "a recommendation is not accepted until it passes the 200-pair equivalence gate",
        },
        "targets": targets,
        "recommendedMapping": (
            [
                {
                    "preset": target["preset"],
                    "targetElo": target["targetElo"],
                    **target["recommendation"],
                }
                for target in targets
            ]
            if all(recommendations)
            else None
        ),
    }


def _render_delta(candidate: dict[str, Any]) -> str:
    delta = candidate.get("eloDelta")
    rendered = (
        f"{delta:+.1f}"
        if isinstance(delta, (int, float))
        else "+infinity" if candidate.get("arasanScore") == 1 else "-infinity"
    )
    interval = candidate.get("eloDeltaCi95")
    if isinstance(interval, dict):
        lower = interval.get("lower")
        upper = interval.get("upper")
        lower_text = "-infinity" if lower is None else f"{lower:+.1f}"
        upper_text = "+infinity" if upper is None else f"{upper:+.1f}"
        rendered += f" [{lower_text}, {upper_text}]"
    return rendered


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# SixtyFour calibration bracket search",
        "",
        f"Overall status: **{summary['status']}**",
        "",
        "Stockfish remains fixed at each product target while candidate Arasan",
        "UCI_Elo inputs are tested. Suggested inputs interpolate point estimates;",
        "they are hypotheses for the 200-pair equivalence gate, not calibrated",
        "values and not human Elo.",
        "",
        "| Preset | Target | Candidate Elo deltas (95% CI) | Finding | Suggested Arasan input | Bucket |",
        "| --- | ---: | --- | --- | ---: | ---: |",
    ]
    for target in summary["targets"]:
        outcomes = "; ".join(
            f"{candidate['arasanElo']}: {_render_delta(candidate)}"
            for candidate in target["candidates"]
        )
        recommendation = target["recommendation"]
        lines.append(
            f"| {target['preset']} | {target['targetElo']} | {outcomes} "
            f"| **{target['status']}** | "
            f"{recommendation['arasanElo'] if recommendation else '—'} | "
            f"{recommendation['internalStrengthBucket'] if recommendation else '—'} |"
        )
    lines.extend([""])
    if summary["status"] == "ready-for-confirmation":
        lines.extend(
            [
                "Every target has an exploratory bracket or passing candidate, and",
                "the suggested inputs form a strictly increasing bucket mapping.",
                "Run those suggestions through the 200-pair equivalence gate before",
                "changing product values.",
            ]
        )
    elif summary["status"] == "expand-brackets":
        lines.extend(
            [
                "At least one target was not straddled. Expand only the indicated",
                "bracket direction, then regenerate this report.",
            ]
        )
    elif summary["status"] == "review":
        lines.extend(
            [
                "The observed curve has a statistically separated decrease, or the",
                "suggested mapping is not monotonic. Review the affected target before",
                "spending a full confirmation run.",
            ]
        )
    elif summary["status"] == "incomplete":
        lines.append("At least one configured candidate is missing or incomplete.")
    else:
        lines.append("A hard game termination makes this search operationally invalid.")
    lines.append("")
    return "\n".join(lines)


def write_search_summary(results_directory: Path) -> dict[str, Any]:
    calibration_summary = write_summary(results_directory)
    manifest_path = results_directory / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SummaryError(f"cannot read {manifest_path}: {error}") from error
    summary = build_search_summary(manifest, calibration_summary)
    (results_directory / "search-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (results_directory / "search-summary.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_directory", type=Path)
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="return a failing exit code unless every target is ready for confirmation",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        summary = write_search_summary(args.results_directory.resolve())
    except (SummaryError, KeyError, TypeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    output = args.results_directory.resolve() / "search-summary.md"
    print(f"Search summary ({summary['status']}): {output}")
    if args.require_ready and summary["status"] != "ready-for-confirmation":
        print(
            f"error: calibration search is not ready, observed {summary['status']}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
