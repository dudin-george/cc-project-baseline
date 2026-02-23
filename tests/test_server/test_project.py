"""Tests for ProjectState."""

import pytest

from mycroft.shared.protocol import StepId, StepStatus, STEP_ORDER
from mycroft.server.state.project import ProjectState


@pytest.fixture(autouse=True)
def patch_projects_dir(tmp_path, monkeypatch):
    """Redirect all project state to tmp_path."""
    monkeypatch.setattr(
        "mycroft.server.state.project.settings.data_dir", tmp_path
    )
    return tmp_path


class TestProjectStateInit:
    def test_default_values(self):
        p = ProjectState()
        assert p.project_name == "untitled"
        assert p.current_step == StepId.IDEA_SCOPING
        assert len(p.project_id) == 12

    def test_all_steps_initialized(self):
        p = ProjectState()
        for step_id in STEP_ORDER:
            assert step_id in p.steps
            assert p.steps[step_id].status == StepStatus.DRAFT

    def test_custom_name(self):
        p = ProjectState(project_name="My App")
        assert p.project_name == "My App"


class TestProjectStateSlug:
    def test_simple_name(self):
        p = ProjectState(project_name="My Cool App")
        assert p.slug == "my-cool-app"

    def test_special_chars(self):
        p = ProjectState(project_name="App v2.0 (beta)")
        assert p.slug == "app-v2-0-beta"

    def test_empty_name_falls_back_to_id(self):
        p = ProjectState(project_name="")
        assert p.slug == p.project_id

    def test_only_special_chars_falls_back(self):
        p = ProjectState(project_name="!!!")
        assert p.slug == p.project_id

    def test_numbers(self):
        p = ProjectState(project_name="test123")
        assert p.slug == "test123"


class TestProjectStatePersistence:
    def test_save_and_load(self, patch_projects_dir):
        p = ProjectState(project_name="Test")
        p.save()

        loaded = ProjectState.load(p.project_id)
        assert loaded.project_id == p.project_id
        assert loaded.project_name == "Test"
        assert loaded.current_step == StepId.IDEA_SCOPING

    def test_exists(self, patch_projects_dir):
        p = ProjectState()
        assert not ProjectState.exists(p.project_id)
        p.save()
        assert ProjectState.exists(p.project_id)

    def test_exists_nonexistent(self):
        assert not ProjectState.exists("nonexistent")

    def test_load_missing_raises(self):
        with pytest.raises(FileNotFoundError):
            ProjectState.load("nonexistent")

    def test_list_all_empty(self, patch_projects_dir):
        assert ProjectState.list_all() == []

    def test_list_all(self, patch_projects_dir):
        p1 = ProjectState(project_name="One")
        p1.save()
        p2 = ProjectState(project_name="Two")
        p2.save()

        projects = ProjectState.list_all()
        names = {p.project_name for p in projects}
        assert names == {"One", "Two"}

    def test_save_preserves_step_state(self, patch_projects_dir):
        p = ProjectState()
        p.steps[StepId.IDEA_SCOPING].status = StepStatus.LOCKED
        p.current_step = StepId.USE_CASES_MANUAL
        p.save()

        loaded = ProjectState.load(p.project_id)
        assert loaded.steps[StepId.IDEA_SCOPING].status == StepStatus.LOCKED
        assert loaded.current_step == StepId.USE_CASES_MANUAL
