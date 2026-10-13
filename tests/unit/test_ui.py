# ============================================================
# FILE: tests/unit/test_ui.py
# ============================================================
"""Learner UI static serving and vendored-library integrity (D-55)."""
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

STATIC = Path(__file__).parents[2] / "src" / "api" / "static"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_root_redirects_to_ui(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/app/"


def test_ui_page_and_assets_are_served(client):
    page = client.get("/app/")
    assert page.status_code == 200 and 'id="app"' in page.text
    assert client.get("/app/app.js").headers["content-type"].startswith(
        ("text/javascript", "application/javascript"))
    assert client.get("/app/vendor/uPlot-1.6.31.esm.js").status_code == 200


def test_vendored_files_match_their_recorded_checksums():
    """Pinned third-party code must never change silently."""
    manifest = json.loads((STATIC / "vendor" / "manifest.json").read_text())
    assert manifest
    for name, entry in manifest.items():
        digest = hashlib.sha256((STATIC / "vendor" / name).read_bytes()).hexdigest()
        assert digest == entry["sha256"], f"{name} differs from the recorded {entry['version']}"


def test_app_imports_only_vendored_modules():
    """No CDN or bare-specifier imports: the UI must work offline from the container."""
    imports = [line for line in (STATIC / "app.js").read_text().splitlines()
               if line.startswith("import ")]
    assert imports and all('from "./vendor/' in line for line in imports)
