import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.ipa_scanner import scan_ipa
from src.bundle_inspector import inspect_header


class ScannerTests(unittest.TestCase):
    def test_scans_catalog_and_matches_bundle_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ipa = root / "sample.ipa"
            output = root / "reports"
            bundle = "Payload/Game.app/aa/iOS/sample.bundle"
            catalog = {
                "m_InternalIds": [
                    "{UnityEngine.AddressableAssets.Addressables.RuntimePath}/iOS/sample.bundle"
                ]
            }
            with zipfile.ZipFile(ipa, "w") as zf:
                zf.writestr(bundle, b"fake bundle bytes")
                zf.writestr("Payload/Game.app/Raw/aa/catalog.json", json.dumps(catalog))
            report = scan_ipa(ipa, output, None)
            self.assertEqual(report["summary"]["catalog_json_count"], 1)
            self.assertEqual(report["summary"]["catalog_bundle_id_count"], 1)
            self.assertEqual(report["summary"]["catalog_paths_matched_to_ipa"], 1)
            self.assertTrue((output / "analysis.json").is_file())
            self.assertTrue((output / "report.html").is_file())

    def test_identifies_unityfs_header(self):
        import io
        result = inspect_header(io.BytesIO(b"UnityFS\\x00  6.x.x\\x00" + b"\\x00" * 40))
        self.assertEqual(result["signature"], "UnityFS")
        self.assertEqual(result["format"], "UnityFS")

    def test_unknown_bundle_header_is_not_misidentified(self):
        import io
        result = inspect_header(io.BytesIO(b"not a unity bundle"))
        self.assertIsNone(result["signature"])
        self.assertEqual(result["format"], "unknown_or_nonstandard")

    def test_reports_missing_catalog_path_without_claiming_asset_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ipa = root / "sample.ipa"
            with zipfile.ZipFile(ipa, "w") as zf:
                zf.writestr(
                    "Payload/Game.app/Raw/aa/catalog.json",
                    json.dumps({"m_InternalIds": ["iOS/not_in_ipa.bundle"]}),
                )
            report = scan_ipa(ipa, root / "out", None)
            self.assertEqual(report["summary"]["catalog_paths_not_found_in_ipa"], 1)
            self.assertEqual(report["summary"]["physical_bundle_entry_count"], 0)


if __name__ == "__main__":
    unittest.main()
