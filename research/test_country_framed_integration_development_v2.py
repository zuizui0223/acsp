import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd

from predeclare_country_framed_integration_development_v2 import EXPECTED_PROTOCOL_FINGERPRINT, _protocol, select_v2_taxa
from regional_country_lattice import LATTICE_STEP_DEG, POINTS_PER_REGIONAL_TILE
from run_country_framed_integration_development_v2 import evaluate

ROOT=Path(__file__).resolve().parents[1]

class V2ContractTests(unittest.TestCase):
    def test_protocol_is_frozen_and_single_method_change(self):
        p=_protocol()
        self.assertEqual(p["protocol_fingerprint"],EXPECTED_PROTOCOL_FINGERPRINT)
        self.assertEqual(p["method_change_from_v1_1"],"replace_one_sparse_country_surface_with_frozen_2deg_regional_lattice_only")
        self.assertEqual(p["provider"]["regional_lattice_freeze_fingerprint"],"6d5c0ca8cc699eda7856d37e72007cadcc208a9312765f1162ed963ae0de0ba1")
        self.assertEqual(LATTICE_STEP_DEG,2.0); self.assertEqual(POINTS_PER_REGIONAL_TILE,800)
        self.assertEqual(p["robust_core"]["support_fraction"],0.025)
        self.assertEqual(p["evaluation"]["primary_recovery_radius_km"],10.0)
        self.assertEqual(p["evaluation"]["random_baseline_repetitions"],200)
        self.assertFalse(p["retuning_after_outcome_opening_allowed"])

    def test_third_v4_subset_is_balanced_and_disjoint(self):
        source=pd.read_csv(ROOT/"validation/geographic_framing_development_v4/predeclared_taxon_region_pairs.csv")
        selected=select_v2_taxa(source)
        self.assertEqual(len(selected),24); self.assertEqual(selected.speciesKey.nunique(),24)
        self.assertEqual(selected.taxon_group.value_counts().to_dict(),{"plant":12,"animal":12})
        self.assertEqual(selected.record_count_stratum.astype(int).value_counts().sort_index().to_dict(),{0:6,1:6,2:6,3:6})
        for row in selected.itertuples(index=False): self.assertEqual(int(row.record_count_stratum),(int(row.region_cell_index)+1)%4)
        v1=set(pd.read_csv(ROOT/"validation/country_framed_robust_integration_development_v1/predeclared_taxon_country_pairs_compact.csv").speciesKey.astype(int))
        v11=set(pd.read_csv(ROOT/"validation/country_framed_robust_integration_development_v1_1/predeclared_taxon_country_pairs_compact.csv").speciesKey.astype(int))
        self.assertFalse(set(selected.speciesKey.astype(int)) & (v1|v11))

    @patch("run_country_framed_integration_development_v2.fetch_recent_country_occurrences")
    @patch("run_country_framed_integration_development_v2.validated_robust_candidate_patches")
    @patch("run_country_framed_integration_development_v2.regional_terrain_inputs")
    @patch("run_country_framed_integration_development_v2.fetch_country_occurrences")
    @patch("run_country_framed_integration_development_v2.fetch_geoboundaries_country_geometry")
    def test_candidate_generation_precedes_recent_outcome(self,geom,hist,terrain,robust,recent):
        order=[]
        class G: source_version="canonical_geojson_sha256="+"a"*64
        class A: intersecting_tile_count=1; total_geometry_points=800
        class S:
            def as_dict(self): return {}
        geom.side_effect=lambda code:(order.append("geometry") or G())
        hist.side_effect=lambda *a,**k:(order.append("historical") or pd.DataFrame({"latitude":[1,2,3,4,5],"longitude":[1,2,3,4,5]}))
        surface=pd.DataFrame({"latitude":[1.,2.],"longitude":[1.,2.],"survey_area_id":["country-US"]*2})
        terrain.side_effect=lambda *a,**k:(order.append("terrain") or (surface,surface.copy(),A()))
        robust.side_effect=lambda *a,**k:(order.append("robust") or (pd.DataFrame({"candidate_patch_id":["p"],"survey_area_id":["country-US"],"latitude":[1.],"longitude":[1.]}),S()))
        recent.side_effect=lambda *a,**k:(order.append("recent") or pd.DataFrame())
        rows=[]
        for i in range(24): rows.append({"integration_pair_id":i+1,"speciesKey":1000+i,"scientific_name":f"s{i}","taxon_group":"plant" if i<12 else "animal","declaration_status":"declared","selected_country_code":"US","geometry_canonical_sha256":"a"*64})
        _,_,summary=evaluate(pd.DataFrame(rows))
        self.assertEqual(order[:5],["geometry","historical","terrain","robust","recent"])
        self.assertTrue(summary["candidate_generation_preceded_recent_outcome_fetch"])
        self.assertEqual(summary["primary_radius_km"],10.0)

if __name__=="__main__": unittest.main()
