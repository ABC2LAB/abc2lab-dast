"""Smoke test for the abc2lab-webdiag development environment."""

from importlib import import_module
from importlib.resources import files


def test_package_is_importable_and_typed() -> None:
    module = import_module("abc2lab_webdiag")
    assert module.__package__ == "abc2lab_webdiag"
    assert files("abc2lab_webdiag").joinpath("py.typed").is_file()
