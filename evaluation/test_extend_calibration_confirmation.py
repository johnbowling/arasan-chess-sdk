import copy
import json
import tempfile
import unittest
from pathlib import Path

import extend_calibration_confirmation as subject
import summarize_calibration_eval


BASE_HASHES = {
    "config": "base-config-hash",
    "fastchess": "fastchess-hash",
    "arasan": "arasan-hash",
    "reference": "reference-hash",
    "openings": "openings-hash",
}
CONFIRMATION = {
    "openingPairs": 200,
    "pairsPerShard": 50,
    "openingOrder": "sequential",
    "mapping": [
        {"preset": "casual", "arasanElo": 1500},
        {"preset": "club", "arasanElo": 1800},
    ],
}
EXTENSION = {
    "baseRunId": 12345,
    "baseSdkRevision": "base-sdk",
    "baseOpeningPairs": 200,
    "openingPairs": 300,
    "pairsPerShard": 50,
    "openingOrder": "sequential",
    "openingStarts": [201, 251],
    "baseInputHashes": BASE_HASHES,
    "mapping": [{"preset": "club", "arasanElo": 1800}],
}
PRESETS = [
    {"id": "casual", "requestedElo": 1320},
    {"id": "club", "requestedElo": 1600},
]
OPENING_SUITE = {"id": "suite", "positions": 400, "sha256": "openings-hash"}
ENGINE_OPTIONS = {"arasan": {"Threads": 1}, "reference": {"Threads": 1}}
RATING_MODEL = {"minimumElo": 1000, "maximumElo": 3450}
REFERENCE = {"id": "stockfish-19", "name": "Stockfish 19", "revision": "ref"}


def input_records(config_hash):
    return {
        name: {
            "path": f"/inputs/{name}",
            "sha256": config_hash if name == "config" else BASE_HASHES[name],
        }
        for name in BASE_HASHES
    }


def match(preset, target, arasan):
    return {
        "id": f"calibration__{preset}__a{arasan}",
        "preset": preset,
        "requestedElo": target,
        "arasanElo": arasan,
        "referenceElo": target,
        "argv": ["fastchess"],
    }


def stats(pairs):
    return {
        "wins": 0,
        "losses": 0,
        "draws": 2 * pairs,
        "penta_WW": 0,
        "penta_WD": 0,
        "penta_WL": 0,
        "penta_DD": pairs,
        "penta_LD": 0,
        "penta_LL": 0,
    }


def write_match_files(directory, value, pairs, opening_start, console_name):
    value_id = value["id"]
    stats_name = f"Arasan-{value['preset']} vs stockfish-19-{value['referenceElo']}"
    fastchess = {
        "rounds": pairs,
        "opening": {"start": opening_start},
        "stats": {stats_name: stats(pairs)},
    }
    (directory / f"{value_id}.fastchess.json").write_text(
        json.dumps(fastchess), encoding="utf-8"
    )
    (directory / f"{value_id}.pgn").write_text(
        '[Termination "normal"]\n\n' * (2 * pairs), encoding="utf-8"
    )
    (directory / f"{value_id}.log").write_text("log\n", encoding="utf-8")
    (directory / console_name).write_text("console\n", encoding="utf-8")


