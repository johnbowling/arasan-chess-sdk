#!/usr/bin/env python3
"""Summarize completed fastchess matches from a SixtyFour evaluation run."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CI95_Z_SCORE = 1.959963984540054


class SummaryError(ValueError):
    """Raised when evaluation artifacts cannot be summarized."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise SummaryError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise SummaryError(f"expected a JSON object in {path}")
    return value


def _round(value: float) -> float:
    return round(value, 6)


def summarize_stats(stats: dict[str, Any], expected_games: int) -> dict[str, Any]:
    """Summarize paired statistics from the higher preset's perspective."""
    integer_fields = (
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
    for field in integer_fields:
        if not isinstance(stats.get(field), int) or stats[field] < 0:
            raise SummaryError(f"fastchess stat {field} must be a non-negative integer")

    games = stats["wins"] + stats["losses"] + stats["draws"]
    pairs = sum(
        stats[field]
        for field in (
            "penta_WW",
            "penta_WD",
            "penta_WL",
            "penta_DD",
            "penta_LD",
            "penta_LL",
        )
    )
    complete = games == expected_games
    if games == 0 or pairs == 0:
        return {
            "status": "incomplete",
            "complete": complete,
            "expectedGames": expected_games,
            "games": games,
            "pairs": pairs,
        }

    # fastchess records stats from the first engine's perspective. The
    # manifest always puts the lower preset first, so reverse the pentanomial
    # buckets to evaluate the higher preset.
    higher_penta = {
        "WW": stats["penta_LL"],
        "WD": stats["penta_LD"],
        "WLDD": stats["penta_WL"] + stats["penta_DD"],
        "LD": stats["penta_WD"],
        "LL": stats["penta_WW"],
    }
    if sum(higher_penta.values()) != pairs or games != 2 * pairs:
        raise SummaryError("fastchess game and pentanomial counts are inconsistent")

    weights = {"WW": 1.0, "WD": 0.75, "WLDD": 0.5, "LD": 0.25, "LL": 0.0}
    score = sum(higher_penta[key] * weights[key] for key in weights) / pairs
    variance = sum(
        higher_penta[key] / pairs * (weights[key] - score) ** 2 for key in weights
    )
    standard_error = math.sqrt(variance / pairs)
    margin = CI95_Z_SCORE * standard_error
    raw_lower = score - margin
    raw_upper = score + margin

    if standard_error == 0:
        los = 1.0 if score > 0.5 else 0.0 if score < 0.5 else 0.5
    else:
        z_score = (score - 0.5) / standard_error
        los = 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))

    if not complete:
        status = "incomplete"
    elif raw_lower > 0.5:
        status = "pass"
    elif raw_upper <= 0.5:
        status = "fail"
    else:
        status = "inconclusive"

    return {
        "status": status,
        "complete": complete,
        "expectedGames": expected_games,
        "games": games,
        "pairs": pairs,
        "higherWins": stats["losses"],
        "draws": stats["draws"],
        "higherLosses": stats["wins"],
        "higherScore": _round(score),
        "higherScoreCi95": {
            "lower": _round(max(0.0, raw_lower)),
            "upper": _round(min(1.0, raw_upper)),
        },
        "higherLosPercent": _round(100.0 * los),
        "higherPentanomial": higher_penta,
    }


def _combined_status(matches: list[dict[str, Any]]) -> str:
    statuses = {match["result"]["status"] for match in matches}
    if "incomplete" in statuses:
        return "incomplete"
    if "fail" in statuses:
        return "fail"
    if "inconclusive" in statuses:
        return "inconclusive"
    return "pass"


def build_summary(results_directory: Path) -> dict[str, Any]:
    manifest = _load_json(results_directory / "manifest.json")
    matches = manifest.get("matches")
    if not isinstance(matches, list) or not matches:
        raise SummaryError("manifest.matches must contain at least one match")

    summarized_matches = []
    expected_games = 2 * manifest["study"]["openingPairs"]
    for match in matches:
        match_id = match["id"]
        result_path = results_directory / f"{match_id}.fastchess.json"
        if not result_path.is_file():
            result = {
                "status": "incomplete",
                "complete": False,
                "expectedGames": expected_games,
                "games": 0,
                "pairs": 0,
            }
        else:
            fastchess = _load_json(result_path)
            stats_by_match = fastchess.get("stats")
            if not isinstance(stats_by_match, dict) or len(stats_by_match) != 1:
                raise SummaryError(f"expected one stats entry in {result_path}")
            result = summarize_stats(next(iter(stats_by_match.values())), expected_games)
        summarized_matches.append(
            {
                "id": match_id,
                "lane": match["lane"],
                "lowerPreset": match["lowerPreset"],
                "higherPreset": match["higherPreset"],
                "result": result,
            }
        )

    lanes = []
    for lane in manifest["lanes"]:
        lane_matches = [match for match in summarized_matches if match["lane"] == lane["id"]]
        lanes.append(
            {
                "id": lane["id"],
                "label": lane["label"],
                "status": _combined_status(lane_matches),
            }
        )

    return {
        "schemaVersion": 1,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "manifest": str((results_directory / "manifest.json").resolve()),
        "method": {
            "unit": "paired openings",
            "confidenceInterval": "normal approximation over pentanomial pair scores",
            "pass": "higher preset's 95% score interval is entirely above 50%",
            "fail": "higher preset's 95% score interval is at or below 50%",
        },
        "status": _combined_status(summarized_matches),
        "lanes": lanes,
        "matches": summarized_matches,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# SixtyFour difficulty evaluation summary",
        "",
        f"Overall status: **{summary['status']}**",
        "",
        "The score and confidence interval are for the higher preset. Results use paired",
        "openings; `W-D-L` is shown from that preset's perspective.",
        "",
        "| Lane | Matchup | W-D-L | Score (95% CI) | LOS | Status |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for match in summary["matches"]:
        result = match["result"]
        if not result["complete"]:
            record = f"{result['games']}/{result['expectedGames']} games"
            lines.append(
                f"| {match['lane']} | {match['lowerPreset']} → {match['higherPreset']} "
                f"| {record} | — | — | **incomplete** |"
            )
            continue
        interval = result["higherScoreCi95"]
        lines.append(
            f"| {match['lane']} | {match['lowerPreset']} → {match['higherPreset']} "
            f"| {result['higherWins']}-{result['draws']}-{result['higherLosses']} "
            f"| {100 * result['higherScore']:.1f}% "
            f"({100 * interval['lower']:.1f}%–{100 * interval['upper']:.1f}%) "
            f"| {result['higherLosPercent']:.1f}% | **{result['status']}** |"
        )
    lines.extend(
        [
            "",
            "A pass establishes relative ordering for this binary, opening sample, and lane.",
            "An inconclusive result needs more paired openings; it is not evidence of equality.",
            "",
        ]
    )
    return "\n".join(lines)


def write_summary(results_directory: Path) -> dict[str, Any]:
    summary = build_summary(results_directory)
    (results_directory / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (results_directory / "summary.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_directory", type=Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        summary = write_summary(args.results_directory.resolve())
    except (SummaryError, KeyError, TypeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Summary ({summary['status']}): {args.results_directory.resolve() / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
