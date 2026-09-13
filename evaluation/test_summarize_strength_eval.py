import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import summarize_strength_eval as subject


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


class StrengthSummaryTest(unittest.TestCase):
    def test_reports_pass_from_higher_presets_perspective(self):
        result = subject.summarize_stats(
            stats(losses=20, penta_LL=10), expected_games=20
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["higherWins"], 20)
        self.assertEqual(result["higherScore"], 1.0)
        self.assertEqual(result["higherLosPercent"], 100.0)
        self.assertGreater(result["higherScoreCi95"]["lower"], 0.5)
        self.assertLess(result["higherScoreCi95"]["lower"], 1.0)

    def test_reports_fail_when_higher_preset_is_confidently_worse(self):
        result = subject.summarize_stats(
            stats(wins=20, penta_WW=10), expected_games=20
        )
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["higherLosses"], 20)

    def test_balanced_pairs_are_inconclusive(self):
        result = subject.summarize_stats(
            stats(
                wins=4,
                losses=4,
                draws=12,
                penta_WW=2,
                penta_DD=6,
                penta_LL=2,
            ),
            expected_games=20,
        )
        self.assertEqual(result["status"], "inconclusive")
        self.assertEqual(result["higherScore"], 0.5)
        self.assertEqual(result["higherLosPercent"], 50.0)

    def test_build_summary_marks_missing_match_incomplete(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            manifest = {
                "study": {"openingPairs": 10},
                "lanes": [{"id": "algorithm", "label": "Algorithm"}],
                "matches": [
                    {
                        "id": "algorithm__casual_vs_club",
                        "lane": "algorithm",
                        "lowerPreset": "casual",
                        "higherPreset": "club",
                    }
                ],
            }
            (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            summary = subject.build_summary(directory)

        self.assertEqual(summary["status"], "incomplete")
        self.assertEqual(summary["lanes"][0]["status"], "incomplete")

    def test_renders_completed_match_as_markdown(self):
        summary = {
            "status": "pass",
            "matches": [
                {
                    "lane": "product",
                    "lowerPreset": "casual",
                    "higherPreset": "club",
                    "result": subject.summarize_stats(
                        stats(losses=20, penta_LL=10), expected_games=20
                    ),
                }
            ],
        }
        markdown = subject.render_markdown(summary)
        self.assertIn("casual → club", markdown)
        self.assertIn("20-0-0", markdown)
        self.assertIn("**pass**", markdown)

    def test_hard_termination_overrides_winning_score(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            match_id = "algorithm__casual_vs_club"
            manifest = {
                "study": {"openingPairs": 1},
                "lanes": [{"id": "algorithm", "label": "Algorithm"}],
                "matches": [
                    {
                        "id": match_id,
                        "lane": "algorithm",
                        "lowerPreset": "casual",
                        "higherPreset": "club",
                    }
                ],
            }
            result = {"stats": {"lower vs higher": stats(losses=2, penta_LL=1)}}
            (directory / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            (directory / f"{match_id}.fastchess.json").write_text(
                json.dumps(result), encoding="utf-8"
            )
            (directory / f"{match_id}.pgn").write_text(
                '[Termination "normal"]\n\n[Termination "time forfeit"]\n',
                encoding="utf-8",
            )

            summary = subject.build_summary(directory)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                exit_code = subject.main([str(directory), "--require-pass"])

        match_result = summary["matches"][0]["result"]
        self.assertEqual(summary["status"], "fail")
        self.assertEqual(match_result["higherScore"], 1.0)
        self.assertEqual(
            match_result["terminationAudit"]["hardFailures"], {"time forfeit": 1}
        )
        self.assertIn("time forfeit: 1", subject.render_markdown(summary))
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
