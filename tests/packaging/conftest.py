from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--installation", type=Path, help="Expected artifact installation")
