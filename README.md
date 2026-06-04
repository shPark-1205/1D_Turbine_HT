# 1D_Turbine_HT

## Internal Passage 1D Prototype

This repository contains a Python prototype for steady 1D heat-transfer and
pressure-loss calculations in gas-turbine internal cooling passages.

The current version focuses on a GUI-driven workflow. Users can define a
node-edge cooling network, assign edge-level geometry and cooling technologies,
run the 1D calculation, visualize results on an image overlay, and perform
parametric sweeps.

## Current Capabilities

- Steady fixed-flow 1D network calculation.
- Inlet nodes use user-defined mass flow, temperature, and pressure.
- Directed node-edge networks with no recirculating flow loops.
- Merge mixing by mass-flow-weighted coolant temperature.
- Edge-based geometry, wall boundary, cooling technology, and tag inputs.
- Edge tags for batch targeting, currently including `Leading edge` and
  `Trailing edge`.
- Image-based workspace where nodes can be moved and edges can be selected on
  top of a turbine internal-passage image.
- Unit-aware GUI inputs with common SI and US engineering units; internal
  calculations remain SI.
- Ideal-gas air property model by default.
- Optional CoolProp air properties with automatic ideal-gas fallback when
  CoolProp is unavailable.
- Smooth, rib, turning, and pin-fin heat-transfer/pressure-loss models.
- Rib rotation pressure-loss correction.
- Automatic pin-fin row/across-count calculation from channel and pitch
  geometry.
- External gas convection, TBC conduction, blade wall conduction, and internal
  cooling convection coupled as a 1D thermal resistance network.
- Result tables, selected-edge result summary, wall/TBC/coolant stack view,
  image overlay coloring, and CSV export.
- Parametric sweep with objective selection, constraints, stop control, and
  response plots.
- Batch edge editing from the currently selected source edge.

## Quick Start

Install optional GUI/property dependencies:

```powershell
pip install -r requirements.txt
```

Run the desktop GUI:

```powershell
python run_turbine_1d_gui.py
```

The same GUI is also available from the example launcher:

```powershell
python examples/run_gui.py
```

Run the code-only fixed-flow example:

```powershell
python examples/run_fixed_flow_example.py
```

## GUI Workflow

The GUI starts with the sample turbine internal-passage network in the
`Workspace` tab.

Typical workflow:

1. Load a turbine passage image with `Load Image`.
2. Move existing nodes on the image or add new nodes with `Add Node`.
3. Connect nodes with `Connect Nodes`.
4. Select a node or edge from the image overlay or from the network tables.
5. Edit the selected node or edge from the right-side editor.
6. Press `Calculate`.
7. Review result tables, warnings, selected-edge results, and overlay contours.

Node inputs are shown only when they are relevant. For example, inlet mass flow,
temperature, and pressure are editable only for inlet nodes.

Edge inputs are also filtered by the selected technology, shape, and wall mode.
For example, rib parameters are shown only for rib edges, and external gas
temperature/HTC plus wall/TBC properties are shown only for
`external_convection` wall mode.

## Workspace Overlay

The image overlay can color the network by:

- edge outlet temperature
- edge HTC
- edge pressure drop
- edge heat transfer
- node temperature
- node pressure

The overlay legend uses blue for the lowest value and red for the highest value.
Selected edges remain highlighted even when the result overlay is active.

Use `Ctrl` + edge click to build a layout edge selection for batch editing. The
selection hit area includes both the edge line and the edge label box.

## Batch Apply

Batch editing copies checked variables from the currently selected edge to a
target set of edges.

To use it:

1. Select the edge that contains the values to copy.
2. Check `Batch` beside the edge variables to copy.
3. Choose a target in `Batch Apply`.
4. Press `Apply Batch`.

Available target modes:

- all edges
- current edge
- layout-selected edges
- edges with the selected cooling technology
- edges with the selected tag

Batch-capable fields include numeric inputs and dropdown inputs such as
`Technology`, `Shape`, `Wall mode`, and `Tag`. `Undo Batch` restores the previous
edge data after the most recent batch operation.

## Parametric Sweep

The `Parametric Sweep` tab repeatedly solves the 1D model while varying selected
input variables.

To use it:

1. Check `Sweep` beside numeric node or edge inputs in `Workspace`.
2. Open `Parametric Sweep`.
3. Set start, end, and step for each selected variable.
4. Choose an objective.
5. Add optional constraints.
6. Press `Run Sweep`.

Objective scopes:

- `Global`: `total_dp`, `outlet_T`, `max_wall_T`
- `Node`: available node result values
- `Edge`: available edge result values and numeric intermediate values

Supported constraints:

- outlet pressure range
- maximum wall temperature range
- total pressure-drop range

There is no hard limit on the number of sweep variables, but the total case
count can grow very quickly. Check `Total cases` before running large sweeps.
The sweep can be stopped with `Stop`.

Available plot modes include automatic selection, line, heatmap, surface, and
scatter plots.

## Correlations

The `Correlations` tab summarizes the current prototype equations with
matplotlib mathtext rendering.

Included models:

- Smooth channel: Dittus-Boelter Nusselt number with user `C_Nu`, plus smooth
  friction pressure loss.
- Rib turbulator: iterative rib friction calculation, roughness/heat-transfer
  functions, Stanton-number HTC, and rotation pressure loss.
- Turning: simplified `f_turning = 3 * f_smooth` and `Nu = C_Nu * Nu_DB`.
- Pin-fin array: minimum-area velocity, pin-diameter Reynolds number, pin-fin
  friction, and pin-fin HTC.
- Wall/TBC thermal network: external convection, TBC conduction, blade wall
  conduction, and internal convection.

## Optional Dependencies

`requirements.txt` currently includes:

- `CoolProp`
- `matplotlib`
- `Pillow`

`CoolProp` enables real-gas air properties. If the GUI is set to CoolProp but
CoolProp is not available, the calculation automatically falls back to the
ideal-gas property model and reports a warning.

`matplotlib` is used for equation rendering and sweep plots. `Pillow` is used
for loading and resizing image overlays.

## Distribution Notes

For this stage, the repository keeps two GUI launch styles:

- `run_turbine_1d_gui.py`: top-level launcher for general users.
- `examples/run_gui.py`: example/developer launcher that can be updated when
  reference cases and final correlation parameters are fixed.

For wider internal distribution, the usual next step is to package the GUI as a
Windows executable with PyInstaller after the correlations and input format are
stable.

## Run Tests

```powershell
python -m unittest discover -s tests
```

## Current Modeling Notes

- The solver currently uses fixed inlet flows. It computes pressure loss along
  the known flow paths but does not yet solve branch flow from pressure balance.
- Merge pressure consistency is reported as a warning when incoming branch
  pressures differ.
- Turning edges use the simplified pressure-loss and heat-transfer assumptions
  listed above until a project-specific turn correlation is selected.
- Rib friction is solved iteratively because `e+` depends on the rib friction
  factor.
- Pin-fin row count and pins across the channel are calculated from channel
  length, channel width, and pin pitch.
- `external_convection` wall mode computes heat transfer with
  `R_i + R_wall + R_TBC + R_o`, using the same thermal area as the internal
  cooling correlation in this first implementation.
- Internal calculations are SI even when GUI input units are changed.
