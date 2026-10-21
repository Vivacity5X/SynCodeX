import os
import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


CHUNK_SIZE = 40
CHUNK_OVERLAP = 8
MAX_SOURCE_FILES = 3000
MAX_FILE_BYTES = 1_000_000
MAX_QUERY_RESULTS = 20

COMMON_QUERY_WORDS = {
    "a", "an", "and", "are", "does", "for", "from", "how", "i", "in",
    "is", "it", "of", "on", "or", "the", "this", "to", "what", "where",
    "which", "with", "you",
}

QUERY_SYNONYMS = {
    "config": {"configuration", "setting", "settings", "properties"},
    "configuration": {"config", "setting", "settings", "properties"},
    "endpoint": {"route", "mapping", "api"},
    "route": {"endpoint", "mapping", "api"},
    "file": {"filename", "path"},
    "files": {"filename", "path"},
    "search": {"find", "lookup", "retrieval"},
    "find": {"search", "lookup", "retrieval"},
    "tool": {"tools", "mcp"},
    "tools": {"tool", "mcp"},
}


def _normalized_text(value: str) -> str:
    """Split common code identifiers so natural language can match them."""
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    value = re.sub(r"([A-Za-z])([0-9])|([0-9])([A-Za-z])", " ", value)
    return value.replace("_", " ").replace("-", " ").casefold()


def _query_terms(query: str) -> list[str]:
    normalized = _normalized_text(query)
    terms = re.findall(r"[a-z][a-z0-9]{1,}", normalized)
    expanded = list(terms)
    for term in terms:
        expanded.extend(sorted(QUERY_SYNONYMS.get(term, ())))
    return [term for term in dict.fromkeys(expanded) if term not in COMMON_QUERY_WORDS]


def _iter_source_files(
    repository_root: Path,
    searchable_extensions: set[str],
    ignored_directories: set[str],
):
    """Walk source folders while pruning hidden, generated, and ignored folders."""
    ignored = {name.casefold() for name in ignored_directories}
    discovered = []

    for current_dir, directories, filenames in os.walk(repository_root):
        directories[:] = sorted(
            directory
            for directory in directories
            if directory.casefold() not in ignored and not directory.startswith(".")
        )
        current_path = Path(current_dir)
        for filename in filenames:
            path = current_path / filename
            if path.suffix.casefold() in searchable_extensions:
                discovered.append((path.relative_to(repository_root).as_posix(), path))

    return sorted(discovered, key=lambda item: item[0].casefold())[:MAX_SOURCE_FILES]


def _read_source(path: Path) -> list[str] | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None


