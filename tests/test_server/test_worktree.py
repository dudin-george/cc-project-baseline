"""Tests for git worktree lifecycle management."""

from __future__ import annotations

from pathlib import Path

import git
import pytest

from mycroft.server.git.worktree import (
    _cleanup_worktree_sync,
    _commit_and_push_sync,
    _create_worktree_sync,
)


@pytest.fixture()
def git_repo(tmp_path) -> Path:
    """Create a bare git repo with an initial commit."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = git.Repo.init(repo_path)
    # Create initial commit so HEAD exists
    readme = repo_path / "README.md"
    readme.write_text("# Test")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")
    return repo_path


class TestCreateWorktree:
    def test_creates_worktree_directory(self, git_repo):
        wt_path = _create_worktree_sync(git_repo, "feature-branch")
        assert wt_path.exists()
        assert (wt_path / "README.md").exists()

    def test_worktree_is_in_expected_location(self, git_repo):
        wt_path = _create_worktree_sync(git_repo, "my-branch")
        expected = git_repo / ".worktrees" / "my-branch"
        assert wt_path == expected

    def test_creates_branch(self, git_repo):
        _create_worktree_sync(git_repo, "new-branch")
        repo = git.Repo(git_repo)
        assert "new-branch" in [ref.name for ref in repo.heads]


class TestCleanupWorktree:
    def test_removes_worktree(self, git_repo):
        wt_path = _create_worktree_sync(git_repo, "to-remove")
        assert wt_path.exists()
        _cleanup_worktree_sync(git_repo, "to-remove")
        assert not wt_path.exists()

    def test_cleanup_nonexistent_is_safe(self, git_repo):
        # Should not raise
        _cleanup_worktree_sync(git_repo, "nonexistent")


class TestCommitAndPush:
    def test_commit_no_changes_returns_none(self, git_repo):
        result = _commit_and_push_sync(git_repo, "nothing to commit", push=False)
        assert result is None

    def test_commit_with_changes(self, git_repo):
        (git_repo / "new_file.py").write_text("print('hello')")
        sha = _commit_and_push_sync(git_repo, "feat: add new file", push=False)
        assert sha is not None
        assert len(sha) == 40  # full SHA

        repo = git.Repo(git_repo)
        assert repo.head.commit.message == "feat: add new file"

    def test_commit_stages_all_files(self, git_repo):
        (git_repo / "a.py").write_text("a")
        (git_repo / "b.py").write_text("b")
        subdir = git_repo / "sub"
        subdir.mkdir()
        (subdir / "c.py").write_text("c")

        sha = _commit_and_push_sync(git_repo, "feat: add multiple", push=False)
        assert sha is not None

        repo = git.Repo(git_repo)
        committed_files = [item.a_path for item in repo.head.commit.diff("HEAD~1")]
        assert "a.py" in committed_files
        assert "b.py" in committed_files
        assert "sub/c.py" in committed_files

    def test_commit_in_worktree(self, git_repo):
        wt_path = _create_worktree_sync(git_repo, "wt-commit-test")
        (wt_path / "feature.py").write_text("# feature")
        sha = _commit_and_push_sync(wt_path, "feat: new feature", push=False)
        assert sha is not None

        wt_repo = git.Repo(wt_path)
        assert wt_repo.head.commit.message == "feat: new feature"
