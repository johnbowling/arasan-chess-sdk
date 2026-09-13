import copy
import json
import tempfile
import unittest
from pathlib import Path

import merge_calibration_eval as subject


def manifest(match_id, preset):
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
        "openingSuite": {"id": "suite", "sha256": "openings-hash"},
        "calibration": {
            "openingPairs": 2,
            "timeControl": "120+1",
            "reference": {"id": "stockfish-19"},
        },
        "engineOptions": {"arasan": {"Threads": 1}, "reference": {"Threads": 1}},
        "presets": [{"id": "casual"}, {"id": "club"}],
        "matches": [
            {
                "id": match_id,
                "preset": preset,
                "requestedElo": 1320 if preset == "casual" else 1600,
                "referenceElo": 1320 if preset == "casual" else 1600,
                "argv": ["fastchess"],
            }
        ],
    }


def write_shard(root, name, value):
    directory = root / name
    directory.mkdir()
    match_id = value["matches"][0]["id"]
    (directory / "manifest.json").write_text(json.dumps(value), encoding="utf-8")
    for suffix in subject.MATCH_SUFFIXES:
        (directory / f"{match_id}.{suffix}").write_text(suffix, encoding="utf-8")
    (directory / "console.log").write_text("console", encoding="utf-8")
    return directory


class MergeCalibrationEvaluationTest(unittest.TestCase):
    def test_merges_complete_calibration_and_preserves_hosts(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = write_shard(
                root, "first", manifest("calibration__casual", "casual")
            )
            second_manifest = manifest("calibration__club", "club")
            second_manifest["host"] = {"platform": "Linux", "cpuCount": 8}
            second = write_shard(root, "second", second_manifest)
            output = root / "merged"

            merged = subject.merge_shards(
                output, [second, first], require_complete_calibration=True
            )

            self.assertEqual(merged["schemaVersion"], 2)
            self.assertNotIn("host", merged)
            self.assertEqual(
                [match["id"] for match in merged["matches"]],
                ["calibration__casual", "calibration__club"],
            )
            self.assertEqual(
                [shard["host"]["cpuCount"] for shard in merged["execution"]["shards"]],
                [4, 8],
            )
            self.assertTrue((output / "calibration__casual.pgn").is_file())
            self.assertTrue((output / "calibration__club.console.log").is_file())

    def test_rejects_missing_complete_calibration_match(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shard = write_shard(
                root, "first", manifest("calibration__casual", "casual")
            )
            with self.assertRaisesRegex(subject.MergeError, "missing.*calibration__club"):
                subject.merge_shards(
                    root / "merged", [shard], require_complete_calibration=True
                )

    def test_rejects_incompatible_reference_hash(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_manifest = manifest("calibration__casual", "casual")
            second_manifest = copy.deepcopy(manifest("calibration__club", "club"))
            second_manifest["inputs"]["reference"]["sha256"] = "different"
            first = write_shard(root, "first", first_manifest)
            second = write_shard(root, "second", second_manifest)

            with self.assertRaisesRegex(subject.MergeError, "incompatible input hashes"):
                subject.merge_shards(root / "merged", [first, second])

    def test_rejects_duplicate_match_ids(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            value = manifest("calibration__casual", "casual")
            first = write_shard(root, "first", value)
            second = write_shard(root, "second", value)

            with self.assertRaisesRegex(subject.MergeError, "duplicate match id"):
                subject.merge_shards(root / "merged", [first, second])


if __name__ == "__main__":
    unittest.main()
