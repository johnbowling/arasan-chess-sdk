import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import summarize_calibration_eval as subject


def stats(**overrides):
    values = {
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "penta_WW": 0,
        "penta_WD": 0,
        "penta_WL": 0,
        "penta_DD": 0,
        "penta_LD": 0,
        "penta_LL": 0,
    }
    values.update(overrides)
    return values


def manifest(match_id="calibration__club", opening_pairs=200):
    return {
        "evaluationType": "stockfish-anchored-calibration",
        "calibration": {
            "openingPairs": opening_pairs,
            "timeControl": "120+1",
            "equivalenceToleranceElo": 100,
            "reference": {
                "name": "Stockfish 19",
                "revision": "edb0d9db6731067ec50ce619ff372b463bc4dd5d",
            },
        },
        "matches": [
            {
                "id": match_id,
                "preset": "club",
                "requestedElo": 1600,
                "referenceElo": 1600,
            }
        ],
    }


class CalibrationSummaryTest(unittest.TestCase):
    def test_balanced_200_pair_result_passes_equivalence(self):
        result = subject.summarize_stats(
            stats(draws=400, penta_DD=200),
            expected_games=400,
            reference_elo=1600,
            tolerance_elo=100,
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["arasanScore"], 0.5)
        self.assertEqual(result["eloDelta"], 0.0)
        self.assertEqual(result["estimatedAnchoredElo"], 1600.0)
        self.assertGreater(result["eloDeltaCi95"]["lower"], -100)
        self.assertLess(result["eloDeltaCi95"]["upper"], 100)

    def test_clear_mismatch_fails_equivalence(self):
        result = subject.summarize_stats(
            stats(wins=300, losses=100, penta_WW=150, penta_LL=50),
            expected_games=400,
            reference_elo=1600,
            tolerance_elo=100,
        )
        self.assertEqual(result["status"], "fail")
        self.assertGreater(result["eloDeltaCi95"]["lower"], 100)

    def test_small_balanced_sample_is_inconclusive(self):
        result = subject.summarize_stats(
            stats(draws=40, penta_DD=20),
            expected_games=40,
            reference_elo=1600,
            tolerance_elo=100,
        )
        self.assertEqual(result["status"], "inconclusive")
        self.assertLess(result["eloDeltaCi95"]["lower"], -100)
        self.assertGreater(result["eloDeltaCi95"]["upper"], 100)

    def test_search_summary_renders_target_and_distinct_arasan_input(self):
        value = {
            "status": "inconclusive",
            "reference": {
                "name": "Stockfish 19",
                "revision": "edb0d9db6731067ec50ce619ff372b463bc4dd5d",
            },
            "method": {"equivalenceToleranceElo": 100},
            "matches": [
                {
                    "preset": "club",
                    "requestedElo": 1600,
                    "arasanElo": 1800,
                    "referenceElo": 1600,
                    "result": subject.summarize_stats(
                        stats(wins=10, losses=10, penta_WW=5, penta_LL=5),
                        expected_games=20,
                        reference_elo=1600,
                        tolerance_elo=100,
                    ),
                }
            ],
        }
        value["matches"][0]["result"]["terminationAudit"] = {
            "hardFailures": {}
        }

        markdown = subject.render_markdown(value)

        self.assertIn("| club | 1600 | 1800 |", markdown)
        self.assertIn("candidate UCI_Elo inputs", markdown)

    def test_endpoints_are_json_safe(self):
        result = subject.summarize_stats(
            stats(wins=20, penta_WW=10),
            expected_games=20,
            reference_elo=1600,
            tolerance_elo=100,
        )
        self.assertIsNone(result["eloDelta"])
        self.assertNotIn("Infinity", json.dumps(result))

    def test_missing_result_is_incomplete(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "manifest.json").write_text(
                json.dumps(manifest()), encoding="utf-8"
            )
            summary = subject.build_summary(directory)

        self.assertEqual(summary["status"], "incomplete")
        self.assertEqual(summary["matches"][0]["result"]["games"], 0)

    def test_hard_termination_overrides_equivalent_score(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            match_id = "calibration__club"
            (directory / "manifest.json").write_text(
                json.dumps(manifest(match_id, opening_pairs=200)), encoding="utf-8"
            )
            (directory / f"{match_id}.fastchess.json").write_text(
                json.dumps(
                    {"stats": {"Arasan vs Stockfish": stats(draws=400, penta_DD=200)}}
                ),
                encoding="utf-8",
            )
            terminations = '[Termination "normal"]\n\n' * 399
            terminations += '[Termination "time forfeit"]\n'
            (directory / f"{match_id}.pgn").write_text(
                terminations, encoding="utf-8"
            )

            summary = subject.build_summary(directory)
            markdown = subject.render_markdown(summary)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                exit_code = subject.main([str(directory), "--require-pass"])

        self.assertEqual(summary["status"], "fail")
        self.assertIn("time forfeit: 1", markdown)
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
