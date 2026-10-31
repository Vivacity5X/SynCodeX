
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10, which does not include tomllib.
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("SynCodeX")

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _configured_project_root() -> Path:
    configured = os.environ.get("SYNCODEX_PROJECT_ROOT")
    root = Path(configured).expanduser() if configured else DEFAULT_PROJECT_ROOT
    try:
        root = root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RuntimeError("SYNCODEX_PROJECT_ROOT must point to an existing directory.") from exc
    if not root.is_dir():
        raise RuntimeError("SYNCODEX_PROJECT_ROOT must point to a directory.")
    return root


PROJECT_ROOT = _configured_project_root()

IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "target",
    "build",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".gradle",
    ".syncodex",
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

SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials",
    "secrets",
    "id_rsa",
    "id_ed25519",
}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore"}
MAX_READ_BYTES = 200_000
MAX_SEARCH_FILE_BYTES = 1_000_000
MAX_LIST_RESULTS = 500
MAX_SEARCH_RESULTS = 100
MAX_MANIFESTS = 100
DEPENDENCY_MANIFEST_NAMES = {
    "pom.xml", "build.gradle", "build.gradle.kts", "requirements.txt", "pyproject.toml",
}
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:[\w.-]*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|credential)[\w.-]*)\b\s*[:=]\s*)([^\s,;#]+)"
)


def is_safe_project_path(relative_path: str) -> Path:
    """Resolve an authorized source file without following links or exposing secrets."""
    if not relative_path or Path(relative_path).is_absolute():
        raise ValueError("A relative project file path is required.")

    unresolved = PROJECT_ROOT / relative_path
    relative = unresolved.relative_to(PROJECT_ROOT)
    cursor = PROJECT_ROOT
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("Symbolic links are not allowed.")
    try:
        candidate = unresolved.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("The requested file does not exist.") from exc

    if not candidate.is_relative_to(PROJECT_ROOT):
        raise ValueError("Access outside the configured project root is not allowed.")

    if any(part in IGNORED_DIRECTORIES for part in candidate.relative_to(PROJECT_ROOT).parts):
        raise ValueError("Access to ignored directories is not allowed.")

    if _is_sensitive(candidate):
        raise ValueError("Access to sensitive files is not allowed.")

    return candidate


def _is_sensitive(path: Path) -> bool:
    name = path.name.casefold()
    return (
        name in SENSITIVE_NAMES
        or name.startswith(".env.")
        or path.suffix.casefold() in SENSITIVE_SUFFIXES
        or any(token in name for token in ("credential", "secret", "private_key"))
    )


def _redact_secrets(text: str) -> str:
    """Redact common key/value secrets while preserving configuration keys."""
    return SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", text)


def _find_dependency_manifests() -> list[str]:
    manifests = []
    for current_dir, directories, filenames in os.walk(PROJECT_ROOT):
        current_path = Path(current_dir)
        directories[:] = sorted(
            directory for directory in directories
            if directory not in IGNORED_DIRECTORIES
            and not directory.startswith(".")
            and not (current_path / directory).is_symlink()
        )
        for filename in filenames:
            path = current_path / filename
            if filename.casefold() in DEPENDENCY_MANIFEST_NAMES and not path.is_symlink():
                manifests.append(path.relative_to(PROJECT_ROOT).as_posix())
                if len(manifests) >= MAX_MANIFESTS:
                    return sorted(manifests, key=str.casefold)
    return sorted(manifests, key=str.casefold)


@mcp.tool()
def list_project_files() -> list[str]:
    """List supported, non-sensitive source files inside the configured project."""
    results = []

    for current_dir, directories, filenames in os.walk(PROJECT_ROOT):
        current_path = Path(current_dir)
        directories[:] = sorted(
            directory
            for directory in directories
            if directory not in IGNORED_DIRECTORIES
            and not directory.startswith(".")
            and not (current_path / directory).is_symlink()
        )

        for filename in filenames:
            path = current_path / filename
            if (
                path.suffix.lower() in SEARCHABLE_EXTENSIONS
                and not path.is_symlink()
                and not _is_sensitive(path)
            ):
                results.append(path.relative_to(PROJECT_ROOT).as_posix())

    return sorted(results)[:MAX_LIST_RESULTS]


@mcp.tool()
def read_file(path: str) -> str:
    """Read a UTF-8 text file within the selected project root."""
    file_path = is_safe_project_path(path)

    if not file_path.is_file():
        raise ValueError("The requested file does not exist.")

    if file_path.suffix.lower() not in SEARCHABLE_EXTENSIONS:
        raise ValueError("This file type is not supported.")

    if file_path.stat().st_size > MAX_READ_BYTES:
        raise ValueError("File is too large to read in one request.")

    return _redact_secrets(file_path.read_text(encoding="utf-8"))


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
            if file_path.stat().st_size > MAX_SEARCH_FILE_BYTES:
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
                    "content": _redact_secrets(line.strip())[:500],
                })

                if len(results) >= MAX_SEARCH_RESULTS:
                    return results

    return results


