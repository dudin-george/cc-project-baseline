"""Tests for git template population and CLAUDE.md generation."""

from __future__ import annotations

import pytest

from mycroft.server.git.template import generate_claude_md, populate_repo, write_claude_md
from mycroft.server.state.project import ProjectState
from mycroft.shared.protocol import StepId


@pytest.fixture(autouse=True)
def patch_projects_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("mycroft.server.state.project.settings.data_dir", tmp_path)
    return tmp_path


def _make_project_with_docs() -> ProjectState:
    """Create a project with idea, architecture, and service docs."""
    p = ProjectState(project_name="TestApp")
    p.save()
    docs_dir = p.project_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    (docs_dir / "00-idea.md").write_text("# TestApp Idea\nA cool app.")
    (docs_dir / "01-use-cases.md").write_text("# Use Cases\n- Login\n- Dashboard")
    (docs_dir / "02-architecture.md").write_text("# Architecture\nMicroservices.")

    svc_dir = docs_dir / "services"
    svc_dir.mkdir()
    (svc_dir / "svc-auth.md").write_text("# Auth Service")
    (svc_dir / "svc-api.md").write_text("# API Gateway")

    design_dir = docs_dir / "03-design"
    design_dir.mkdir()
    (design_dir / "svc-auth.md").write_text("# Auth Design\nClasses and functions.")

    return p


class TestPopulateRepo:
    def test_copies_docs(self, tmp_path):
        project = _make_project_with_docs()
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        written = populate_repo(repo_path, project)
        assert len(written) > 0
        assert (repo_path / "docs" / "specs" / "00-idea.md").exists()
        assert (repo_path / "docs" / "specs" / "02-architecture.md").exists()

    def test_copies_service_specs(self, tmp_path):
        project = _make_project_with_docs()
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        populate_repo(repo_path, project)
        assert (repo_path / "docs" / "specs" / "services" / "svc-auth.md").exists()

    def test_copies_design_docs(self, tmp_path):
        project = _make_project_with_docs()
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        populate_repo(repo_path, project)
        assert (repo_path / "docs" / "specs" / "03-design" / "svc-auth.md").exists()

    def test_empty_project_returns_empty_list(self, tmp_path):
        p = ProjectState(project_name="Empty")
        p.save()
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        written = populate_repo(repo_path, p)
        assert written == []


class TestGenerateClaudeMd:
    def test_contains_project_name(self):
        project = _make_project_with_docs()
        content = generate_claude_md(project)
        assert "# Project: TestApp" in content

    def test_contains_overview(self):
        project = _make_project_with_docs()
        content = generate_claude_md(project)
        assert "A cool app." in content

    def test_contains_architecture(self):
        project = _make_project_with_docs()
        content = generate_claude_md(project)
        assert "Microservices." in content

    def test_contains_service_links(self):
        project = _make_project_with_docs()
        content = generate_claude_md(project)
        assert "services/svc-auth.md" in content

    def test_contains_design_links(self):
        project = _make_project_with_docs()
        content = generate_claude_md(project)
        assert "03-design/svc-auth.md" in content

    def test_contains_placeholder_sections(self):
        project = _make_project_with_docs()
        content = generate_claude_md(project)
        assert "[PLACEHOLDER:" in content
        assert "General Coding Conventions" in content
        assert "Team Lead Instructions" in content
        assert "Blocker Rules" in content

    def test_empty_project(self):
        p = ProjectState(project_name="Empty")
        p.save()
        content = generate_claude_md(p)
        assert "# Project: Empty" in content
        assert "*No idea document found.*" in content


class TestWriteClaudeMd:
    def test_writes_file(self, tmp_path):
        project = _make_project_with_docs()
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        path = write_claude_md(repo_path, project)
        assert (repo_path / "CLAUDE.md").exists()
        content = (repo_path / "CLAUDE.md").read_text()
        assert "TestApp" in content
        assert path == str(repo_path / "CLAUDE.md")
