"""Validate that every compiled extension module in the venv actually loads.

The distroless runtime ships only the system libraries `scripts/stage_libs.py`
could discover through `ldd` (the eager `DT_NEEDED` closure) plus those
named in `extra-libs.txt`. A compiled wheel can still reach for a system
library *lazily*, via `dlopen` at import time, which `ldd` never sees and
staging therefore misses. On distroless that gap surfaces as
`ImportError: libfoo.so.1: cannot open shared object file` at *runtime*, in
production, instead of at build time.

This script closes the gap: it imports every extension module the venv ships
and fails the build if any of them cannot be dynamically *linked*. It runs as
the final step of the hardened (distroless) image build, so a missing or
ABI-incompatible system library stops the release instead of paging someone at
3am.

Discovery is self-maintaining: it globs the interpreter's site-packages for
files whose name ends in the platform's extension suffix (`EXT_SUFFIX`, e.g.
`.cpython-313-x86_64-linux-gnu.so`) or the stable-ABI suffix (`.abi3.so`,
used by e.g. cryptography's Rust bindings), derives the dotted module name from
each path, and imports it. There is no list of packages to keep in sync.

Only *linkage* failures are fatal. Importing a compiled module standalone can
raise for perfectly benign reasons, a submodule not meant to be imported
directly, an optional dependency that is absent, and those are not what this
gate tests. It therefore fails the build only when the failure looks like a
real dynamic-linker problem (a missing shared object, an undefined symbol, an
ABI/arch mismatch); everything else is reported and skipped.

Scope is deliberately limited to the venv's site-packages, the project's own
dependency surface. The managed interpreter's optional stdlib extensions
(`_tkinter`, `_curses`, ...) are *not* swept: distroless legitimately lacks
the libraries some of them want, and the app does not use them.

Pure standard library, it runs inside the distroless image, which has no
third-party tooling and no shell.
"""

from __future__ import annotations

import argparse
import importlib.machinery
import sys
import sysconfig
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

# Substrings that mark an import failure as a real dynamic-linker problem, the
# only failures this gate treats as fatal. Matched against `str(exception)`.
_LINKAGE_ERROR_MARKERS: tuple[str, ...] = (
    "cannot open shared object file",  # missing system library
    "undefined symbol",  # ABI mismatch / missing symbol provider
    "GLIBC_",  # glibc too old: "version `GLIBC_x.y' not found"
    "wrong ELF class",  # 32/64-bit or architecture mismatch
    "failed to map segment",  # corrupt / incompatible shared object
)


def _extension_suffixes() -> tuple[str, ...]:
    """Return the filename suffixes that denote an importable extension module.

    Derived from :data:`importlib.machinery.EXTENSION_SUFFIXES`, the very list
    the import system itself uses, with the ambiguous bare `.so` removed. A
    plain `.so` is also how auditwheel vendors third-party libraries into a
    wheel, and those are not importable modules; importing them would be noise
    at best and a misleading failure at worst. What remains is the
    version-specific suffix (`EXT_SUFFIX`, e.g.
    `.cpython-313-x86_64-linux-gnu.so`) and the stable-ABI suffix
    (`.abi3.so`, PEP 384, used by e.g. cryptography's Rust binding). Both are
    standard CPython conventions, so discovery needs no per-project upkeep.
    """
    return tuple(s for s in importlib.machinery.EXTENSION_SUFFIXES if s != ".so")


def _site_packages_dirs() -> list[Path]:
    """Return the running interpreter's purelib/platlib dirs (deduplicated)."""
    dirs: set[Path] = set()
    for key in ("purelib", "platlib"):
        path = Path(sysconfig.get_path(key))
        if path.is_dir():
            dirs.add(path.resolve())
    return sorted(dirs)


def _module_name(path: Path, root: Path, suffix: str) -> str:
    """Derive the dotted import name of extension *path* located under *root*."""
    relative = path.relative_to(root)
    stem = relative.name[: -len(suffix)]
    return ".".join((*relative.parent.parts, stem))


def _iter_extension_modules(roots: Sequence[Path]) -> Iterator[tuple[str, Path]]:
    """Yield `(module_name, path)` for every extension module under *roots*."""
    suffixes = _extension_suffixes()
    seen: set[str] = set()
    for root in roots:
        for path in sorted(root.rglob("*.so")):
            suffix = next((s for s in suffixes if path.name.endswith(s)), None)
            if suffix is None:
                continue
            name = _module_name(path, root, suffix)
            if name not in seen:
                seen.add(name)
                yield name, path


def _is_linkage_error(exc: Exception) -> bool:
    """Return whether *exc* looks like a fatal dynamic-linker failure."""
    message = str(exc)
    return any(marker in message for marker in _LINKAGE_ERROR_MARKERS)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Import every compiled extension module in the venv and "
        "fail if any cannot be dynamically linked.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        action="append",
        default=None,
        help="Directory to scan for extension modules (repeatable). Defaults to "
        "the running interpreter's site-packages.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Import every extension module and report dynamic-linkage failures.

    Returns:
        `0` if every module either imported cleanly or failed for a
        non-linkage reason; `1` if any module failed to link, or if no
        extension modules were found at all.
    """
    args = _parse_args(argv)
    roots = args.root or _site_packages_dirs()

    checked = 0
    skipped = 0
    failures: list[tuple[str, str]] = []

    for name, _path in _iter_extension_modules(roots):
        checked += 1
        try:
            importlib.import_module(name)
        except Exception as exc:  # broad on purpose: re-classified below
            if _is_linkage_error(exc):
                failures.append((name, f"{type(exc).__name__}: {exc}"))
            else:
                skipped += 1
                sys.stderr.write(
                    f"validate_imports: skipped {name} (non-linkage {type(exc).__name__}: {exc})\n",
                )

    if checked == 0:
        roots_text = ", ".join(str(r) for r in roots)
        sys.stderr.write(
            "validate_imports: ERROR no extension modules found under "
            f"{roots_text}, is the virtualenv present?\n",
        )
        return 1

    for name, detail in failures:
        sys.stderr.write(f"validate_imports: FAIL {name}: {detail}\n")

    linked = checked - len(failures) - skipped
    sys.stdout.write(
        f"validate_imports: {linked} linked, {skipped} skipped, "
        f"{len(failures)} failed (of {checked} extension modules)\n",
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
