from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Tests must never contact LRCLIB: any real HTTP request fails the test."""
    import lyrics_source

    def blocked(url, timeout=15.0):
        raise AssertionError(f"test tried to reach the network: {url}")

    monkeypatch.setattr(lyrics_source, "_http_get", blocked)
