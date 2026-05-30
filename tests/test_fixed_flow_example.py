from __future__ import annotations

import math
import unittest

from internal_passage_1d import FixedFlowSolver, SolverOptions
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

        for edge in result.edges.values():
            self.assertGreater(edge.reynolds, 0.0)
            self.assertGreater(edge.nusselt, 0.0)
            self.assertGreater(edge.htc, 0.0)
            self.assertTrue(math.isfinite(edge.dp_total))


if __name__ == "__main__":
    unittest.main()
