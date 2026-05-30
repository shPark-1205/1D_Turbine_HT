from __future__ import annotations

import unittest

from internal_passage_1d.gui import _edge_to_row, _params_from_row, _param_row_key, _parse_params
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
            "cooling_technology": "u_turn",
            "params_text": "custom_loss = 3.2\nturn_style = rounded",
            _param_row_key("nu_multiplier_turn"): "1.4",
            _param_row_key("k_turn"): "1.1",
            _param_row_key("user_K_loss"): "",
            _param_row_key("turn_angle_deg"): "180",
            _param_row_key("bend_radius_m"): "0.012",
            _param_row_key("turn_style"): "sharp",
            _param_row_key("turn_clearance_m"): "",
            _param_row_key("upstream_width_m"): "",
            _param_row_key("upstream_height_m"): "",
            _param_row_key("downstream_width_m"): "",
            _param_row_key("downstream_height_m"): "",
        }

        params = _params_from_row(row)

        self.assertEqual(params["custom_loss"], 3.2)
        self.assertEqual(params["nu_multiplier_turn"], 1.4)
        self.assertEqual(params["k_turn"], 1.1)
        self.assertEqual(params["turn_style"], "sharp")


if __name__ == "__main__":
    unittest.main()
