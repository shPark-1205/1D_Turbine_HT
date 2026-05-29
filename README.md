# 1D_Turbine_HT

## Internal Passage 1D Prototype

This repository contains an early Python skeleton for a steady 1D gas-turbine
internal cooling passage solver.

The first version focuses on:

- fixed inlet mass flow, temperature, and pressure
- directed acyclic node-edge networks
- merge mixing by mass-flow-weighted temperature
- edge-based geometry and cooling technology inputs
- ideal-gas air properties by default
- optional CoolProp air properties when CoolProp is installed
- smooth, rib, U-turn, and pin-fin placeholder correlations
- user friction multipliers and user K-loss inputs

## Run the example

```powershell
python examples/run_fixed_flow_example.py
```

## Run tests

```powershell
python -m unittest discover -s tests
```

## Current modeling notes

- The solver currently uses fixed inlet flows. It computes pressure loss along
  the known flow paths but does not yet solve branch flow from pressure balance.
- Merge pressure consistency is reported as a warning when incoming branch
  pressures differ.
- U-turn pressure loss is represented by user K-loss values and a Nusselt
  multiplier.
- Rib and pin-fin formulas are implemented as replaceable modules. Their
  pressure-drop models are intentionally simple until project-specific
  correlations are added.
- Internal calculations are SI.
