
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


CHUNK_SIZE = 40
CHUNK_OVERLAP = 8


def retrieve_relevant_chunks(
    question: str,
    repository_root: Path,
    searchable_extensions: set[str],
    ignored_directories: set[str],
    top_k: int = 8,
) -> list[dict]:
    """Retrieve relevant source-code chunks using TF-IDF."""

    chunks = []

    for file_path in repository_root.rglob("*"):
        if not file_path.is_file():
            continue

        relative_path = file_path.relative_to(repository_root)

        # Skip hidden folders and generated directories.
        if any(
            part.startswith(".") or part in ignored_directories
            for part in relative_path.parts
        ):
            continue

        if file_path.suffix.lower() not in searchable_extensions:
            continue

        try:
            if file_path.stat().st_size > 1_000_000:
                continue

            lines = file_path.read_text(
                encoding="utf-8",
                errors="ignore",
            ).splitlines()

        except OSError:
            continue

        start = 0

        while start < len(lines):
            end = min(start + CHUNK_SIZE, len(lines))
            content = "\n".join(lines[start:end])

            if content.strip():
                chunks.append({
                    "file": relative_path.as_posix(),
                    "start_line": start + 1,
                    "end_line": end,
                    "content": content,
                })

            if end == len(lines):
                break

            start = end - CHUNK_OVERLAP

    if not chunks:
        return []

    documents = [chunk["content"] for chunk in chunks]

    # Fit the vectorizer on source chunks and transform the question.
    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        sublinear_tf=True,
        token_pattern=r"(?u)\b[a-zA-Z_][a-zA-Z0-9_]{1,}\b",
    )

    try:
        document_vectors = vectorizer.fit_transform(documents)
        question_vector = vectorizer.transform([question])
    except ValueError:
        # For example, the repository may contain no usable tokens.
        return []

    scores = cosine_similarity(
        question_vector,
        document_vectors,
    ).flatten()

    ranked_indices = scores.argsort()[::-1]

    results = []

    for index in ranked_indices:
        score = float(scores[index])

        # Ignore chunks with no matching terms.
        if score <= 0:
            break

        result = chunks[int(index)].copy()
        result["score"] = round(score, 4)
        results.append(result)

        if len(results) >= top_k:
            break

    return results
