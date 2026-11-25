"""Guard the HACS/repo docs so the integration stays installable and documented."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from custom_components.sendblue.const import SEND_STYLES

ROOT = Path(__file__).parent.parent
SERVICES_YAML = ROOT / "custom_components" / "sendblue" / "services.yaml"


def test_hacs_json_valid_and_requires_readme() -> None:
    """hacs.json is valid, names the integration, and (render_readme) has a README."""
    data = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert data["name"]
    if data.get("render_readme"):
        assert (ROOT / "README.md").is_file()


def test_hacs_minimum_matches_devcontainer_image() -> None:
    """The tested Home Assistant image is the minimum HACS advertises."""
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    image = json.loads((ROOT / ".devcontainer" / "devcontainer.json").read_text())["image"]
    assert image.endswith(f":{hacs['homeassistant']}")


def test_docs_document_every_service() -> None:
    """The README and both docs pages mention every service in services.yaml."""
    services = yaml.safe_load(SERVICES_YAML.read_text(encoding="utf-8"))
    for page in ("README.md", "docs/en/index.md", "docs/ko/index.md"):
        text = (ROOT / page).read_text(encoding="utf-8")
        for name in services:
            assert f"sendblue.{name}" in text, f"{page} missing sendblue.{name}"


def test_send_styles_match_services_yaml() -> None:
    """The send_style selector offers exactly the styles the action schema accepts."""
    services = yaml.safe_load(SERVICES_YAML.read_text(encoding="utf-8"))
    options = services["send_message"]["fields"]["send_style"]["selector"]["select"]["options"]
    assert options == SEND_STYLES
