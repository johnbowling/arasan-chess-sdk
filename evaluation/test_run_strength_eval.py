import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import run_strength_eval as subject


class StrengthEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = subject.load_config(subject.DEFAULT_CONFIG)
        cls.algorithm_lane = next(
            lane for lane in cls.config["lanes"] if lane["id"] == "algorithm"
        )
        cls.product_lane = next(
            lane for lane in cls.config["lanes"] if lane["id"] == "product"
        )

    def test_sixtyfour_presets_map_to_expected_internal_buckets(self):
        model = self.config["arasanRatingModel"]
        observed = {
            preset["id"]: subject.strength_bucket(preset["requestedElo"], model)
            for preset in self.config["presets"]
        }
        self.assertEqual(
            observed,
            {
                "casual": 13,
                "club": 24,
                "strong-club": 36,
                "expert": 48,
                "master": 61,
                "elite": 73,
                "maximum": 100,
            },
        )

    def test_builds_six_adjacent_paired_matches(self):
        pairs = list(subject.adjacent_pairs(self.config["presets"]))
        self.assertEqual(len(pairs), 6)
        self.assertEqual(
            subject.pair_id(self.algorithm_lane, *pairs[0]),
            "algorithm__casual_vs_club",
        )
        self.assertEqual(
            subject.pair_id(self.product_lane, *pairs[-1]),
            "product__elite_vs_maximum",
        )

    def test_limited_and_maximum_commands_mirror_app_settings(self):
        lower = self.config["presets"][-2]
        higher = self.config["presets"][-1]
        with tempfile.TemporaryDirectory() as temporary_directory:
            command = subject.build_fastchess_command(
                Path("/tools/fastchess"),
                Path("/sdk/arasanx"),
                Path("/sdk"),
                Path("/data/openings.epd"),
                Path(temporary_directory),
                self.config,
                self.product_lane,
                lower,
                higher,
            )

        self.assertEqual(command.count("-engine"), 2)
        self.assertIn("st=0.65", command)
        self.assertEqual(command.count("timemargin=100"), 2)
        self.assertIn("option.Hash=32", command)
        self.assertIn("option.Position learning=false", command)
        self.assertIn("option.UCI_Elo=2800", command)
        self.assertEqual(command.count("option.UCI_LimitStrength=true"), 1)
        self.assertEqual(command.count("option.UCI_LimitStrength=false"), 1)
        self.assertNotIn("option.UCI_Elo=None", command)
        self.assertIn("-repeat", command)
        self.assertIn("200", command)
        self.assertNotIn("-strict", command)

    def test_algorithm_lane_uses_depth_without_movetime(self):
        lower, higher = self.config["presets"][:2]
        with tempfile.TemporaryDirectory() as temporary_directory:
            command = subject.build_fastchess_command(
                Path("/tools/fastchess"),
                Path("/sdk/arasanx"),
                Path("/sdk"),
                Path("/data/openings.epd"),
                Path(temporary_directory),
                self.config,
                self.algorithm_lane,
                lower,
                higher,
            )

        self.assertEqual(command.count("plies=16"), 2)
        self.assertFalse(any(argument.startswith("st=") for argument in command))

    def test_configured_depth_caps_match_arasan_source(self):
        sdk_root = subject.SCRIPT_DIR.parent
        options_source = (sdk_root / "src/options.h").read_text(encoding="utf-8")
        search_source = (sdk_root / "src/search.cpp").read_text(encoding="utf-8")
        minimum = int(re.search(r"MIN_RATING\s*=\s*(\d+)", options_source).group(1))
        maximum = int(re.search(r"MAX_RATING\s*=\s*(\d+)", options_source).group(1))
        table_match = re.search(
            r"STRENGTH_DEPTH_LIMITS\[40\]\s*=\s*\{([^}]+)\}",
            search_source,
            re.DOTALL,
        )
        depth_caps = [int(value) for value in re.findall(r"\d+", table_match.group(1))]

        self.assertEqual(self.config["arasanRatingModel"]["minimumElo"], minimum)
        self.assertEqual(self.config["arasanRatingModel"]["maximumElo"], maximum)
        self.assertEqual(len(depth_caps), 40)
        for preset in self.config["presets"]:
            if preset["requestedElo"] is None:
                continue
            bucket = subject.strength_bucket(
                preset["requestedElo"], self.config["arasanRatingModel"]
            )
            self.assertEqual(preset["expectedDepthCap"], depth_caps[(2 * bucket) // 5])

        highest_extended_cap = max(
            preset["expectedDepthCap"] + 2
            for preset in self.config["presets"]
            if preset["expectedDepthCap"] is not None
        )
        self.assertGreaterEqual(
            self.algorithm_lane["search"]["value"], highest_extended_cap
        )

    def test_plan_mode_does_not_require_binaries_to_exist(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "not-created"
            rendered = io.StringIO()
            with redirect_stdout(rendered):
                exit_code = subject.main(
                    [
                        "plan",
                        "--fastchess",
                        "/missing/fastchess",
                        "--engine",
                        "/missing/arasan",
                        "--openings",
                        "/missing/openings.epd",
                        "--output-directory",
                        str(output),
                        "--pair",
                        "casual:club",
                    ]
                )
        self.assertEqual(exit_code, 0)
        plan = json.loads(rendered.getvalue())
        self.assertEqual(len(plan["matches"]), 2)
        self.assertEqual(plan["matches"][0]["id"], "algorithm__casual_vs_club")

    def test_checked_in_config_is_valid_json(self):
        with subject.DEFAULT_CONFIG.open(encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["schemaVersion"], 1)

    def test_plan_overrides_are_recorded(self):
        rendered = io.StringIO()
        with redirect_stdout(rendered):
            exit_code = subject.main(
                [
                    "plan",
                    "--fastchess",
                    "/missing/fastchess",
                    "--engine",
                    "/missing/arasan",
                    "--openings",
                    "/missing/openings.epd",
                    "--output-directory",
                    "/missing/results",
                    "--pair",
                    "casual:club",
                    "--opening-pairs",
                    "2",
                    "--concurrency",
                    "3",
                    "--opening-seed",
                    "42",
                    "--depth",
                    "18",
                    "--move-time-ms",
                    "500",
                ]
            )
        plan = json.loads(rendered.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(plan["study"]["openingPairs"], 2)
        self.assertEqual(plan["study"]["concurrency"], 3)
        self.assertEqual(plan["study"]["openingSeed"], 42)
        lanes = {lane["id"]: lane for lane in plan["lanes"]}
        self.assertEqual(lanes["algorithm"]["search"]["value"], 18)
        self.assertEqual(lanes["product"]["search"]["milliseconds"], 500)


if __name__ == "__main__":
    unittest.main()
