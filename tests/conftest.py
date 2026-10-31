"""Suite-wide isolation: tests never touch the real projects/ or cache/.

get_settings() caches on first use, so merely setting PROJECTS_DIR is not
enough — reload after setenv. (Before this, every suite run littered the repo
with projects/2026*-test-idea-* junk dirs.)
"""
import pytest


@pytest.fixture(autouse=True)
def _isolated_dirs(monkeypatch, tmp_path):
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    from science_studio.config import get_settings
    get_settings(reload=True)
    yield
    get_settings(reload=True)
