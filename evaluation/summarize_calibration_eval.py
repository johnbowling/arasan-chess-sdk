#!/usr/bin/env python3
"""Summarize SixtyFour's Stockfish-anchored Elo calibration matches."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from summarize_strength_eval import (
    SummaryError,
    _load_json,
    audit_pgn_terminations,
    score_interval,
)


def _round(value: float) -> float:
    return round(value, 6)


def score_to_elo(score: float) -> float | None:
    """Convert expected score to Elo difference; endpoints are unbounded."""
    if score <= 0.0 or score >= 1.0:
        return None
    return 400.0 * math.log10(score / (1.0 - score))


def _elo_interval(score_lower: float, score_upper: float) -> dict[str, Any]:
    elo_lower = score_to_elo(score_lower)
    elo_upper = score_to_elo(score_upper)
    return {
        "lower": _round(elo_lower) if elo_lower is not None else None,
        "upper": _round(elo_upper) if elo_upper is not None else None,
    }


def summarize_stats(
    stats: dict[str, Any],
    expected_games: int,
    reference_elo: int,
    tolerance_elo: int,
) -> dict[str, Any]:
    """Summarize paired statistics from Arasan's first-engine perspective."""
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
    pairs = sum(stats[field] for field in integer_fields[3:])
    complete = games == expected_games
    if games == 0 or pairs == 0:
        return {
            "status": "incomplete",
            "complete": complete,
            "expectedGames": expected_games,
            "games": games,
            "pairs": pairs,
            "referenceElo": reference_elo,
            "toleranceElo": tolerance_elo,
        }

    arasan_penta = {
        "WW": stats["penta_WW"],
        "WD": stats["penta_WD"],
        "WLDD": stats["penta_WL"] + stats["penta_DD"],
        "LD": stats["penta_LD"],
        "LL": stats["penta_LL"],
    }
    if sum(arasan_penta.values()) != pairs or games != 2 * pairs:
        raise SummaryError("fastchess game and pentanomial counts are inconsistent")

    weights = {"WW": 1.0, "WD": 0.75, "WLDD": 0.5, "LD": 0.25, "LL": 0.0}
    score = sum(arasan_penta[key] * weights[key] for key in weights) / pairs
    variance = sum(
        arasan_penta[key] / pairs * (weights[key] - score) ** 2 for key in weights
    )
    standard_error = math.sqrt(variance / pairs)
    score_lower, score_upper = score_interval(score, pairs)
    elo_delta = score_to_elo(score)
    elo_interval = _elo_interval(score_lower, score_upper)

    if standard_error == 0:
        los = 1.0 if score > 0.5 else 0.0 if score < 0.5 else 0.5
    else:
        z_score = (score - 0.5) / standard_error
        los = 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))

    lower_delta = elo_interval["lower"]
    upper_delta = elo_interval["upper"]
    if not complete:
        status = "incomplete"
    elif (
        lower_delta is not None
        and upper_delta is not None
        and lower_delta >= -tolerance_elo
        and upper_delta <= tolerance_elo
    ):
        status = "pass"
    elif (
        (lower_delta is not None and lower_delta > tolerance_elo)
        or (upper_delta is not None and upper_delta < -tolerance_elo)
    ):
        status = "fail"
    else:
        status = "inconclusive"

    estimated_elo = _round(reference_elo + elo_delta) if elo_delta is not None else None
    estimated_interval = {
        "lower": (
            _round(reference_elo + lower_delta) if lower_delta is not None else None
        ),
        "upper": (
            _round(reference_elo + upper_delta) if upper_delta is not None else None
        ),
    }
    return {
        "status": status,
        "complete": complete,
        "expectedGames": expected_games,
        "games": games,
        "pairs": pairs,
        "arasanWins": stats["wins"],
        "draws": stats["draws"],
        "arasanLosses": stats["losses"],
        "arasanScore": _round(score),
        "arasanScoreCi95": {
            "lower": _round(score_lower),
            "upper": _round(score_upper),
        },
        "arasanLosPercent": _round(100.0 * los),
        "arasanPentanomial": arasan_penta,
        "referenceElo": reference_elo,
        "toleranceElo": tolerance_elo,
        "eloDelta": _round(elo_delta) if elo_delta is not None else None,
        "eloDeltaCi95": elo_interval,
        "estimatedAnchoredElo": estimated_elo,
        "estimatedAnchoredEloCi95": estimated_interval,
    }


