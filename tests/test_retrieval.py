import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "ai-service"))
from retrieval import retrieve_relevant_chunks  # noqa: E402


class RepositoryRetrievalTests(unittest.TestCase):
    def test_splits_code_identifiers_for_natural_language_retrieval(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as directory:
            root = Path(directory)
            (root / "service_impl.py").write_text(
                "class AiService:\n    def ask(self):\n        return repositoryClient.askRepositoryQuestion()\n",
                encoding="utf-8",
            )
            (root / "unrelated.py").write_text(
                "def calculate_tax(amount):\n    return amount * 0.2\n",
                encoding="utf-8",
            )

            chunks = retrieve_relevant_chunks(
                question="How does AiService call repositoryClient?",
                repository_root=root,
                searchable_extensions={".py"},
                ignored_directories={".git", "__pycache__"},
                top_k=4,
            )

        self.assertTrue(chunks)
        self.assertEqual(chunks[0]["file"], "service_impl.py")


if __name__ == "__main__":
    unittest.main()
