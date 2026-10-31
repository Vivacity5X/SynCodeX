"""Request-scoped repository resolution and project capability detection."""

import json
import os
from pathlib import Path


DEFAULT_REPOSITORY_ROOT = Path(
    os.getenv("SYNCODEX_PROJECT_ROOT") or Path(__file__).resolve().parent.parent
).expanduser().resolve()


def resolve_repository_root(value: str | None) -> Path:
    candidate = Path(value).expanduser() if value else DEFAULT_REPOSITORY_ROOT
    try:
        root = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("The selected repository directory does not exist.") from exc
    if not root.is_dir():
        raise ValueError("The selected repository path is not a directory.")
    return root


def inspect_project(root: Path) -> dict:
    """Detect project families from bounded manifest and source-file inspection."""
    manifests: dict[str, str] = {}
    manifest_names = {
        "pom.xml", "build.gradle", "build.gradle.kts", "requirements.txt",
        "pyproject.toml", "package.json", "tsconfig.json",
    }
    ignored = {".git", ".venv", "venv", "node_modules", "target", "build", "dist", "__pycache__", ".syncodex"}
    manifest_count = 0
    for current, directories, files in os.walk(root):
        current_path = Path(current)
        directories[:] = [
            name for name in directories
            if name not in ignored and not name.startswith(".") and not (current_path / name).is_symlink()
        ]
        for filename in files:
            if filename.casefold() not in manifest_names:
                continue
            path = Path(current) / filename
            try:
                if path.is_symlink() or path.stat().st_size > 200_000:
                    continue
                manifests[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8", errors="replace")
                manifest_count += 1
                if manifest_count >= 100:
                    break
            except OSError:
                continue
        if manifest_count >= 100:
            break

    names = {Path(name).name.casefold() for name in manifests}
    contents = "\n".join(manifests.values()).casefold()
    detected: list[str] = []
    languages: set[str] = set()
    inspected_files = 0
    for current, directories, files in os.walk(root):
        current_path = Path(current)
        directories[:] = [
            name for name in directories
            if name not in ignored and not name.startswith(".") and not (current_path / name).is_symlink()
        ]
        for filename in files:
            inspected_files += 1
            suffix = Path(filename).suffix.casefold()
            if suffix == ".java": languages.add("Java")
            elif suffix == ".py": languages.add("Python")
            elif suffix in {".ts", ".tsx"}: languages.add("TypeScript")
            elif suffix in {".js", ".jsx"}: languages.add("JavaScript")
            if len(languages) == 4:
                break
            if inspected_files >= 10_000:
                break
        if len(languages) == 4:
            break
        if inspected_files >= 10_000:
            break

    if {"pom.xml", "build.gradle", "build.gradle.kts"} & names and ("spring-boot" in contents or "org.springframework.boot" in contents):
        detected.append("Java/Spring Boot")
    if {"requirements.txt", "pyproject.toml"} & names and "fastapi" in contents:
        detected.append("Python/FastAPI")
    package = next((text for name, text in manifests.items() if Path(name).name.casefold() == "package.json"), "")
    if "react" in package.casefold() and (".tsx" in package.casefold() or "tsconfig.json" in names or "TypeScript" in languages):
        detected.append("React/TypeScript")

    debug_languages = sorted(languages & {"Java", "Python"})
    unsupported = sorted(languages - {"Java", "Python"})
    if not detected:
        message = "No supported project framework was detected; repository text search is available, but framework-specific analysis is limited."
    elif not debug_languages:
        message = "Project detected, but stack-trace debugging is implemented only for Java and Python frames."
    else:
        message = "Project detected. Debugging parses Java and Python stack frames; other languages use repository context only."
    return {
        "repository": str(root),
        "project_types": detected,
        "languages": sorted(languages),
        "debug_languages": debug_languages,
        "unsupported_debug_languages": unsupported,
        "message": message,
        "manifests": sorted(manifests),
    }