@mcp.tool()
def find_symbol(symbol: str) -> list[dict]:
    """Find likely class, function, method, interface, and variable declarations by text pattern."""
    symbol = symbol.strip()
    if not symbol or len(symbol) > 200:
        raise ValueError("Symbol must contain between 1 and 200 characters.")

    patterns = (
        ("python", re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\("), "function"),
        ("python", re.compile(r"^\s*class\s+([A-Za-z_]\w*)\b"), "class"),
        ("java", re.compile(r"^\s*(?:public|protected|private|static|abstract|final|\s)+\s*(class|interface|enum|record)\s+([A-Za-z_]\w*)\b"), "type"),
        ("java", re.compile(r"^\s*(?:public|protected|private|static|final|synchronized|\s)+[\w<>?,.\[\]]+\s+([A-Za-z_]\w*)\s*\([^;]*\)\s*(?:\{|throws\b)"), "method"),
        ("js", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_$]\w*)\s*\("), "function"),
        ("js", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?(?:class|interface|type)\s+([A-Za-z_$]\w*)\b"), "type"),
        ("js", re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$]\w*)\s*="), "variable"),
    )
    results = []
    for relative_path in list_project_files():
        extension = Path(relative_path).suffix.casefold()
        languages = {".py": "python", ".java": "java", ".js": "js", ".jsx": "js", ".ts": "js", ".tsx": "js"}
        language = languages.get(extension)
        if language is None:
            continue
        try:
            source_path = is_safe_project_path(relative_path)
            if source_path.stat().st_size > MAX_READ_BYTES:
                continue
            lines = source_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except (OSError, ValueError):
            continue

        for line_number, line in enumerate(lines, 1):
            for pattern_language, pattern, kind in patterns:
                if pattern_language != language:
                    continue
                match = pattern.match(line)
                if match and match.group(1 if kind != "type" or pattern_language != "java" else 2).casefold() == symbol.casefold():
                    results.append({
                        "file": relative_path,
                        "line": line_number,
                        "symbol": symbol,
                        "kind": kind,
                        "declaration": _redact_secrets(line.strip())[:300],
                        "match_type": "text_pattern",
                    })
                    if len(results) >= 100:
                        return results
                    break
    return results


@mcp.tool()
def find_references(symbol: str) -> list[dict]:
    """Find textual occurrences of a symbol; matches are not semantic references."""
    symbol = symbol.strip()
    if not symbol or len(symbol) > 200:
        raise ValueError("Symbol must contain between 1 and 200 characters.")
    pattern = re.compile(rf"(?<![\w$]){re.escape(symbol)}(?![\w$])", re.IGNORECASE)
    results = []
    for relative_path in list_project_files():
        try:
            path = is_safe_project_path(relative_path)
            if path.stat().st_size > MAX_SEARCH_FILE_BYTES:
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except (OSError, ValueError):
            continue
        for line_number, line in enumerate(lines, 1):
            if pattern.search(line):
                results.append({
                    "file": relative_path,
                    "line": line_number,
                    "content": _redact_secrets(line.strip())[:300],
                    "match_type": "text",
                })
                if len(results) >= MAX_SEARCH_RESULTS:
                    return results
    return results


@mcp.tool()
def get_project_structure() -> dict:
    """Summarize source directories, test paths, manifests, and common entry points."""
    files = list_project_files()
    directories = sorted({
        part
        for filename in files
        for part in Path(filename).parts[:-1]
    }, key=str.casefold)
    manifests = _find_dependency_manifests()
    tests = [filename for filename in files if any(part.casefold() in {"test", "tests"} for part in Path(filename).parts[:-1])]
    entry_names = {"main.java", "application.java", "main.py", "app.py", "index.ts", "index.js"}
    entry_points = [filename for filename in files if Path(filename).name.casefold() in entry_names]
    return {
        "root_name": PROJECT_ROOT.name,
        "source_directories": [item for item in directories if item.split("/")[0].casefold() in {"src", "app", "ai-service", "backend", "frontend", "mcp-server"}],
        "test_files": tests[:100],
        "manifests": manifests,
        "entry_points": entry_points[:100],
        "listed_file_count": len(files),
        "file_list_truncated": len(files) >= MAX_LIST_RESULTS,
    }


@mcp.tool()
def analyze_dependencies() -> list[dict]:
    """Read supported Maven, Gradle, requirements.txt, and pyproject dependency manifests."""
    dependencies = []
    for relative_manifest in _find_dependency_manifests():
        manifest = PROJECT_ROOT / relative_manifest
        if manifest.stat().st_size > MAX_READ_BYTES:
            continue
        manifest_name = manifest.name.casefold()
        try:
            content = manifest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if manifest_name == "pom.xml":
            try:
                root = ET.fromstring(content)
                for item in root.findall(".//{*}dependency"):
                    group = item.findtext("{*}groupId")
                    artifact = item.findtext("{*}artifactId")
                    version = item.findtext("{*}version")
                    if artifact:
                        dependencies.append({"manifest": relative_manifest, "name": f"{group}:{artifact}" if group else artifact, "version": version, "version_resolved": bool(version and not version.startswith("${"))})
            except ET.ParseError:
                continue
        elif manifest_name in {"build.gradle", "build.gradle.kts"}:
            for match in re.finditer(r"\b(?:implementation|api|compileOnly|runtimeOnly|testImplementation)\s*(?:\(\s*)?[\"']([^:\"']+):([^:\"']+):([^\"']+)", content):
                dependencies.append({"manifest": relative_manifest, "name": f"{match.group(1)}:{match.group(2)}", "version": match.group(3), "version_resolved": True})
        elif manifest_name == "requirements.txt":
            for line in content.splitlines():
                match = re.match(r"^\s*([A-Za-z0-9_.-]+)(?:\[[^]]+\])?\s*(.*)$", line)
                if match and not line.lstrip().startswith(("#", "-")):
                    version = match.group(2).strip() or None
                    dependencies.append({"manifest": relative_manifest, "name": match.group(1), "version": version, "version_resolved": bool(version and not version.startswith((";", "#")))})
        elif manifest_name == "pyproject.toml" and tomllib:
            try:
                project = tomllib.loads(content).get("project", {})
                for requirement in project.get("dependencies", []):
                    match = re.match(r"([A-Za-z0-9_.-]+)(.*)", requirement)
                    if match:
                        constraint = match.group(2).strip() or None
                        dependencies.append({"manifest": relative_manifest, "name": match.group(1), "version": constraint, "version_resolved": bool(constraint)})
            except (tomllib.TOMLDecodeError, ValueError):
                continue

    return dependencies[:500]


if __name__ == "__main__":
    mcp.run()
