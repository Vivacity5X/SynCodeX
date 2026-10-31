import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "mcp-server"))
import server as mcp_server  # noqa: E402


class McpRepositorySecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT)
        self.root = Path(self.temp_dir.name).resolve()
        self.original_root = mcp_server.PROJECT_ROOT
        mcp_server.PROJECT_ROOT = self.root

    def tearDown(self):
        mcp_server.PROJECT_ROOT = self.original_root
        self.temp_dir.cleanup()

    def test_configured_root_must_exist_and_be_directory(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as directory:
            with patch.dict(os.environ, {"SYNCODEX_PROJECT_ROOT": directory}):
                importlib.reload(mcp_server)
                self.assertEqual(mcp_server.PROJECT_ROOT, Path(directory).resolve())

            missing = str(Path(directory) / "missing")
            with patch.dict(os.environ, {"SYNCODEX_PROJECT_ROOT": missing}):
                with self.assertRaisesRegex(RuntimeError, "existing directory"):
                    importlib.reload(mcp_server)

        # Restore module defaults for the remaining test cases.
        with patch.dict(os.environ, {}, clear=True):
            importlib.reload(mcp_server)
        mcp_server.PROJECT_ROOT = self.root

    def test_listing_includes_supported_source_and_excludes_build_and_secrets(self):
        (self.root / "src").mkdir()
        (self.root / "src" / "Main.java").write_text("class Main {}", encoding="utf-8")
        (self.root / ".env").write_text("TOKEN=hidden", encoding="utf-8")
        (self.root / "credentials.json").write_text("{}", encoding="utf-8")
        (self.root / "target").mkdir()
        (self.root / "target" / "Generated.java").write_text("class Generated {}", encoding="utf-8")

        self.assertEqual(mcp_server.list_project_files(), ["src/Main.java"])

    def test_reads_supported_file_and_rejects_unsupported_or_sensitive_files(self):
        (self.root / "Main.py").write_text("print('ok')", encoding="utf-8")
        (self.root / "application.properties").write_text(
            "service.api-key=do-not-return\n", encoding="utf-8"
        )
        (self.root / "settings.ini").write_text("secret=true", encoding="utf-8")
        (self.root / ".env").write_text("TOKEN=hidden", encoding="utf-8")

        self.assertEqual(mcp_server.read_file("Main.py"), "print('ok')")
        config = mcp_server.read_file("application.properties")
        self.assertIn("[REDACTED]", config)
        self.assertNotIn("do-not-return", config)
        search_result = mcp_server.search_repository("do-not-return")
        self.assertEqual(len(search_result), 1)
        self.assertNotIn("do-not-return", search_result[0]["content"])
        for path in ("settings.ini", ".env", "missing.py"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                mcp_server.read_file(path)

    def test_rejects_traversal_and_absolute_paths(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as outside:
            secret = Path(outside) / "secret.py"
            secret.write_text("private", encoding="utf-8")
            for path in ("../secret.py", str(secret)):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    mcp_server.read_file(path)

    def test_rejects_symlinks_even_when_target_is_inside_root(self):
        target = self.root / "real.py"
        target.write_text("safe", encoding="utf-8")
        link = self.root / "alias.py"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is unavailable")

        with self.assertRaisesRegex(ValueError, "Symbolic links"):
            mcp_server.read_file("alias.py")

    def test_search_is_case_insensitive_and_bounded(self):
        (self.root / "Search.py").write_text("Needle here\nneedle there", encoding="utf-8")
        results = mcp_server.search_repository("NEEDLE")
        self.assertEqual([item["line"] for item in results], [1, 2])
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            mcp_server.search_repository("  ")

    def test_rejects_oversized_files(self):
        large_file = self.root / "large.py"
        large_file.write_text("x" * (mcp_server.MAX_READ_BYTES + 1), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "too large"):
            mcp_server.read_file("large.py")

    def test_symbol_lookup_and_references_are_labeled_as_text_matches(self):
        (self.root / "service.py").write_text(
            "class Service:\n    def calculate(self):\n        return calculate_value()\n",
            encoding="utf-8",
        )

        declarations = mcp_server.find_symbol("calculate")
        references = mcp_server.find_references("calculate")
        self.assertEqual(declarations[0]["kind"], "function")
        self.assertEqual(declarations[0]["match_type"], "text_pattern")
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0]["match_type"], "text")

    def test_project_structure_and_dependency_manifests(self):
        (self.root / "src").mkdir()
        (self.root / "src" / "Main.java").write_text("class Main {}", encoding="utf-8")
        component = self.root / "component"
        component.mkdir()
        (component / "requirements.txt").write_text("fastapi==0.115.0\n", encoding="utf-8")
        (component / "pyproject.toml").write_text(
            '[project]\ndependencies = ["pytest>=8"]\n', encoding="utf-8"
        )
        (component / "pom.xml").write_text(
            "<project><dependencies><dependency><groupId>org.example</groupId>"
            "<artifactId>demo</artifactId><version>1.2.3</version></dependency>"
            "</dependencies></project>",
            encoding="utf-8",
        )

        structure = mcp_server.get_project_structure()
        dependencies = mcp_server.analyze_dependencies()
        self.assertIn("component/pom.xml", structure["manifests"])
        self.assertIn("component/requirements.txt", structure["manifests"])
        self.assertIn("component/pyproject.toml", structure["manifests"])
        self.assertTrue(any(item["name"] == "org.example:demo" for item in dependencies))
        self.assertTrue(any(item["name"] == "fastapi" for item in dependencies))
        self.assertTrue(any(item["name"] == "pytest" for item in dependencies))


if __name__ == "__main__":
    unittest.main()
