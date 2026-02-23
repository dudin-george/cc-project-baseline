"""Tests for pipeline state machine: transitions, cascade-back, locking."""

import pytest

from mycroft.shared.protocol import StepId, StepStatus, STEP_ORDER
from mycroft.server.state.project import ProjectState
from mycroft.server.state import conversation as conv
from mycroft.server.pipeline.state import (
    advance,
    go_back,
    get_step_documents,
    get_all_previous_documents,
    PipelineError,
)


@pytest.fixture(autouse=True)
def patch_projects_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "mycroft.server.state.project.settings.data_dir", tmp_path
    )
    return tmp_path


def make_project(name: str = "test") -> ProjectState:
    p = ProjectState(project_name=name)
    p.save()
    return p


class TestAdvance:
    def test_advance_from_step_0(self):
        p = make_project()
        new = advance(p)
        assert new == StepId.USE_CASES_MANUAL
        assert p.current_step == StepId.USE_CASES_MANUAL
        assert p.steps[StepId.IDEA_SCOPING].status == StepStatus.LOCKED

    def test_advance_through_all_steps(self):
        p = make_project()
        expected = STEP_ORDER[1:]
        for expected_step in expected:
            new = advance(p)
            assert new == expected_step

    def test_advance_from_last_step_raises(self):
        p = make_project()
        # Advance to last step
        for _ in range(len(STEP_ORDER) - 1):
            advance(p)
        assert p.current_step == StepId.E2E_TESTING
        with pytest.raises(PipelineError, match="last step"):
            advance(p)

    def test_advance_locks_current_step(self):
        p = make_project()
        advance(p)
        assert p.steps[StepId.IDEA_SCOPING].status == StepStatus.LOCKED

    def test_advance_persists(self):
        p = make_project()
        advance(p)
        loaded = ProjectState.load(p.project_id)
        assert loaded.current_step == StepId.USE_CASES_MANUAL

    def test_step_22_gets_permanently_locked(self):
        p = make_project()
        # Advance to 2.2 (index 4, need 4 advances)
        for _ in range(4):
            advance(p)
        assert p.current_step == StepId.ARCHITECTURE_AUTO
        # Step 2.1 should be locked (not permanently)
        assert p.steps[StepId.ARCHITECTURE_MANUAL].status == StepStatus.LOCKED


class TestGoBack:
    def test_go_back_one_step(self):
        p = make_project()
        advance(p)  # now at 1.1
        new = go_back(p, StepId.IDEA_SCOPING)
        assert new == StepId.IDEA_SCOPING
        assert p.current_step == StepId.IDEA_SCOPING
        assert p.steps[StepId.IDEA_SCOPING].status == StepStatus.DRAFT

    def test_go_back_multiple_steps(self):
        p = make_project()
        advance(p)  # 1.1
        advance(p)  # 1.2
        advance(p)  # 2.1
        new = go_back(p, StepId.IDEA_SCOPING)
        assert new == StepId.IDEA_SCOPING
        # All intermediate steps reset to draft
        assert p.steps[StepId.USE_CASES_MANUAL].status == StepStatus.DRAFT
        assert p.steps[StepId.USE_CASES_AUTO].status == StepStatus.DRAFT
        assert p.steps[StepId.ARCHITECTURE_MANUAL].status == StepStatus.DRAFT

    def test_go_back_to_current_raises(self):
        p = make_project()
        with pytest.raises(PipelineError, match="not a previous step"):
            go_back(p, StepId.IDEA_SCOPING)

    def test_go_back_to_future_raises(self):
        p = make_project()
        with pytest.raises(PipelineError, match="not a previous step"):
            go_back(p, StepId.USE_CASES_MANUAL)

    def test_go_back_deletes_downstream_conversations(self):
        p = make_project()
        advance(p)  # 1.1
        conv.append_message(p.project_dir, StepId.USE_CASES_MANUAL, {"role": "user", "content": "x"})
        go_back(p, StepId.IDEA_SCOPING)
        assert conv.load_messages(p.project_dir, StepId.USE_CASES_MANUAL) == []

    def test_go_back_cascade_removes_docs(self):
        p = make_project()
        advance(p)  # 1.1
        # Create a doc for step 1.1
        docs_dir = p.project_dir / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "01-use-cases.md").write_text("test")
        go_back(p, StepId.IDEA_SCOPING)
        assert not (docs_dir / "01-use-cases.md").exists()

    def test_go_back_persists(self):
        p = make_project()
        advance(p)
        go_back(p, StepId.IDEA_SCOPING)
        loaded = ProjectState.load(p.project_id)
        assert loaded.current_step == StepId.IDEA_SCOPING


class TestPermanentLock:
    def _advance_to_end(self, p: ProjectState) -> None:
        """Advance through all steps. After this, 2.2 is current but not locked yet."""
        for _ in range(len(STEP_ORDER) - 1):
            advance(p)

    def test_back_past_permanent_lock_rejected(self):
        p = make_project()
        self._advance_to_end(p)
        assert p.current_step == StepId.E2E_TESTING
        # Manually permanently lock step 2.2
        p.steps[StepId.ARCHITECTURE_AUTO].status = StepStatus.PERMANENTLY_LOCKED
        p.save()
        with pytest.raises(PipelineError, match="permanently locked"):
            go_back(p, StepId.IDEA_SCOPING)


class TestGetDocuments:
    def test_get_step_documents_empty(self):
        p = make_project()
        assert get_step_documents(p, StepId.IDEA_SCOPING) == {}

    def test_get_step_documents(self):
        p = make_project()
        docs_dir = p.project_dir / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "00-idea.md").write_text("# Idea")
        result = get_step_documents(p, StepId.IDEA_SCOPING)
        assert "00-idea.md" in result
        assert result["00-idea.md"] == "# Idea"

    def test_get_step_documents_services(self):
        p = make_project()
        svc_dir = p.project_dir / "docs" / "services"
        svc_dir.mkdir(parents=True)
        (svc_dir / "svc-auth.md").write_text("# Auth")
        (svc_dir / "svc-api.md").write_text("# API")
        result = get_step_documents(p, StepId.ARCHITECTURE_AUTO)
        assert "services/svc-api.md" in result
        assert "services/svc-auth.md" in result

    def test_get_all_previous_documents_at_step_0(self):
        p = make_project()
        assert get_all_previous_documents(p) == {}

    def test_get_all_previous_documents(self):
        p = make_project()
        docs_dir = p.project_dir / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "00-idea.md").write_text("# Idea")
        p.current_step = StepId.USE_CASES_MANUAL
        result = get_all_previous_documents(p)
        assert "00-idea.md" in result
