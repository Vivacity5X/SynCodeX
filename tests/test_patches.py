import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "ai-service"))
import main  # noqa: E402
from patches import PatchTargetError, build_unified_diff, read_patch_target  # noqa: E402


class ReviewablePatchTests(unittest.TestCase):
    def setUp(self):
        main.PENDING_PATCHES.clear()
        main.APPLIED_PATCHES.clear()

    def tearDown(self):
        main.PENDING_PATCHES.clear()
        main.APPLIED_PATCHES.clear()

    def test_diff_is_single_file_unified_format_and_does_not_apply(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as directory:
            root = Path(directory)
            source = root / "src" / "service.py"
            source.parent.mkdir()
            source.write_text("def run():\n    return None\n", encoding="utf-8")
            original = read_patch_target(
                "src/service.py", root, {".py"}, {".git", "__pycache__"}
            )
            diff = build_unified_diff(
                "src/service.py", original, "def run():\n    return True\n"
            )

            self.assertIn("--- a/src/service.py", diff)
            self.assertIn("+++ b/src/service.py", diff)
            self.assertIn("+    return True", diff)
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_rejects_unsafe_paths_and_secret_bearing_files(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as directory:
            root = Path(directory)
            (root / "safe.py").write_text("print('safe')\n", encoding="utf-8")
            (root / "settings.py").write_text("api_key=super-secret-value\n", encoding="utf-8")
            for unsafe in ("../outside.py", str(root / "safe.py"), "settings.py"):
                with self.subTest(path=unsafe), self.assertRaises(PatchTargetError):
                    read_patch_target(unsafe, root, {".py"}, {".git"})

    def test_endpoint_returns_review_only_diff(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as directory:
            root = Path(directory)
            source = root / "service.py"
            original = "def run():\n    return None\n"
            source.write_text(original, encoding="utf-8")
            provider = MagicMock()
            provider.chat.completions.create.return_value.choices[0].message.content = json.dumps({
                "explanation": "Return a boolean from this function.",
                "proposed_content": "def run():\n    return True\n",
            })
            with patch.object(main, "REPOSITORY_ROOT", root), patch.object(main, "client", provider):
                result = main.propose_fix(main.FixProposalRequest(
                    file="service.py",
                    instructions="Return true.",
                ))

            self.assertIn("--- a/service.py", result["diff"])
            self.assertFalse(result["applied"])
            self.assertTrue(result["approval_required"])
            self.assertEqual(result["validation_status"], "not_run")
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_rejects_noop_provider_proposal(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as directory:
            root = Path(directory)
            (root / "service.py").write_text("print('same')\n", encoding="utf-8")
            provider = MagicMock()
            provider.chat.completions.create.return_value.choices[0].message.content = json.dumps({
                "explanation": "No changes needed.",
                "proposed_content": "print('same')\n",
            })
            with patch.object(main, "REPOSITORY_ROOT", root), patch.object(main, "client", provider):
                with self.assertRaises(main.HTTPException) as raised:
                    main.propose_fix(main.FixProposalRequest(file="service.py", instructions="Change it."))

        self.assertEqual(raised.exception.status_code, 422)

    def test_apply_requires_explicit_approval_and_can_be_reverted(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as directory:
            root = Path(directory)
            source = root / "service.py"
            original = "def run():\n    return None\n"
            source.write_text(original, encoding="utf-8")
            provider = MagicMock()
            provider.chat.completions.create.return_value.choices[0].message.content = json.dumps({
                "explanation": "Return true.",
                "proposed_content": "def run():\n    return True\n",
            })
            with patch.object(main, "REPOSITORY_ROOT", root), patch.object(main, "client", provider):
                proposal = main.propose_fix(main.FixProposalRequest(file="service.py", instructions="Return true."))
                with self.assertRaises(main.HTTPException) as cross_session:
                    main.apply_approved_fix(main.PatchApprovalRequest(
                        proposal_id=proposal["proposal_id"], approved=True, session_id="different-session"
                    ))
                self.assertEqual(cross_session.exception.status_code, 404)
                with self.assertRaises(main.HTTPException) as denied:
                    main.apply_approved_fix(main.PatchApprovalRequest(proposal_id=proposal["proposal_id"]))
                self.assertEqual(denied.exception.status_code, 400)
                self.assertEqual(source.read_text(encoding="utf-8"), original)

                applied = main.apply_approved_fix(main.PatchApprovalRequest(
                    proposal_id=proposal["proposal_id"], approved=True
                ))
                self.assertTrue(applied["applied"])
                self.assertEqual(source.read_text(encoding="utf-8"), "def run():\n    return True\n")

                with self.assertRaises(main.HTTPException) as revert_denied:
                    main.revert_approved_fix(main.PatchRevertRequest(
                        backup_id=applied["backup_id"],
                        file="service.py",
                        expected_current_sha256=applied["applied_sha256"],
                    ))
                self.assertEqual(revert_denied.exception.status_code, 400)
                # Revert metadata and the original backup survive an AI-service restart.
                main.APPLIED_PATCHES.clear()
                reverted = main.revert_approved_fix(main.PatchRevertRequest(
                    backup_id=applied["backup_id"],
                    file="service.py",
                    expected_current_sha256=applied["applied_sha256"],
                    approved=True,
                ))

            self.assertTrue(reverted["reverted"])
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_refuses_to_apply_proposal_when_file_changed_after_review(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as directory:
            root = Path(directory)
            source = root / "service.py"
            source.write_text("def run():\n    return None\n", encoding="utf-8")
            provider = MagicMock()
            provider.chat.completions.create.return_value.choices[0].message.content = json.dumps({
                "explanation": "Return true.",
                "proposed_content": "def run():\n    return True\n",
            })
            with patch.object(main, "REPOSITORY_ROOT", root), patch.object(main, "client", provider):
                proposal = main.propose_fix(main.FixProposalRequest(file="service.py", instructions="Return true."))
                source.write_text("def run():\n    return 1\n", encoding="utf-8")
                with self.assertRaises(main.HTTPException) as raised:
                    main.apply_approved_fix(main.PatchApprovalRequest(
                        proposal_id=proposal["proposal_id"], approved=True
                    ))

            self.assertEqual(raised.exception.status_code, 409)
            self.assertEqual(source.read_text(encoding="utf-8"), "def run():\n    return 1\n")


if __name__ == "__main__":
    unittest.main()
