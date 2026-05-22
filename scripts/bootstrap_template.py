#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# ruff: noqa: T201 -> allow print
# ruff: noqa: S607 -> allow git subprocess
"""One-time template initialization.

Renames the placeholder package (`my_project` / `my-project`) to a name derived
from the current directory (or chosen interactively), rewrites the relevant
fields in `pyproject.toml`, README, and tests, and deletes the stale
`uv.lock` so `uv sync` can regenerate it cleanly.

This script is invoked automatically by `make bootstrap` on first run. The
`Makefile` removes it (and the surrounding `scripts/` directory if empty)
after a successful exit so it does not linger in downstream project history.

Usage:
    uv run --script scripts/bootstrap_template.py            # interactive
    uv run --script scripts/bootstrap_template.py --yes      # accept defaults
"""

from __future__ import annotations

import argparse
import keyword
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
SRC = ROOT / "src"
README = ROOT / "README.md"
TESTS = ROOT / "tests"
UV_LOCK = ROOT / "uv.lock"
REPO_SETUP = ROOT / "docs" / "REPO_SETUP.md"

PLACEHOLDER_PROJECT = "my-project"
PLACEHOLDER_PACKAGE = "my_project"
PLACEHOLDER_DISPLAY = "[Project Name]"
PLACEHOLDER_DESCRIPTION = "Your project description"
PLACEHOLDER_PYPROJECT_DESCRIPTION = "Type your project description here."


@dataclass(frozen=True)
class TemplateInputs:
    """User-supplied (or inferred) values that drive the rename."""

    project: str
    package: str
    display: str
    description: str
    author_name: str
    author_email: str


# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------


def slugify_project(raw: str) -> str:
    """Return a PyPI-compatible project name (lower-case, hyphen-separated)."""
    slug = raw.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug or PLACEHOLDER_PROJECT


def slugify_package(raw: str) -> str:
    """Return a valid Python identifier derived from a project name."""
    ident = re.sub(r"[^a-z0-9_]+", "_", raw.strip().lower().replace("-", "_")).strip("_")
    if ident and ident[0].isdigit():
        ident = f"_{ident}"
    return ident or PLACEHOLDER_PACKAGE


def validate_package(name: str) -> str:
    """Raise if *name* is not usable as a top-level Python package."""
    if not name.isidentifier():
        msg = f"{name!r} is not a valid Python identifier"
        raise ValueError(msg)
    if keyword.iskeyword(name):
        msg = f"{name!r} is a reserved Python keyword"
        raise ValueError(msg)
    return name


