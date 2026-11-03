import re
from pathlib import Path

import pytest
from jinja2 import Environment, StrictUndefined

SOURCE_DESKTOP = "binary_sensor.teams_status_desktop_meeting"
SOURCE_LAPTOP = "binary_sensor.teams_status_laptop_meeting"


@pytest.mark.parametrize("desktop", ["on", "off", "unknown", "unavailable", None])
@pytest.mark.parametrize("laptop", ["on", "off", "unknown", "unavailable", None])
def test_combined_sensor_templates_preserve_joined_and_uncertainty(
    desktop: str | None,
    laptop: str | None,
) -> None:
    example = Path(__file__).parents[1] / "examples" / "home-assistant-combined.yaml"
    text = example.read_text(encoding="utf-8")
    templates = dict(
        re.findall(r"^        (availability|state): >-\n((?:          .*\n)+)", text, re.M)
    )
    assert set(templates) == {"availability", "state"}
    sources = {SOURCE_DESKTOP: desktop, SOURCE_LAPTOP: laptop}

    def is_state(entity_id: str, state: str) -> bool:
        assert entity_id in sources
        return sources[entity_id] == state

    environment = Environment(undefined=StrictUndefined)
    rendered = {
        key: environment.from_string(value).render(is_state=is_state).strip()
        for key, value in templates.items()
    }

    if "on" in (desktop, laptop):
        assert rendered == {"availability": "True", "state": "True"}
    elif desktop == laptop == "off":
        assert rendered == {"availability": "True", "state": "False"}
    else:
        assert rendered == {"availability": "False", "state": "False"}
