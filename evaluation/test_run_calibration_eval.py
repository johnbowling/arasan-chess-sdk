import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import run_calibration_eval as subject


class CalibrationRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = subject.load_config(subject.DEFAULT_CONFIG)

    def test_selects_six_rated_presets_and_excludes_maximum(self):
        presets = subject.select_presets(self.config["presets"], [])
        self.assertEqual(len(presets), 6)
        self.assertEqual(presets[0]["id"], "casual")
        self.assertEqual(presets[-1]["id"], "elite")
        self.assertNotIn("maximum", {preset["id"] for preset in presets})

    def test_rejects_unrestricted_maximum(self):
        with self.assertRaisesRegex(subject.ConfigError, "unrestricted"):
            subject.select_presets(self.config["presets"], ["maximum"])

    def test_command_matches_same_elo_at_calibration_time_control(self):
        preset = self.config["presets"][1]
        with tempfile.TemporaryDirectory() as temporary_directory:
            command = subject.build_fastchess_command(
                Path("/tools/fastchess"),
                Path("/sdk/arasanx"),
                Path("/sdk"),
                Path("/reference/stockfish"),
                Path("/reference"),
                Path("/data/openings.epd"),
                Path(temporary_directory),
                self.config,
                preset,
            )

        self.assertEqual(command.count("-engine"), 2)
        self.assertEqual(command.count("tc=120+1"), 2)
        self.assertEqual(command.count("option.UCI_LimitStrength=true"), 2)
        self.assertEqual(command.count("option.UCI_Elo=1600"), 2)
        self.assertIn("name=Arasan-club", command)
        self.assertIn("name=stockfish-19-1600", command)
        self.assertIn("option.Position learning=false", command)
        self.assertIn("option.Ponder=false", command)
        self.assertIn("-repeat", command)
        self.assertNotIn("-strict", command)

    def test_search_candidate_holds_reference_target_fixed(self):
        preset = self.config["presets"][1]
        with tempfile.TemporaryDirectory() as temporary_directory:
            command = subject.build_fastchess_command(
                Path("/tools/fastchess"),
                Path("/sdk/arasanx"),
                Path("/sdk"),
                Path("/reference/stockfish"),
                Path("/reference"),
                Path("/data/openings.epd"),
                Path(temporary_directory),
                self.config,
                preset,
                arasan_elo=1800,
            )

        self.assertEqual(subject.match_id(preset, 1800), "calibration__club__a1800")
        self.assertEqual(command.count("option.UCI_Elo=1800"), 1)
        self.assertEqual(command.count("option.UCI_Elo=1600"), 1)
        self.assertIn("name=Arasan-club", command)
        self.assertIn("name=stockfish-19-1600", command)

    def test_plan_records_reference_pin_and_overrides(self):
        rendered = io.StringIO()
        with redirect_stdout(rendered):
            exit_code = subject.main(
                [
                    "plan",
                    "--fastchess",
                    "/missing/fastchess",
                    "--arasan",
                    "/missing/arasan",
                    "--reference",
                    "/missing/stockfish",
                    "--output-directory",
                    "/missing/results",
                    "--preset",
                    "casual",
                    "--opening-pairs",
                    "12",
                    "--concurrency",
                    "3",
                    "--opening-seed",
                    "42",
                    "--time-control",
                    "60+0.6",
                    "--tolerance-elo",
                    "75",
                ]
            )

        self.assertEqual(exit_code, 0)
        plan = json.loads(rendered.getvalue())
        self.assertEqual(plan["evaluationType"], "stockfish-anchored-calibration")
        self.assertEqual(len(plan["matches"]), 1)
        self.assertEqual(len(plan["presets"]), 6)
        self.assertEqual(plan["matches"][0]["id"], "calibration__casual")
        self.assertEqual(plan["matches"][0]["arasanElo"], 1320)
        calibration = plan["calibration"]
        self.assertEqual(calibration["openingPairs"], 12)
        self.assertEqual(calibration["concurrency"], 3)
        self.assertEqual(calibration["openingSeed"], 42)
        self.assertEqual(calibration["timeControl"], "60+0.6")
        self.assertEqual(calibration["equivalenceToleranceElo"], 75)
        self.assertEqual(calibration["reference"]["tag"], "sf_19")
        self.assertRegex(calibration["reference"]["revision"], r"^[0-9a-f]{40}$")
        self.assertNotIn("sha256", plan["inputs"]["reference"])

    def test_plan_records_distinct_arasan_search_input(self):
        rendered = io.StringIO()
        with redirect_stdout(rendered):
            exit_code = subject.main(
                [
                    "plan",
                    "--fastchess",
                    "/missing/fastchess",
                    "--arasan",
                    "/missing/arasan",
                    "--reference",
                    "/missing/stockfish",
                    "--output-directory",
                    "/missing/results",
                    "--preset",
                    "casual",
                    "--arasan-elo",
                    "1600",
                ]
            )

        self.assertEqual(exit_code, 0)
        match = json.loads(rendered.getvalue())["matches"][0]
        self.assertEqual(match["id"], "calibration__casual__a1600")
        self.assertEqual(match["requestedElo"], 1320)
        self.assertEqual(match["arasanElo"], 1600)
        self.assertEqual(match["referenceElo"], 1320)

    def test_arasan_search_input_requires_one_preset(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            exit_code = subject.main(
                [
                    "plan",
                    "--fastchess",
                    "/missing/fastchess",
                    "--arasan",
                    "/missing/arasan",
                    "--reference",
                    "/missing/stockfish",
                    "--output-directory",
                    "/missing/results",
                    "--arasan-elo",
                    "1600",
                ]
            )
        self.assertEqual(exit_code, 2)

    def test_bad_time_control_returns_usage_error(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            exit_code = subject.main(
                [
                    "plan",
                    "--fastchess",
                    "/missing/fastchess",
                    "--arasan",
                    "/missing/arasan",
                    "--reference",
                    "/missing/stockfish",
                    "--output-directory",
                    "/missing/results",
                    "--time-control",
                    "depth16",
                ]
            )
        self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
