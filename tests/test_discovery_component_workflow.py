from __future__ import annotations

from types import SimpleNamespace
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acsp.discovery.cli import build_parser
from acsp.discovery.component_workflow import prepare_worldcover_component_partition


class DiscoveryComponentWorkflowTests(unittest.TestCase):
    def candidate_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"candidate_cell_id": "a", "latitude": 35.0, "longitude": 139.0, "grid_row": 0, "grid_col": 0},
                {"candidate_cell_id": "b", "latitude": 35.0, "longitude": 139.01, "grid_row": 0, "grid_col": 1},
                {"candidate_cell_id": "c", "latitude": 35.01, "longitude": 139.0, "grid_row": 1, "grid_col": 0},
            ]
        )

    def anchors(self) -> pd.DataFrame:
        return pd.DataFrame({"latitude": [35.0], "longitude": [139.0]})

    def test_preparation_writes_source_backed_partition_semantics(self) -> None:
        candidate = self.candidate_frame()
        land = candidate.copy()
        land["ecological_component_id"] = ["COMP_1", "COMP_1", "COMP_2"]
        wc_audit = SimpleNamespace(
            release_id="2021_v200",
            source_urls=("https://example.invalid/worldcover.tif",),
            output_sha256="a" * 64,
        )
        component_audit = SimpleNamespace(anchored_component_ids=("COMP_1",))
        with tempfile.TemporaryDirectory() as tmp, patch(
            "acsp.discovery.component_workflow.build_worldcover_2021_map_crop",
            return_value=wc_audit,
        ), patch(
            "acsp.discovery.component_workflow.attach_worldcover_component_ids",
            return_value=(land, component_audit),
        ):
            all_land, anchored, other, audit = prepare_worldcover_component_partition(
                candidate,
                self.anchors(),
                snapshot_path=Path(tmp) / "worldcover.tif",
            )
        self.assertEqual(len(all_land), 3)
        self.assertEqual(anchored["candidate_cell_id"].tolist(), ["a", "b"])
        self.assertEqual(other["candidate_cell_id"].tolist(), ["c"])
        self.assertEqual(audit.anchored_component_ids, ("COMP_1",))
        self.assertEqual(audit.anchored_candidate_count, 2)
        self.assertEqual(audit.other_component_candidate_count, 1)
        self.assertEqual(
            {row["layer_role"] for row in audit.source_manifest["sources"]},
            {"component_geometry", "landcover"},
        )
        self.assertFalse(audit.field_outcomes_used)
        self.assertFalse(audit.component_selection_fitted_to_outcomes)

    def test_cli_has_prepare_components_without_component_id_input(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "prepare-components",
                "--candidate-frame", "broad.csv",
                "--anchors", "anchors.csv",
                "--out-dir", "components",
            ]
        )
        self.assertEqual(args.command, "prepare-components")
        self.assertFalse(hasattr(args, "anchored_component_id"))
        self.assertEqual(args.crop_margin_m, 3000.0)


if __name__ == "__main__":
    unittest.main()
