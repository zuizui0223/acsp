import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GlobalReleaseTests(unittest.TestCase):
    def test_canonical_taxon_results_match_recorded_artifact_hash(self):
        result = json.loads((ROOT / "validation/acsp_global_availability_parity_confirmation_result_v2.json").read_text())
        data = (ROOT / result["authoritative_taxon_result_path"]).read_text(encoding="utf-8").encode()
        self.assertEqual(hashlib.sha256(data).hexdigest(), result["source_workflow"]["heldout_taxon_results_sha256"])
        self.assertEqual(result["taxon_count"], 48)
        self.assertEqual(result["robust_constructible_taxa"], 44)
        self.assertEqual(result["temporally_evaluable_constructible_taxa"], 35)

    def test_audited_port_files_have_not_drifted(self):
        manifest = json.loads((ROOT / "validation/acsp_global_release_port_manifest_v1.json").read_text())
        for entry in manifest["files"]:
            with self.subTest(path=entry["release_path"]):
                text = (ROOT / entry["release_path"]).read_text(encoding="utf-8")
                self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), entry["release_lf_sha256"])

    def test_no_discovery_or_research_dependency(self):
        code = '''
import importlib.abc
import sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("acsp.discovery") or fullname == "research" or fullname.startswith("research."):
            raise AssertionError("excluded release dependency: " + fullname)
sys.meta_path.insert(0, Block())
import acsp.global_cli
from acsp.global_country import _provider_inventory
assert len(_provider_inventory()[0]) == 249
assert "acsp.planning" not in sys.modules
'''
        subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


if __name__ == "__main__":
    unittest.main()
