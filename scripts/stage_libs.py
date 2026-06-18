"""Stage the system shared libraries a distroless runtime is missing.

`gcr.io/distroless/cc` ships glibc, libstdc++, and libgcc and nothing
else. The compiled extension modules in our wheels (numpy, onnxruntime, av,
cryptography, ...) link against a handful of *additional* system libraries
(libz, libgomp, liblzma, ...) that an ordinary Debian provides but distroless
does not. Importing such a wheel under distroless then dies with
`ImportError: libz.so.1: cannot open shared object file`.

distroless has no package manager, so the only way to add those libraries is
to `COPY` them in from a stage that has them. This script discovers exactly
which ones are needed and copies them into a staging tree, ready for a single
`COPY --from=... /staging-libs/ /` in the runtime stage. Discovery has two
parts:

1. **Link-time closure (automatic).** `ldd` is run over every `.so` in the
   given roots (the virtualenv and the managed interpreter). Each dependency
   that resolves to a real system path is a candidate. This is the
   `DT_NEEDED` graph, the libraries the dynamic loader resolves *eagerly*
   at load time, and it stays correct with no hand-maintenance as the
   dependency tree changes. Dependencies that resolve *inside* the venv or
   interpreter (vendored libraries shipped in the wheel) are ignored: they
   already travel with us.

2. **Runtime allowlist (manual).** A few libraries are loaded lazily via
   `dlopen` at call time and therefore carry no `DT_NEEDED` entry, so
   `ldd` cannot see them. The rare ones that are *mandatory* system
   libraries, not vendored in a wheel, must be named explicitly, one SONAME
   per line, in the allowlist file (`--allowlist`). Keeping this list short
   and explicit is deliberate: it is the audit trail of every system library
   we consciously ship into the hardened image, the surgical alternative to
   shipping a whole Debian userland "just in case".

Libraries distroless/cc already provides (the glibc family, the dynamic
loader, libstdc++, libgcc) are always excluded.

Each staged library is written under its original absolute path inside the
output directory (e.g. `/staging-libs/lib/x86_64-linux-gnu/libz.so.1`), so
merging that tree onto `/` in the runtime restores each library to a
multiarch directory already on the loader's default search path. This is
architecture-portable: builder and runtime are built for the same platform,
so the discovered paths are always correct for that platform.

Pure standard library, it runs inside the builder image with no third-party
dependencies.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Libraries distroless/cc already provides; never stage these. Matched against
# a file's basename, so e.g. `libc.so.6` is excluded but `libcrypto.so.3`
# (which starts with "libc" but not "libc.so") is not.
_EXCLUDED = re.compile(
    r"^(libc|libm|libdl|libpthread|librt|libutil|libresolv|"
    r"ld-linux.*|libstdc\+\+|libgcc_s)\.so",
)

# Standard directories to resolve an allowlisted SONAME in, in priority order.
# The globs expand to the multiarch dirs (e.g. /usr/lib/x86_64-linux-gnu) so
# the lookup is architecture-agnostic, no triplet is hard-coded.
_SEARCH_DIR_GLOBS = (
    "usr/lib/*-linux-gnu",
    "lib/*-linux-gnu",
    "usr/local/lib",
    "usr/lib",
    "lib",
)

# An ldd line looks like "<soname> => /resolved/path (0x...)"; capture the path.
_LDD_RESOLVED = re.compile(r"=>\s+(/\S+)")

_DEFAULT_ROOTS = ("/app/.venv", "/python")
_DEFAULT_OUTPUT = "/staging-libs"

# Cap how many paths are passed to a single ldd invocation, to stay clear of
# the OS argument-length limit on large dependency trees.
_LDD_BATCH = 256


def _find_shared_objects(roots: list[Path]) -> list[Path]:
    """Return every shared-object file (`*.so*`) found under *roots*.

    Args:
        roots: Directory trees to search recursively.

    Returns:
        A list of paths to regular `.so` files (symlinks dereferenced by the
        later copy step, not here).
    """
    found: list[Path] = []
    for root in roots:
        if root.is_dir():
            found.extend(path for path in root.rglob("*.so*") if path.is_file())
    return found


def _ldd_dependencies(objects: list[Path]) -> tuple[set[Path], set[str]]:
    """Resolve the link-time dependencies of *objects* via `ldd`.

    `ldd` is asked about the objects in batches. Lines whose dependency
    resolved to an absolute path are collected; lines reporting `not found`
    are returned separately so the caller can warn about them. `ldd` exits
    non-zero on the occasional non-dynamic object, which is expected and
    ignored, discovery is best-effort.

    Args:
        objects: Shared objects to inspect.

    Returns:
        A tuple `(resolved, not_found)` where `resolved` is the set of
        absolute paths every dependency resolved to, and `not_found` is the
        set of SONAMEs `ldd` could not resolve at all.
    """
    resolved: set[Path] = set()
    not_found: set[str] = set()
    for start in range(0, len(objects), _LDD_BATCH):
        batch = objects[start : start + _LDD_BATCH]
        cmd = ["ldd", *(str(path) for path in batch)]
        proc = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        for line in proc.stdout.splitlines():
            if "=> not found" in line:
                not_found.add(line.split("=>", 1)[0].strip())
                continue
            match = _LDD_RESOLVED.search(line)
            if match:
                resolved.add(Path(match.group(1)))
    return resolved, not_found


def _is_stageable_system_lib(path: Path) -> bool:
    """Decide whether *path* is a system library we should stage.

    A library qualifies when it lives under `/lib` or `/usr/lib` (i.e. it
    is a real system library, not a wheel-vendored one resolved inside the
    venv) and is not one distroless/cc already provides.

    Args:
        path: An absolute path reported by `ldd`.

    Returns:
        `True` if the library should be copied into the staging tree.
    """
    text = str(path)
    if not text.startswith(("/lib", "/usr/lib")):
        return False
    return _EXCLUDED.match(path.name) is None


def _resolve_soname(soname: str) -> Path | None:
    """Locate an allowlisted *soname* in the standard library directories.

    Args:
        soname: The library file name to find, e.g. `libGL.so.1`.

    Returns:
        The absolute path to the library, or `None` if it is not present.
    """
    root = Path("/")
    for pattern in _SEARCH_DIR_GLOBS:
        for directory in sorted(root.glob(pattern)):
            candidate = directory / soname
            if candidate.exists():
                return candidate
    return None


def _read_allowlist(path: Path) -> list[str]:
    """Return the SONAMEs listed in *path*.

    Blank lines and `#` comments (whole-line or trailing) are ignored.

    Args:
        path: The allowlist file.

    Returns:
        The SONAMEs to stage, in file order.
    """
    sonames: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            sonames.append(line)
    return sonames


def _stage(sources: set[Path], output_dir: Path) -> list[Path]:
    """Copy each library in *sources* into *output_dir*, mirroring its path.

    Symlinks are dereferenced (the real file's bytes are copied) but the
    destination keeps the referenced name, so a SONAME symlink such as
    `libz.so.1` lands as a real file named `libz.so.1`, exactly what the
    loader looks for. File mode and timestamps are preserved.

    Args:
        sources: Absolute paths of the libraries to copy.
        output_dir: Root of the staging tree.

    Returns:
        The staged destination paths, sorted.
    """
    staged: list[Path] = []
    for source in sorted(sources):
        dest = output_dir / source.relative_to("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        staged.append(dest)
    return staged


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument vector, or `None` to read from `sys.argv`.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Stage the system shared libraries a distroless runtime lacks.",
    )
    parser.add_argument(
        "--root",
        action="append",
        type=Path,
        dest="roots",
        metavar="DIR",
        help=(
            "Directory tree to scan for .so files (repeatable). "
            f"Default: {' '.join(_DEFAULT_ROOTS)}"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(_DEFAULT_OUTPUT),
        metavar="DIR",
        help=f"Staging directory to populate (default: {_DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        metavar="FILE",
        help="File of extra SONAMEs to stage (dlopen'd system libs), one per line.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Discover and stage the system shared libraries distroless omits.

    Args:
        argv: Argument vector, or `None` to read from `sys.argv`.

    Returns:
        Process exit code: `0` on success, `1` if no shared objects were
        found or an allowlisted SONAME could not be located in the builder.
    """
    args = _parse_args(argv)
    roots: list[Path] = args.roots or [Path(root) for root in _DEFAULT_ROOTS]

    objects = _find_shared_objects(roots)
    if not objects:
        joined = ", ".join(str(root) for root in roots)
        sys.stderr.write(f"stage_libs: no shared objects found under {joined}\n")
        return 1

    resolved, not_found = _ldd_dependencies(objects)
    system_libs = {path for path in resolved if _is_stageable_system_lib(path)}

    missing_allowlisted: list[str] = []
    if args.allowlist is not None and args.allowlist.is_file():
        for soname in _read_allowlist(args.allowlist):
            location = _resolve_soname(soname)
            if location is None:
                missing_allowlisted.append(soname)
            else:
                system_libs.add(location)

    args.output.mkdir(parents=True, exist_ok=True)
    staged = _stage(system_libs, args.output)

    for dest in staged:
        sys.stdout.write(f"staged {dest}\n")
    sys.stdout.write(f"stage_libs: staged {len(staged)} system librar(y/ies)\n")

    if not_found:
        joined = ", ".join(sorted(not_found))
        sys.stderr.write(
            "stage_libs: WARNING ldd could not resolve (vendored in a wheel or "
            f"loaded at runtime, usually harmless): {joined}\n",
        )

    if missing_allowlisted:
        joined = ", ".join(missing_allowlisted)
        sys.stderr.write(
            f"stage_libs: ERROR allowlisted SONAMEs not found in the builder: {joined}\n"
            "  Fix the name in the allowlist, or install the providing package "
            "in the builder stage.\n",
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
