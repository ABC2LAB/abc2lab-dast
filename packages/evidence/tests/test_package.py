"""Smoke test for the abc2lab-evidence development environment."""

from importlib import import_module
from importlib.resources import files


def test_package_is_importable_and_typed() -> None:
    module = import_module("abc2lab_evidence")
    assert module.__package__ == "abc2lab_evidence"
    assert files("abc2lab_evidence").joinpath("py.typed").is_file()
