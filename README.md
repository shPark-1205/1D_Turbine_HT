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

## Run the desktop GUI

```powershell
python examples/run_gui.py
```

The GUI starts with the current sample network. The opening dashboard follows
the earlier DLC 1D Streamlit layout: design summary on the left, real-time key
metrics in the center, and edge-level verification results on the right. Select
a node or edge, edit its values, click `Apply`, then click `Calculate`. In the
`Edges` tab, the `Technology` field controls which cooling-technology
parameters are shown. Full results are shown as node and edge tables, and
warnings are collected in a separate tab.

## PyCharm workflow

Open this repository folder in PyCharm:

```text
C:\Users\HTL-SHP\Documents\1D Internal Passage
```

Use Python 3.10 or newer as the project interpreter. Then run:

```text
examples/run_gui.py
```

For code-only checks, run:

```powershell
python -m unittest discover -s tests
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
