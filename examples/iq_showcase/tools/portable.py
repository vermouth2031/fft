"""Repository-relative provenance and adapter for the original capture verifier."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import tempfile


def discover_project(start: Path | None = None) -> Path:
    start = (start or Path(__file__)).resolve()
    for candidate in (start, *start.parents):
        if (candidate / "config/build_profile.json").is_file() and (candidate / "host").is_dir():
            return candidate
    raise ValueError("Cannot find the repository root; supply --project explicitly.")


def safe_path(root: Path, relative: str) -> Path:
    """Accept only portable relative paths which resolve inside their owner."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError(f"Not a portable relative path: {relative!r}")
    if PureWindowsPath(relative).drive or PurePosixPath(relative).is_absolute():
        raise ValueError(f"Absolute provenance path is forbidden: {relative!r}")
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError(f"Provenance path escapes its root: {relative!r}")
    return result


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def binding_name(path: Path, project: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError as error:
        raise ValueError("Reference sources and --out must be inside --project.") from error


def portable_oracle(identity: dict) -> dict:
    # Model hashes describe the reviewed oracle; installation paths do not.
    return {key: value for key, value in identity.items() if not key.endswith("_path")}


@contextmanager
def materialized_reference(reference: Path, project: Path):
    """Resolve checked bindings temporarily, without editing published evidence.

    The original verifier accepts absolute bindings. Its implementation is kept
    unchanged, while this adapter checks each repository-relative binding before
    passing a private temporary copy to that verifier.
    """
    value = json.loads(reference.read_text(encoding="utf-8-sig"))
    if value.get("binding_base") != "repository":
        raise ValueError("Expected a published repository-relative reference.")
    bindings = value.get("bindings")
    if not isinstance(bindings, dict) or not bindings:
        raise ValueError("Reference has no source bindings.")
    resolved = {}
    for relative, expected in bindings.items():
        path = safe_path(project, relative)
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"Reference binding changed: {relative}")
        resolved[str(path)] = expected
    value["bindings"] = resolved
    with tempfile.TemporaryDirectory(prefix="iq-showcase-reference-") as directory:
        target = Path(directory) / "qualification.json"
        target.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        yield target
