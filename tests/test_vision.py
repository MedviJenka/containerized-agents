import unittest

from pydantic import ValidationError

from ai.agents.vision.crew import Vision
from ai.agents.vision.schemas import VisionSchema


class VisionSchemaTests(unittest.TestCase):
    def test_accepts_and_normalizes_grounded_findings(self) -> None:
        result = VisionSchema(
            confidence_level=87.5,
            items_found=["  delivery truck  "],
            colors=[{"name": " blue ", "hex_code": "#0057B8"}],
            names=["  Acme Logistics "],
            dates=[" 2026-10-05 "],
        )

        self.assertEqual(result.items_found, ["delivery truck"])
        self.assertEqual(result.colors[0].name, "blue")
        self.assertEqual(result.names, ["Acme Logistics"])
        self.assertEqual(result.dates, ["2026-10-05"])

    def test_rejects_confidence_outside_percentage_range(self) -> None:
        for confidence in (-0.1, 100.1):
            with self.subTest(confidence=confidence), self.assertRaises(ValidationError):
                VisionSchema(confidence_level=confidence)

    def test_rejects_blank_findings_and_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            VisionSchema(confidence_level=50, items_found=["   "])

        with self.assertRaises(ValidationError):
            VisionSchema.model_validate(
                {"confidence_level": 50, "unsupported": ["value"]}
            )


class VisionCrewTests(unittest.TestCase):
    def test_builds_crew_with_structured_output_and_local_skills(self) -> None:
        vision = Vision()
        crew = vision.crew()

        self.assertEqual(len(crew.agents), 1)
        self.assertEqual(len(crew.tasks), 1)
        self.assertIs(crew.tasks[0].output_pydantic, VisionSchema)
        self.assertEqual(
            {skill.name for skill in crew.agents[0].skills or []},
            {"evaluator", "vision"},
        )


if __name__ == "__main__":
    unittest.main()
