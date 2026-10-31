import sys
import tempfile
import unittest
from pathlib import Path
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-service"))
import main  # noqa: E402


class RepositoryInspectContractTests(unittest.TestCase):
    def test_valid_windows_absolute_path_is_inspected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            repository = Path(directory).resolve()
            (repository / "Main.java").write_text("class Main {}\n", encoding="utf-8")
            request = main.RepositoryInspectRequest(
                repository_root=str(repository), session_id="windows-session"
            )
            result = main.inspect_repository(request)

        self.assertEqual(result["repository"], str(repository))
        self.assertIn("Java", result["languages"])

    def test_nonexistent_repository_returns_clear_client_error(self):
        request = main.RepositoryInspectRequest(
            repository_root=str(ROOT / "does-not-exist"), session_id="session-1"
        )
        with self.assertRaises(main.HTTPException) as raised:
            main.inspect_repository(request)
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("does not exist", raised.exception.detail)

    def test_missing_fields_are_rejected_with_field_locations(self):
        for body, expected_fields in (
            ({}, {"repository_root", "session_id"}),
            ({"repository_root": str(ROOT)}, {"session_id"}),
        ):
            with self.subTest(body=body), self.assertRaises(ValidationError) as raised:
                main.RepositoryInspectRequest.model_validate(body)
            locations = {str(error["loc"][0]) for error in raised.exception.errors()}
            self.assertEqual(locations, expected_fields)

    def test_malformed_and_mismatched_payloads_are_rejected(self):
        invalid_payloads = (
            {"repository_root": ["D:", "MCP-Test", "ProjectA"], "session_id": "session-1"},
            {"path": "D:\\MCP-Test\\ProjectA", "session_id": "session-1"},
        )
        for body in invalid_payloads:
            with self.subTest(body=body), self.assertRaises(ValidationError):
                main.RepositoryInspectRequest.model_validate(body)


if __name__ == "__main__":
    unittest.main()
