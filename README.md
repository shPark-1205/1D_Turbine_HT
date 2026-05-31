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
- smooth, rib, turning, and pin-fin correlations
- rib rotation pressure-loss correction
- automatic pin-fin row/across-count calculation from channel and pitch geometry
- external gas convection, TBC conduction, blade wall conduction, and internal
  cooling convection coupled as a 1D thermal resistance network

## Run the example

```powershell
python examples/run_fixed_flow_example.py
```

## Run the desktop GUI

```powershell
python run_turbine_1d_gui.py
```

The same GUI is also available from the example launcher:

```powershell
python examples/run_gui.py
```

The GUI starts with the current sample network in a single `Workspace` screen.
Load a turbine internal-passage image, drag nodes to the desired locations, and
select nodes or edges directly on the image. Node and edge editors are shown on
the right side of the same screen. Use `Add Node` to place a node by clicking on
the image, and `Connect Nodes` to create an edge by clicking a source node and a
target node. The `Technology` field controls which cooling-technology
parameters are shown. The `Correlations` tab summarizes the pressure-drop and
heat-transfer equations used by the current prototype. The layout overlay can
color edges or nodes by outlet temperature, HTC, pressure drop, heat transfer,
node temperature, or node pressure. Selecting an edge shows a compact result
summary plus the wall/TBC/coolant temperature stack when external convection is
used. Full calculation results and warnings remain available in separate result
tabs.

## Install Optional Dependencies

For development environments, install optional property/image dependencies with:

```powershell
pip install -r requirements.txt
```

`CoolProp` enables real-gas air properties. If the GUI is set to CoolProp but
CoolProp is not available, the calculation automatically falls back to the
ideal-gas property model and reports a warning.

## PyCharm workflow

Open this repository folder in PyCharm:

```text
C:\Users\HTL-SHP\Documents\1D Internal Passage
```

Use Python 3.10 or newer as the project interpreter. Then run:

```text
run_turbine_1d_gui.py
```

For code-only checks, run:

```powershell
python -m unittest discover -s tests
```

## Distribution Notes

For this early stage, the repository keeps two launch styles:

- `run_turbine_1d_gui.py`: top-level launcher for general users.
- `examples/run_gui.py`: example/developer launcher that can be updated when
  reference cases and final correlation parameters are fixed.

For wider internal distribution, the usual next step is to package the GUI as a
Windows executable with PyInstaller after the correlations and input format are
stable.

## Run tests

```powershell
python -m unittest discover -s tests
```

## Current modeling notes

- The solver currently uses fixed inlet flows. It computes pressure loss along
  the known flow paths but does not yet solve branch flow from pressure balance.
- Merge pressure consistency is reported as a warning when incoming branch
  pressures differ.
- Turning edges use `f_turning = 3 * f_smooth` and `Nu = C_Nu * Nu_DB` until a
  project-specific turn correlation is selected.
- Rib friction is solved iteratively because `e+` depends on the rib friction
  factor.
- Pin-fin row count and pins across the channel are calculated from channel
  length, channel width, and pin pitch.
- `external_convection` wall mode computes heat transfer with
  `R_i + R_wall + R_TBC + R_o`, using the same thermal area as the internal
  cooling correlation in this first implementation.
- Internal calculations are SI.