def retrieve_relevant_chunks(
    question: str,
    repository_root: Path,
    searchable_extensions: set[str],
    ignored_directories: set[str],
    top_k: int = 8,
) -> list[dict]:
    """Retrieve relevant chunks using code-aware TF-IDF plus filename signals."""
    chunks = []

    for relative_path, file_path in _iter_source_files(
        repository_root,
        searchable_extensions,
        ignored_directories,
    ):
        lines = _read_source(file_path)
        if not lines:
            continue

        start = 0
        while start < len(lines):
            end = min(start + CHUNK_SIZE, len(lines))
            content = "\n".join(lines[start:end])
            if content.strip():
                chunks.append({
                    "file": relative_path,
                    "start_line": start + 1,
                    "end_line": end,
                    "content": content,
                })
            if end == len(lines):
                break
            start = end - CHUNK_OVERLAP

    if not chunks:
        return []

    normalized_question = _normalized_text(question)
    query_terms = _query_terms(question)
    documents = [
        f"{_normalized_text(chunk['file'])} {chunk['content']}"
        for chunk in chunks
    ]
    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        sublinear_tf=True,
        token_pattern=r"(?u)\b[a-zA-Z_][a-zA-Z0-9_]{1,}\b",
    )

    try:
        document_vectors = vectorizer.fit_transform(documents)
        question_vector = vectorizer.transform([normalized_question])
    except ValueError:
        return []

    lexical_scores = cosine_similarity(question_vector, document_vectors).flatten()
    ranked = []
    question_words = set(re.findall(r"[a-z][a-z0-9]{1,}", normalized_question))
    asks_about_repository = bool(
        question_words & {"project", "repository", "repo", "codebase", "application", "app"}
    )
    broad_overview = asks_about_repository and bool(
        question_words & {"overview", "structure", "architecture", "purpose", "about", "do", "built"}
    )

    for index, chunk in enumerate(chunks):
        path_text = _normalized_text(chunk["file"])
        path_terms = set(re.findall(r"[a-z][a-z0-9]{1,}", path_text))
        matched_path_terms = sum(term in path_terms for term in query_terms)
        path_coverage = matched_path_terms / max(1, len(query_terms))
        normalized_content = _normalized_text(chunk["content"])
        exact_phrase_bonus = 0.12 if normalized_question.strip() in normalized_content else 0.0
        filename_bonus = min(0.24, path_coverage * 0.24)
        overview_bonus = 0.18 if broad_overview and Path(chunk["file"]).name.casefold() == "readme.md" else 0.0
        score = float(lexical_scores[index]) + filename_bonus + exact_phrase_bonus + overview_bonus
        if score > 0:
            ranked.append((score, index))

    ranked.sort(key=lambda item: (-item[0], chunks[item[1]]["file"].casefold(), chunks[item[1]]["start_line"]))

    results = []
    per_file = {}
    for score, index in ranked:
        chunk = chunks[index]
        if per_file.get(chunk["file"], 0) >= 2:
            continue
        result = chunk.copy()
        result["score"] = round(score, 4)
        results.append(result)
        per_file[chunk["file"]] = per_file.get(chunk["file"], 0) + 1
        if len(results) >= top_k:
            break

    return results


def search_repository_lines(
    query: str,
    repository_root: Path,
    searchable_extensions: set[str],
    ignored_directories: set[str],
    max_results: int = MAX_QUERY_RESULTS,
) -> dict:
    """Rank file-name and line matches for the repository search endpoint."""
    query = query.strip()
    query_terms = _query_terms(query)
    if not query_terms:
        query_terms = re.findall(r"[a-z0-9]{2,}", _normalized_text(query))
    normalized_query = _normalized_text(query).strip()
    candidates = []
    files_scanned = 0

    for relative_path, file_path in _iter_source_files(
        repository_root,
        searchable_extensions,
        ignored_directories,
    ):
        files_scanned += 1
        lines = _read_source(file_path)
        if lines is None:
            continue

        normalized_path = _normalized_text(relative_path)
        path_tokens = set(re.findall(r"[a-z][a-z0-9]{1,}", normalized_path))
        path_matches = sum(term in path_tokens for term in query_terms)
        path_score = path_matches / max(1, len(query_terms))
        if normalized_query and normalized_query in normalized_path:
            path_score += 1.0

        if path_matches:
            candidates.append((path_score + 0.2, relative_path, 0, f"Filename match: {relative_path}"))

        for line_number, line in enumerate(lines, start=1):
            normalized_line = _normalized_text(line)
            line_tokens = set(re.findall(r"[a-z][a-z0-9]{1,}", normalized_line))
            matches = sum(term in line_tokens for term in query_terms)
            if not matches:
                continue
            line_score = matches / max(1, len(query_terms))
            if normalized_query and normalized_query in normalized_line:
                line_score += 1.0
            candidates.append((line_score, relative_path, line_number, line.strip()[:300]))

    candidates.sort(key=lambda item: (-item[0], item[1].casefold(), item[2]))
    results = []
    per_file = {}
    for _, path, line_number, content in candidates:
        if per_file.get(path, 0) >= 3:
            continue
        results.append({"file": path, "line": line_number, "content": content})
        per_file[path] = per_file.get(path, 0) + 1
        if len(results) >= max_results:
            break
    return {
        "query": query,
        "results": results,
        "result_count": len(results),
        "truncated": len(candidates) > max_results or files_scanned >= MAX_SOURCE_FILES,
    }
