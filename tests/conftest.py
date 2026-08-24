import os

os.environ["DEMO_MODE"] = "true"
os.environ["USE_LOCAL_STORE"] = "true"

import pytest

from backend.main import store


@pytest.fixture(autouse=True)
def reset_store():
    store.clear()
    yield
    store.clear()
