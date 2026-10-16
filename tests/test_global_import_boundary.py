"""Global entry imports only historical country framing, never structural discovery."""
import importlib
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GlobalImportBoundaryTests(unittest.TestCase):
    def test_global_entry_works_when_experimental_imports_are_blocked(self):
        code = '''
import importlib.abc
import sys
allowed = {
    "acsp.discovery", "acsp.discovery.country_entry", "acsp.discovery.country_frames",
    "acsp.discovery.providers", "acsp.discovery.providers.gbif",
}
class BlockExperimental(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("acsp.discovery") and fullname not in allowed:
            raise AssertionError("experimental dependency: " + fullname)
sys.meta_path.insert(0, BlockExperimental())
import acsp.global_cli
from acsp.discovery.country_entry import _provider_inventory
assert len(_provider_inventory()[0]) == 249
assert "acsp.planning" not in sys.modules
assert "gbif_fieldmap_builder_app" not in sys.modules
'''
        subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)

    def test_all_existing_exports_resolve_to_original_objects(self):
        for module_name in ("acsp.discovery", "acsp.discovery.providers"):
            module = importlib.import_module(module_name)
            for name, implementation in module._LAZY_EXPORTS.items():
                with self.subTest(module=module_name, name=name):
                    self.assertIs(getattr(module, name), getattr(importlib.import_module(f"{module_name}.{implementation}"), name))
                    self.assertIn(name, dir(module))
            self.assertTrue(set(module.__all__).issubset(dir(module)))
            namespace = {}
            exec(f"from {module_name} import *", namespace)
            self.assertTrue(set(module.__all__).issubset(namespace))
            with self.assertRaises(AttributeError):
                getattr(module, "not_an_export")

    def test_public_export_lists_match_pre_change_contract(self):
        # Freeze the public name lists independently of the lazy mapping.
        self.assertEqual(len(importlib.import_module("acsp.discovery").__all__), 66)
        self.assertEqual(len(importlib.import_module("acsp.discovery.providers").__all__), 15)


if __name__ == "__main__":
    unittest.main()
