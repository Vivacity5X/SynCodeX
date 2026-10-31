import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "ai-service"))
import main  # noqa: E402


class DebugApiContractTests(unittest.TestCase):
    def test_debugging_routes_are_exposed_with_matching_request_fields(self):
        schema = main.app.openapi()
        paths = schema["paths"]
        expected_routes = {
            "/api/v1/debug/analyze",
            "/api/v1/debug/propose-fix",
            "/api/v1/debug/apply-fix",
            "/api/v1/debug/revert-fix",
        }
        self.assertTrue(expected_routes.issubset(paths))
        for route in expected_routes:
            self.assertIn("post", paths[route])

        schemas = schema["components"]["schemas"]
        debug_fields = schemas["DebugRequest"]["properties"]
        self.assertIn("project_context", debug_fields)
        proposal_fields = schemas["FixProposalRequest"]["properties"]
        self.assertTrue({"file", "instructions", "error", "question"}.issubset(proposal_fields))
        self.assertIn("approved", schemas["PatchApprovalRequest"]["properties"])
        self.assertIn("expected_current_sha256", schemas["PatchRevertRequest"]["properties"])


if __name__ == "__main__":
    unittest.main()
