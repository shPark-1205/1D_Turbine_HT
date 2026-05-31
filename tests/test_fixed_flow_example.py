from __future__ import annotations

import math
import unittest

from internal_passage_1d import FixedFlowSolver, SolverOptions
from internal_passage_1d.models import EdgeSpec, Geometry, NodeSpec
from internal_passage_1d.sample_cases import build_default_network


class FixedFlowExampleTest(unittest.TestCase):
    def test_example_solves_to_outlet(self) -> None:
        result = FixedFlowSolver(
            build_default_network(),
            SolverOptions(property_model="ideal_gas"),
        ).solve()

        self.assertIn("8", result.nodes)
        self.assertEqual(len(result.edges), 8)
        self.assertAlmostEqual(result.nodes["8"].mass_flow, 0.128, places=9)
        self.assertLess(result.nodes["8"].pressure, 707_000.0)
        self.assertGreater(result.nodes["8"].pressure, 0.0)

        for edge in result.edges.values():
            self.assertGreater(edge.reynolds, 0.0)
            self.assertGreater(edge.nusselt, 0.0)
            self.assertGreater(edge.htc, 0.0)
            self.assertTrue(math.isfinite(edge.dp_total))

        self.assertGreater(result.edges["2_to_3"].dp_rotation, 0.0)
        self.assertEqual(result.edges["3_to_4"].cooling_technology, "turning")
        self.assertEqual(result.edges["7_to_8"].intermediate["row_count"], 6)
        self.assertEqual(result.edges["7_to_8"].intermediate["pins_cross"], 10)

    def test_sample_can_be_extended_after_original_outlet(self) -> None:
        network = build_default_network()
        nodes = [
            NodeSpec(
                node.node_id,
                kind="internal" if node.node_id == "8" else node.kind,
                inlet_mdot=node.inlet_mdot,
                inlet_temperature=node.inlet_temperature,
                inlet_pressure=node.inlet_pressure,
            )
            for node in network.nodes
        ]
        nodes.append(NodeSpec("9", kind="outlet"))
        edges = [
            *network.edges,
            EdgeSpec(
                "8_to_9",
                "8",
                "9",
                Geometry(length=0.05, width=0.01, height=0.01),
                "smooth",
            ),
        ]

        result = FixedFlowSolver(
            type(network)(nodes=nodes, edges=edges),
            SolverOptions(property_model="ideal_gas"),
        ).solve()

        self.assertIn("9", result.nodes)
        self.assertGreater(result.nodes["9"].pressure, 0.0)


if __name__ == "__main__":
    unittest.main()