def detect_git_author() -> tuple[str, str]:
    """Return (name, email) from `git config`, falling back to empty strings."""

    def _git(key: str) -> str:
        try:
            return subprocess.check_output(  # noqa: S603
                ["git", "config", "--get", key],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""

    return _git("user.name"), _git("user.email")


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------


def ask(prompt: str, default: str, *, non_interactive: bool) -> str:
    """Prompt the user with a default, or return the default in non-interactive mode."""
    if non_interactive or not sys.stdin.isatty():
        return default
    raw = input(f"  {prompt} [{default}]: ").strip()
    return raw or default


def confirm(prompt: str, *, default: bool = True, non_interactive: bool) -> bool:
    """Ask a yes/no question, defaulting to *default* in non-interactive mode."""
    if non_interactive or not sys.stdin.isatty():
        return default
    suffix = "Y/n" if default else "y/N"
    raw = input(f"  {prompt} [{suffix}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes"}


def collect_inputs(*, non_interactive: bool) -> TemplateInputs:
    """Gather all template values (interactively unless ``non_interactive``)."""
    project_default = slugify_project(ROOT.name)
    project = slugify_project(
        ask("Project name (PyPI-style)", project_default, non_interactive=non_interactive)
    )

    package_default = slugify_package(project)
    package = validate_package(
        slugify_package(
            ask(
                "Package name (Python identifier)", package_default, non_interactive=non_interactive
            )
        )
    )

    display_default = project.replace("-", " ").replace("_", " ").title()
    display = ask("Display name (for README)", display_default, non_interactive=non_interactive)

    description = ask(
        "Description",
        "A short description of your project.",
        non_interactive=non_interactive,
    )

    git_name, git_email = detect_git_author()
    author_name = ask("Author name", git_name or "Your Name", non_interactive=non_interactive)
    author_email = ask("Author email", git_email, non_interactive=non_interactive)

    return TemplateInputs(
        project=project,
        package=package,
        display=display,
        description=description,
        author_name=author_name,
        author_email=author_email,
    )


# ---------------------------------------------------------------------------
# Rewrites
# ---------------------------------------------------------------------------


def rename_package_dir(package: str) -> None:
    """Rename ``src/my_project`` to ``src/<package>`` (skip if already correct)."""
    source = SRC / PLACEHOLDER_PACKAGE
    target = SRC / package
    if not source.exists():
        if target.exists():
            print(f"  - package dir already renamed to src/{package}/")
            return
        msg = f"Expected placeholder layout at {source} but it is missing."
        raise FileNotFoundError(msg)
    if target.exists() and target != source:
        msg = f"Target {target} already exists; refusing to clobber."
        raise FileExistsError(msg)
    if target != source:
        source.rename(target)
        print(f"  - renamed src/{PLACEHOLDER_PACKAGE}/ -> src/{package}/")


def update_pyproject(inputs: TemplateInputs) -> None:
    """Update name, description, authors, and build module-name."""
    text = PYPROJECT.read_text()

    text = re.sub(
        rf'^name = "{re.escape(PLACEHOLDER_PROJECT)}"',
        f'name = "{inputs.project}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    text = text.replace(
        f'description = "{PLACEHOLDER_PYPROJECT_DESCRIPTION}"',
        f'description = "{inputs.description}"',
    )

    if inputs.author_email:
        new_authors = (
            f'authors = [{{ name = "{inputs.author_name}", email = "{inputs.author_email}" }}]'
        )
    else:
        new_authors = f'authors = [{{ name = "{inputs.author_name}" }}]'
    text = re.sub(r"^authors = .*$", new_authors, text, count=1, flags=re.MULTILINE)

    text = re.sub(
        rf'^module-name = "{re.escape(PLACEHOLDER_PACKAGE)}"',
        f'module-name = "{inputs.package}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )

    PYPROJECT.write_text(text)
    print("  - updated pyproject.toml")


def update_version_file(inputs: TemplateInputs) -> None:
    """Point ``importlib.metadata.version(...)`` at the new project name."""
    version_file = SRC / inputs.package / "__version__.py"
    if not version_file.exists():
        return
    text = version_file.read_text()
    new_text = text.replace(f'version("{PLACEHOLDER_PROJECT}")', f'version("{inputs.project}")')
    if new_text != text:
        version_file.write_text(new_text)
        print(f"  - updated {version_file.relative_to(ROOT)}")


def update_readme(inputs: TemplateInputs) -> None:
    """Swap placeholders and update the project-structure block."""
    text = README.read_text()
    text = text.replace(PLACEHOLDER_DISPLAY, inputs.display)
    text = text.replace(PLACEHOLDER_DESCRIPTION, inputs.description)
    text = text.replace(f"src/{PLACEHOLDER_PACKAGE}/", f"src/{inputs.package}/")
    README.write_text(text)
    print("  - updated README.md")


def update_test_imports(package: str) -> None:
    """Rewrite ``from my_project...`` imports under ``tests/`` to use the new package."""
    if package == PLACEHOLDER_PACKAGE:
        return
    pattern_from = re.compile(rf"\bfrom {re.escape(PLACEHOLDER_PACKAGE)}\b")
    pattern_import = re.compile(rf"\bimport {re.escape(PLACEHOLDER_PACKAGE)}\b")
    for path in TESTS.rglob("*.py"):
        text = path.read_text()
        new_text = pattern_from.sub(f"from {package}", text)
        new_text = pattern_import.sub(f"import {package}", new_text)
        if new_text != text:
            path.write_text(new_text)
            print(f"  - rewrote imports in {path.relative_to(ROOT)}")


def delete_uv_lock() -> None:
    """Drop the lock file so ``uv sync`` regenerates it under the new name."""
    if UV_LOCK.exists():
        UV_LOCK.unlink()
        print("  - deleted uv.lock (will be regenerated on next `uv sync`)")


def maybe_delete_repo_setup(*, non_interactive: bool) -> None:
    """Offer to delete `docs/REPO_SETUP.md` (template-specific docs)."""
    if not REPO_SETUP.exists():
        return
    if confirm(
        f"Delete {REPO_SETUP.relative_to(ROOT)}? (template-specific docs you likely don't need to keep)",
        default=True,
        non_interactive=non_interactive,
    ):
        REPO_SETUP.unlink()
        print(f"  - deleted {REPO_SETUP.relative_to(ROOT)}")


def self_delete() -> None:
    """Delete this script (and the surrounding `scripts/` dir if it ends up empty).

    Called near the end of bootstrap so the running process keeps working
    (the file is removed from disk, but the interpreter has already loaded it).
    Doing this from inside the script — rather than from the Makefile — means
    a subsequent ``reset_git_history`` call captures a clean working tree.
    """
    here = Path(__file__).resolve()
    parent = here.parent
    rel = here.relative_to(ROOT)
    if here.exists():
        here.unlink()
        print(f"  - removed {rel}")
    try:
        parent.rmdir()
    except OSError:
        return
    print(f"  - removed empty {parent.relative_to(ROOT)}/ dir")


# ---------------------------------------------------------------------------
# Git history reset
# ---------------------------------------------------------------------------


def decide_git_reset(*, override: bool | None, non_interactive: bool) -> bool:
    """Decide whether to wipe and re-initialize git history.

    Precedence: explicit CLI flag > non-interactive default (off) > prompt.
    """
    if override is not None:
        return override
    if non_interactive:
        return False
    return confirm(
        "Reset git history? (starts a fresh repo with one initial commit)",
        default=True,
        non_interactive=False,
    )


def _git_default_branch() -> str:
    """Return the user's configured ``init.defaultBranch``, falling back to ``main``."""
    try:
        out = subprocess.check_output(
            ["git", "config", "--get", "init.defaultBranch"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        out = ""
    return out or "main"


def reset_git_history(*, author_name: str, author_email: str) -> None:
    """Wipe ``.git/`` and create a fresh repo with a single initial commit.

    Author identity is passed via ``GIT_AUTHOR_*`` / ``GIT_COMMITTER_*`` env
    vars so the commit succeeds even when ``git config user.{name,email}`` is
    unset globally — which is common on fresh machines.
    """
    if shutil.which("git") is None:
        print("  - git not found on PATH; skipping git history reset")
        return

    git_dir = ROOT / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)
        print("  - removed existing .git/")

    branch = _git_default_branch()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": author_name or "Project Author",
        "GIT_AUTHOR_EMAIL": author_email or "author@example.invalid",
        "GIT_COMMITTER_NAME": author_name or "Project Author",
        "GIT_COMMITTER_EMAIL": author_email or "author@example.invalid",
    }
    subprocess.run(["git", "init", "-q", "-b", branch], cwd=ROOT, check=True)  # noqa: S603
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "chore: initial commit from template"],
        cwd=ROOT,
        env=env,
        check=True,
    )
    print(f"  - initialized fresh git repo on branch '{branch}' with one commit")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def print_plan(inputs: TemplateInputs, *, reset_git: bool) -> None:
    """Show the user exactly what will change before we touch anything."""
    print()
    print("The following changes will be made:")
    print(f"  - rename layout to src/{inputs.package}/")
    print(f"  - set [project].name = {inputs.project!r}")
    print(f"  - set [project].description = {inputs.description!r}")
    author = (
        f"{inputs.author_name} <{inputs.author_email}>"
        if inputs.author_email
        else inputs.author_name
    )
    print(f"  - set [project].authors = {author!r}")
    print(f"  - set [tool.uv.build-backend].module-name = {inputs.package!r}")
    print(f"  - replace placeholders in README.md ({PLACEHOLDER_DISPLAY!r}, project structure)")
    print(f"  - rewrite `{PLACEHOLDER_PACKAGE}` imports under tests/")
    print("  - delete uv.lock (regenerated on next `uv sync`)")
    print("  - remove this script (and the scripts/ dir if empty)")
    if reset_git:
        print("  - WIPE .git/ and create a fresh repo with a single initial commit")
    print()


