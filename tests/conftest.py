import pytest
from fastapi.testclient import TestClient

from voxstudio.api import create_app
from voxstudio.engines.fake import FakeEngine
from voxstudio.worker import TTSWorker
from voxstudio.workspace import Workspace


def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", help="also run tests that load real models (Kokoro)")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: loads real models; run with --slow")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--slow"):
        return
    skip = pytest.mark.skip(reason="needs --slow")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def workspace(tmp_path):
    ws = Workspace(tmp_path / "ws")
    (ws.root / "pronunciations.yaml").write_text("ISRO: Iss-roh\n")
    (ws.root / "signatures.yaml").write_text("host: af_heart:0.6,bf_emma:0.4\n")   # old one-line form
    return ws


@pytest.fixture
def engine():
    return FakeEngine()


@pytest.fixture
def client(workspace, engine):
    app = create_app(workspace, worker=TTSWorker(engine, warm=True), extra_hosts={"testserver"})
    return TestClient(app)
