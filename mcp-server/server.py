
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("SynCodeX")

# SynCodeX project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.resolve()

IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "target",
    "build",
    "dist",
    "__pycache__",
}

SEARCHABLE_EXTENSIONS = {
    ".java",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".css",
    ".json",
    ".xml",
    ".properties",
    ".yml",
    ".yaml",
    ".md",
    ".sql",
}


def is_safe_project_path(relative_path: str) -> Path:
    """Resolve a path and prevent access outside the project root."""
    candidate = (PROJECT_ROOT / relative_path).resolve()

    if not candidate.is_relative_to(PROJECT_ROOT):
        raise ValueError("Access outside the SynCodeX project is not allowed.")

    if any(part in IGNORED_DIRECTORIES for part in candidate.relative_to(PROJECT_ROOT).parts):
        raise ValueError("Access to ignored directories is not allowed.")

    return candidate


@mcp.tool()
def list_project_files() -> list[str]:
    """List searchable source files inside the SynCodeX project."""
    results = []

    for current_dir, directories, filenames in os.walk(PROJECT_ROOT):
        current_path = Path(current_dir)
        directories[:] = sorted(
            directory
            for directory in directories
            if directory not in IGNORED_DIRECTORIES and not directory.startswith(".")
        )

        for filename in filenames:
            path = current_path / filename
            if path.suffix.lower() in SEARCHABLE_EXTENSIONS:
                results.append(path.relative_to(PROJECT_ROOT).as_posix())

    return sorted(results)[:500]


@mcp.tool()
def read_file(path: str) -> str:
    """Read a UTF-8 text file within the SynCodeX project."""
    file_path = is_safe_project_path(path)

    if not file_path.is_file():
        raise ValueError("The requested file does not exist.")

    if file_path.suffix.lower() not in SEARCHABLE_EXTENSIONS:
        raise ValueError("This file type is not supported.")

    if file_path.stat().st_size > 200_000:
        raise ValueError("File is too large to read in one request.")

    return file_path.read_text(encoding="utf-8")


@mcp.tool()
def search_repository(query: str) -> list[dict]:
    """Search project source files for a case-insensitive text match."""
    query = query.strip()

    if not query:
        raise ValueError("Search query cannot be empty.")

    if len(query) > 200:
        raise ValueError("Search query is too long.")

    results = []

    for relative_path in list_project_files():
        file_path = is_safe_project_path(relative_path)

        try:
            if file_path.stat().st_size > 1_000_000:
                continue
            lines = file_path.read_text(
                encoding="utf-8",
                errors="replace",
            ).splitlines()
        except OSError:
            continue

        for line_number, line in enumerate(lines, start=1):
            if query.casefold() in line.casefold():
                results.append({
                    "file": relative_path,
                    "line": line_number,
                    "content": line.strip()[:500],
                })

                if len(results) >= 100:
                    return results

    return results


if __name__ == "__main__":
    mcp.run()
