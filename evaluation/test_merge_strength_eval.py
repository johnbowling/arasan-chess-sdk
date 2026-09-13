import copy
import json
import tempfile
import unittest
from pathlib import Path

import merge_strength_eval as subject


def manifest(match_id, lower, higher):
    return {
        "schemaVersion": 1,
        "generatedAtUtc": "2026-09-13T00:00:00+00:00",
        "sdkRevision": "abc123",
        "host": {"platform": "Linux", "cpuCount": 4},
        "inputs": {
            name: {"path": f"/inputs/{name}", "sha256": f"{name}-hash"}
            for name in ("config", "fastchess", "engine", "openings")
        },
        "openingSuite": {"id": "suite", "sha256": "openings-hash"},
        "study": {"openingPairs": 2, "concurrency": 4},
        "lanes": [{"id": "algorithm", "label": "Algorithm"}],
        "engineOptions": {"Threads": 1},
        "presets": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        "matches": [
            {
                "id": match_id,
                "lane": "algorithm",
                "lowerPreset": lower,
                "higherPreset": higher,
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


class MergeStrengthEvaluationTest(unittest.TestCase):
    def test_merges_complete_ladder_and_preserves_shard_hosts(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = write_shard(
                root, "first", manifest("algorithm__a_vs_b", "a", "b")
            )
            second_manifest = manifest("algorithm__b_vs_c", "b", "c")
            second_manifest["host"] = {"platform": "Linux", "cpuCount": 8}
            second = write_shard(root, "second", second_manifest)
            output = root / "merged"

            merged = subject.merge_shards(
                output, [second, first], require_complete_ladder=True
            )

            self.assertEqual(merged["schemaVersion"], 2)
            self.assertNotIn("host", merged)
            self.assertEqual(
                [match["id"] for match in merged["matches"]],
                ["algorithm__a_vs_b", "algorithm__b_vs_c"],
            )
            self.assertEqual(
                [shard["host"]["cpuCount"] for shard in merged["execution"]["shards"]],
                [4, 8],
            )
            self.assertTrue((output / "algorithm__a_vs_b.pgn").is_file())
            self.assertTrue((output / "algorithm__b_vs_c.console.log").is_file())

    def test_rejects_missing_complete_ladder_match(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shard = write_shard(
                root, "first", manifest("algorithm__a_vs_b", "a", "b")
            )
            with self.assertRaisesRegex(subject.MergeError, "missing.*algorithm__b_vs_c"):
                subject.merge_shards(
                    root / "merged", [shard], require_complete_ladder=True
                )

    def test_rejects_incompatible_input_hashes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_manifest = manifest("algorithm__a_vs_b", "a", "b")
            second_manifest = copy.deepcopy(manifest("algorithm__b_vs_c", "b", "c"))
            second_manifest["inputs"]["engine"]["sha256"] = "different"
            first = write_shard(root, "first", first_manifest)
            second = write_shard(root, "second", second_manifest)

            with self.assertRaisesRegex(subject.MergeError, "incompatible input hashes"):
                subject.merge_shards(root / "merged", [first, second])

    def test_rejects_duplicate_match_ids(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            value = manifest("algorithm__a_vs_b", "a", "b")
            first = write_shard(root, "first", value)
            second = write_shard(root, "second", value)

            with self.assertRaisesRegex(subject.MergeError, "duplicate match id"):
                subject.merge_shards(root / "merged", [first, second])


if __name__ == "__main__":
    unittest.main()
