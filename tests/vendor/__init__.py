"""Vendored subset of Home Assistant core's own test helpers.

The other ha-* repositories run their suites inside the pinned Home Assistant
image (see .devcontainer/devcontainer.json) with these helpers instead of
pytest-homeassistant-custom-component, whose releases are generated from one
specific HA version and can lag the image. Everything here is copied from
home-assistant/core at the tag matching the image, trimmed to what this
repo's tests use.
"""
