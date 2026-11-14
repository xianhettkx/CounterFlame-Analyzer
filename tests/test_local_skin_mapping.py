import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class LocalSkinManifestTests(unittest.TestCase):
    def test_manifest_has_six_complete_local_mappings(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result.json"
            proc = subprocess.run(
                [sys.executable, "src/validate_local_skin_mapping.py",
                 "--manifest", "config/local_skin_pseudo_entity_map.json",
                 "--out", str(out)],
                capture_output=True, text=True
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            result = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(result["skin_count"], 6)
            self.assertTrue(result["mapping_entries_complete"])
            self.assertEqual(result["activation_status"],
                             "asset_mapping_confirmed_runtime_activation_unverified")

if __name__ == "__main__":
    unittest.main()
