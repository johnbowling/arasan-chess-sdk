import unittest

import summarize_calibration_search as subject


RATING_MODEL = {
    "minimumElo": 1000,
    "maximumElo": 3450,
    "minimumStrength": 0,
    "maximumStrength": 100,
}


def match(arasan_elo, delta, status="fail", complete=True, hard_failures=None):
    return {
        "preset": "club",
        "requestedElo": 1600,
        "arasanElo": arasan_elo,
        "referenceElo": 1600,
        "result": {
            "status": status,
            "complete": complete,
            "games": 50 if complete else 0,
            "expectedGames": 50,
            "arasanScore": 0.5,
            "eloDelta": delta,
            "eloDeltaCi95": {"lower": delta - 100, "upper": delta + 100},
            "terminationAudit": {"hardFailures": hard_failures or {}},
        },
    }


class CalibrationSearchSummaryTest(unittest.TestCase):
    def test_interpolates_between_point_estimates_that_straddle_zero(self):
        analysis = subject.analyze_target(
            "club",
            1600,
            [match(1600, -100), match(1750, 50)],
            RATING_MODEL,
        )

        self.assertEqual(analysis["status"], "bracketed")
        self.assertEqual(analysis["recommendation"]["arasanElo"], 1700)
        self.assertEqual(analysis["recommendation"]["bracket"], [1600, 1750])

    def test_prefers_an_observed_candidate_that_passes_equivalence(self):
        analysis = subject.analyze_target(
            "club",
            1600,
            [match(1600, -80), match(1750, 10, status="pass")],
            RATING_MODEL,
        )

        self.assertEqual(analysis["status"], "candidate-passes")
        self.assertEqual(analysis["recommendation"]["arasanElo"], 1750)

    def test_requests_a_higher_bracket_when_every_candidate_is_too_weak(self):
        analysis = subject.analyze_target(
            "club",
            1600,
            [match(1600, -200), match(1750, -50)],
            RATING_MODEL,
        )

        self.assertEqual(analysis["status"], "expand-higher")
        self.assertIsNone(analysis["recommendation"])

    def test_flags_a_decreasing_candidate_curve(self):
        analysis = subject.analyze_target(
            "club",
            1600,
            [match(1600, -20), match(1750, -80)],
            RATING_MODEL,
        )

        self.assertEqual(analysis["status"], "non-monotonic")

    def test_hard_termination_invalidates_target(self):
        analysis = subject.analyze_target(
            "club",
            1600,
            [
                match(1600, -100),
                match(1750, 50, hard_failures={"time forfeit": 1}),
            ],
            RATING_MODEL,
        )

        self.assertEqual(analysis["status"], "hard-failure")

    def test_complete_monotone_mapping_is_ready_for_confirmation(self):
        manifest = {
            "evaluationType": "stockfish-anchored-calibration",
            "arasanRatingModel": RATING_MODEL,
            "calibration": {
                "openingPairs": 25,
                "timeControl": "120+1",
                "search": {
                    "candidates": [
                        {
                            "preset": "casual",
                            "arasanEloCandidates": [1500, 1650],
                        },
                        {
                            "preset": "club",
                            "arasanEloCandidates": [1800, 1950],
                        },
                    ]
                },
            },
            "presets": [
                {"id": "casual", "requestedElo": 1320},
                {"id": "club", "requestedElo": 1600},
            ],
        }
        matches = [
            {**match(1500, -100), "preset": "casual", "referenceElo": 1320},
            {**match(1650, 50), "preset": "casual", "referenceElo": 1320},
            match(1800, -50),
            match(1950, 100),
        ]
        summary = subject.build_search_summary(
            manifest,
            {"matches": matches, "reference": {"name": "Stockfish 19"}},
        )

        self.assertEqual(summary["status"], "ready-for-confirmation")
        self.assertEqual(
            [value["arasanElo"] for value in summary["recommendedMapping"]],
            [1600, 1850],
        )
        self.assertIn("hypotheses", subject.render_markdown(summary))


if __name__ == "__main__":
    unittest.main()
