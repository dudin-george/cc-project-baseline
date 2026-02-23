"""Git operations for the docs repository — clone, commit, push."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import git

from mycroft.server.settings import settings
from mycroft.server.state.project import ProjectState

logger = logging.getLogger(__name__)

_git_lock = asyncio.Lock()


def _get_repo() -> git.Repo:
    """Get or clone the docs repo."""
    repo_path = settings.docs_repo_local_path

    if repo_path.exists() and (repo_path / ".git").exists():
        repo = git.Repo(repo_path)
        # Pull latest
        try:
            repo.remotes.origin.pull()
        except Exception:
            logger.warning("Failed to pull latest docs repo changes")
        return repo

    # Clone
    repo_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Cloning docs repo to %s", repo_path)
    return git.Repo.clone_from(settings.docs_repo_url, repo_path)


def _sync_commit_push(project: ProjectState, filename: str, content: str) -> None:
    """Blocking git operations: write, add, commit, push."""
    repo = _get_repo()
    repo_path = Path(repo.working_dir)

    # Write file under project slug directory
    project_dir = repo_path / project.slug
    file_path = project_dir / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content)

    # Stage
    rel_path = file_path.relative_to(repo_path)
    repo.index.add([str(rel_path)])

    # Commit
    message = f"[{project.slug}] Update {filename}"
    repo.index.commit(message)

    # Push
    repo.remotes.origin.push()
    logger.info("Pushed %s to docs repo", rel_path)


async def commit_and_push(project: ProjectState, filename: str, content: str) -> None:
    """Async wrapper: serialize git operations and run in thread."""
    async with _git_lock:
        await asyncio.to_thread(_sync_commit_push, project, filename, content)
