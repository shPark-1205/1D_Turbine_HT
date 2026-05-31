from __future__ import annotations

import unittest

from internal_passage_1d.gui import (
    DEFAULT_NODE_POSITIONS,
    _auto_node_positions,
    _point_to_segment_distance,
    _edge_to_row,
    _params_from_row,
    _param_row_key,
    _parse_params,
    _unique_id,
)
from internal_passage_1d.sample_cases import build_default_network


class GuiHelperTest(unittest.TestCase):
    def test_parse_params(self) -> None:
        params = _parse_params(
            """
            e_over_dh = 0.067
            row_count = 16
            turn_style = sharp
            enabled = true
            """
        )

        self.assertEqual(params["e_over_dh"], 0.067)
        self.assertEqual(params["row_count"], 16)
        self.assertEqual(params["turn_style"], "sharp")
        self.assertIs(params["enabled"], True)

    def test_edge_row_exposes_technology_parameters(self) -> None:
        network = build_default_network()
        rib_edge = next(edge for edge in network.edges if edge.edge_id == "2_to_3")

        row = _edge_to_row(rib_edge)

        self.assertEqual(row["cooling_technology"], "rib")
        self.assertEqual(row[_param_row_key("e_over_dh")], "0.069")
        self.assertEqual(row[_param_row_key("p_over_e")], "11")
        self.assertEqual(row[_param_row_key("angle_deg")], "45")
        self.assertEqual(row["params_text"], "")

    def test_params_from_row_merges_visible_fields_and_extra_params(self) -> None:
        row = {
            "cooling_technology": "turning",
            "params_text": "custom_loss = 3.2",
            _param_row_key("c_nu"): "1.4",
            _param_row_key("turn_angle_deg"): "180",
        }

        params = _params_from_row(row)

        self.assertEqual(params["custom_loss"], 3.2)
        self.assertEqual(params["c_nu"], 1.4)
        self.assertEqual(params["turn_angle_deg"], 180)

    def test_default_node_positions_cover_sample_inlets(self) -> None:
        self.assertIn("1-1", DEFAULT_NODE_POSITIONS)
        self.assertIn("1-2", DEFAULT_NODE_POSITIONS)

    def test_auto_node_positions_are_normalized(self) -> None:
        positions = _auto_node_positions(["A", "B", "C"])

        self.assertEqual(set(positions), {"A", "B", "C"})
        for x_pos, y_pos in positions.values():
            self.assertGreaterEqual(x_pos, 0.0)
            self.assertLessEqual(x_pos, 1.0)
            self.assertGreaterEqual(y_pos, 0.0)
            self.assertLessEqual(y_pos, 1.0)

    def test_canvas_geometry_helpers(self) -> None:
        self.assertEqual(_unique_id("A_to_B", {"A_to_B"}), "A_to_B_2")
        self.assertAlmostEqual(
            _point_to_segment_distance(5.0, 2.0, 0.0, 0.0, 10.0, 0.0),
            2.0,
        )


if __name__ == "__main__":
    unittest.main()