def _combined_status(matches: list[dict[str, Any]]) -> str:
    statuses = {match["result"]["status"] for match in matches}
    if "fail" in statuses:
        return "fail"
    if "incomplete" in statuses:
        return "incomplete"
    if "inconclusive" in statuses:
        return "inconclusive"
    return "pass"


def build_summary(results_directory: Path) -> dict[str, Any]:
    manifest = _load_json(results_directory / "manifest.json")
    if manifest.get("evaluationType") != "stockfish-anchored-calibration":
        raise SummaryError("manifest is not a Stockfish-anchored calibration")
    matches = manifest.get("matches")
    if not isinstance(matches, list) or not matches:
        raise SummaryError("manifest.matches must contain at least one match")
    calibration = manifest["calibration"]
    expected_games = 2 * calibration["openingPairs"]
    tolerance_elo = calibration["equivalenceToleranceElo"]

    summarized_matches = []
    for match in matches:
        match_id_value = match["id"]
        result_path = results_directory / f"{match_id_value}.fastchess.json"
        if not result_path.is_file():
            result = {
                "status": "incomplete",
                "complete": False,
                "expectedGames": expected_games,
                "games": 0,
                "pairs": 0,
                "referenceElo": match["referenceElo"],
                "toleranceElo": tolerance_elo,
            }
        else:
            fastchess = _load_json(result_path)
            stats_by_match = fastchess.get("stats")
            if not isinstance(stats_by_match, dict) or len(stats_by_match) != 1:
                raise SummaryError(f"expected one stats entry in {result_path}")
            result = summarize_stats(
                next(iter(stats_by_match.values())),
                expected_games,
                match["referenceElo"],
                tolerance_elo,
            )
        termination_audit = audit_pgn_terminations(
            results_directory / f"{match_id_value}.pgn", expected_games
        )
        result["terminationAudit"] = termination_audit
        if result["complete"] and not termination_audit["complete"]:
            result["status"] = "incomplete"
        elif termination_audit["hardFailures"]:
            result["status"] = "fail"
        summarized_matches.append(
            {
                "id": match_id_value,
                "preset": match["preset"],
                "requestedElo": match["requestedElo"],
                "arasanElo": match.get("arasanElo", match["requestedElo"]),
                "referenceElo": match["referenceElo"],
                "result": result,
            }
        )

    reference = calibration["reference"]
    return {
        "schemaVersion": 1,
        "evaluationType": "stockfish-anchored-calibration-summary",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "manifest": str((results_directory / "manifest.json").resolve()),
        "reference": reference,
        "method": {
            "unit": "paired openings",
            "timeControl": calibration["timeControl"],
            "confidenceInterval": "Wilson-style interval over bounded paired-opening scores",
            "eloConversion": "400 * log10(score / (1 - score))",
            "equivalenceToleranceElo": tolerance_elo,
            "pass": "the full 95% Elo-difference interval is inside the equivalence band",
            "fail": "the full 95% interval is outside one side of the band, or a game has a hard termination",
            "inconclusive": "the interval overlaps both the equivalence band and values outside it",
            "scope": "Stockfish-anchored engine Elo; not human Elo",
        },
        "status": _combined_status(summarized_matches),
        "matches": summarized_matches,
    }


def _render_bound(value: float | None, negative: bool) -> str:
    if value is None:
        return "−∞" if negative else "+∞"
    return f"{value:.1f}"


