import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-service"))
import main  # noqa: E402
import mcp_client  # noqa: E402
from project_context import inspect_project  # noqa: E402


class MultiRepositoryTests(unittest.TestCase):
    def test_three_project_types_are_detected_and_analysis_uses_only_selected_root(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            base = Path(temp)
            java = base / "java-app"
            python = base / "python-app"
            react = base / "react-app"
            (java / "src/main/java/demo").mkdir(parents=True)
            (java / "pom.xml").write_text(
                "<project><artifactId>spring-boot-starter-web</artifactId></project>", encoding="utf-8"
            )
            (java / "src/main/java/demo/JavaController.java").write_text(
                "package demo;\nclass JavaController {\n  void run() { throw new IllegalStateException(\"JAVA_SENTINEL\"); }\n}\n",
                encoding="utf-8",
            )

            python.mkdir()
            (python / "requirements.txt").write_text("fastapi==0.115.0\n", encoding="utf-8")
            (python / "app.py").write_text(
                "from fastapi import FastAPI\napp = FastAPI()\ndef python_sentinel():\n    raise RuntimeError('PYTHON_SENTINEL')\n",
                encoding="utf-8",
            )

            (react / "src").mkdir(parents=True)
            (react / "package.json").write_text(
                '{"dependencies":{"react":"^18.0.0","typescript":"^5.0.0"}}', encoding="utf-8"
            )
            (react / "tsconfig.json").write_text("{}", encoding="utf-8")
            (react / "src/App.tsx").write_text(
                "export function ReactSentinel() { return <main>REACT_SENTINEL</main>; }\n", encoding="utf-8"
            )

            expected = (
                (java, "Java/Spring Boot", "java.lang.IllegalStateException: JAVA_SENTINEL\n    at demo.JavaController.run(JavaController.java:3)", "JAVA_SENTINEL"),
                (python, "Python/FastAPI", "RuntimeError: PYTHON_SENTINEL\n  File \"app.py\", line 4, in python_sentinel", "PYTHON_SENTINEL"),
                (react, "React/TypeScript", "TypeError: REACT_SENTINEL", "REACT_SENTINEL"),
            )
            observed_files = []
            with patch.object(main, "client", None):
                for index, (repository, project_type, trace, marker) in enumerate(expected):
                    profile = inspect_project(repository)
                    self.assertIn(project_type, profile["project_types"])
                    request = main.DebugRequest(
                        error=trace,
                        question=f"Locate {marker} in this project",
                        repository_root=str(repository),
                        session_id=f"sample-session-{index}",
                    )
                    report = main.analyze_debug_request(request)
                    self.assertEqual(report["project"]["repository"], str(repository.resolve()))
                    evidence = "\n".join(item["excerpt"] for item in report["evidence"])
                    self.assertIn(marker, evidence)
                    observed_files.extend(item["file"] for item in report["evidence"])

            self.assertTrue(any(path.endswith("JavaController.java") for path in observed_files))
            self.assertTrue(any(path.endswith("app.py") for path in observed_files))
            self.assertTrue(any(path.endswith("App.tsx") for path in observed_files))

    def test_invalid_repository_context_is_rejected(self):
        request = main.RepositoryBoundRequest(repository_root=str(ROOT / "missing-repository"))
        with self.assertRaises(main.HTTPException) as raised:
            main.inspect_repository(request)
        self.assertEqual(raised.exception.status_code, 400)

    def test_mcp_process_receives_the_selected_repository_root(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            selected = Path(directory).resolve()
            parameters = mcp_client.server_parameters(selected)
        self.assertEqual(parameters.env["SYNCODEX_PROJECT_ROOT"], str(selected))

    def test_unsupported_debug_language_is_reported(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            (root / "package.json").write_text('{"dependencies":{"react":"18"}}', encoding="utf-8")
            (root / "tsconfig.json").write_text("{}", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src/App.tsx").write_text("export const App = () => null;\n", encoding="utf-8")
            with patch.object(main, "client", None):
                report = main.analyze_debug_request(main.DebugRequest(
                    error="TypeError: failed",
                    repository_root=str(root),
                    session_id="typescript-session",
                ))
        self.assertTrue(any("currently supported" in item for item in report["missing_information"]))


if __name__ == "__main__":
    unittest.main()
