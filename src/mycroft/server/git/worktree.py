"""Git worktree lifecycle management for isolated agent work."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import git

from mycroft.server.settings import settings

logger = logging.getLogger(__name__)

_git_lock = asyncio.Lock()


def _get_repo(repo_path: Path) -> git.Repo:
    """Open existing repo at the given path."""
    return git.Repo(repo_path)


def _create_worktree_sync(repo_path: Path, branch_name: str) -> Path:
    """Create a git worktree for the given branch (blocking)."""
    repo = _get_repo(repo_path)
    worktree_dir = repo_path / ".worktrees" / branch_name
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)

    # Create branch from current HEAD if it doesn't exist
    if branch_name not in [ref.name for ref in repo.references]:
        repo.create_head(branch_name)

    repo.git.worktree("add", str(worktree_dir), branch_name)
    logger.info("Created worktree at %s for branch %s", worktree_dir, branch_name)
    return worktree_dir


def _cleanup_worktree_sync(repo_path: Path, branch_name: str) -> None:
    """Remove a git worktree (blocking)."""
    repo = _get_repo(repo_path)
    worktree_dir = repo_path / ".worktrees" / branch_name

    if worktree_dir.exists():
        repo.git.worktree("remove", str(worktree_dir), "--force")
        logger.info("Removed worktree at %s", worktree_dir)

    # Delete branch if it exists and is fully merged
    try:
        if branch_name in [ref.name for ref in repo.heads]:
            repo.delete_head(branch_name, force=False)
            logger.info("Deleted branch %s", branch_name)
    except git.GitCommandError:
        logger.warning("Could not delete branch %s (may not be fully merged)", branch_name)


def _commit_and_push_sync(
    worktree_path: Path, message: str, push: bool = True
) -> str | None:
    """Stage all, commit, and optionally push (blocking). Returns commit SHA."""
    repo = git.Repo(worktree_path)

    # Stage all changes
    repo.git.add("-A")

    if not repo.is_dirty(untracked_files=True):
        logger.info("No changes to commit in %s", worktree_path)
        return None

    repo.index.commit(message)
    sha = repo.head.commit.hexsha
    logger.info("Committed %s in %s", sha[:8], worktree_path)

    if push:
        branch = repo.active_branch.name
        repo.git.push("origin", branch, "--set-upstream")
        logger.info("Pushed branch %s", branch)

    return sha


async def create_worktree(repo_path: Path, branch_name: str) -> Path:
    """Create a git worktree for isolated agent work."""
    async with _git_lock:
        return await asyncio.to_thread(_create_worktree_sync, repo_path, branch_name)


async def cleanup_worktree(repo_path: Path, branch_name: str) -> None:
    """Remove a worktree and optionally its branch."""
    async with _git_lock:
        await asyncio.to_thread(_cleanup_worktree_sync, repo_path, branch_name)


async def commit_and_push(
    worktree_path: Path, message: str, push: bool = True
) -> str | None:
    """Stage all changes, commit, and push from a worktree."""
    async with _git_lock:
        return await asyncio.to_thread(_commit_and_push_sync, worktree_path, message, push)
