import re
from pathlib import Path
from typing import Any

from retrieval import _iter_source_files, _read_source


MAX_TRACE_CHARS = 20_000
MAX_FRAMES = 100
MAX_FRAME_CONTEXTS = 8
FRAME_CONTEXT_LINES = 8

JAVA_FRAME = re.compile(
    r"^\s*at\s+([\w.$]+)\.([\w$<>]+)\(([^():]+\.java)(?::(\d+))?\)"
)
PYTHON_FRAME = re.compile(
    r'^\s*File\s+["\']([^"\']+)["\']\s*,\s*line\s+(\d+),\s*in\s+([\w<>.]+)'
)
PYTHON_PATH_LINE = re.compile(r'(?m)(\bFile\s+["\'])([^"\']+)(["\'])')
EXCEPTION_LINE = re.compile(
    r"(?i)(?:^|\s)(?:caused by:\s*)?[\w.$]*(?:Exception|Error|Failure|Fault)(?::\s*.*)?$"
)
LOG_LEVEL = re.compile(r"\b(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\b", re.IGNORECASE)
LOG_TIMESTAMP = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,9})?(?:Z|[+-]\d{2}:?\d{2})?)\b"
)
EXCEPTION_CLASS = re.compile(r"(?i)([\w.$]*(?:Exception|Error|Failure|Fault))(?::|\b)")
SPRING_LOGGER = re.compile(r"\]\s+([\w.$]+)\s*[:\-]\s*(.*)$")
PLAIN_LOGGER = re.compile(
    r"\b(?:TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\b\s+(?:\[[^]]+\]\s*)?([\w.$]+)\s*[-:]\s*(.*)$",
    re.IGNORECASE,
)
SECRET_VALUE = re.compile(
    r"(?i)(\b(?:[\w.-]*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|credential)[\w.-]*)\b\s*[:=]\s*)([^\s,;#]+)"
)


def redact_debug_input(text: str) -> str:
    return redact_secret_values(text[:MAX_TRACE_CHARS])


def redact_secret_values(text: str) -> str:
    return SECRET_VALUE.sub(r"\1[REDACTED]", text)


def sanitize_trace_paths(text: str) -> str:
    """Remove machine-specific absolute paths from Python traceback lines."""
    def replace_path(match: re.Match) -> str:
        raw_path = match.group(2).replace("\\", "/")
        if re.match(r"^(?:[A-Za-z]:/|/)", raw_path):
            raw_path = Path(raw_path).name
        return f"{match.group(1)}{raw_path}{match.group(3)}"

    return PYTHON_PATH_LINE.sub(replace_path, text[:MAX_TRACE_CHARS])


