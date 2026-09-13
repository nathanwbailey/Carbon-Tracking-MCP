"""
Converts an energy estimate (Wh) into kgCO2eq and expresses that total as
everyday-activity comparisons (washing machine cycles, EV charges, flights,
...), loaded from carbon_equivalents.json.

Grid carbon intensity defaults to a rough UK average; comparisons defined in
kWh are converted through it, comparisons defined directly in kgCO2 (a
flight, a car mile, a kg of beef) are not grid-dependent and pass through
unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_DATA_PATH = Path(__file__).parent / "carbon_equivalents.json"

UK_GRID_GCO2_PER_KWH = 141.0


def kwh_to_co2_kg(kwh: float, intensity_gco2_per_kwh: float = UK_GRID_GCO2_PER_KWH) -> float:
    """kgCO2eq for a given kWh at the given grid carbon intensity."""
    return kwh * intensity_gco2_per_kwh / 1000


def wh_to_co2_kg(wh: float, intensity_gco2_per_kwh: float = UK_GRID_GCO2_PER_KWH) -> float:
    """kgCO2eq for a given Wh at the given grid carbon intensity."""
    return kwh_to_co2_kg(wh / 1000, intensity_gco2_per_kwh)


@dataclass
class Equivalent:
    id: str
    label: str
    kg_co2: float


def load_equivalents(path: str | Path = _DATA_PATH) -> list[Equivalent]:
    """Load comparison items from the JSON database, resolving kWh-based
    entries through the file's grid intensity into kgCO2."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    intensity = data.get("grid_intensity_gco2_per_kwh", UK_GRID_GCO2_PER_KWH)
    return [
        Equivalent(
            id=item["id"],
            label=item["label"],
            kg_co2=item["kg_co2"] if "kg_co2" in item else kwh_to_co2_kg(item["kwh"], intensity),
        )
        for item in data["items"]
    ]


def co2_comparisons(kg_co2: float, path: str | Path = _DATA_PATH) -> list[dict]:
    """How many of each equivalent a given kgCO2eq total represents."""
    return [{"id": eq.id, "label": eq.label, "count": round(kg_co2 / eq.kg_co2, 2)} for eq in load_equivalents(path)]


def co2_summary(wh: float, intensity_gco2_per_kwh: float = UK_GRID_GCO2_PER_KWH, path: str | Path = _DATA_PATH) -> dict:
    """kgCO2eq for an energy estimate (Wh) plus everyday-activity comparisons."""
    kg_co2 = wh_to_co2_kg(wh, intensity_gco2_per_kwh)
    return {"estimated_kg_co2": round(kg_co2, 4), "comparisons": co2_comparisons(kg_co2, path)}
