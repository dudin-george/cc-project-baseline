"""Populate a project repo with specs and CLAUDE.md from Mycroft state."""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from mycroft.server.pipeline.state import get_step_documents
from mycroft.server.state.project import ProjectState
from mycroft.shared.protocol import StepId

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates"


def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )


def populate_repo(repo_path: Path, project: ProjectState) -> list[str]:
    """Copy all project specs into the repo's docs/specs/ directory.

    Returns list of relative file paths written.
    """
    written: list[str] = []
    specs_dir = repo_path / "docs" / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)

    # Copy documents from each completed step
    step_doc_sources: list[tuple[StepId, str]] = [
        (StepId.IDEA_SCOPING, ""),
        (StepId.USE_CASES_AUTO, ""),
        (StepId.ARCHITECTURE_AUTO, ""),
        (StepId.C4_DESIGN, ""),
    ]
    for step_id, _subdir in step_doc_sources:
        docs = get_step_documents(project, step_id)
        for filename, content in docs.items():
            dest = specs_dir / filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)
            written.append(f"docs/specs/{filename}")
            logger.info("Wrote %s", dest)

    return written


def generate_claude_md(project: ProjectState) -> str:
    """Generate the CLAUDE.md file content from project state.

    Fills in the AUTO sections with real project data,
    leaves PLACEHOLDER sections for user customization.
    """
    # Gather project data
    idea_docs = get_step_documents(project, StepId.IDEA_SCOPING)
    arch_docs = get_step_documents(project, StepId.ARCHITECTURE_AUTO)
    design_docs = get_step_documents(project, StepId.C4_DESIGN)

    # Build service list from architecture docs
    service_files = [k for k in arch_docs if k.startswith("services/")]
    design_files = [k for k in design_docs if k.startswith("03-design/")]

    sections = []
    sections.append(f"# Project: {project.project_name}\n")
    sections.append("> This file is the single source of truth for all AI agents working on this project.\n")
    sections.append("---\n")

    # Section 1: Overview (from idea doc)
    sections.append("## 1. Project Overview\n")
    idea_content = idea_docs.get("00-idea.md", "*No idea document found.*")
    sections.append(idea_content + "\n")

    # Section 2: Architecture summary
    sections.append("## 2. Architecture Summary\n")
    arch_content = arch_docs.get("02-architecture.md", "*No architecture document found.*")
    sections.append(arch_content + "\n")

    # Section 3: Service specs
    sections.append("## 3. Service Specifications\n")
    if service_files:
        for f in sorted(service_files):
            sections.append(f"- [docs/specs/{f}](docs/specs/{f})")
    else:
        sections.append("*No service specs found.*")
    sections.append("")

    # Section 4: C4 L4 design
    sections.append("## 4. C4 Level 4 Design\n")
    if design_files:
        for f in sorted(design_files):
            sections.append(f"- [docs/specs/{f}](docs/specs/{f})")
    else:
        sections.append("*No C4 Level 4 design docs found.*")
    sections.append("")

    sections.append("---\n")

    # Sections 5-12: Placeholder sections for user customization
    placeholder_sections = [
        ("5", "General Coding Conventions", "Add your project-wide coding conventions here"),
        ("6", "Team Lead Instructions", "Add team lead behavior rules here"),
        ("7", "CodeWriter Agent Instructions", "Add code writer specific rules here"),
        ("8", "UnitTester Agent Instructions", "Add unit test specific rules here"),
        ("9", "QATester Agent Instructions", "Add QA tester specific rules here"),
        ("10", "Blocker Rules", "Define when agents should create blockers"),
        ("11", "Git Conventions", None),
        ("12", "Security", "Add security rules specific to your project"),
    ]

    for num, title, placeholder in placeholder_sections:
        sections.append(f"## {num}. {title}\n")
        if placeholder:
            sections.append(f"[PLACEHOLDER: USER — {placeholder}]\n")
        else:
            # Git conventions — fill with defaults
            sections.append(
                'Branch naming: `mycroft/<linear-id>-<short-description>`\n'
                "Commit format: `feat|fix|refactor|test|docs: <short description>`\n"
            )
        sections.append("---\n")

    return "\n".join(sections)


def write_claude_md(repo_path: Path, project: ProjectState) -> str:
    """Generate and write CLAUDE.md to the repo root. Returns the path written."""
    content = generate_claude_md(project)
    dest = repo_path / "CLAUDE.md"
    dest.write_text(content)
    logger.info("Wrote CLAUDE.md to %s", dest)
    return str(dest)