def parse_stack_trace(text: str) -> dict[str, Any]:
    """Extract explicit exception lines and Java/Python frames without inferring causality."""
    bounded = text[:MAX_TRACE_CHARS]
    exceptions = []
    frames = []
    for line_number, raw_line in enumerate(bounded.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if EXCEPTION_LINE.search(line) and len(exceptions) < 30:
            exceptions.append({"line": line_number, "text": redact_debug_input(line)[:500]})

        java = JAVA_FRAME.match(raw_line)
        if java:
            frames.append({
                "language": "java",
                "class": java.group(1),
                "method": java.group(2),
                "file": java.group(3),
                "line": int(java.group(4)) if java.group(4) else None,
                "trace_line": line_number,
            })
        else:
            python = PYTHON_FRAME.match(raw_line)
            if python:
                raw_path = python.group(1).replace("\\", "/")
                safe_path_hint = (
                    Path(raw_path).name
                    if re.match(r"^(?:[A-Za-z]:/|/)", raw_path)
                    else raw_path
                )
                frames.append({
                    "language": "python",
                    "class": None,
                    "method": python.group(3),
                    "file": Path(raw_path).name,
                    "path_hint": safe_path_hint,
                    "line": int(python.group(2)),
                    "trace_line": line_number,
                })
        if len(frames) >= MAX_FRAMES:
            break

    return {
        "exceptions": exceptions,
        "frames": frames,
        "truncated": len(text) > MAX_TRACE_CHARS,
    }


def _normalize_log_signature(message: str) -> str:
    normalized = message.casefold()
    normalized = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", "<id>", normalized)
    normalized = re.sub(r"\b0x[0-9a-f]+\b", "<hex>", normalized)
    normalized = re.sub(r"\b\d+\b", "<n>", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized[:300]


def parse_log_events(text: str) -> dict[str, Any]:
    """Extract bounded log events and repeated signatures; temporal order is not causality."""
    bounded = text[:MAX_TRACE_CHARS]
    events = []
    for line_number, raw_line in enumerate(bounded.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        timestamp_match = LOG_TIMESTAMP.search(line)
        level_match = LOG_LEVEL.search(line)
        exception_match = EXCEPTION_CLASS.search(line)
        if not timestamp_match and not level_match and not exception_match:
            continue

        level = level_match.group(1).upper() if level_match else ("ERROR" if exception_match else None)
        component = None
        message = line
        spring_match = SPRING_LOGGER.search(line)
        if spring_match:
            component, message = spring_match.groups()
        else:
            plain_match = PLAIN_LOGGER.search(line)
            if plain_match:
                component, message = plain_match.groups()
            elif level_match:
                message = line[level_match.end():].lstrip(" :-|")

        if exception_match and not message:
            message = line
        safe_message = redact_debug_input(message)
        signature = _normalize_log_signature(
            f"{exception_match.group(1) if exception_match else ''} {safe_message}"
        )
        if not signature:
            signature = _normalize_log_signature(line)
        event = {
            "line": line_number,
            "timestamp": timestamp_match.group(1) if timestamp_match else None,
            "level": level,
            "component": component,
            "exception": exception_match.group(1) if exception_match else None,
            "message": safe_message[:500],
            "signature": signature,
            "is_failure": bool(level in {"ERROR", "FATAL"} or exception_match),
        }
        events.append(event)
        if len(events) >= 100:
            break

    groups_by_key = {}
    for event in events:
        if not event["is_failure"]:
            continue
        key = (event["level"], event["component"], event["signature"])
        group = groups_by_key.get(key)
        if group is None:
            group = {
                "level": event["level"],
                "component": event["component"],
                "signature": event["signature"],
                "count": 0,
                "first_line": event["line"],
                "last_line": event["line"],
                "first_timestamp": event["timestamp"],
                "last_timestamp": event["timestamp"],
                "sample_message": event["message"],
            }
            groups_by_key[key] = group
        group["count"] += 1
        group["last_line"] = event["line"]
        group["last_timestamp"] = event["timestamp"]

    failures = [event for event in events if event["is_failure"]]
    first = failures[0] if failures else None
    later = []
    if first:
        for event in failures[1:21]:
            later.append({
                "line": event["line"],
                "timestamp": event["timestamp"],
                "level": event["level"],
                "component": event["component"],
                "message": event["message"],
                "classification": (
                    "same_signature_repeat" if event["signature"] == first["signature"]
                    else "later_distinct_failure"
                ),
                "causal_link_established": False,
            })

    return {
        "events": events[:50],
        "groups": list(groups_by_key.values())[:20],
        "first_observed_failure": (
            {key: first[key] for key in ("line", "timestamp", "level", "component", "exception", "message")}
            if first else None
        ),
        "later_failures": later,
        "causality_note": (
            "Events are ordered by their appearance in the supplied text. Later failures may be related, "
            "but this ordering does not prove that one caused another."
        ),
        "truncated": len(text) > MAX_TRACE_CHARS,
    }


def retrieve_frame_context(
    frames: list[dict[str, Any]],
    repository_root: Path,
    searchable_extensions: set[str],
    ignored_directories: set[str],
) -> list[dict[str, Any]]:
    """Return short, line-numbered source windows for stack frames that map to the repository."""
    source_files = _iter_source_files(repository_root, searchable_extensions, ignored_directories)
    contexts = []
    seen: set[tuple[str, int]] = set()

    for frame in frames:
        source_name = frame.get("file")
        line_number = frame.get("line")
        if not source_name or not isinstance(line_number, int) or line_number < 1:
            continue

        class_name = frame.get("class") or ""
        class_path = class_name.split("$", 1)[0].replace(".", "/")
        preferred_suffix = f"{class_path}/{source_name}" if class_path else source_name
        path_hint = frame.get("path_hint") or preferred_suffix
        matching = [item for item in source_files if item[0].casefold().endswith(path_hint.casefold())]
        if not matching:
            matching = [item for item in source_files if Path(item[0]).name.casefold() == source_name.casefold()]
        if not matching:
            continue

        # A basename collision is unresolved unless the stack frame's class path selected one file.
        if len(matching) > 1:
            continue
        selected = matching[0]
        relative_path, source_path = selected
        key = (relative_path, line_number)
        if key in seen:
            continue
        seen.add(key)
        lines = _read_source(source_path)
        if lines is None or line_number > len(lines):
            continue

        start = max(1, line_number - FRAME_CONTEXT_LINES)
        end = min(len(lines), line_number + FRAME_CONTEXT_LINES)
        excerpt = "\n".join(
            f"{number}: {lines[number - 1]}"
            for number in range(start, end + 1)
        )
        contexts.append({
            "file": relative_path,
            "line_start": start,
            "line_end": end,
            "frame_line": line_number,
            "description": f"Stack frame {frame.get('class') or frame.get('method')}",
            "excerpt": excerpt,
            "verified": True,
        })
        if len(contexts) >= MAX_FRAME_CONTEXTS:
            break

    return contexts
