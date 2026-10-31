import difflib
from pathlib import Path, PurePosixPath, PureWindowsPath

from debugging import redact_secret_values
from retrieval import _iter_source_files


MAX_PATCH_FILE_BYTES = 100_000
MAX_PATCH_BYTES = 200_000


class PatchTargetError(ValueError):
    pass


def read_patch_target(
    relative_path: str,
    repository_root: Path,
    searchable_extensions: set[str],
    ignored_directories: set[str],
) -> str:
    """Read one listed source file, rejecting paths and content unsafe to send to a model."""
    source_path = resolve_patch_target(
        relative_path, repository_root, searchable_extensions, ignored_directories
    )
    try:
        if source_path.stat().st_size > MAX_PATCH_FILE_BYTES:
            raise PatchTargetError("The selected file is too large to generate a patch safely.")
        content = source_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PatchTargetError("The selected file is not valid UTF-8 text.") from exc
    except OSError as exc:
        raise PatchTargetError("The selected file could not be read.") from exc

    if redact_secret_values(content) != content:
        raise PatchTargetError("The selected file appears to contain a secret; patch generation is disabled for it.")
    return content


def resolve_patch_target(
    relative_path: str,
    repository_root: Path,
    searchable_extensions: set[str],
    ignored_directories: set[str],
) -> Path:
    """Resolve a listed source file using the repository scanner's symlink and extension rules."""
    normalized = relative_path.replace("\\", "/").strip()
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(relative_path)
    if (
        not normalized
        or posix.is_absolute()
        or windows.is_absolute()
        or ".." in posix.parts
        or "\x00" in normalized
    ):
        raise PatchTargetError("Choose a relative file inside the configured project.")

    allowed = {
        item[0]: item[1]
        for item in _iter_source_files(repository_root, searchable_extensions, ignored_directories)
    }
    source_path = allowed.get(posix.as_posix())
    if source_path is None:
        raise PatchTargetError("The selected file is not an accessible supported source file.")
    return source_path


def build_unified_diff(relative_path: str, original: str, proposed: str) -> str:
    """Build a reviewable one-file unified diff without modifying the source file."""
    if original == proposed:
        raise PatchTargetError("The proposed content contains no changes.")
    normalized_path = PurePosixPath(relative_path.replace("\\", "/"))
    if normalized_path.is_absolute() or ".." in normalized_path.parts:
        raise PatchTargetError("The diff path must be a relative project path.")

    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        proposed.splitlines(keepends=True),
        fromfile=f"a/{normalized_path.as_posix()}",
        tofile=f"b/{normalized_path.as_posix()}",
        n=3,
    ))
    if not diff or len(diff.encode("utf-8")) > MAX_PATCH_BYTES:
        raise PatchTargetError("The generated diff is empty or exceeds the review size limit.")
    return diff
