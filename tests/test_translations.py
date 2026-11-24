"""Translations must cover exactly the keys in strings.json."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent / "custom_components" / "sendblue"


def _keys(node: object, prefix: str = "") -> set[str]:
    if not isinstance(node, dict):
        return {prefix}
    return set().union(*(_keys(v, f"{prefix}.{k}") for k, v in node.items()))


@pytest.mark.parametrize("language", ["en", "ko"])
def test_translation_matches_strings(language: str) -> None:
    strings = json.loads((ROOT / "strings.json").read_text())
    translation = json.loads((ROOT / "translations" / f"{language}.json").read_text())

    assert _keys(translation) == _keys(strings)
