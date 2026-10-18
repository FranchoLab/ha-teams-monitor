import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "src" / "ha_teams_status"


def violations(source: str, module: str, is_package: bool) -> list[str]:
    allowed = {"domain": {"domain"}, "application": {"domain", "application"}}
    layer = module.split(".")[1]
    package = module if is_package else module.rpartition(".")[0]
    invalid = []
    for node in ast.walk(ast.parse(source)):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1] + ([base] if base else []))
            names = [f"{base}.{alias.name}" for alias in node.names]
        for name in names:
            if name == "ha_teams_status" or name.startswith("ha_teams_status."):
                parts = name.split(".")
                if len(parts) < 2 or parts[1] not in allowed[layer]:
                    invalid.append(name)
            elif name.split(".")[0] not in __import__("sys").stdlib_module_names:
                invalid.append(name)
    return invalid


def test_core_dependency_direction() -> None:
    for layer in ("domain", "application"):
        for path in (ROOT / layer).rglob("*.py"):
            relative = path.relative_to(ROOT).with_suffix("")
            parts = relative.parts
            is_package = parts[-1] == "__init__"
            module = ".".join(("ha_teams_status", *(parts[:-1] if is_package else parts)))
            assert not violations(path.read_text(), module, is_package), path


@pytest.mark.parametrize(
    "source",
    [
        "import ha_teams_status.adapters",
        "from ha_teams_status import adapters",
        "from ..adapters import mqtt",
        "import paho.mqtt.client",
        "from ha_teams_status import __main__",
    ],
)
def test_boundary_guard_rejects_outward_imports(source: str) -> None:
    assert violations(source, "ha_teams_status.application.monitor", False)


def test_application_can_import_domain() -> None:
    assert not violations(
        "from ..domain import observation",
        "ha_teams_status.application.monitor",
        False,
    )