def main() -> int:
    """Run the bootstrap interactively (or non-interactively with ``--yes``)."""
    parser = argparse.ArgumentParser(
        description="Initialize this template for a new project. Run via `make bootstrap`."
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Use inferred defaults without prompting (for CI / scripted use).",
    )
    parser.add_argument(
        "--reset-git",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Wipe the existing .git/ and create a fresh repo with one initial commit. "
            "If unspecified, you are prompted interactively (default Yes) or it is "
            "skipped under --yes."
        ),
    )
    args = parser.parse_args()
    non_interactive = bool(args.yes)

    print("=" * 60)
    print(" Template bootstrap")
    print("=" * 60)
    print(f"  Detected directory: {ROOT.name}")
    print()
    if not non_interactive:
        print("Press <enter> to accept each default in [brackets].")
        print()

    inputs = collect_inputs(non_interactive=non_interactive)
    reset_git = decide_git_reset(override=args.reset_git, non_interactive=non_interactive)
    print_plan(inputs, reset_git=reset_git)

    if not confirm("Proceed with these changes?", default=True, non_interactive=non_interactive):
        print("Aborted. No files were modified.")
        return 1

    print()
    rename_package_dir(inputs.package)
    update_pyproject(inputs)
    update_version_file(inputs)
    update_readme(inputs)
    update_test_imports(inputs.package)
    delete_uv_lock()
    print()
    maybe_delete_repo_setup(non_interactive=non_interactive)
    print()
    self_delete()
    if reset_git:
        print()
        reset_git_history(author_name=inputs.author_name, author_email=inputs.author_email)

    print()
    print("Template initialization complete.")
    print("`make bootstrap` will now finish installing dependencies and pre-commit hooks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