def write_base(root):
    directory = root / "base"
    directory.mkdir()
    matches = [match("casual", 1320, 1500), match("club", 1600, 1800)]
    manifest = {
        "schemaVersion": 2,
        "evaluationType": "stockfish-anchored-calibration",
        "generatedAtUtc": "2026-09-14T00:00:00+00:00",
        "sdkRevision": "base-sdk",
        "inputs": input_records(BASE_HASHES["config"]),
        "openingSuite": OPENING_SUITE,
        "openingSelection": {
            "order": "sequential",
            "start": 1,
            "pairs": 200,
            "sharded": True,
        },
        "calibration": {
            "openingPairs": 200,
            "timeControl": "120+1",
            "equivalenceToleranceElo": 100,
            "confirmation": CONFIRMATION,
            "reference": REFERENCE,
        },
        "arasanRatingModel": RATING_MODEL,
        "engineOptions": ENGINE_OPTIONS,
        "presets": PRESETS,
        "execution": {
            "mode": "sharded-opening-blocks",
            "shards": [
                {
                    "matchId": value["id"],
                    "openingStart": start,
                    "openingPairs": 50,
                    "host": {"cpuModel": "test"},
                }
                for value in matches
                for start in (1, 51, 101, 151)
            ],
        },
        "matches": matches,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for value in matches:
        write_match_files(directory, value, 200, 1, f"{value['id']}.console.log")
    return directory


def write_supplement(root, opening_start):
    directory = root / f"supplement-{opening_start}"
    directory.mkdir()
    value = match("club", 1600, 1800)
    manifest = {
        "schemaVersion": 1,
        "evaluationType": "stockfish-anchored-calibration",
        "generatedAtUtc": "2026-09-14T01:00:00+00:00",
        "sdkRevision": "extension-sdk",
        "host": {"cpuModel": "test", "cpuCount": 4},
        "inputs": input_records("extension-config-hash"),
        "openingSuite": OPENING_SUITE,
        "openingSelection": {
            "order": "sequential",
            "start": opening_start,
            "pairs": 50,
        },
        "calibration": {
            "openingPairs": 50,
            "timeControl": "120+1",
            "equivalenceToleranceElo": 100,
            "confirmation": CONFIRMATION,
            "confirmationExtension": EXTENSION,
            "reference": REFERENCE,
        },
        "arasanRatingModel": RATING_MODEL,
        "engineOptions": ENGINE_OPTIONS,
        "presets": PRESETS,
        "matches": [value],
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    write_match_files(directory, value, 50, opening_start, "console.log")
    return directory


class ExtendCalibrationConfirmationTest(unittest.TestCase):
    def test_combines_base_and_supplemental_blocks(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            base = write_base(root)
            supplements = [write_supplement(root, start) for start in (201, 251)]
            output = root / "extended"

            merged = subject.extend_confirmation(output, base, supplements)
            summary = summarize_calibration_eval.build_summary(output)
            combined = json.loads(
                (output / "calibration__club__a1800.fastchess.json").read_text(
                    encoding="utf-8"
                )
            )
            combined_stats = next(iter(combined["stats"].values()))

            self.assertEqual(merged["calibration"]["openingPairs"], 300)
            self.assertEqual(len(merged["matches"]), 1)
            self.assertEqual(merged["matches"][0]["preset"], "club")
            self.assertEqual(
                merged["matches"][0]["aggregation"]["openingStarts"],
                [1, 51, 101, 151, 201, 251],
            )
            self.assertEqual(len(merged["execution"]["shards"]), 6)
            self.assertEqual(combined_stats["draws"], 600)
            self.assertEqual(combined_stats["penta_DD"], 300)
            self.assertEqual(summary["status"], "pass")
            self.assertEqual(summary["matches"][0]["result"]["games"], 600)

    def test_rejects_missing_supplemental_block(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            base = write_base(root)
            supplement = write_supplement(root, 201)

            with self.assertRaisesRegex(subject.MergeError, "incomplete extension"):
                subject.extend_confirmation(root / "extended", base, [supplement])

    def test_rejects_supplemental_engine_hash_change(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            base = write_base(root)
            supplements = [write_supplement(root, start) for start in (201, 251)]
            path = supplements[0] / "manifest.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            changed = copy.deepcopy(value)
            changed["inputs"]["arasan"]["sha256"] = "different"
            path.write_text(json.dumps(changed), encoding="utf-8")

            with self.assertRaisesRegex(subject.MergeError, "arasan hash differs"):
                subject.extend_confirmation(root / "extended", base, supplements)


if __name__ == "__main__":
    unittest.main()
