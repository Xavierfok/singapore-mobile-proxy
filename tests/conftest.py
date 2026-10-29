import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import mockproxy  # noqa: E402


@pytest.fixture
def line():
    """A fresh mock line: (state, env)."""
    server, state, env = mockproxy.start()
    yield state, env
    server.shutdown()
    server.server_close()
