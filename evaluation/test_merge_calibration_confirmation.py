import copy
import json
import tempfile
import unittest
from pathlib import Path

import merge_calibration_confirmation as subject
import summarize_calibration_eval


def manifest(match_id, preset, target_elo, arasan_elo, opening_start):
    mapping = [
        {"preset": "casual", "arasanElo": 1500},
        {"preset": "club", "arasanElo": 1800},
    ]
    return {
        "schemaVersion": 1,
        "evaluationType": "stockfish-anchored-calibration",
        "generatedAtUtc": "2026-09-13T00:00:00+00:00",
        "sdkRevision": "abc123",
        "host": {"platform": "Linux", "cpuCount": 4},
        "inputs": {
            name: {"path": f"/inputs/{name}", "sha256": f"{name}-hash"}
            for name in ("config", "fastchess", "arasan", "reference", "openings")
        },
        "openingSuite": {"id": "suite", "positions": 10, "sha256": "openings-hash"},
        "openingSelection": {
            "order": "sequential",
            "start": opening_start,
            "pairs": 2,
        },
        "calibration": {
            "openingPairs": 2,
            "timeControl": "120+1",
            "equivalenceToleranceElo": 100,
            "confirmation": {
                "openingPairs": 4,
                "pairsPerShard": 2,
                "openingOrder": "sequential",
                "mapping": mapping,
            },
            "reference": {"id": "stockfish-19", "name": "Stockfish 19"},
        },
        "arasanRatingModel": {"minimumElo": 1000, "maximumElo": 3450},
        "engineOptions": {"arasan": {"Threads": 1}, "reference": {"Threads": 1}},
        "presets": [
            {"id": "casual", "requestedElo": 1320},
            {"id": "club", "requestedElo": 1600},
        ],
        "matches": [
            {
                "id": match_id,
                "preset": preset,
                "requestedElo": target_elo,
                "arasanElo": arasan_elo,
                "referenceElo": target_elo,
                "argv": ["fastchess"],
            }
        ],
    }


def write_shard(root, preset, target_elo, arasan_elo, opening_start):
    match_id = f"calibration__{preset}__a{arasan_elo}"
    directory = root / f"{preset}-{opening_start}"
    directory.mkdir()
    value = manifest(match_id, preset, target_elo, arasan_elo, opening_start)
    (directory / "manifest.json").write_text(json.dumps(value), encoding="utf-8")
    stats_name = f"Arasan-{preset} vs stockfish-19-{target_elo}"
    fastchess = {
        "rounds": 2,
        "opening": {"start": opening_start},
        "stats": {
            stats_name: {
                "wins": 0,
                "losses": 0,
                "draws": 4,
                "penta_WW": 0,
                "penta_WD": 0,
                "penta_WL": 0,
                "penta_DD": 2,
                "penta_LD": 0,
                "penta_LL": 0,
            }
        },
    }
    (directory / f"{match_id}.fastchess.json").write_text(
        json.dumps(fastchess), encoding="utf-8"
    )
    (directory / f"{match_id}.pgn").write_text(
        '[Termination "normal"]\n\n' * 4, encoding="utf-8"
    )
    (directory / f"{match_id}.log").write_text("log\n", encoding="utf-8")
    (directory / "console.log").write_text("console\n", encoding="utf-8")
    return directory


class MergeCalibrationConfirmationTest(unittest.TestCase):
    def _complete_shards(self, root):
        return [
            write_shard(root, preset, target, arasan, start)
            for preset, target, arasan in (
                ("casual", 1320, 1500),
                ("club", 1600, 1800),
            )
            for start in (1, 3)
        ]

    def test_combines_disjoint_blocks_into_full_matches(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            merged = subject.merge_confirmation(
                root / "merged", self._complete_shards(root)
            )
            output = root / "merged"
            stats = json.loads(
                (output / "calibration__club__a1800.fastchess.json").read_text(
                    encoding="utf-8"
                )
            )["stats"]["Arasan-club vs stockfish-19-1600"]
            summary = summarize_calibration_eval.build_summary(output)

            self.assertEqual(merged["schemaVersion"], 2)
            self.assertEqual(merged["calibration"]["openingPairs"], 4)
            self.assertEqual(merged["openingSelection"]["pairs"], 4)
            self.assertEqual(len(merged["execution"]["shards"]), 4)
            self.assertEqual(
                [match["id"] for match in merged["matches"]],
                ["calibration__casual__a1500", "calibration__club__a1800"],
            )
            self.assertEqual(stats["draws"], 8)
            self.assertEqual(stats["penta_DD"], 4)
            self.assertEqual(summary["matches"][1]["result"]["games"], 8)
            self.assertTrue(summary["matches"][1]["result"]["complete"])
            self.assertEqual(
                (output / "calibration__club__a1800.pgn")
                .read_text(encoding="utf-8")
                .count('[Termination "normal"]'),
                8,
            )

    def test_rejects_missing_opening_block(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shards = self._complete_shards(root)
            with self.assertRaisesRegex(subject.MergeError, "incomplete confirmation"):
                subject.merge_confirmation(root / "merged", shards[:-1])

    def test_rejects_duplicate_opening_block(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shards = self._complete_shards(root)
            duplicate = root / "duplicate"
            duplicate.mkdir()
            source = shards[0]
            for path in source.iterdir():
                (duplicate / path.name).write_bytes(path.read_bytes())
            with self.assertRaisesRegex(subject.MergeError, "duplicate opening block"):
                subject.merge_confirmation(root / "merged", [*shards, duplicate])

    def test_rejects_mapping_disagreement(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shards = self._complete_shards(root)
            path = shards[0] / "manifest.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            changed = copy.deepcopy(value)
            changed["matches"][0]["arasanElo"] = 1501
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(subject.MergeError, "unexpected confirmation match"):
                subject.merge_confirmation(root / "merged", shards)


if __name__ == "__main__":
    unittest.main()
