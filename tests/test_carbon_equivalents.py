import json
import tempfile
import unittest
from pathlib import Path

from mcps.carbon_equivalents import co2_comparisons, co2_summary, kwh_to_co2_kg, load_equivalents, wh_to_co2_kg
from mcps.schema import CO2Comparison


class CarbonEquivalentsTests(unittest.TestCase):
    def test_kwh_to_co2_kg_uses_given_intensity(self):
        self.assertAlmostEqual(kwh_to_co2_kg(1, intensity_gco2_per_kwh=200), 0.2)

    def test_wh_to_co2_kg_converts_through_kwh(self):
        self.assertAlmostEqual(wh_to_co2_kg(1000, intensity_gco2_per_kwh=200), 0.2)

    def test_load_equivalents_resolves_kwh_and_passes_through_kg_co2(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text(
                json.dumps(
                    {
                        "grid_intensity_gco2_per_kwh": 200,
                        "items": [
                            {"id": "a", "label": "a", "kwh": 1.0},
                            {"id": "b", "label": "b", "kg_co2": 5.0},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            equivalents = {eq.id: eq.kg_co2 for eq in load_equivalents(path)}

            self.assertAlmostEqual(equivalents["a"], 0.2)
            self.assertAlmostEqual(equivalents["b"], 5.0)

    def test_co2_comparisons_counts_multiples_of_each_equivalent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text(
                json.dumps(
                    {
                        "grid_intensity_gco2_per_kwh": 100,
                        "items": [{"id": "half_kg", "label": "half kg item", "kg_co2": 0.5}],
                    }
                ),
                encoding="utf-8",
            )

            comparisons = co2_comparisons(1.0, path)

            self.assertEqual(comparisons, [CO2Comparison(id="half_kg", label="half kg item", count=2.0)])

    def test_co2_summary_reports_kg_and_comparisons(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text(
                json.dumps(
                    {
                        "grid_intensity_gco2_per_kwh": 100,
                        "items": [{"id": "half_kg", "label": "half kg item", "kg_co2": 0.5}],
                    }
                ),
                encoding="utf-8",
            )

            summary = co2_summary(1000, intensity_gco2_per_kwh=100, path=path)

            self.assertAlmostEqual(summary.estimated_kg_co2, 0.1)
            self.assertEqual(summary.comparisons, [CO2Comparison(id="half_kg", label="half kg item", count=0.2)])


if __name__ == "__main__":
    unittest.main()
