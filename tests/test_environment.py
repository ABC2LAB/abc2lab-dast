"""Check runtime clients in the complete development environment."""

from importlib import import_module

import pytest


@pytest.mark.parametrize("client", ("httpx", "playwright.async_api"))
def test_gateway_clients_are_installed(client: str) -> None:
    import_module(client)
