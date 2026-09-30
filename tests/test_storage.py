import tempfile, os
from pathlib import Path

def test_create_and_state(monkeypatch, tmp_path):
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path / "projects"))
    from science_studio import storage
    from science_studio.models import ProjectState
    pid, root = storage.create_project("Test idea?", duration="8-10")
    assert (root / "idea.json").exists()
    assert (root / "research").exists()
    storage.set_state(pid, ProjectState.RESEARCHING)
    assert storage.get_state(pid) == "RESEARCHING"
    # second project never overwrites first
    pid2, _ = storage.create_project("Test idea?", duration="8-10")
    assert pid2 != pid
