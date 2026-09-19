from pathlib import Path

import pytest

from nailque.factory import create_app
from nailque.paths import AppPaths


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("MANAGER_PIN", "1234")
    monkeypatch.setenv("AUTO_UPDATE_ENABLED", "false")
    monkeypatch.setenv("TRUST_PROXY", "false")
    monkeypatch.setenv("AUTO_OPEN_BROWSER", "false")
    assets_dir = Path(__file__).resolve().parents[1]
    paths = AppPaths(assets_dir=assets_dir, runtime_dir=tmp_path)
    application = create_app(paths)
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def client(app):
    return app.test_client()
