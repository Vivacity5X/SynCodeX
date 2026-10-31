import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "ai-service"))
from debugging import parse_log_events, parse_stack_trace, retrieve_frame_context, sanitize_trace_paths  # noqa: E402


class StackTraceParsingTests(unittest.TestCase):
    def test_parses_java_exception_and_frames(self):
        trace = """java.lang.NullPointerException: cannot call service
    at com.example.Controller.handle(Controller.java:42)
    at com.example.Router.dispatch(Router.java:18)
"""
        parsed = parse_stack_trace(trace)
        self.assertIn("NullPointerException", parsed["exceptions"][0]["text"])
        self.assertEqual(parsed["frames"][0]["class"], "com.example.Controller")
        self.assertEqual(parsed["frames"][0]["line"], 42)

    def test_groups_repeated_failures_and_preserves_order_without_claiming_causality(self):
        logs = """2026-10-31 10:00:00.000 ERROR 1234 --- [main] c.example.DbClient : Connection refused password=hunter2
2026-10-31 10:00:01.000 ERROR 1234 --- [main] c.example.DbClient : Connection refused password=hunter2
2026-10-31 10:00:02.000 ERROR 1234 --- [main] c.example.Api : Request failed after database error
"""
        parsed = parse_log_events(logs)

        self.assertEqual(parsed["first_observed_failure"]["line"], 1)
        self.assertEqual(parsed["first_observed_failure"]["component"], "c.example.DbClient")
        self.assertEqual(parsed["groups"][0]["count"], 2)
        self.assertEqual(parsed["later_failures"][0]["classification"], "same_signature_repeat")
        self.assertFalse(parsed["later_failures"][0]["causal_link_established"])
        self.assertNotIn("hunter2", str(parsed))

    def test_parses_python_frames_without_returning_absolute_paths(self):
        trace = 'File "C:/private/project/app.py", line 9, in handle\n'
        self.assertNotIn("C:/private", sanitize_trace_paths(trace))
        parsed = parse_stack_trace(trace)
        self.assertEqual(parsed["frames"][0]["file"], "app.py")
        self.assertNotIn("C:/private", str(parsed["frames"]))

    def test_maps_frame_to_a_bounded_line_numbered_source_window(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as directory:
            root = Path(directory)
            source = root / "com" / "example" / "Controller.java"
            source.parent.mkdir(parents=True)
            source.write_text("package com.example;\nclass Controller {\n    void handle() {}\n}\n", encoding="utf-8")
            evidence = retrieve_frame_context(
                frames=[{"class": "com.example.Controller", "method": "handle", "file": "Controller.java", "line": 3}],
                repository_root=root,
                searchable_extensions={".java"},
                ignored_directories={".git", "target"},
            )

        self.assertEqual(evidence[0]["file"], "com/example/Controller.java")
        self.assertEqual(evidence[0]["frame_line"], 3)
        self.assertIn("3:     void handle", evidence[0]["excerpt"])

    def test_debug_endpoint_returns_grounded_report_without_provider(self):
        import main

        trace = "java.lang.NullPointerException: cannot call service\n    at com.example.Controller.handle(Controller.java:3)"
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as directory:
            root = Path(directory)
            source = root / "com" / "example" / "Controller.java"
            source.parent.mkdir(parents=True)
            source.write_text("package com.example;\nclass Controller {\n    void handle() {}\n}\n", encoding="utf-8")
            with patch.object(main, "REPOSITORY_ROOT", root), patch.object(main, "client", None):
                report = main.analyze_debug_request(main.DebugRequest(error=trace, question="Why does this fail?"))

        self.assertEqual(report["analysis_status"], "provider_unconfigured")
        self.assertEqual(report["confidence"], "low")
        self.assertEqual(report["evidence"][0]["file"], "com/example/Controller.java")
        self.assertTrue(report["observed_error"]["stack_frames"])
        self.assertTrue(report["validation_steps"])

    def test_provider_cannot_inject_unverified_execution_locations(self):
        from unittest.mock import MagicMock
        import main

        trace = "java.lang.NullPointerException: cannot call service\n    at com.example.Controller.handle(Controller.java:3)"
        model_response = {
            "problem_summary": "A service call failed.",
            "likely_root_cause": "The service value may be null.",
            "execution_flow": ["invented.py:999"],
            "recommended_fix": ["Check the service value."],
            "proposed_code_changes": [],
            "validation_steps": ["Run the targeted test."],
            "confidence": "medium",
            "missing_information": [],
        }
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value.choices[0].message.content = json.dumps(model_response)
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as directory:
            root = Path(directory)
            source = root / "com" / "example" / "Controller.java"
            source.parent.mkdir(parents=True)
            source.write_text("package com.example;\nclass Controller {\n    void handle() {}\n}\n", encoding="utf-8")
            with patch.object(main, "REPOSITORY_ROOT", root), patch.object(main, "client", fake_client):
                report = main.analyze_debug_request(main.DebugRequest(error=trace))

        self.assertEqual(report["analysis_status"], "ai_analyzed")
        self.assertNotIn("invented.py:999", report["execution_flow"])
        self.assertEqual(report["execution_flow"][0], "com.example.Controller.handle at Controller.java:3")
        self.assertEqual(report["evidence"][0]["file"], "com/example/Controller.java")

    def test_malformed_provider_response_falls_back_to_deterministic_report(self):
        from unittest.mock import MagicMock
        import main

        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value.choices[0].message.content = "not json"
        with patch.object(main, "client", fake_client):
            report = main.analyze_debug_request(main.DebugRequest(error="RuntimeError: failed"))

        self.assertEqual(report["analysis_status"], "invalid_provider_response")
        self.assertEqual(report["confidence"], "low")
        self.assertTrue(report["missing_information"])

    def test_provider_failure_returns_deterministic_report_and_empty_input_is_rejected(self):
        from fastapi import HTTPException
        from unittest.mock import MagicMock
        import main

        fake_client = MagicMock()
        provider_detail = "private diagnostic " + "e5a4a7"
        fake_client.chat.completions.create.side_effect = RuntimeError(provider_detail)
        with patch.object(main, "client", fake_client):
            report = main.analyze_debug_request(main.DebugRequest(error="RuntimeError: failed"))
            with self.assertRaises(HTTPException) as raised:
                main.analyze_debug_request(main.DebugRequest())

        self.assertEqual(report["analysis_status"], "provider_error")
        self.assertEqual(raised.exception.status_code, 400)
        self.assertNotIn(provider_detail, str(report))


if __name__ == "__main__":
    unittest.main()
