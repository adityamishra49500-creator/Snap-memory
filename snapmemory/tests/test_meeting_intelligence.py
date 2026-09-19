import unittest
from ai import meeting_intelligence


class TestMeetingIntelligence(unittest.TestCase):
    def test_empty_transcript_says_not_found(self):
        result = meeting_intelligence.extract("")
        self.assertIn("Not found", result["summary"])
        self.assertEqual(result["decisions"], [])
        self.assertEqual(result["action_items"], [])

    def test_extracts_decision_sentence(self):
        transcript = "We decided to use Firebase authentication because it was fastest to ship."
        result = meeting_intelligence.extract(transcript)
        self.assertTrue(any("Firebase" in d for d in result["decisions"]))

    def test_extracts_dates_present_in_text(self):
        transcript = "The launch is planned for December 12th, and assets are due December 5th."
        result = meeting_intelligence.extract(transcript)
        self.assertTrue(len(result["important_dates"]) >= 1)
        for d in result["important_dates"]:
            self.assertIn(d, transcript)  # never invents a date not in the source

    def test_does_not_invent_action_items_when_none_present(self):
        transcript = "The weather was nice today and we had coffee."
        result = meeting_intelligence.extract(transcript)
        self.assertEqual(result["action_items"], [])

    def test_open_questions_extracted(self):
        transcript = "Does anyone have concerns about the Firebase approach? We moved on after that."
        result = meeting_intelligence.extract(transcript)
        self.assertTrue(any("?" in q for q in result["open_questions"]))


if __name__ == "__main__":
    unittest.main()