def render_markdown(summary: dict[str, Any]) -> str:
    tolerance = summary["method"]["equivalenceToleranceElo"]
    reference = summary["reference"]
    is_baseline = all(
        match.get("arasanElo", match["requestedElo"]) == match["referenceElo"]
        for match in summary["matches"]
    )
    comparison_description = (
        "same UCI_Elo as each Arasan preset. This measures agreement with Stockfish's"
        if is_baseline
        else "fixed target Elo for each preset while Arasan uses candidate UCI_Elo inputs."
    )
    lines = [
        "# SixtyFour Stockfish-anchored calibration summary",
        "",
        f"Overall status: **{summary['status']}**",
        "",
        f"Reference: {reference['name']} (`{reference['revision']}`), configured to the",
        comparison_description,
        "This measures agreement with Stockfish's documented approximate CCRL Blitz",
        "scale; it does **not** establish human Elo.",
        "",
        f"Equivalence band: ±{tolerance} Elo. A pass requires the complete 95% Elo",
        "interval to fit inside that band.",
        "",
        "| Preset | Target | Arasan input | W-D-L | Score (95% CI) | Elo delta (95% CI) | Anchored estimate (95% CI) | Hard failures | Status |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for match in summary["matches"]:
        result = match["result"]
        if not result["complete"]:
            lines.append(
                f"| {match['preset']} | {match['referenceElo']} | "
                f"{match.get('arasanElo', match['requestedElo'])} | "
                f"{result['games']}/{result['expectedGames']} games | — | — | — | — | **incomplete** |"
            )
            continue
        score_interval_value = result["arasanScoreCi95"]
        elo_interval = result["eloDeltaCi95"]
        estimate_interval = result["estimatedAnchoredEloCi95"]
        hard_failures = result.get("terminationAudit", {}).get("hardFailures", {})
        rendered_failures = (
            ", ".join(f"{name}: {count}" for name, count in hard_failures.items())
            if hard_failures
            else "—"
        )
        if result["eloDelta"] is not None:
            delta = f"{result['eloDelta']:+.1f}"
        else:
            delta = "+∞" if result["arasanScore"] == 1.0 else "−∞"
        delta_ci = (
            f"{_render_bound(elo_interval['lower'], True)} to "
            f"{_render_bound(elo_interval['upper'], False)}"
        )
        estimate = (
            f"{result['estimatedAnchoredElo']:.1f}"
            if result["estimatedAnchoredElo"] is not None
            else "—"
        )
        estimate_ci = (
            f"{_render_bound(estimate_interval['lower'], True)} to "
            f"{_render_bound(estimate_interval['upper'], False)}"
        )
        lines.append(
            f"| {match['preset']} | {match['referenceElo']} "
            f"| {match.get('arasanElo', match['requestedElo'])} "
            f"| {result['arasanWins']}-{result['draws']}-{result['arasanLosses']} "
            f"| {100 * result['arasanScore']:.1f}% "
            f"({100 * score_interval_value['lower']:.1f}%–{100 * score_interval_value['upper']:.1f}%) "
            f"| {delta} ({delta_ci}) | {estimate} ({estimate_ci}) "
            f"| {rendered_failures} | **{result['status']}** |"
        )
    lines.extend(
        [
            "",
            "A failure means a statistically clear mismatch from the configured anchor,",
            "not that either engine's label equals or differs from a human rating.",
            "An inconclusive result needs more paired openings.",
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
    parser.add_argument(
        "--require-pass",
        action="store_true",
        help="return a failing exit code unless every calibration match passes",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        summary = write_summary(args.results_directory.resolve())
    except (SummaryError, KeyError, TypeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Summary ({summary['status']}): {args.results_directory.resolve() / 'summary.md'}")
    if args.require_pass and summary["status"] != "pass":
        print(
            f"error: calibration gate requires pass, observed {summary['status']}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
