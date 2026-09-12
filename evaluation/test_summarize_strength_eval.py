import json
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
