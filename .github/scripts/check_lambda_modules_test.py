import tempfile
import unittest
from pathlib import Path

from check_lambda_modules import collisions


class LambdaModuleTests(unittest.TestCase):
    def test_detects_module_and_package_name_collision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "shared.py").write_text("value = 1\n")
            package = root / "shared"
            package.mkdir()
            (package / "__init__.py").write_text("value = 2\n")
            self.assertEqual(set(collisions(root)), {"shared"})

    def test_detects_module_blocking_a_submodule(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "shared.py").write_text("value = 1\n")
            package = root / "shared"
            package.mkdir()
            (package / "child.py").write_text("value = 2\n")
            self.assertIn("shared (module/package conflict)", collisions(root))

    def test_distinct_modules_and_tests_are_not_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("handler.py", "models.py", "handler_test.py", "tests/handler_test.py"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("value = 1\n")
            self.assertEqual(collisions(root), {})


if __name__ == "__main__":
    unittest.main()