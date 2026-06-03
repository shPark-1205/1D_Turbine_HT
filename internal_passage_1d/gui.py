from __future__ import annotations

import csv
import tkinter as tk
from copy import deepcopy
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, NamedTuple

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - exercised only when Pillow is absent.
    Image = None
    ImageTk = None

try:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
except ImportError:  # pragma: no cover - text fallback is used when absent.
    Figure = None
    FigureCanvasAgg = None

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
except ImportError:  # pragma: no cover - plot fallback is used when absent.
    FigureCanvasTkAgg = None

from .models import (
    EdgeSpec,
    Geometry,
    NetworkSpec,
    NodeSpec,
    SolverOptions,
    SolverResult,
    WallBoundary,
)
from .network import FixedFlowSolver
from .sample_cases import build_default_network


NODE_KINDS = ("inlet", "internal", "merge", "split", "outlet")
TECHNOLOGIES = ("smooth", "rib", "turning", "pin_fin")
SHAPES = ("rectangular", "circular")
WALL_MODES = ("adiabatic", "wall_temperature", "heat_flux", "external_convection")
PROPERTY_MODELS = ("ideal_gas", "coolprop")
TAG_OPTIONS = ("Unassigned", "Leading edge", "Trailing edge")
BATCH_TARGET_MODES = (
    "All edges",
    "Current edge",
    "Layout selected edges",
    "Cooling technology",
    "Tag",
)
BATCH_BASE_FIELDS = (
    ("tag", "Tag", "choice", TAG_OPTIONS),
    ("cooling_technology", "Cooling technology", "choice", TECHNOLOGIES),
    ("shape", "Shape", "choice", SHAPES),
    ("wall_mode", "Wall mode", "choice", WALL_MODES),
    ("length", "Length", "number", ()),
    ("width", "Width", "number", ()),
    ("height", "Height", "number", ()),
    ("diameter", "Diameter", "number", ()),
    ("wall_temperature", "Wall T", "number", ()),
    ("heat_flux", "Heat flux", "number", ()),
    ("external_temperature", "External gas T", "number", ()),
    ("external_htc", "External h", "number", ()),
    ("wall_thickness", "Blade wall thickness", "number", ()),
    ("wall_conductivity", "Blade wall k", "number", ()),
    ("tbc_thickness", "TBC thickness", "number", ()),
    ("tbc_conductivity", "TBC k", "number", ()),
)
SWEEP_OBJECTIVE_SCOPES = ("Global", "Node", "Edge")
SWEEP_DIRECTIONS = ("Minimize", "Maximize")
GLOBAL_OBJECTIVE_METRICS = ("total_dp", "outlet_T", "max_wall_T")
NODE_OBJECTIVE_METRICS = ("mass_flow", "temperature", "pressure")
EDGE_BASE_OBJECTIVE_METRICS = (
    "mass_flow",
    "inlet_temperature",
    "outlet_temperature",
    "inlet_pressure",
    "outlet_pressure",
    "reynolds",
    "nusselt",
    "htc",
    "friction_factor_darcy",
    "velocity",
    "heat_transfer_area",
    "heat_rate",
    "dp_friction",
    "dp_rotation",
    "dp_minor",
    "dp_total",
)
CONSTRAINT_SPECS = {
    "outlet_pressure": ("Outlet pressure", "pressure"),
    "max_wall_T": ("Max wall temperature", "temperature"),
    "total_dp": ("Total dp", "pressure"),
}
OVERLAY_METRICS = (
    "Technology",
    "Edge Tout [K]",
    "Edge HTC [W/m2-K]",
    "Edge dp [Pa]",
    "Edge q [W]",
    "Node T [K]",
    "Node P [Pa]",
)
UNIT_OPTIONS = {
    "length": ("m", "cm", "mm", "um", "in", "ft"),
    "pressure": ("Pa", "kPa", "MPa", "bar", "psi"),
    "temperature": ("K", "C", "F", "R"),
    "mass_flow": ("kg/s", "g/s", "kg/min", "g/min", "lb/s", "lb/min"),
    "thermal_conductivity": ("W/m/K", "BTU/h/ft/F"),
    "heat_flux": ("W/m2", "kW/m2", "MW/m2", "BTU/h/ft2"),
    "htc": ("W/m2/K", "kW/m2/K", "BTU/h/ft2/F"),
}
FIELD_UNIT_GROUPS = {
    "inlet_mdot": "mass_flow",
    "inlet_temperature": "temperature",
    "inlet_pressure": "pressure",
    "length": "length",
    "width": "length",
    "height": "length",
    "diameter": "length",
    "wall_temperature": "temperature",
    "heat_flux": "heat_flux",
    "external_temperature": "temperature",
    "external_htc": "htc",
    "wall_thickness": "length",
    "wall_conductivity": "thermal_conductivity",
    "tbc_thickness": "length",
    "tbc_conductivity": "thermal_conductivity",
    "radius_m": "length",
    "pin_diameter": "length",
    "pin_height": "length",
    "pitch_x": "length",
    "pitch_s": "length",
}
IMAGE_FILETYPES = (
    ("Image files", "*.png *.jpg *.jpeg *.gif *.ppm *.pgm"),
    ("PNG files", "*.png"),
    ("JPEG files", "*.jpg *.jpeg"),
    ("All files", "*.*"),
)
ACCENT_COLOR = "#1f77b4"
TEXT_COLOR = "#31333F"
MUTED_COLOR = "#5c6670"
WINDOW_BG = "#f5f7fb"
PANEL_BG = "#ffffff"
BORDER_COLOR = "#d8e1ec"
SAFE_COLOR = "#0f7b3d"
WARNING_COLOR = "#b36b00"
DANGER_COLOR = "#b00020"
DEFAULT_NODE_POSITIONS: dict[str, tuple[float, float]] = {
    "1-1": (0.82, 0.78),
    "1-2": (0.48, 0.86),
    "2": (0.69, 0.69),
    "3": (0.69, 0.13),
    "4": (0.54, 0.13),
    "5": (0.55, 0.70),
    "6": (0.44, 0.70),
    "7": (0.31, 0.34),
    "8": (0.11, 0.34),
}


class ParamSpec(NamedTuple):
    key: str
    label: str
    default: str = ""


@dataclass
class SweepVariable:
    target_id: str
    scope: str
    object_id: str
    field_key: str
    row_key: str
    label: str
    unit_group: str | None
    unit: str
    start: str = ""
    end: str = ""
    step: str = ""


TECH_PARAM_SPECS: dict[str, tuple[ParamSpec, ...]] = {
    "smooth": (
        ParamSpec("c_nu", "C_Nu [-]", "1"),
    ),
    "rib": (
        ParamSpec("e_over_dh", "Rib e/Dh [-]"),
        ParamSpec("p_over_e", "Rib pitch/e [-]"),
        ParamSpec("angle_deg", "Rib angle [deg]", "45"),
        ParamSpec("radius_m", "Blade radius", "1.23"),
        ParamSpec("rpm", "Blade RPM", "3000"),
        ParamSpec("c_rotation", "C_rotation [-]", "1.056"),
        ParamSpec("ribbed_walls", "Ribbed walls", "2"),
    ),
    "turning": (
        ParamSpec("c_nu", "C_Nu [-]", "1.5"),
        ParamSpec("turn_angle_deg", "Turn angle [deg]", "180"),
    ),
    "pin_fin": (
        ParamSpec("pin_diameter", "Pin diameter"),
        ParamSpec("pin_height", "Pin height"),
        ParamSpec("pitch_x", "Streamwise pitch X"),
        ParamSpec("pitch_s", "Spanwise pitch S"),
    ),
}
ALL_PARAM_KEYS = tuple(
    dict.fromkeys(
        spec.key
        for specs in TECH_PARAM_SPECS.values()
        for spec in specs
    )
)
NODE_UNIT_KEYS = ("inlet_mdot", "inlet_temperature", "inlet_pressure")
EDGE_FIELD_UNIT_KEYS = (
    "length",
    "width",
    "height",
    "diameter",
    "wall_temperature",
    "heat_flux",
    "external_temperature",
    "external_htc",
    "wall_thickness",
    "wall_conductivity",
    "tbc_thickness",
    "tbc_conductivity",
)
EDGE_UNIT_KEYS = EDGE_FIELD_UNIT_KEYS + tuple(
    key for key in ALL_PARAM_KEYS if key in FIELD_UNIT_GROUPS
)
BATCH_FIELD_SPECS = BATCH_BASE_FIELDS + tuple(
    (
        spec.key,
        f"{technology.replace('_', ' ').title()} / {spec.label}",
        "number",
        (),
    )
    for technology, specs in TECH_PARAM_SPECS.items()
    for spec in specs
)

class PassageApp(tk.Tk):
    """Desktop GUI for editing and running the 1D passage solver."""

    def __init__(self) -> None:
        super().__init__()
        self.title("1D Turbine Internal Passage Solver")
        self.geometry("1380x860")
        self.minsize(1260, 780)
        self.configure(bg=WINDOW_BG)

        self.node_rows: list[dict[str, str]] = []
        self.edge_rows: list[dict[str, str]] = []
        self.last_result: SolverResult | None = None
        self._syncing_edge_form = False
        self._suppress_auto_apply = False
        self.node_positions: dict[str, tuple[float, float]] = {}
        self.layout_image_path: Path | None = None
        self._layout_source_image: Any = None
        self._layout_native_photo: tk.PhotoImage | None = None
        self._layout_photo: Any = None
        self._layout_image_bbox = (20.0, 20.0, 1.0, 1.0)
        self._edge_label_bboxes: dict[str, tuple[float, float, float, float]] = {}
        self.selected_node_id: str | None = None
        self.selected_edge_id: str | None = None
        self.selected_layout_edge_ids: set[str] = set()
        self._layout_mode = tk.StringVar(value="select")
        self._pending_edge_from: str | None = None
        self._drag_node_id: str | None = None
        self._drag_started = False
        self._workspace_scroll_canvas: tk.Canvas | None = None
        self._correlations_scroll_canvas: tk.Canvas | None = None
        self._sweep_scroll_canvas: tk.Canvas | None = None
        self._formula_images: list[Any] = []
        self.results_stale = False
        self._focused_form: str | None = None
        self._is_committing_form = False
        self._suppress_stale_mark = False
        self.sweep_variables: dict[str, SweepVariable] = {}
        self.sweep_results: list[dict[str, Any]] = []
        self._sweep_checkbox_vars: dict[str, tk.BooleanVar] = {}
        self._selected_sweep_variable_id: str | None = None
        self._sweep_cancel_requested = False
        self._sweep_plot_canvas: Any = None
        self.batch_field_keys: set[str] = set()
        self._batch_checkbox_vars: dict[str, tk.BooleanVar] = {}
        self._last_batch_snapshot: tuple[list[dict[str, str]], list[dict[str, str]]] | None = None

        self.property_model = tk.StringVar(value="ideal_gas")
        self.overlay_metric = tk.StringVar(value="Technology")
        self.auto_calculate = tk.BooleanVar(value=False)
        self.sweep_objective_scope = tk.StringVar(value="Global")
        self.sweep_objective_node = tk.StringVar()
        self.sweep_objective_edge = tk.StringVar()
        self.sweep_objective_metric = tk.StringVar(value="total_dp")
        self.sweep_direction = tk.StringVar(value="Minimize")
        self.sweep_range_start = tk.StringVar()
        self.sweep_range_end = tk.StringVar()
        self.sweep_range_step = tk.StringVar()
        self.sweep_range_unit = tk.StringVar()
        self.sweep_plot_type = tk.StringVar(value="Auto")
        self.sweep_plot_x = tk.StringVar()
        self.sweep_plot_y = tk.StringVar()
        self.batch_target_mode = tk.StringVar(value="All edges")
        self.batch_target_technology = tk.StringVar(value=TECHNOLOGIES[0])
        self.batch_target_tag = tk.StringVar(value=TAG_OPTIONS[0])
        self._constraint_enabled = {
            key: tk.BooleanVar(value=False) for key in CONSTRAINT_SPECS
        }
        self._constraint_min = {
            key: tk.StringVar() for key in CONSTRAINT_SPECS
        }
        self._constraint_max = {
            key: tk.StringVar() for key in CONSTRAINT_SPECS
        }
        self._constraint_units = {
            key: tk.StringVar(value=UNIT_OPTIONS[group][0])
            for key, (_label, group) in CONSTRAINT_SPECS.items()
        }
        self._unit_vars = {
            key: tk.StringVar(value=_default_unit_for_key(key))
            for key in FIELD_UNIT_GROUPS
        }
        self._last_unit_values = {
            key: variable.get()
            for key, variable in self._unit_vars.items()
        }

        self._node_vars = {
            "node_id": tk.StringVar(),
            "kind": tk.StringVar(value="internal"),
            "inlet_mdot": tk.StringVar(),
            "inlet_temperature": tk.StringVar(),
            "inlet_pressure": tk.StringVar(),
        }
        self._edge_vars = {
            "edge_id": tk.StringVar(),
            "from_node": tk.StringVar(),
            "to_node": tk.StringVar(),
            "tag": tk.StringVar(value=TAG_OPTIONS[0]),
            "cooling_technology": tk.StringVar(value="smooth"),
            "shape": tk.StringVar(value="rectangular"),
            "length": tk.StringVar(),
            "width": tk.StringVar(),
            "height": tk.StringVar(),
            "diameter": tk.StringVar(),
            "wall_mode": tk.StringVar(value="adiabatic"),
            "wall_temperature": tk.StringVar(),
            "heat_flux": tk.StringVar(),
            "external_htc": tk.StringVar(),
            "external_temperature": tk.StringVar(),
            "wall_thickness": tk.StringVar(),
            "wall_conductivity": tk.StringVar(),
            "tbc_thickness": tk.StringVar(),
            "tbc_conductivity": tk.StringVar(),
            "flow_fraction": tk.StringVar(),
            "fixed_mdot": tk.StringVar(),
        }
        self._tech_param_vars = {
            key: tk.StringVar() for key in ALL_PARAM_KEYS
        }

        self._configure_style()
        self._build_widgets()
        self._install_form_traces()
        self._edge_vars["cooling_technology"].trace_add(
            "write", self._on_technology_change
        )
        self._edge_vars["shape"].trace_add("write", self._on_shape_change)
        self._edge_vars["wall_mode"].trace_add("write", self._on_wall_mode_change)
        self._node_vars["kind"].trace_add("write", self._on_node_kind_change)
        self.property_model.trace_add("write", self._on_property_model_change)
        self.overlay_metric.trace_add(
            "write", lambda *_args: self._redraw_layout_canvas()
        )
        self._load_network(build_default_network())
        self.calculate(show_success=False)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        default_font = ("Segoe UI", 11)
        title_font = ("Segoe UI", 21, "bold")
        heading_font = ("Segoe UI", 12, "bold")
        small_heading_font = ("Segoe UI", 11, "bold")

        style.configure(".", font=default_font, background=WINDOW_BG, foreground=TEXT_COLOR)
        style.configure("TFrame", background=WINDOW_BG)
        style.configure("Panel.TFrame", background=PANEL_BG)
        style.configure("Header.TFrame", background=PANEL_BG)
        style.configure("Toolbar.TFrame", background=PANEL_BG)
        style.configure("TLabel", background=WINDOW_BG, foreground=TEXT_COLOR)
        style.configure("Header.TLabel", background=PANEL_BG, foreground=TEXT_COLOR)
        style.configure(
            "Title.TLabel",
            background=PANEL_BG,
            foreground=TEXT_COLOR,
            font=title_font,
        )
        style.configure(
            "Subtitle.TLabel",
            background=PANEL_BG,
            foreground=MUTED_COLOR,
            font=("Segoe UI", 11),
        )
        style.configure(
            "Section.TLabel",
            background=PANEL_BG,
            foreground=TEXT_COLOR,
            font=heading_font,
        )
        style.configure(
            "SmallSection.TLabel",
            background=PANEL_BG,
            foreground=ACCENT_COLOR,
            font=small_heading_font,
        )
        style.configure("TLabelframe", background=WINDOW_BG, foreground=TEXT_COLOR)
        style.configure(
            "TLabelframe.Label",
            background=WINDOW_BG,
            foreground=TEXT_COLOR,
            font=small_heading_font,
        )
        style.configure("TNotebook", background=WINDOW_BG, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            padding=(16, 9),
            font=("Segoe UI", 11, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", PANEL_BG)],
            foreground=[("selected", ACCENT_COLOR)],
        )
        style.configure(
            "Accent.TButton",
            background=ACCENT_COLOR,
            foreground="#ffffff",
            padding=(13, 8),
            font=("Segoe UI", 11, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#17629a"), ("pressed", "#14557f")],
            foreground=[("active", "#ffffff"), ("pressed", "#ffffff")],
        )
        style.configure("TButton", padding=(11, 7), font=("Segoe UI", 11))
        style.configure(
            "Treeview",
            background=PANEL_BG,
            fieldbackground=PANEL_BG,
            foreground=TEXT_COLOR,
            rowheight=32,
            borderwidth=0,
            font=("Segoe UI", 11),
        )
        style.configure(
            "Treeview.Heading",
            background="#edf3f8",
            foreground=TEXT_COLOR,
            font=("Segoe UI", 11, "bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", "#b9dcff")],
            foreground=[("selected", "#111827")],
        )

    def _build_widgets(self) -> None:
        header = tk.Frame(
            self,
            bg=PANEL_BG,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        header.pack(fill=tk.X, padx=12, pady=(12, 8))
        title_block = ttk.Frame(header, style="Header.TFrame", padding=(16, 12))
        title_block.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            title_block,
            text="Turbine Internal Passage 1D Solver",
            style="Title.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            title_block,
            text=(
                "Steady 1D heat-transfer and pressure-drop network solver "
                "for gas-turbine internal cooling passages"
            ),
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(4, 0))

        toolbar = ttk.Frame(header, style="Toolbar.TFrame", padding=(10, 12))
        toolbar.pack(side=tk.RIGHT)

        ttk.Button(toolbar, text="Load Example", command=self.load_example).pack(
            side=tk.LEFT
        )
        ttk.Button(
            toolbar,
            text="Calculate",
            command=self.calculate,
            style="Accent.TButton",
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(
            toolbar,
            text="Auto calculate",
            variable=self.auto_calculate,
        ).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Label(toolbar, text="Property model", style="Header.TLabel").pack(
            side=tk.LEFT, padx=(16, 4)
        )
        property_combo = ttk.Combobox(
            toolbar,
            textvariable=self.property_model,
            values=PROPERTY_MODELS,
            state="readonly",
            width=12,
        )
        property_combo.pack(side=tk.LEFT)
        self._bind_combobox_mousewheel(property_combo)
        ttk.Button(toolbar, text="Export CSV", command=self.export_results).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        self.workspace_tab = ttk.Frame(self.notebook)
        self.sweep_tab = ttk.Frame(self.notebook)
        self.correlations_tab = ttk.Frame(self.notebook)
        self.results_tab = ttk.Frame(self.notebook)
        self.warnings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.workspace_tab, text="Workspace")
        self.notebook.add(self.sweep_tab, text="Parametric Sweep")
        self.notebook.add(self.correlations_tab, text="Correlations")
        self.notebook.add(self.results_tab, text="Results")
        self.notebook.add(self.warnings_tab, text="Warnings")

        self._build_workspace_tab()
        self._build_sweep_tab()
        self._build_correlations_tab()
        self._build_results_tab()
        self._build_warnings_tab()

    def _build_workspace_tab(self) -> None:
        main = ttk.PanedWindow(self.workspace_tab, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        left = ttk.Frame(main)
        right_container = ttk.Frame(main)
        main.add(left, weight=5)
        main.add(right_container, weight=3)

        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        canvas_toolbar = self._panel(left)
        canvas_toolbar.grid(row=0, column=0, sticky=tk.EW, pady=(0, 8))
        ttk.Label(
            canvas_toolbar,
            text="Passage Layout & Network Editor",
            style="Section.TLabel",
        ).pack(side=tk.LEFT, padx=(0, 14))
        ttk.Button(
            canvas_toolbar,
            text="Load Image",
            command=self.load_layout_image,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            canvas_toolbar,
            text="Select / Move",
            command=self.set_select_mode,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            canvas_toolbar,
            text="Add Node",
            command=self.set_add_node_mode,
            style="Accent.TButton",
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            canvas_toolbar,
            text="Connect Nodes",
            command=self.set_connect_edge_mode,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            canvas_toolbar,
            text="Reset Positions",
            command=self.reset_layout_positions,
        ).pack(side=tk.LEFT)
        ttk.Label(canvas_toolbar, text="Overlay", style="Header.TLabel").pack(
            side=tk.LEFT,
            padx=(12, 4),
        )
        overlay_combo = ttk.Combobox(
            canvas_toolbar,
            textvariable=self.overlay_metric,
            values=OVERLAY_METRICS,
            state="readonly",
            width=18,
        )
        overlay_combo.pack(side=tk.LEFT)
        self._bind_combobox_mousewheel(overlay_combo)
        self.layout_status_label = ttk.Label(
            canvas_toolbar,
            text="Mode: Select / Move",
            style="Header.TLabel",
        )
        self.layout_status_label.pack(side=tk.RIGHT)

        canvas_panel = self._panel(left)
        canvas_panel.grid(row=1, column=0, sticky=tk.NSEW)
        canvas_panel.rowconfigure(0, weight=1)
        canvas_panel.columnconfigure(0, weight=1)
        self.layout_canvas = tk.Canvas(
            canvas_panel,
            bg="#eef3f8",
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
        )
        self.layout_canvas.grid(row=0, column=0, sticky=tk.NSEW)
        self.layout_canvas.bind(
            "<Configure>",
            lambda _event: self._redraw_layout_canvas(),
        )
        self.layout_canvas.bind("<ButtonPress-1>", self._on_layout_press)
        self.layout_canvas.bind("<B1-Motion>", self._on_layout_drag)
        self.layout_canvas.bind("<ButtonRelease-1>", self._on_layout_release)

        right_canvas = tk.Canvas(
            right_container,
            highlightthickness=0,
            bg=WINDOW_BG,
        )
        right_scroll = ttk.Scrollbar(
            right_container,
            orient=tk.VERTICAL,
            command=right_canvas.yview,
        )
        right_canvas.configure(yscrollcommand=right_scroll.set)
        right_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        right_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right = ttk.Frame(right_canvas, padding=(0, 0, 8, 0))
        right_window = right_canvas.create_window((0, 0), window=right, anchor=tk.NW)

        def resize_scroll_region(_event: tk.Event) -> None:
            right_canvas.configure(scrollregion=right_canvas.bbox(tk.ALL))

        def resize_form_width(event: tk.Event) -> None:
            right_canvas.itemconfigure(right_window, width=event.width)

        right.bind("<Configure>", resize_scroll_region)
        right_canvas.bind("<Configure>", resize_form_width)
        self._workspace_scroll_canvas = right_canvas
        self.bind_all("<MouseWheel>", self._on_workspace_mousewheel, add="+")

        self._build_workspace_summary(right)
        self._build_workspace_node_editor(right)
        self._build_workspace_edge_editor(right)
        self._build_batch_apply_panel(right)
        self._build_selected_result_panel(right)
        self._build_workspace_tables(right)

    def _build_sweep_tab(self) -> None:
        top = ttk.PanedWindow(self.sweep_tab, orient=tk.HORIZONTAL)
        top.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        controls = ttk.Frame(top)
        results = ttk.Frame(top)
        top.add(controls, weight=2)
        top.add(results, weight=3)

        objective_panel = self._panel(controls)
        objective_panel.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(objective_panel, text="Objective", style="Section.TLabel").grid(
            row=0, column=0, columnspan=4, sticky=tk.W, pady=(0, 8)
        )
        self._sweep_combo(
            objective_panel,
            1,
            "Scope",
            self.sweep_objective_scope,
            SWEEP_OBJECTIVE_SCOPES,
        )
        self._sweep_combo(
            objective_panel,
            2,
            "Node",
            self.sweep_objective_node,
            (),
        )
        self.sweep_objective_node_combo = objective_panel.grid_slaves(row=2, column=1)[0]
        self._sweep_combo(
            objective_panel,
            3,
            "Edge",
            self.sweep_objective_edge,
            (),
        )
        self.sweep_objective_edge_combo = objective_panel.grid_slaves(row=3, column=1)[0]
        self._sweep_combo(
            objective_panel,
            4,
            "Metric",
            self.sweep_objective_metric,
            GLOBAL_OBJECTIVE_METRICS,
        )
        self.sweep_objective_metric_combo = objective_panel.grid_slaves(row=4, column=1)[0]
        self._sweep_combo(
            objective_panel,
            5,
            "Direction",
            self.sweep_direction,
            SWEEP_DIRECTIONS,
        )
        objective_panel.columnconfigure(1, weight=1)
        self.sweep_objective_scope.trace_add(
            "write",
            lambda *_args: self._update_sweep_objective_controls(),
        )
        self.sweep_objective_edge.trace_add(
            "write",
            lambda *_args: self._update_sweep_objective_controls(preserve_metric=True),
        )

        constraint_panel = self._panel(controls)
        constraint_panel.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(
            constraint_panel,
            text="Constraints",
            style="Section.TLabel",
        ).grid(row=0, column=0, columnspan=5, sticky=tk.W, pady=(0, 8))
        ttk.Label(constraint_panel, text="Use", style="Header.TLabel").grid(
            row=1, column=0, sticky=tk.W
        )
        ttk.Label(constraint_panel, text="Metric", style="Header.TLabel").grid(
            row=1, column=1, sticky=tk.W
        )
        ttk.Label(constraint_panel, text="Min", style="Header.TLabel").grid(
            row=1, column=2, sticky=tk.W
        )
        ttk.Label(constraint_panel, text="Max", style="Header.TLabel").grid(
            row=1, column=3, sticky=tk.W
        )
        ttk.Label(constraint_panel, text="Unit", style="Header.TLabel").grid(
            row=1, column=4, sticky=tk.W
        )
        for row_index, (key, (label, unit_group)) in enumerate(CONSTRAINT_SPECS.items(), start=2):
            ttk.Checkbutton(
                constraint_panel,
                variable=self._constraint_enabled[key],
            ).grid(row=row_index, column=0, sticky=tk.W, pady=2)
            ttk.Label(constraint_panel, text=label).grid(
                row=row_index, column=1, sticky=tk.W, pady=2, padx=(4, 10)
            )
            ttk.Entry(
                constraint_panel,
                textvariable=self._constraint_min[key],
                width=12,
            ).grid(row=row_index, column=2, sticky=tk.EW, pady=2, padx=(0, 6))
            ttk.Entry(
                constraint_panel,
                textvariable=self._constraint_max[key],
                width=12,
            ).grid(row=row_index, column=3, sticky=tk.EW, pady=2, padx=(0, 6))
            unit_combo = ttk.Combobox(
                constraint_panel,
                textvariable=self._constraint_units[key],
                values=UNIT_OPTIONS[unit_group],
                state="readonly",
                width=12,
            )
            unit_combo.grid(row=row_index, column=4, sticky=tk.EW, pady=2)
            self._bind_combobox_mousewheel(unit_combo)
        constraint_panel.columnconfigure(2, weight=1)
        constraint_panel.columnconfigure(3, weight=1)

        variable_panel = self._panel(controls)
        variable_panel.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        ttk.Label(
            variable_panel,
            text="Sweep Variables",
            style="Section.TLabel",
        ).pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(
            variable_panel,
            text="Check numeric inputs in Workspace. Total case count is shown below.",
            style="Header.TLabel",
        ).pack(anchor=tk.W, pady=(0, 6))
        variable_columns = ("label", "current", "start", "end", "step", "unit")
        self.sweep_variable_tree = ttk.Treeview(
            variable_panel,
            columns=variable_columns,
            show="headings",
            height=7,
        )
        variable_headings = {
            "label": "Variable",
            "current": "Current",
            "start": "Start",
            "end": "End",
            "step": "Step",
            "unit": "Unit",
        }
        variable_widths = {
            "label": 230,
            "current": 80,
            "start": 80,
            "end": 80,
            "step": 80,
            "unit": 70,
        }
        for column in variable_columns:
            self.sweep_variable_tree.heading(column, text=variable_headings[column])
            self.sweep_variable_tree.column(column, width=variable_widths[column], anchor=tk.W)
        self.sweep_variable_tree.pack(fill=tk.X)
        self.sweep_variable_tree.bind(
            "<<TreeviewSelect>>",
            self._on_sweep_variable_select,
        )

        range_frame = ttk.Frame(variable_panel, style="Panel.TFrame")
        range_frame.pack(fill=tk.X, pady=(8, 0))
        self.sweep_selected_variable_label = ttk.Label(
            range_frame,
            text="Select a sweep variable to edit its range.",
            style="Header.TLabel",
        )
        self.sweep_selected_variable_label.grid(
            row=0,
            column=0,
            columnspan=6,
            sticky=tk.W,
            pady=(0, 4),
        )
        for column, label in enumerate(("Start", "End", "Step", "Unit")):
            ttk.Label(range_frame, text=label, style="Header.TLabel").grid(
                row=1,
                column=column,
                sticky=tk.W,
            )
        ttk.Entry(range_frame, textvariable=self.sweep_range_start, width=12).grid(
            row=2,
            column=0,
            sticky=tk.EW,
            padx=(0, 6),
        )
        ttk.Entry(range_frame, textvariable=self.sweep_range_end, width=12).grid(
            row=2,
            column=1,
            sticky=tk.EW,
            padx=(0, 6),
        )
        ttk.Entry(range_frame, textvariable=self.sweep_range_step, width=12).grid(
            row=2,
            column=2,
            sticky=tk.EW,
            padx=(0, 6),
        )
        self.sweep_range_unit_combo = ttk.Combobox(
            range_frame,
            textvariable=self.sweep_range_unit,
            values=(),
            state="readonly",
            width=12,
        )
        self.sweep_range_unit_combo.grid(row=2, column=3, sticky=tk.EW, padx=(0, 6))
        self._bind_combobox_mousewheel(self.sweep_range_unit_combo)
        ttk.Button(
            range_frame,
            text="Apply Range",
            command=self._apply_sweep_range,
        ).grid(row=2, column=4, sticky=tk.EW, padx=(0, 6))
        ttk.Button(
            range_frame,
            text="Remove",
            command=self._remove_selected_sweep_variable,
        ).grid(row=2, column=5, sticky=tk.EW)
        for column in range(4):
            range_frame.columnconfigure(column, weight=1)
        self.sweep_case_count_label = ttk.Label(
            variable_panel,
            text="Total cases: 0",
            style="Header.TLabel",
        )
        self.sweep_case_count_label.pack(anchor=tk.W, pady=(8, 0))

        run_panel = self._panel(controls)
        run_panel.pack(fill=tk.X)
        ttk.Button(
            run_panel,
            text="Run Sweep",
            command=self.run_sweep,
            style="Accent.TButton",
        ).pack(side=tk.LEFT)
        ttk.Button(
            run_panel,
            text="Stop",
            command=self.stop_sweep,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            run_panel,
            text="Clear Variables",
            command=self._clear_sweep_variables,
        ).pack(side=tk.LEFT, padx=(8, 0))
        self.sweep_progress = ttk.Progressbar(run_panel, mode="determinate")
        self.sweep_progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 8))
        self.sweep_status_label = ttk.Label(
            run_panel,
            text="Ready",
            style="Header.TLabel",
        )
        self.sweep_status_label.pack(side=tk.RIGHT)

        best_panel = self._panel(results)
        best_panel.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(best_panel, text="Best Case", style="Section.TLabel").pack(
            anchor=tk.W,
            pady=(0, 8),
        )
        self.sweep_best_tree = ttk.Treeview(
            best_panel,
            columns=("item", "value"),
            show="headings",
            height=7,
        )
        self.sweep_best_tree.heading("item", text="Item")
        self.sweep_best_tree.heading("value", text="Value")
        self.sweep_best_tree.column("item", width=180, anchor=tk.W)
        self.sweep_best_tree.column("value", width=260, anchor=tk.W)
        self.sweep_best_tree.pack(fill=tk.X)

        table_panel = self._panel(results)
        table_panel.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        ttk.Label(table_panel, text="Sweep Results", style="Section.TLabel").pack(
            anchor=tk.W,
            pady=(0, 8),
        )
        result_frame = ttk.Frame(table_panel, style="Panel.TFrame")
        result_frame.pack(fill=tk.BOTH, expand=True)
        self.sweep_result_tree = ttk.Treeview(result_frame, show="headings", height=10)
        self.sweep_result_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        result_scroll = ttk.Scrollbar(
            result_frame,
            orient=tk.VERTICAL,
            command=self.sweep_result_tree.yview,
        )
        self.sweep_result_tree.configure(yscrollcommand=result_scroll.set)
        result_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        plot_panel = self._panel(results)
        plot_panel.pack(fill=tk.BOTH, expand=True)
        plot_toolbar = ttk.Frame(plot_panel, style="Panel.TFrame")
        plot_toolbar.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(plot_toolbar, text="Plot", style="Section.TLabel").pack(
            side=tk.LEFT,
            padx=(0, 12),
        )
        ttk.Label(plot_toolbar, text="Type", style="Header.TLabel").pack(side=tk.LEFT)
        plot_type_combo = ttk.Combobox(
            plot_toolbar,
            textvariable=self.sweep_plot_type,
            values=("Auto", "Line", "Heatmap", "Surface", "Scatter"),
            state="readonly",
            width=10,
        )
        plot_type_combo.pack(side=tk.LEFT, padx=(4, 10))
        self._bind_combobox_mousewheel(plot_type_combo)
        ttk.Label(plot_toolbar, text="X", style="Header.TLabel").pack(side=tk.LEFT)
        self.sweep_plot_x_combo = ttk.Combobox(
            plot_toolbar,
            textvariable=self.sweep_plot_x,
            values=(),
            state="readonly",
            width=22,
        )
        self.sweep_plot_x_combo.pack(side=tk.LEFT, padx=(4, 10))
        self._bind_combobox_mousewheel(self.sweep_plot_x_combo)
        ttk.Label(plot_toolbar, text="Y", style="Header.TLabel").pack(side=tk.LEFT)
        self.sweep_plot_y_combo = ttk.Combobox(
            plot_toolbar,
            textvariable=self.sweep_plot_y,
            values=(),
            state="readonly",
            width=22,
        )
        self.sweep_plot_y_combo.pack(side=tk.LEFT, padx=(4, 10))
        self._bind_combobox_mousewheel(self.sweep_plot_y_combo)
        ttk.Button(
            plot_toolbar,
            text="Update Plot",
            command=self._update_sweep_plot,
        ).pack(side=tk.LEFT)
        self.sweep_plot_frame = ttk.Frame(plot_panel, style="Panel.TFrame")
        self.sweep_plot_frame.pack(fill=tk.BOTH, expand=True)
        self._set_sweep_best_rows([("Status", "Run a sweep to view the best case.")])
        self._set_sweep_result_columns([])
        self._update_sweep_objective_controls()

    def _build_workspace_summary(self, parent: ttk.Frame) -> None:
        summary_panel = self._panel(parent)
        summary_panel.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(
            summary_panel,
            text="Design Summary",
            style="Section.TLabel",
        ).pack(anchor=tk.W, pady=(0, 8))
        self.dashboard_summary_frame = ttk.Frame(summary_panel, style="Panel.TFrame")
        self.dashboard_summary_frame.pack(fill=tk.X)
        self._summary_labels = {}
        for label, key in (
            ("Nodes", "nodes"),
            ("Edges", "edges"),
            ("Inlets", "inlets"),
            ("Total inlet flow", "flow"),
            ("Property model", "property_model"),
        ):
            self._summary_row(self.dashboard_summary_frame, label, key)

        self.metric_cards_frame = ttk.Frame(summary_panel, style="Panel.TFrame")
        self.metric_cards_frame.pack(fill=tk.X, pady=(10, 0))
        self.metric_labels = {}
        for title, key in (
            ("Outlet pressure", "outlet_pressure"),
            ("Outlet temperature", "outlet_temperature"),
            ("Total pressure drop", "total_dp"),
            ("Total heat transfer", "total_heat"),
            ("Max HTC", "max_htc"),
            ("Warnings", "warnings"),
        ):
            self._metric_card(self.metric_cards_frame, title, key)
        self.dashboard_status_label = tk.Label(
            summary_panel,
            text="READY",
            bg="#e7f3ec",
            fg=SAFE_COLOR,
            font=("Segoe UI", 14, "bold"),
            padx=12,
            pady=8,
        )
        self.dashboard_status_label.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(
            summary_panel,
            text="Warnings Preview",
            style="SmallSection.TLabel",
        ).pack(anchor=tk.W, pady=(10, 4))
        self.dashboard_warning_text = tk.Text(
            summary_panel,
            height=5,
            wrap=tk.WORD,
            bg="#fbfcfe",
            fg=TEXT_COLOR,
            font=("Segoe UI", 11),
            relief=tk.FLAT,
            padx=8,
            pady=8,
        )
        self.dashboard_warning_text.pack(fill=tk.X)

    def _build_workspace_node_editor(self, parent: ttk.Frame) -> None:
        node_panel = self._panel(parent)
        node_panel.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(node_panel, text="Selected Node", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8)
        )
        self._labeled_entry(
            node_panel,
            1,
            "Node ID",
            self._node_vars["node_id"],
            form="node",
        )
        ttk.Label(node_panel, text="Kind", style="Header.TLabel").grid(
            row=2, column=0, sticky=tk.W, pady=3
        )
        node_kind_combo = ttk.Combobox(
            node_panel,
            textvariable=self._node_vars["kind"],
            values=NODE_KINDS,
            state="readonly",
            width=20,
        )
        node_kind_combo.grid(row=2, column=1, sticky=tk.EW, pady=3)
        self._bind_combobox_mousewheel(node_kind_combo)
        self.node_inlet_fields = []
        self.node_inlet_fields.append(self._labeled_entry(
            node_panel,
            3,
            "Inlet m_dot",
            self._node_vars["inlet_mdot"],
            form="node",
            unit_key="inlet_mdot",
            sweep_key="inlet_mdot",
        ))
        self.node_inlet_fields.append(self._labeled_entry(
            node_panel,
            4,
            "Inlet temperature",
            self._node_vars["inlet_temperature"],
            form="node",
            unit_key="inlet_temperature",
            sweep_key="inlet_temperature",
        ))
        self.node_inlet_fields.append(self._labeled_entry(
            node_panel,
            5,
            "Inlet pressure",
            self._node_vars["inlet_pressure"],
            form="node",
            unit_key="inlet_pressure",
            sweep_key="inlet_pressure",
        ))
        node_panel.columnconfigure(1, weight=1)

        buttons = ttk.Frame(node_panel, style="Panel.TFrame")
        buttons.grid(row=6, column=0, columnspan=2, sticky=tk.EW, pady=(10, 0))
        ttk.Button(buttons, text="Add Node", command=self.add_node).pack(
            side=tk.LEFT
        )
        ttk.Button(buttons, text="Delete Node", command=self.delete_node).pack(
            side=tk.LEFT, padx=6
        )

    def _build_workspace_edge_editor(self, parent: ttk.Frame) -> None:
        edge_panel = self._panel(parent)
        edge_panel.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(edge_panel, text="Selected Edge", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8)
        )
        row = 1
        self._labeled_entry(
            edge_panel,
            row,
            "Edge ID",
            self._edge_vars["edge_id"],
            form="edge",
        )
        row += 1
        self._labeled_combo(
            edge_panel,
            row,
            "From node",
            self._edge_vars["from_node"],
            (),
            form="edge",
        )
        self.edge_from_combo = edge_panel.grid_slaves(row=row, column=1)[0]
        row += 1
        self._labeled_combo(
            edge_panel,
            row,
            "To node",
            self._edge_vars["to_node"],
            (),
            form="edge",
        )
        self.edge_to_combo = edge_panel.grid_slaves(row=row, column=1)[0]
        row += 1
        self._labeled_combo(
            edge_panel,
            row,
            "Tag",
            self._edge_vars["tag"],
            TAG_OPTIONS,
            form="edge",
            batch_key="tag",
        )
        row += 1
        self._labeled_combo(
            edge_panel,
            row,
            "Technology",
            self._edge_vars["cooling_technology"],
            TECHNOLOGIES,
            form="edge",
            batch_key="cooling_technology",
        )
        row += 1
        self._labeled_combo(
            edge_panel,
            row,
            "Shape",
            self._edge_vars["shape"],
            SHAPES,
            form="edge",
            batch_key="shape",
        )
        row += 1
        self.edge_geometry_fields = {}
        for label, key in (
            ("Length", "length"),
            ("Width", "width"),
            ("Height", "height"),
            ("Diameter", "diameter"),
        ):
            self.edge_geometry_fields[key] = self._labeled_entry(
                edge_panel,
                row,
                label,
                self._edge_vars[key],
                form="edge",
                unit_key=key,
                sweep_key=key,
                batch_key=key,
            )
            row += 1
        self._labeled_combo(
            edge_panel,
            row,
            "Wall mode",
            self._edge_vars["wall_mode"],
            WALL_MODES,
            form="edge",
            batch_key="wall_mode",
        )
        row += 1
        self.edge_wall_fields = {}
        for label, key in (
            ("Wall T", "wall_temperature"),
            ("Heat flux", "heat_flux"),
            ("External gas T", "external_temperature"),
            ("External h", "external_htc"),
            ("Blade wall thickness", "wall_thickness"),
            ("Blade wall k", "wall_conductivity"),
            ("TBC thickness", "tbc_thickness"),
            ("TBC k", "tbc_conductivity"),
        ):
            self.edge_wall_fields[key] = self._labeled_entry(
                edge_panel,
                row,
                label,
                self._edge_vars[key],
                form="edge",
                unit_key=key,
                sweep_key=key,
                batch_key=key,
            )
            row += 1

        self.tech_param_frame = ttk.LabelFrame(
            edge_panel,
            text="Cooling technology parameters",
            padding=8,
        )
        self.tech_param_frame.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky=tk.EW,
            pady=(8, 4),
        )
        row += 1

        self.params_text = tk.Text(edge_panel, height=1, width=1, wrap=tk.NONE)
        row += 1
        edge_panel.columnconfigure(1, weight=1)
        self._render_tech_params("smooth")
        self._update_shape_visibility()
        self._update_wall_field_visibility()

        buttons = ttk.Frame(edge_panel, style="Panel.TFrame")
        buttons.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(10, 0))
        ttk.Button(buttons, text="Add Edge", command=self.add_edge).pack(
            side=tk.LEFT
        )
        ttk.Button(buttons, text="Delete Edge", command=self.delete_edge).pack(
            side=tk.LEFT, padx=6
        )

    def _build_batch_apply_panel(self, parent: ttk.Frame) -> None:
        batch_panel = self._panel(parent)
        self.batch_panel = batch_panel
        batch_panel.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(batch_panel, text="Batch Apply", style="Section.TLabel").grid(
            row=0,
            column=0,
            columnspan=3,
            sticky=tk.W,
            pady=(0, 8),
        )
        ttk.Label(
            batch_panel,
            text="Ctrl+click edges on the layout to build a batch selection.",
            style="Header.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(0, 6))

        self._labeled_combo(
            batch_panel,
            2,
            "Target",
            self.batch_target_mode,
            BATCH_TARGET_MODES,
        )
        self._labeled_combo(
            batch_panel,
            3,
            "Technology",
            self.batch_target_technology,
            TECHNOLOGIES,
        )
        self.batch_target_technology_widgets = batch_panel.grid_slaves(row=3)
        self._labeled_combo(
            batch_panel,
            4,
            "Tag",
            self.batch_target_tag,
            TAG_OPTIONS,
        )
        self.batch_target_tag_widgets = batch_panel.grid_slaves(row=4)
        ttk.Label(
            batch_panel,
            text="Checked fields",
            style="Header.TLabel",
        ).grid(row=5, column=0, sticky=tk.NW, pady=(8, 3))
        self.batch_field_tree = ttk.Treeview(
            batch_panel,
            columns=("field",),
            show="headings",
            height=4,
        )
        self.batch_field_tree.heading("field", text="Variable")
        self.batch_field_tree.column("field", width=260, anchor=tk.W)
        self.batch_field_tree.grid(
            row=5,
            column=1,
            columnspan=2,
            sticky=tk.EW,
            pady=(8, 3),
        )
        buttons = ttk.Frame(batch_panel, style="Panel.TFrame")
        buttons.grid(row=6, column=0, columnspan=3, sticky=tk.EW, pady=(10, 0))
        ttk.Button(
            buttons,
            text="Apply Batch",
            command=self.apply_batch_edit,
            style="Accent.TButton",
        ).pack(side=tk.LEFT)
        ttk.Button(
            buttons,
            text="Undo Batch",
            command=self.undo_batch_edit,
        ).pack(side=tk.LEFT, padx=(8, 0))
        self.batch_status_label = ttk.Label(
            batch_panel,
            text="Target edges: 0",
            style="Header.TLabel",
        )
        self.batch_status_label.grid(
            row=7,
            column=0,
            columnspan=3,
            sticky=tk.W,
            pady=(8, 0),
        )
        batch_panel.columnconfigure(1, weight=1)
        self.batch_target_mode.trace_add(
            "write",
            lambda *_args: self._update_batch_target_visibility(),
        )
        self.batch_target_technology.trace_add(
            "write",
            lambda *_args: self._update_batch_status(),
        )
        self.batch_target_tag.trace_add(
            "write",
            lambda *_args: self._update_batch_status(),
        )
        self._update_batch_target_visibility()
        self._refresh_batch_field_tree()

    def _build_selected_result_panel(self, parent: ttk.Frame) -> None:
        result_panel = self._panel(parent)
        result_panel.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(
            result_panel,
            text="Selected Edge Result",
            style="Section.TLabel",
        ).pack(anchor=tk.W, pady=(0, 8))
        self.selected_result_tree = ttk.Treeview(
            result_panel,
            columns=("item", "value"),
            show="headings",
            height=10,
        )
        self.selected_result_tree.heading("item", text="Item")
        self.selected_result_tree.heading("value", text="Value")
        self.selected_result_tree.column("item", width=170, anchor=tk.W)
        self.selected_result_tree.column("value", width=270, anchor=tk.W)
        self.selected_result_tree.tag_configure(
            "stale",
            background="#fff4df",
            foreground=WARNING_COLOR,
        )
        self.selected_result_tree.pack(fill=tk.X)
        self.wall_stack_canvas = tk.Canvas(
            result_panel,
            height=150,
            bg="#fbfcfe",
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
        )
        self.wall_stack_canvas.pack(fill=tk.X, pady=(8, 0))
        self._update_selected_result_panel()

    def _build_workspace_tables(self, parent: ttk.Frame) -> None:
        table_panel = self._panel(parent)
        table_panel.pack(fill=tk.BOTH, expand=True)
        ttk.Label(table_panel, text="Network Tables", style="Section.TLabel").pack(
            anchor=tk.W,
            pady=(0, 8),
        )

        ttk.Label(table_panel, text="Nodes", style="SmallSection.TLabel").pack(
            anchor=tk.W,
            pady=(0, 4),
        )
        node_columns = ("node_id", "kind", "mdot", "temperature", "pressure")
        self.node_tree = ttk.Treeview(
            table_panel,
            columns=node_columns,
            show="headings",
            height=5,
        )
        node_headings = {
            "node_id": "Node",
            "kind": "Kind",
            "mdot": "m_dot [kg/s]",
            "temperature": "T [K]",
            "pressure": "P [Pa]",
        }
        for column in node_columns:
            self.node_tree.heading(column, text=node_headings[column])
            self.node_tree.column(column, width=72, anchor=tk.W)
        self.node_tree.pack(fill=tk.X)
        self.node_tree.bind("<<TreeviewSelect>>", self._on_node_select)

        ttk.Label(table_panel, text="Edges", style="SmallSection.TLabel").pack(
            anchor=tk.W,
            pady=(10, 4),
        )
        edge_columns = ("edge_id", "route", "tech", "tag", "length")
        self.edge_tree = ttk.Treeview(
            table_panel,
            columns=edge_columns,
            show="headings",
            height=7,
        )
        edge_headings = {
            "edge_id": "Edge",
            "route": "Route",
            "tech": "Tech",
            "tag": "Tag",
            "length": "L [m]",
        }
        for column in edge_columns:
            self.edge_tree.heading(column, text=edge_headings[column])
            self.edge_tree.column(column, width=88, anchor=tk.W)
        self.edge_tree.pack(fill=tk.X)
        self.edge_tree.bind("<<TreeviewSelect>>", self._on_edge_select)

    def _build_dashboard_tab(self) -> None:
        main = ttk.Frame(self.dashboard_tab, padding=4)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(0, weight=2)
        main.columnconfigure(1, weight=2)
        main.columnconfigure(2, weight=4)
        main.rowconfigure(0, weight=1)

        overview_panel = self._panel(main)
        overview_panel.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 6), pady=4)
        results_panel = self._panel(main)
        results_panel.grid(row=0, column=1, sticky=tk.NSEW, padx=6, pady=4)
        detail_panel = self._panel(main)
        detail_panel.grid(row=0, column=2, sticky=tk.NSEW, padx=(6, 0), pady=4)

        ttk.Label(
            overview_panel,
            text="1. Design Parameters",
            style="Section.TLabel",
        ).pack(anchor=tk.W, pady=(0, 8))
        self.dashboard_summary_frame = ttk.Frame(overview_panel, style="Panel.TFrame")
        self.dashboard_summary_frame.pack(fill=tk.X)
        self._summary_labels: dict[str, ttk.Label] = {}
        for label, key in (
            ("Nodes", "nodes"),
            ("Edges", "edges"),
            ("Inlets", "inlets"),
            ("Total inlet flow", "flow"),
            ("Property model", "property_model"),
        ):
            self._summary_row(self.dashboard_summary_frame, label, key)

        ttk.Label(
            overview_panel,
            text="Passage Map",
            style="SmallSection.TLabel",
        ).pack(anchor=tk.W, pady=(18, 6))
        map_columns = ("edge", "route", "technology")
        self.dashboard_map_tree = ttk.Treeview(
            overview_panel, columns=map_columns, show="headings", height=12
        )
        map_headings = {
            "edge": "Edge",
            "route": "Route",
            "technology": "Technology",
        }
        for column in map_columns:
            self.dashboard_map_tree.heading(column, text=map_headings[column])
            self.dashboard_map_tree.column(column, width=105, anchor=tk.W)
        self.dashboard_map_tree.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            results_panel,
            text="2. Real-time Simulation Results",
            style="Section.TLabel",
        ).pack(anchor=tk.W, pady=(0, 8))
        self.metric_cards_frame = ttk.Frame(results_panel, style="Panel.TFrame")
        self.metric_cards_frame.pack(fill=tk.X)
        self.metric_labels: dict[str, ttk.Label] = {}
        for title, key in (
            ("Outlet pressure", "outlet_pressure"),
            ("Outlet temperature", "outlet_temperature"),
            ("Total pressure drop", "total_dp"),
            ("Total heat transfer", "total_heat"),
            ("Max HTC", "max_htc"),
            ("Warnings", "warnings"),
        ):
            self._metric_card(self.metric_cards_frame, title, key)

        self.dashboard_status_label = tk.Label(
            results_panel,
            text="READY",
            bg="#e7f3ec",
            fg=SAFE_COLOR,
            font=("Segoe UI", 14, "bold"),
            padx=12,
            pady=8,
        )
        self.dashboard_status_label.pack(fill=tk.X, pady=(16, 8))
        ttk.Button(
            results_panel,
            text="Calculate",
            command=self.calculate,
            style="Accent.TButton",
        ).pack(fill=tk.X)

        ttk.Label(
            detail_panel,
            text="3. Edge Result Table",
            style="Section.TLabel",
        ).pack(anchor=tk.W, pady=(0, 8))
        dash_edge_columns = (
            "edge",
            "tech",
            "re",
            "nu",
            "h",
            "dp",
            "tout",
            "pout",
        )
        self.dashboard_edge_tree = ttk.Treeview(
            detail_panel, columns=dash_edge_columns, show="headings"
        )
        dash_headings = {
            "edge": "Edge",
            "tech": "Tech",
            "re": "Re",
            "nu": "Nu",
            "h": "h",
            "dp": "dp",
            "tout": "Tout",
            "pout": "Pout",
        }
        dash_widths = {
            "edge": 130,
            "tech": 80,
            "re": 80,
            "nu": 70,
            "h": 90,
            "dp": 90,
            "tout": 80,
            "pout": 90,
        }
        for column in dash_edge_columns:
            self.dashboard_edge_tree.heading(column, text=dash_headings[column])
            self.dashboard_edge_tree.column(
                column, width=dash_widths[column], anchor=tk.W
            )
        self.dashboard_edge_tree.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            detail_panel,
            text="Verification Warnings",
            style="SmallSection.TLabel",
        ).pack(anchor=tk.W, pady=(14, 6))
        self.dashboard_warning_text = tk.Text(
            detail_panel,
            height=7,
            wrap=tk.WORD,
            bg="#fbfcfe",
            fg=TEXT_COLOR,
            font=("Segoe UI", 11),
            relief=tk.FLAT,
            padx=8,
            pady=8,
        )
        self.dashboard_warning_text.pack(fill=tk.X)
        self._show_dashboard_empty()

    def _panel(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=PANEL_BG,
            padx=14,
            pady=14,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )

    def _on_workspace_mousewheel(self, event: tk.Event) -> None:
        canvas = self._workspace_scroll_canvas
        if canvas is None:
            return
        if str(self.notebook.select()) != str(self.workspace_tab):
            return
        pointer_x = canvas.winfo_pointerx()
        pointer_y = canvas.winfo_pointery()
        left = canvas.winfo_rootx()
        top = canvas.winfo_rooty()
        right = left + canvas.winfo_width()
        bottom = top + canvas.winfo_height()
        if not (left <= pointer_x <= right and top <= pointer_y <= bottom):
            return
        delta = getattr(event, "delta", 0)
        if delta:
            canvas.yview_scroll(int(-1 * (delta / 120)), "units")

    def _on_correlations_mousewheel(self, event: tk.Event) -> None:
        canvas = self._correlations_scroll_canvas
        if canvas is None:
            return
        if str(self.notebook.select()) != str(self.correlations_tab):
            return
        pointer_x = canvas.winfo_pointerx()
        pointer_y = canvas.winfo_pointery()
        left = canvas.winfo_rootx()
        top = canvas.winfo_rooty()
        right = left + canvas.winfo_width()
        bottom = top + canvas.winfo_height()
        if not (left <= pointer_x <= right and top <= pointer_y <= bottom):
            return
        delta = getattr(event, "delta", 0)
        if delta:
            canvas.yview_scroll(int(-1 * (delta / 120)), "units")

    def _on_sweep_mousewheel(self, event: tk.Event) -> None:
        canvas = self._sweep_scroll_canvas
        if canvas is None:
            return
        if str(self.notebook.select()) != str(self.sweep_tab):
            return
        pointer_x = canvas.winfo_pointerx()
        pointer_y = canvas.winfo_pointery()
        left = canvas.winfo_rootx()
        top = canvas.winfo_rooty()
        right = left + canvas.winfo_width()
        bottom = top + canvas.winfo_height()
        if not (left <= pointer_x <= right and top <= pointer_y <= bottom):
            return
        delta = getattr(event, "delta", 0)
        if delta:
            canvas.yview_scroll(int(-1 * (delta / 120)), "units")

    def _summary_row(
        self,
        parent: tk.Widget,
        label: str,
        key: str,
    ) -> None:
        row = ttk.Frame(parent, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=label, style="Header.TLabel").pack(side=tk.LEFT)
        value = ttk.Label(
            row,
            text="-",
            style="Header.TLabel",
            font=("Segoe UI", 11, "bold"),
        )
        value.pack(side=tk.RIGHT)
        self._summary_labels[key] = value

    def _metric_card(self, parent: tk.Widget, title: str, key: str) -> None:
        card = tk.Frame(
            parent,
            bg="#fbfcfe",
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        card.pack(fill=tk.X, pady=4)
        tk.Label(
            card,
            text=title,
            bg="#fbfcfe",
            fg=MUTED_COLOR,
            font=("Segoe UI", 11),
        ).pack(anchor=tk.W)
        value = tk.Label(
            card,
            text="-",
            bg="#fbfcfe",
            fg=TEXT_COLOR,
            font=("Segoe UI", 18, "bold"),
        )
        value.pack(anchor=tk.W, pady=(2, 0))
        self.metric_labels[key] = value

    def _build_layout_tab(self) -> None:
        main = ttk.Frame(self.layout_tab, padding=4)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        tools_panel = self._panel(main)
        tools_panel.grid(row=0, column=0, sticky=tk.NS, padx=(0, 8), pady=4)
        canvas_panel = self._panel(main)
        canvas_panel.grid(row=0, column=1, sticky=tk.NSEW, pady=4)
        canvas_panel.rowconfigure(1, weight=1)
        canvas_panel.columnconfigure(0, weight=1)

        ttk.Label(
            tools_panel,
            text="Passage Layout",
            style="Section.TLabel",
        ).pack(anchor=tk.W, pady=(0, 8))
        ttk.Button(
            tools_panel,
            text="Load Image",
            command=self.load_layout_image,
            style="Accent.TButton",
        ).pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            tools_panel,
            text="Clear Image",
            command=self.clear_layout_image,
        ).pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            tools_panel,
            text="Reset Node Positions",
            command=self.reset_layout_positions,
        ).pack(fill=tk.X, pady=(0, 16))

        self.layout_image_label = ttk.Label(
            tools_panel,
            text="No image loaded",
            style="Header.TLabel",
            wraplength=230,
        )
        self.layout_image_label.pack(anchor=tk.W, fill=tk.X, pady=(0, 16))

        ttk.Label(
            tools_panel,
            text=(
                "Stage 1 displays the current node-edge network on top of an "
                "imported blade passage image. Node/edge editing remains in "
                "the table tabs for now."
            ),
            style="Header.TLabel",
            wraplength=230,
        ).pack(anchor=tk.W, fill=tk.X)

        ttk.Label(
            canvas_panel,
            text="Network Overlay",
            style="Section.TLabel",
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 8))
        self.layout_canvas = tk.Canvas(
            canvas_panel,
            bg="#eef3f8",
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
        )
        self.layout_canvas.grid(row=1, column=0, sticky=tk.NSEW)
        self.layout_canvas.bind(
            "<Configure>",
            lambda _event: self._redraw_layout_canvas(),
        )

    def load_layout_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Load passage image",
            filetypes=IMAGE_FILETYPES,
        )
        if not path:
            return
        try:
            self._set_layout_image(Path(path))
        except Exception as exc:
            messagebox.showerror("Image load failed", str(exc))

    def _set_layout_image(self, path: Path) -> None:
        self.layout_image_path = path
        self._layout_native_photo = None
        self._layout_photo = None
        if Image is not None:
            self._layout_source_image = Image.open(path)
        else:
            if path.suffix.lower() in {".jpg", ".jpeg"}:
                raise RuntimeError(
                    "JPEG layout images require Pillow. Install it with "
                    "`pip install -r requirements.txt`, or use a PNG image."
                )
            self._layout_source_image = None
            self._layout_native_photo = tk.PhotoImage(file=str(path))
        if hasattr(self, "layout_image_label"):
            self.layout_image_label.configure(text=f"Image: {path.name}")
        self._redraw_layout_canvas()

    def clear_layout_image(self) -> None:
        self.layout_image_path = None
        self._layout_source_image = None
        self._layout_native_photo = None
        self._layout_photo = None
        if hasattr(self, "layout_image_label"):
            self.layout_image_label.configure(text="No image loaded")
        self._redraw_layout_canvas()

    def reset_layout_positions(self) -> None:
        self.node_positions.clear()
        self._ensure_node_positions()
        self._redraw_layout_canvas()

    def _ensure_node_positions(self) -> None:
        current_ids = [row["node_id"] for row in self.node_rows]
        current_set = set(current_ids)
        self.node_positions = {
            node_id: position
            for node_id, position in self.node_positions.items()
            if node_id in current_set
        }
        auto_positions = _auto_node_positions(current_ids)
        for node_id in current_ids:
            self.node_positions.setdefault(
                node_id,
                DEFAULT_NODE_POSITIONS.get(node_id, auto_positions[node_id]),
            )

    def _redraw_layout_canvas(self) -> None:
        if not hasattr(self, "layout_canvas"):
            return
        canvas = self.layout_canvas
        canvas.delete(tk.ALL)
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        self._draw_layout_background(canvas, width, height)
        self._draw_layout_edges(canvas)
        self._draw_layout_nodes(canvas)
        self._draw_overlay_legend(canvas, width, height)
        self._draw_stale_banner(canvas)

    def _draw_layout_background(
        self,
        canvas: tk.Canvas,
        width: int,
        height: int,
    ) -> None:
        margin = 18
        if Image is not None and self._layout_source_image is not None:
            source_width, source_height = self._layout_source_image.size
            scale = min(
                (width - 2 * margin) / source_width,
                (height - 2 * margin) / source_height,
            )
            scale = max(scale, 0.05)
            display_width = max(1, int(source_width * scale))
            display_height = max(1, int(source_height * scale))
            resized = self._layout_source_image.resize(
                (display_width, display_height)
            )
            self._layout_photo = ImageTk.PhotoImage(resized)
            x0 = (width - display_width) / 2
            y0 = (height - display_height) / 2
            canvas.create_image(x0, y0, anchor=tk.NW, image=self._layout_photo)
            self._layout_image_bbox = (x0, y0, display_width, display_height)
            return

        if self._layout_native_photo is not None:
            display_width = self._layout_native_photo.width()
            display_height = self._layout_native_photo.height()
            x0 = max((width - display_width) / 2, margin)
            y0 = max((height - display_height) / 2, margin)
            canvas.create_image(
                x0,
                y0,
                anchor=tk.NW,
                image=self._layout_native_photo,
            )
            self._layout_image_bbox = (x0, y0, display_width, display_height)
            return

        x0, y0 = margin, margin
        display_width = width - 2 * margin
        display_height = height - 2 * margin
        canvas.create_rectangle(
            x0,
            y0,
            x0 + display_width,
            y0 + display_height,
            fill="#f8fbfd",
            outline=BORDER_COLOR,
            dash=(4, 3),
        )
        canvas.create_text(
            width / 2,
            height / 2,
            text="Load a turbine internal-passage image to view the overlay.",
            fill=MUTED_COLOR,
            font=("Segoe UI", 13, "bold"),
            width=max(display_width - 40, 100),
            justify=tk.CENTER,
        )
        self._layout_image_bbox = (x0, y0, display_width, display_height)

    def _draw_stale_banner(self, canvas: tk.Canvas) -> None:
        if not self.results_stale:
            return
        text = "OLD DATA - inputs changed. Press Calculate."
        canvas.create_rectangle(
            24,
            24,
            350,
            58,
            fill="#fff4df",
            outline=WARNING_COLOR,
            width=2,
        )
        canvas.create_text(
            36,
            41,
            text=text,
            anchor=tk.W,
            fill=WARNING_COLOR,
            font=("Segoe UI", 11, "bold"),
        )

    def _draw_layout_edges(self, canvas: tk.Canvas) -> None:
        metric = self.overlay_metric.get() if hasattr(self, "overlay_metric") else "Technology"
        metric_values = self._overlay_edge_values(metric)
        self._edge_label_bboxes = {}
        for row in self.edge_rows:
            from_pos = self.node_positions.get(row["from_node"])
            to_pos = self.node_positions.get(row["to_node"])
            if from_pos is None or to_pos is None:
                continue
            x1, y1 = self._layout_to_canvas(from_pos)
            x2, y2 = self._layout_to_canvas(to_pos)
            is_current = row["edge_id"] == self.selected_edge_id
            is_batch_selected = row["edge_id"] in self.selected_layout_edge_ids
            is_selected = is_current or is_batch_selected
            overlay_value = metric_values.get(row["edge_id"])
            color = ACCENT_COLOR
            if overlay_value is not None:
                color = _value_to_color(overlay_value, list(metric_values.values()))
            selected_color = WARNING_COLOR if is_current else SAFE_COLOR
            if is_selected:
                canvas.create_line(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill="#111827",
                    width=11,
                    arrow=tk.LAST,
                    arrowshape=(18, 20, 8),
                )
            canvas.create_line(
                x1,
                y1,
                x2,
                y2,
                fill=selected_color if is_selected else color,
                width=7 if is_selected or overlay_value is not None else 3,
                arrow=tk.LAST,
                arrowshape=(14, 16, 6),
            )
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2
            label = self._edge_overlay_label(row, metric, overlay_value)
            label_fill = "#ffffff"
            label_text = TEXT_COLOR
            if overlay_value is not None:
                label_fill = selected_color if is_selected else color
                label_text = _contrast_text_color(label_fill)
            label_half_width = max(34, 4.4 * len(label) + 8)
            label_bbox = (
                mid_x - label_half_width,
                mid_y - 13,
                mid_x + label_half_width,
                mid_y + 13,
            )
            self._edge_label_bboxes[row["edge_id"]] = label_bbox
            canvas.create_rectangle(
                *label_bbox,
                fill="#fff8e8" if is_selected and overlay_value is None else label_fill,
                outline=selected_color if is_selected else BORDER_COLOR,
                width=3 if is_selected else 1,
            )
            canvas.create_text(
                mid_x,
                mid_y,
                text=label,
                fill=TEXT_COLOR if is_selected and overlay_value is None else label_text,
                font=("Segoe UI", 9, "bold"),
            )

    def _draw_overlay_legend(
        self,
        canvas: tk.Canvas,
        width: int,
        height: int,
    ) -> None:
        metric = self.overlay_metric.get() if hasattr(self, "overlay_metric") else "Technology"
        if metric == "Technology":
            return
        values = self._overlay_edge_values(metric)
        if not values:
            values = self._overlay_node_values(metric)
        if not values:
            return
        numeric_values = list(values.values())
        low = min(numeric_values)
        high = max(numeric_values)
        legend_width = 170
        legend_height = 150
        x0 = max(width - legend_width - 18, 18)
        y0 = max(height - legend_height - 18, 18)
        canvas.create_rectangle(
            x0,
            y0,
            x0 + legend_width,
            y0 + legend_height,
            fill="#ffffff",
            outline=BORDER_COLOR,
        )
        canvas.create_text(
            x0 + 10,
            y0 + 12,
            text=metric,
            anchor=tk.W,
            fill=TEXT_COLOR,
            font=("Segoe UI", 9, "bold"),
        )
        bar_x0 = x0 + 14
        bar_y0 = y0 + 34
        bar_width = 20
        bar_height = 86
        steps = 18
        for step in range(steps):
            fraction_high_to_low = step / max(steps - 1, 1)
            fraction = 1.0 - fraction_high_to_low
            color = _interpolate_color("#2f80ed", "#d7191c", fraction)
            y_start = bar_y0 + step * bar_height / steps
            y_end = bar_y0 + (step + 1) * bar_height / steps
            canvas.create_rectangle(
                bar_x0,
                y_start,
                bar_x0 + bar_width,
                y_end,
                fill=color,
                outline=color,
            )
        canvas.create_rectangle(
            bar_x0,
            bar_y0,
            bar_x0 + bar_width,
            bar_y0 + bar_height,
            outline="#6b7280",
        )
        canvas.create_text(
            bar_x0 + bar_width + 10,
            bar_y0,
            text=f"High {high:,.3g}",
            anchor=tk.W,
            fill=TEXT_COLOR,
            font=("Segoe UI", 9),
        )
        canvas.create_text(
            bar_x0 + bar_width + 10,
            bar_y0 + bar_height,
            text=f"Low {low:,.3g}",
            anchor=tk.W,
            fill=TEXT_COLOR,
            font=("Segoe UI", 9),
        )

    def _draw_layout_nodes(self, canvas: tk.Canvas) -> None:
        metric = self.overlay_metric.get() if hasattr(self, "overlay_metric") else "Technology"
        metric_values = self._overlay_node_values(metric)
        for row in self.node_rows:
            node_id = row["node_id"]
            position = self.node_positions.get(node_id)
            if position is None:
                continue
            x, y = self._layout_to_canvas(position)
            radius = 15 if row["kind"] != "inlet" else 17
            is_selected = node_id == self.selected_node_id
            overlay_value = metric_values.get(node_id)
            fill = _value_to_color(overlay_value, list(metric_values.values())) if overlay_value is not None else "#ffffff"
            text_fill = _contrast_text_color(fill) if overlay_value is not None else TEXT_COLOR
            if is_selected:
                fill = "#fff8e8"
                text_fill = TEXT_COLOR
            outline = ACCENT_COLOR
            if row["kind"] == "inlet":
                outline = SAFE_COLOR
            elif row["kind"] == "merge":
                outline = WARNING_COLOR
            elif row["kind"] == "outlet":
                outline = DANGER_COLOR
            if is_selected:
                outline = WARNING_COLOR
            canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill=fill,
                outline=outline,
                width=4 if is_selected else 3,
            )
            canvas.create_text(
                x,
                y,
                text=node_id,
                fill=text_fill,
                font=("Segoe UI", 11, "bold"),
            )

    def _overlay_edge_values(self, metric: str) -> dict[str, float]:
        if self.last_result is None:
            return {}
        values: dict[str, float] = {}
        for edge_id, edge in self.last_result.edges.items():
            if metric == "Edge Tout [K]":
                values[edge_id] = edge.outlet_temperature
            elif metric == "Edge HTC [W/m2-K]":
                values[edge_id] = edge.htc
            elif metric == "Edge dp [Pa]":
                values[edge_id] = edge.dp_total
            elif metric == "Edge q [W]":
                values[edge_id] = edge.heat_rate
        return values

    def _overlay_node_values(self, metric: str) -> dict[str, float]:
        if self.last_result is None:
            return {}
        values: dict[str, float] = {}
        for node_id, node in self.last_result.nodes.items():
            if metric == "Node T [K]":
                values[node_id] = node.temperature
            elif metric == "Node P [Pa]":
                values[node_id] = node.pressure
        return values

    def _edge_overlay_label(
        self,
        row: dict[str, str],
        metric: str,
        value: float | None,
    ) -> str:
        if value is None or metric == "Technology":
            return row["cooling_technology"]
        if metric == "Edge HTC [W/m2-K]":
            return f"h={value:,.0f}"
        if metric == "Edge dp [Pa]":
            return f"dp={value:,.0f}"
        if metric == "Edge q [W]":
            return f"q={value:,.0f}"
        if metric == "Edge Tout [K]":
            return f"T={value:,.1f}"
        return _fmt_number(value, 2)

    def _layout_to_canvas(self, position: tuple[float, float]) -> tuple[float, float]:
        x0, y0, width, height = self._layout_image_bbox
        return x0 + position[0] * width, y0 + position[1] * height

    def _canvas_to_layout(self, x_pos: float, y_pos: float) -> tuple[float, float]:
        x0, y0, width, height = self._layout_image_bbox
        x_norm = (x_pos - x0) / max(width, 1e-9)
        y_norm = (y_pos - y0) / max(height, 1e-9)
        return _clamp01(x_norm), _clamp01(y_norm)

    def set_select_mode(self) -> None:
        self._layout_mode.set("select")
        self._pending_edge_from = None
        self._update_layout_status("Mode: Select / Move")

    def set_add_node_mode(self) -> None:
        self._layout_mode.set("add_node")
        self._pending_edge_from = None
        self._update_layout_status("Mode: Add Node - click the image")

    def set_connect_edge_mode(self) -> None:
        self._layout_mode.set("connect_edge")
        self._pending_edge_from = None
        self._update_layout_status("Mode: Connect Nodes - click source node")

    def _update_layout_status(self, text: str) -> None:
        if hasattr(self, "layout_status_label"):
            self.layout_status_label.configure(text=text)

    def _on_layout_press(self, event: tk.Event) -> None:
        mode = self._layout_mode.get()
        node_id = self._node_at_canvas(event.x, event.y)
        if mode == "add_node":
            self._add_node_at_position(self._canvas_to_layout(event.x, event.y))
            self.set_select_mode()
            return
        if mode == "connect_edge":
            if node_id is None:
                return
            if self._pending_edge_from is None:
                self._pending_edge_from = node_id
                self._select_node_by_id(node_id)
                self._update_layout_status(
                    f"Mode: Connect Nodes - source {node_id}, click target node"
                )
                return
            if node_id == self._pending_edge_from:
                self._update_layout_status("Select a different target node")
                return
            self._create_edge_between(self._pending_edge_from, node_id)
            self.set_select_mode()
            return

        if node_id is not None:
            self._select_node_by_id(node_id)
            self._drag_node_id = node_id
            self._drag_started = False
            return

        edge_id = self._edge_at_canvas(event.x, event.y)
        if edge_id is not None:
            if _event_has_control(event):
                self._toggle_layout_edge_selection(edge_id)
                return
            self._select_edge_by_id(edge_id)
            return

        self.selected_node_id = None
        self.selected_edge_id = None
        self.selected_layout_edge_ids.clear()
        self._update_selected_result_panel()
        self._update_batch_status()
        self._redraw_layout_canvas()

    def _toggle_layout_edge_selection(self, edge_id: str) -> None:
        if edge_id in self.selected_layout_edge_ids:
            self.selected_layout_edge_ids.remove(edge_id)
        else:
            self.selected_layout_edge_ids.add(edge_id)
        self.selected_edge_id = edge_id
        self.selected_node_id = None
        index = self._edge_index(edge_id)
        if index is not None:
            self.edge_tree.selection_set(str(index))
            self.edge_tree.focus(str(index))
            self._populate_edge_form(index)
        if hasattr(self, "node_tree"):
            self.node_tree.selection_remove(self.node_tree.selection())
        self._update_selected_result_panel()
        self._update_layout_status(
            f"Ctrl-selected edges: {len(self.selected_layout_edge_ids)}"
        )
        self._update_batch_status()
        self._redraw_layout_canvas()

    def _on_layout_drag(self, event: tk.Event) -> None:
        if self._layout_mode.get() != "select" or self._drag_node_id is None:
            return
        self.node_positions[self._drag_node_id] = self._canvas_to_layout(
            event.x,
            event.y,
        )
        self._drag_started = True
        self._redraw_layout_canvas()

    def _on_layout_release(self, _event: tk.Event) -> None:
        if self._drag_node_id is not None and self._drag_started:
            self._redraw_layout_canvas()
        self._drag_node_id = None
        self._drag_started = False

    def _node_at_canvas(self, x_pos: float, y_pos: float) -> str | None:
        nearest_node: str | None = None
        nearest_distance = 1e9
        for row in self.node_rows:
            node_id = row["node_id"]
            position = self.node_positions.get(node_id)
            if position is None:
                continue
            x_node, y_node = self._layout_to_canvas(position)
            distance = ((x_pos - x_node) ** 2 + (y_pos - y_node) ** 2) ** 0.5
            if distance <= 22 and distance < nearest_distance:
                nearest_node = node_id
                nearest_distance = distance
        return nearest_node

    def _edge_at_canvas(self, x_pos: float, y_pos: float) -> str | None:
        for edge_id, (x0, y0, x1, y1) in self._edge_label_bboxes.items():
            if x0 <= x_pos <= x1 and y0 <= y_pos <= y1:
                return edge_id
        nearest_edge: str | None = None
        nearest_distance = 1e9
        for row in self.edge_rows:
            from_pos = self.node_positions.get(row["from_node"])
            to_pos = self.node_positions.get(row["to_node"])
            if from_pos is None or to_pos is None:
                continue
            x1, y1 = self._layout_to_canvas(from_pos)
            x2, y2 = self._layout_to_canvas(to_pos)
            distance = _point_to_segment_distance(x_pos, y_pos, x1, y1, x2, y2)
            if distance <= 18 and distance < nearest_distance:
                nearest_edge = row["edge_id"]
                nearest_distance = distance
        return nearest_edge

    def _select_node_by_id(self, node_id: str) -> None:
        index = self._node_index(node_id)
        if index is None:
            return
        self.selected_node_id = node_id
        self.selected_edge_id = None
        self.selected_layout_edge_ids.clear()
        self.node_tree.selection_set(str(index))
        self.node_tree.focus(str(index))
        self._populate_node_form(index)
        if hasattr(self, "edge_tree"):
            self.edge_tree.selection_remove(self.edge_tree.selection())
        self._update_selected_result_panel()
        self._update_batch_status()
        self._redraw_layout_canvas()

    def _select_edge_by_id(self, edge_id: str) -> None:
        index = self._edge_index(edge_id)
        if index is None:
            return
        self.selected_edge_id = edge_id
        self.selected_node_id = None
        self.selected_layout_edge_ids.clear()
        self.edge_tree.selection_set(str(index))
        self.edge_tree.focus(str(index))
        self._populate_edge_form(index)
        if hasattr(self, "node_tree"):
            self.node_tree.selection_remove(self.node_tree.selection())
        self._update_selected_result_panel()
        self._update_batch_status()
        self._redraw_layout_canvas()

    def _node_index(self, node_id: str) -> int | None:
        for index, row in enumerate(self.node_rows):
            if row["node_id"] == node_id:
                return index
        return None

    def _edge_index(self, edge_id: str) -> int | None:
        for index, row in enumerate(self.edge_rows):
            if row["edge_id"] == edge_id:
                return index
        return None

    def _add_node_at_position(self, position: tuple[float, float]) -> None:
        node_id = self._next_id("N", {row["node_id"] for row in self.node_rows})
        self.node_rows.append(
            {
                "node_id": node_id,
                "kind": "internal",
                "inlet_mdot": "",
                "inlet_temperature": "",
                "inlet_pressure": "",
                **_unit_defaults_for_keys(NODE_UNIT_KEYS),
            }
        )
        self.node_positions[node_id] = position
        self._ensure_node_positions()
        self._refresh_node_tree()
        self._refresh_node_combos()
        self._update_dashboard_summary()
        self._select_node_by_id(node_id)

    def _create_edge_between(self, from_node: str, to_node: str) -> None:
        existing_ids = {row["edge_id"] for row in self.edge_rows}
        base_id = f"{from_node}_to_{to_node}".replace(" ", "_")
        edge_id = _unique_id(base_id, existing_ids)
        self.edge_rows.append(self._default_edge_row(edge_id, from_node, to_node))
        self._convert_source_outlet_to_internal(from_node)
        self._refresh_node_tree()
        self._refresh_edge_tree()
        self._update_dashboard_summary()
        self._select_edge_by_id(edge_id)

    def _convert_source_outlet_to_internal(self, node_id: str) -> None:
        for row in self.node_rows:
            if row["node_id"] == node_id and row["kind"] == "outlet":
                row["kind"] = "internal"
                row["inlet_mdot"] = ""
                row["inlet_temperature"] = ""
                row["inlet_pressure"] = ""
                if self.selected_node_id == node_id:
                    index = self._node_index(node_id)
                    if index is not None:
                        self._populate_node_form(index)
                return

    def _default_edge_row(
        self,
        edge_id: str,
        from_node: str,
        to_node: str,
    ) -> dict[str, str]:
        return {
            "edge_id": edge_id,
            "from_node": from_node,
            "to_node": to_node,
            "tag": TAG_OPTIONS[0],
            "cooling_technology": "smooth",
            "shape": "rectangular",
            "length": "0.1",
            "width": "0.01",
            "height": "0.01",
            "diameter": "",
            "wall_mode": "adiabatic",
            "wall_temperature": "",
            "heat_flux": "",
            "external_htc": "",
            "external_temperature": "",
            "wall_thickness": "",
            "wall_conductivity": "",
            "tbc_thickness": "",
            "tbc_conductivity": "",
            "flow_fraction": "",
            "fixed_mdot": "",
            "params_text": "",
            **_unit_defaults_for_keys(EDGE_UNIT_KEYS),
            **_default_param_row("smooth"),
        }

    def _build_nodes_tab(self) -> None:
        pane = ttk.PanedWindow(self.nodes_tab, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        table_frame = ttk.Frame(pane)
        form_frame = ttk.LabelFrame(pane, text="Selected node", padding=10)
        pane.add(table_frame, weight=3)
        pane.add(form_frame, weight=2)

        columns = ("node_id", "kind", "mdot", "temperature", "pressure")
        self.node_tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        headings = {
            "node_id": "Node",
            "kind": "Kind",
            "mdot": "m_dot [kg/s]",
            "temperature": "T [K]",
            "pressure": "P [Pa]",
        }
        widths = {
            "node_id": 110,
            "kind": 100,
            "mdot": 130,
            "temperature": 130,
            "pressure": 130,
        }
        for column in columns:
            self.node_tree.heading(column, text=headings[column])
            self.node_tree.column(column, width=widths[column], anchor=tk.W)
        self.node_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.node_tree.bind("<<TreeviewSelect>>", self._on_node_select)
        node_scroll = ttk.Scrollbar(
            table_frame, orient=tk.VERTICAL, command=self.node_tree.yview
        )
        self.node_tree.configure(yscrollcommand=node_scroll.set)
        node_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._labeled_entry(form_frame, 0, "Node ID", self._node_vars["node_id"])
        ttk.Label(form_frame, text="Kind").grid(row=1, column=0, sticky=tk.W, pady=3)
        ttk.Combobox(
            form_frame,
            textvariable=self._node_vars["kind"],
            values=NODE_KINDS,
            state="readonly",
            width=20,
        ).grid(row=1, column=1, sticky=tk.EW, pady=3)
        self._labeled_entry(
            form_frame, 2, "Inlet m_dot [kg/s]", self._node_vars["inlet_mdot"]
        )
        self._labeled_entry(
            form_frame,
            3,
            "Inlet temperature [K]",
            self._node_vars["inlet_temperature"],
        )
        self._labeled_entry(
            form_frame, 4, "Inlet pressure [Pa]", self._node_vars["inlet_pressure"]
        )
        form_frame.columnconfigure(1, weight=1)

        buttons = ttk.Frame(form_frame)
        buttons.grid(row=5, column=0, columnspan=2, sticky=tk.EW, pady=(12, 0))
        ttk.Button(buttons, text="Apply Node", command=self.apply_node).pack(
            side=tk.LEFT
        )
        ttk.Button(buttons, text="Add Node", command=self.add_node).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(buttons, text="Delete Node", command=self.delete_node).pack(
            side=tk.LEFT
        )

    def _build_edges_tab(self) -> None:
        pane = ttk.PanedWindow(self.edges_tab, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        table_frame = ttk.Frame(pane)
        form_container = ttk.LabelFrame(pane, text="Selected edge")
        pane.add(table_frame, weight=3)
        pane.add(form_container, weight=2)

        columns = ("edge_id", "route", "tech", "length", "width", "height", "diameter")
        self.edge_tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        headings = {
            "edge_id": "Edge",
            "route": "Route",
            "tech": "Technology",
            "length": "L [m]",
            "width": "W [m]",
            "height": "H [m]",
            "diameter": "D [m]",
        }
        widths = {
            "edge_id": 140,
            "route": 120,
            "tech": 120,
            "length": 80,
            "width": 80,
            "height": 80,
            "diameter": 80,
        }
        for column in columns:
            self.edge_tree.heading(column, text=headings[column])
            self.edge_tree.column(column, width=widths[column], anchor=tk.W)
        self.edge_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.edge_tree.bind("<<TreeviewSelect>>", self._on_edge_select)
        edge_scroll = ttk.Scrollbar(
            table_frame, orient=tk.VERTICAL, command=self.edge_tree.yview
        )
        self.edge_tree.configure(yscrollcommand=edge_scroll.set)
        edge_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        form_canvas = tk.Canvas(form_container, highlightthickness=0)
        form_scroll = ttk.Scrollbar(
            form_container, orient=tk.VERTICAL, command=form_canvas.yview
        )
        form_canvas.configure(yscrollcommand=form_scroll.set)
        form_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        form_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        form_frame = ttk.Frame(form_canvas, padding=10)
        form_window = form_canvas.create_window((0, 0), window=form_frame, anchor=tk.NW)

        def resize_scroll_region(_event: tk.Event) -> None:
            form_canvas.configure(scrollregion=form_canvas.bbox(tk.ALL))

        def resize_form_width(event: tk.Event) -> None:
            form_canvas.itemconfigure(form_window, width=event.width)

        form_frame.bind("<Configure>", resize_scroll_region)
        form_canvas.bind("<Configure>", resize_form_width)

        row = 0
        self._labeled_entry(form_frame, row, "Edge ID", self._edge_vars["edge_id"])
        row += 1
        self._labeled_combo(
            form_frame, row, "From node", self._edge_vars["from_node"], ()
        )
        self.edge_from_combo = form_frame.grid_slaves(row=row, column=1)[0]
        row += 1
        self._labeled_combo(form_frame, row, "To node", self._edge_vars["to_node"], ())
        self.edge_to_combo = form_frame.grid_slaves(row=row, column=1)[0]
        row += 1
        self._labeled_combo(
            form_frame,
            row,
            "Technology",
            self._edge_vars["cooling_technology"],
            TECHNOLOGIES,
        )
        row += 1
        self._labeled_combo(form_frame, row, "Shape", self._edge_vars["shape"], SHAPES)
        row += 1
        for label, key in (
            ("Length [m]", "length"),
            ("Width [m]", "width"),
            ("Height [m]", "height"),
            ("Diameter [m]", "diameter"),
        ):
            self._labeled_entry(form_frame, row, label, self._edge_vars[key])
            row += 1
        self._labeled_combo(
            form_frame, row, "Wall mode", self._edge_vars["wall_mode"], WALL_MODES
        )
        row += 1
        for label, key in (
            ("Wall T [K]", "wall_temperature"),
            ("Heat flux [W/m2]", "heat_flux"),
            ("External h [W/m2-K]", "external_htc"),
            ("Flow fraction", "flow_fraction"),
            ("Fixed m_dot [kg/s]", "fixed_mdot"),
        ):
            self._labeled_entry(form_frame, row, label, self._edge_vars[key])
            row += 1

        self.tech_param_frame = ttk.LabelFrame(
            form_frame, text="Cooling technology parameters", padding=8
        )
        self.tech_param_frame.grid(
            row=row, column=0, columnspan=2, sticky=tk.EW, pady=(8, 4)
        )
        row += 1

        ttk.Label(form_frame, text="Additional params").grid(
            row=row, column=0, sticky=tk.NW, pady=3
        )
        self.params_text = tk.Text(form_frame, height=5, width=38, wrap=tk.NONE)
        self.params_text.grid(row=row, column=1, sticky=tk.NSEW, pady=3)
        row += 1
        form_frame.columnconfigure(1, weight=1)
        form_frame.rowconfigure(row - 1, weight=1)
        self._render_tech_params("smooth")

        buttons = ttk.Frame(form_frame)
        buttons.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(12, 0))
        ttk.Button(buttons, text="Apply Edge", command=self.apply_edge).pack(
            side=tk.LEFT
        )
        ttk.Button(buttons, text="Add Edge", command=self.add_edge).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(buttons, text="Delete Edge", command=self.delete_edge).pack(
            side=tk.LEFT
        )

    def _build_correlations_tab(self) -> None:
        canvas = tk.Canvas(self.correlations_tab, highlightthickness=0, bg=WINDOW_BG)
        scroll = ttk.Scrollbar(
            self.correlations_tab,
            orient=tk.VERTICAL,
            command=canvas.yview,
        )
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        frame = ttk.Frame(canvas, padding=(4, 4, 12, 4))
        window = canvas.create_window((0, 0), window=frame, anchor=tk.NW)

        def resize_scroll_region(_event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox(tk.ALL))

        def resize_width(event: tk.Event) -> None:
            canvas.itemconfigure(window, width=event.width)

        frame.bind("<Configure>", resize_scroll_region)
        canvas.bind("<Configure>", resize_width)
        self._correlations_scroll_canvas = canvas
        self.bind_all("<MouseWheel>", self._on_correlations_mousewheel, add="+")

        self._formula_section(
            frame,
            "Pressure Update",
            "\n".join(
                (
                    r"\begin{aligned}",
                    r"P_{out} &= P_{in}-\Delta P_{friction}-\Delta P_{rotation}",
                    r"q_{dyn} &= \frac{1}{2}\rho V^2",
                    r"\Delta P_{friction} &= f\,\frac{L}{D}\,q_{dyn}",
                    r"\end{aligned}",
                )
            ),
            (
                ("q_dyn", "Dynamic pressure"),
                ("D", "D_h for channels/turning, D_pin for pin-fin pressure loss"),
                ("Delta P_rotation", "Only rib edges use the rotation term"),
            ),
        )
        self._formula_section(
            frame,
            "Smooth Channel",
            "\n".join(
                (
                    r"\begin{aligned}",
                    r"Nu_{DB} &= 0.023\,Re^{0.8}Pr^{0.3}",
                    r"Nu &= C_{Nu}\,Nu_{DB}",
                    r"f_{smooth} &= 2\left(2.236\ln Re - 4.639\right)^{-2}",
                    r"\Delta P_{friction} &= f_{smooth}\frac{L}{D_h}q_{dyn}",
                    r"\end{aligned}",
                )
            ),
            (
                ("C_Nu", "User heat-transfer multiplier; use 1.0 when no correction is intended"),
                ("Inputs", "L, geometry, C_Nu"),
            ),
        )
        self._formula_section(
            frame,
            "Rib Turbulator",
            "\n".join(
                (
                    r"\begin{aligned}",
                    r"m=0\;(\theta=90^\circ),\quad m=0.35\;(\theta<90^\circ)",
                    r"AR_{used} &= \min\left(\frac{W}{H},2\right)",
                    r"R(e^+) &= \left(\frac{P/e}{10}\right)^{0.35}AR_{used}^{m}",
                    r"&\quad\left[12.31-27.07\left(\frac{\theta}{90}\right)+17.86\left(\frac{\theta}{90}\right)^2\right]",
                    r"e^+ &= \frac{e}{D_h}Re\sqrt{\frac{f_{rib}}{2}}",
                    r"f_{rib} &= 0.5\left[R(e^+)-2.5\ln\left(\frac{2e}{D_h}\frac{2W}{W+H}\right)-2.5\right]^{-2}",
                    r"G(e^+) &= 2.24\left(\frac{W}{H}\right)^{0.1}\left(\frac{\theta}{90}\right)^m\left(\frac{P/e}{10}\right)^{0.1}(e^+)^{0.35}",
                    r"St &= \frac{f_{rib}/2}{(G(e^+)-R(e^+))\sqrt{f_{rib}/2}+1}",
                    r"h &= St\,\rho C_p V",
                    r"\Delta P_{rotation} &= \rho C_{rotation}\left(\frac{RPM\,R_{blade}\pi}{60}\right)^2L",
                    r"\end{aligned}",
                )
            ),
            (
                ("Iteration", "f_rib and e+ are solved together; non-convergence is reported"),
                ("Inputs", "L, W, H, e/D_h, P/e, rib angle, blade radius, RPM, C_rotation"),
            ),
        )
        self._formula_section(
            frame,
            "Turning",
            "\n".join(
                (
                    r"\begin{aligned}",
                    r"W_{turn} &= \frac{W_{upstream}+W_{downstream}}{2}",
                    r"H_{turn} &= \frac{H_{upstream}+H_{downstream}}{2}",
                    r"f_{turning} &= 3f_{smooth}",
                    r"Nu_{turning} &= C_{Nu}Nu_{DB}",
                    r"\Delta P_{friction} &= f_{turning}\frac{L}{D_h}q_{dyn}",
                    r"\end{aligned}",
                )
            ),
            (
                ("Turn angle", "Stored for traceability; current model does not scale by angle"),
                ("C_Nu", "Default 1.5"),
                ("Inputs", "L, turn angle, C_Nu"),
            ),
        )
        self._formula_section(
            frame,
            "Pin-Fin Array",
            "\n".join(
                (
                    r"\begin{aligned}",
                    r"N_{across} &= \left\lfloor\frac{W}{S}\right\rfloor,\quad N_{rows}=\left\lfloor\frac{L}{X}\right\rfloor",
                    r"A_{min} &= WH - N_{across}D_{pin}\min(H_{pin},H)",
                    r"V_{max} &= \frac{\dot{m}}{\rho A_{min}}",
                    r"Re_D &= \frac{\rho V_{max}D_{pin}}{\mu}",
                    r"f_{pin} &= 4(1.76)Re_D^{-0.318}",
                    r"Nu &= 0.135Re_D^{0.69}\left(\frac{S}{D_{pin}}\right)^{-0.34}",
                    r"h &= \frac{Nu\,k_{air}}{D_{pin}}",
                    r"\Delta P_{friction} &= f_{pin}\frac{L}{D_{pin}}q_{dyn,max}",
                    r"\end{aligned}",
                )
            ),
            (
                ("Automatic counts", "pins_across and row_count are calculated from W, L, S, and X"),
                ("Inputs", "L, W, H, D_pin, H_pin, X pitch, S pitch"),
            ),
        )
        self._formula_section(
            frame,
            "Wall / TBC Thermal Network",
            "\n".join(
                (
                    r"\begin{aligned}",
                    r"R_i &= \frac{1}{h_iA},\quad R_w=\frac{t_w}{k_wA},\quad R_{TBC}=\frac{t_{TBC}}{k_{TBC}A},\quad R_o=\frac{1}{h_oA}",
                    r"\dot{Q} &= \frac{T_{\infty,o}-T_{fluid}}{R_i+R_w+R_{TBC}+R_o}",
                    r"T_{wall,i} &= T_{fluid}+\dot{Q}R_i",
                    r"T_{metal,o} &= T_{wall,i}+\dot{Q}R_w",
                    r"T_{TBC,o} &= T_{metal,o}+\dot{Q}R_{TBC}",
                    r"\end{aligned}",
                )
            ),
            (
                ("Boundary", "External gas convection + TBC conduction + blade wall conduction + internal convection"),
                ("Inputs", "External gas T, external h, wall thickness/k, TBC thickness/k"),
            ),
        )

    def _formula_section(
        self,
        parent: ttk.Frame,
        title: str,
        equation: str,
        variables: tuple[tuple[str, str], ...],
    ) -> None:
        panel = self._panel(parent)
        panel.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(panel, text=title, style="Section.TLabel").pack(
            anchor=tk.W,
            pady=(0, 6),
        )
        formula_image = self._create_formula_image(_math_lines(equation))
        if formula_image is not None:
            self._formula_images.append(formula_image)
            tk.Label(
                panel,
                image=formula_image,
                bg="#fbfcfe",
                anchor=tk.W,
                padx=8,
                pady=8,
            ).pack(fill=tk.X, pady=(0, 8))
        else:
            formula = tk.Text(
                panel,
                height=max(4, equation.count("\n") + 1),
                wrap=tk.NONE,
                bg="#fbfcfe",
                fg=TEXT_COLOR,
                font=("Consolas", 12),
                relief=tk.FLAT,
                padx=8,
                pady=8,
            )
            formula.insert(tk.END, equation)
            formula.configure(state=tk.DISABLED)
            formula.pack(fill=tk.X, pady=(0, 8))
        for name, description in variables:
            row = ttk.Frame(panel, style="Panel.TFrame")
            row.pack(fill=tk.X, pady=1)
            ttk.Label(
                row,
                text=name,
                style="Header.TLabel",
                width=18,
                font=("Segoe UI", 11, "bold"),
            ).pack(side=tk.LEFT)
            ttk.Label(
                row,
                text=description,
                style="Header.TLabel",
                wraplength=940,
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _create_formula_image(self, lines: list[str]) -> Any | None:
        if Figure is None or FigureCanvasAgg is None or Image is None or ImageTk is None:
            return None
        if not lines:
            return None
        height = max(0.58 * len(lines) + 0.18, 1.0)
        figure = Figure(figsize=(9.4, height), dpi=130, facecolor="#fbfcfe")
        axis = figure.add_axes((0, 0, 1, 1))
        axis.set_axis_off()
        line_step = 1.0 / max(len(lines), 1)
        for index, line in enumerate(lines):
            axis.text(
                0.02,
                0.98 - index * line_step,
                f"${line}$",
                fontsize=15,
                va="top",
                color=TEXT_COLOR,
            )
        canvas = FigureCanvasAgg(figure)
        try:
            canvas.draw()
            width, height_px = canvas.get_width_height()
            image = Image.frombuffer(
                "RGBA",
                (width, height_px),
                canvas.buffer_rgba(),
                "raw",
                "RGBA",
                0,
                1,
            ).copy()
            return ImageTk.PhotoImage(image)
        except Exception:
            return None

    def _build_results_tab(self) -> None:
        notebook = ttk.Notebook(self.results_tab)
        notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        node_frame = ttk.Frame(notebook)
        edge_frame = ttk.Frame(notebook)
        notebook.add(node_frame, text="Node Results")
        notebook.add(edge_frame, text="Edge Results")

        node_columns = ("node", "kind", "mdot", "temperature", "pressure")
        self.node_result_tree = ttk.Treeview(
            node_frame, columns=node_columns, show="headings"
        )
        node_headings = {
            "node": "Node",
            "kind": "Kind",
            "mdot": "m_dot [kg/s]",
            "temperature": "T [K]",
            "pressure": "P [Pa]",
        }
        for column in node_columns:
            self.node_result_tree.heading(column, text=node_headings[column])
            self.node_result_tree.column(column, width=130, anchor=tk.W)
        self.node_result_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        node_scroll = ttk.Scrollbar(
            node_frame, orient=tk.VERTICAL, command=self.node_result_tree.yview
        )
        self.node_result_tree.configure(yscrollcommand=node_scroll.set)
        node_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        edge_columns = (
            "edge",
            "tech",
            "mdot",
            "re",
            "nu",
            "h",
            "f",
            "dp",
            "q",
            "qflux",
            "twall",
            "tout",
            "pout",
        )
        self.edge_result_tree = ttk.Treeview(
            edge_frame, columns=edge_columns, show="headings"
        )
        edge_headings = {
            "edge": "Edge",
            "tech": "Technology",
            "mdot": "m_dot [kg/s]",
            "re": "Re",
            "nu": "Nu",
            "h": "h [W/m2-K]",
            "f": "f_D",
            "dp": "dp [Pa]",
            "q": "q [W]",
            "qflux": "q'' [W/m2]",
            "twall": "Twall,i [K]",
            "tout": "Tout [K]",
            "pout": "Pout [Pa]",
        }
        widths = {
            "edge": 145,
            "tech": 105,
            "mdot": 105,
            "re": 100,
            "nu": 90,
            "h": 110,
            "f": 80,
            "dp": 110,
            "q": 110,
            "qflux": 115,
            "twall": 105,
            "tout": 95,
            "pout": 110,
        }
        for column in edge_columns:
            self.edge_result_tree.heading(column, text=edge_headings[column])
            self.edge_result_tree.column(column, width=widths[column], anchor=tk.W)
        self.edge_result_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        edge_scroll = ttk.Scrollbar(
            edge_frame, orient=tk.VERTICAL, command=self.edge_result_tree.yview
        )
        self.edge_result_tree.configure(yscrollcommand=edge_scroll.set)
        edge_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_warnings_tab(self) -> None:
        self.warning_text = tk.Text(self.warnings_tab, wrap=tk.WORD)
        self.warning_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        scroll = ttk.Scrollbar(
            self.warnings_tab, orient=tk.VERTICAL, command=self.warning_text.yview
        )
        self.warning_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _labeled_entry(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        form: str | None = None,
        unit_key: str | None = None,
        sweep_key: str | None = None,
        batch_key: str | None = None,
    ) -> tuple[ttk.Label, tk.Widget]:
        label_widget = ttk.Label(parent, text=label)
        label_widget.grid(row=row, column=0, sticky=tk.W, pady=3)
        unit_group = _unit_group_for_key(unit_key)
        if unit_group is None:
            if sweep_key is None and batch_key is None:
                entry = ttk.Entry(parent, textvariable=variable)
                entry.grid(row=row, column=1, sticky=tk.EW, pady=3)
                self._bind_entry_commit(entry, form)
                return label_widget, entry
            value_frame = ttk.Frame(parent)
            value_frame.grid(row=row, column=1, sticky=tk.EW, pady=3)
            value_frame.columnconfigure(0, weight=1)
            entry = ttk.Entry(value_frame, textvariable=variable)
            entry.grid(row=0, column=0, sticky=tk.EW)
            self._bind_entry_commit(entry, form)
            column = 1
            if sweep_key is not None:
                self._create_sweep_checkbutton(value_frame, column, form, sweep_key)
                column += 1
            if batch_key is not None:
                self._create_batch_checkbutton(value_frame, column, form, batch_key)
            return label_widget, value_frame

        value_frame = ttk.Frame(parent)
        value_frame.grid(row=row, column=1, sticky=tk.EW, pady=3)
        value_frame.columnconfigure(0, weight=1)
        entry = ttk.Entry(value_frame, textvariable=variable)
        entry.grid(row=0, column=0, sticky=tk.EW)
        self._bind_entry_commit(entry, form)
        unit_combo = ttk.Combobox(
            value_frame,
            textvariable=self._unit_vars[unit_key],
            values=UNIT_OPTIONS[unit_group],
            state="readonly",
            width=13,
        )
        unit_combo.grid(row=0, column=1, sticky=tk.E, padx=(6, 0))
        self._bind_combobox_mousewheel(unit_combo)
        unit_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event, key=unit_key, form=form: self._on_unit_change(key, form),
        )
        column = 2
        if sweep_key is not None:
            self._create_sweep_checkbutton(value_frame, column, form, sweep_key)
            column += 1
        if batch_key is not None:
            self._create_batch_checkbutton(value_frame, column, form, batch_key)
        return label_widget, value_frame

    def _labeled_combo(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
        form: str | None = None,
        batch_key: str | None = None,
    ) -> tuple[ttk.Label, tk.Widget]:
        label_widget = ttk.Label(parent, text=label)
        label_widget.grid(row=row, column=0, sticky=tk.W, pady=3)
        if batch_key is not None:
            value_parent = ttk.Frame(parent)
            value_parent.grid(row=row, column=1, sticky=tk.EW, pady=3)
            value_parent.columnconfigure(0, weight=1)
            combo_parent: tk.Widget = value_parent
            combo_column = 0
        else:
            value_parent = None
            combo_parent = parent
            combo_column = 1
        combo = ttk.Combobox(
            combo_parent,
            textvariable=variable,
            values=values,
            state="readonly",
            width=20,
        )
        combo.grid(
            row=0 if value_parent is not None else row,
            column=combo_column,
            sticky=tk.EW,
            pady=0 if value_parent is not None else 3,
        )
        self._bind_combobox_mousewheel(combo)
        if batch_key is not None and value_parent is not None:
            self._create_batch_checkbutton(value_parent, 1, form, batch_key)
        if form is not None:
            combo.bind(
                "<FocusIn>",
                lambda _event, form=form: setattr(self, "_focused_form", form),
                add="+",
            )
            combo.bind(
                "<<ComboboxSelected>>",
                lambda _event, form=form: self._commit_form_edit(form),
            )
            combo.bind(
                "<FocusOut>",
                lambda _event, form=form: self._commit_form_edit(form),
                add="+",
            )
            combo.bind(
                "<Return>",
                lambda _event, form=form: self._commit_form_edit(form),
                add="+",
            )
        return label_widget, value_parent if value_parent is not None else combo

    def _sweep_combo(
        self,
        parent: tk.Widget,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
    ) -> tuple[ttk.Label, ttk.Combobox]:
        label_widget = ttk.Label(parent, text=label, style="Header.TLabel")
        label_widget.grid(row=row, column=0, sticky=tk.W, pady=3, padx=(0, 8))
        combo = ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="readonly",
            width=20,
        )
        combo.grid(row=row, column=1, sticky=tk.EW, pady=3)
        self._bind_combobox_mousewheel(combo)
        return label_widget, combo

    def _bind_entry_commit(self, entry: ttk.Entry, form: str | None) -> None:
        if form is None:
            return
        entry.bind(
            "<FocusIn>",
            lambda _event, form=form: setattr(self, "_focused_form", form),
            add="+",
        )
        entry.bind(
            "<FocusOut>",
            lambda _event, form=form: self._commit_form_edit(form),
            add="+",
        )
        entry.bind(
            "<Return>",
            lambda _event, form=form: self._commit_form_edit(form),
            add="+",
        )

    def _bind_combobox_mousewheel(self, combo: ttk.Combobox) -> None:
        combo.bind("<MouseWheel>", self._on_combobox_mousewheel, add="+")

    def _on_combobox_mousewheel(self, event: tk.Event) -> str:
        self._on_workspace_mousewheel(event)
        self._on_correlations_mousewheel(event)
        self._on_sweep_mousewheel(event)
        return "break"

    def _create_sweep_checkbutton(
        self,
        parent: ttk.Frame,
        column: int,
        form: str | None,
        field_key: str,
    ) -> None:
        if form not in {"node", "edge"}:
            return
        var_key = f"{form}:{field_key}"
        variable = self._sweep_checkbox_vars.setdefault(var_key, tk.BooleanVar())
        ttk.Checkbutton(
            parent,
            text="Sweep",
            variable=variable,
            command=lambda form=form, key=field_key: self._toggle_sweep_variable(form, key),
        ).grid(row=0, column=column, sticky=tk.E, padx=(8, 0))

    def _create_batch_checkbutton(
        self,
        parent: ttk.Frame,
        column: int,
        form: str | None,
        field_key: str,
    ) -> None:
        if form != "edge":
            return
        variable = self._batch_checkbox_vars.setdefault(field_key, tk.BooleanVar())
        ttk.Checkbutton(
            parent,
            text="Batch",
            variable=variable,
            command=lambda key=field_key: self._toggle_batch_field(key),
        ).grid(row=0, column=column, sticky=tk.E, padx=(8, 0))

    def _toggle_batch_field(self, field_key: str) -> None:
        variable = self._batch_checkbox_vars.get(field_key)
        checked = bool(variable.get()) if variable is not None else False
        if checked:
            self.batch_field_keys.add(field_key)
        else:
            self.batch_field_keys.discard(field_key)
        self._sync_batch_checkboxes()
        self._refresh_batch_field_tree()
        self._update_batch_status()

    def _sync_batch_checkboxes(self) -> None:
        for field_key, variable in self._batch_checkbox_vars.items():
            variable.set(field_key in self.batch_field_keys)

    def _refresh_batch_field_tree(self) -> None:
        if not hasattr(self, "batch_field_tree"):
            return
        self.batch_field_tree.delete(*self.batch_field_tree.get_children())
        for field_key in sorted(self.batch_field_keys, key=_batch_sort_key):
            self.batch_field_tree.insert(
                "",
                tk.END,
                iid=field_key,
                values=(_field_label(field_key),),
            )

    def _update_batch_target_visibility(self) -> None:
        if not hasattr(self, "batch_target_technology_widgets"):
            return
        mode = self.batch_target_mode.get()
        for widget in self.batch_target_technology_widgets:
            if mode == "Cooling technology":
                widget.grid()
            else:
                widget.grid_remove()
        for widget in self.batch_target_tag_widgets:
            if mode == "Tag":
                widget.grid()
            else:
                widget.grid_remove()
        self._update_batch_status()

    def _update_batch_status(self) -> None:
        if not hasattr(self, "batch_status_label"):
            return
        edge_ids = self._batch_target_edge_ids()
        self.batch_status_label.configure(
            text=(
                f"Target edges: {len(edge_ids)}"
                f" | Ctrl-selected: {len(self.selected_layout_edge_ids)}"
                f" | Batch fields: {len(self.batch_field_keys)}"
            )
        )

    def _batch_target_edge_ids(self) -> list[str]:
        mode = self.batch_target_mode.get()
        if mode == "Current edge":
            return [self.selected_edge_id] if self.selected_edge_id else []
        if mode == "Layout selected edges":
            valid_ids = {row["edge_id"] for row in self.edge_rows}
            return [
                edge_id
                for edge_id in self.selected_layout_edge_ids
                if edge_id in valid_ids
            ]
        if mode == "Cooling technology":
            technology = _normalize_technology(self.batch_target_technology.get())
            return [
                row["edge_id"]
                for row in self.edge_rows
                if _normalize_technology(row["cooling_technology"]) == technology
            ]
        if mode == "Tag":
            tag = self.batch_target_tag.get()
            return [
                row["edge_id"]
                for row in self.edge_rows
                if row.get("tag", TAG_OPTIONS[0]) == tag
            ]
        return [row["edge_id"] for row in self.edge_rows]

    def apply_batch_edit(self) -> None:
        self._commit_focused_form()
        source_row = self._selected_edge_row()
        if source_row is None:
            messagebox.showwarning("No source edge", "Select the edge that contains the values to copy.")
            return
        if not self.batch_field_keys:
            messagebox.showwarning(
                "No batch fields",
                "Check Batch beside at least one edge input variable.",
            )
            return
        edge_ids = set(self._batch_target_edge_ids())
        if not edge_ids:
            messagebox.showwarning("No target edges", "No edges match the selected batch target.")
            return

        self._last_batch_snapshot = (deepcopy(self.node_rows), deepcopy(self.edge_rows))
        changed = 0
        for row in self.edge_rows:
            if row["edge_id"] not in edge_ids:
                continue
            try:
                for field_key in sorted(self.batch_field_keys, key=_batch_sort_key):
                    self._copy_batch_field(source_row, row, field_key)
            except ValueError as exc:
                messagebox.showerror("Invalid source value", str(exc))
                self.node_rows, self.edge_rows = deepcopy(self._last_batch_snapshot)
                return
            changed += 1
        self._refresh_after_batch_edit()
        self.batch_status_label.configure(
            text=f"Applied {len(self.batch_field_keys)} field(s) to {changed} edge(s)."
        )

    def _selected_edge_row(self) -> dict[str, str] | None:
        if self.selected_edge_id:
            return next(
                (row for row in self.edge_rows if row["edge_id"] == self.selected_edge_id),
                None,
            )
        index = self._selected_index(self.edge_tree) if hasattr(self, "edge_tree") else None
        if index is None or index >= len(self.edge_rows):
            return None
        return self.edge_rows[index]

    def _copy_batch_field(
        self,
        source_row: dict[str, str],
        row: dict[str, str],
        field_key: str,
    ) -> None:
        if field_key in ALL_PARAM_KEYS:
            row_key = _param_row_key(field_key)
        else:
            row_key = field_key
        if field_key in {"tag", "cooling_technology", "shape", "wall_mode"}:
            row[row_key] = source_row.get(row_key, "")
            if field_key == "cooling_technology":
                row["cooling_technology"] = _normalize_technology(row["cooling_technology"])
                self._apply_batch_param_defaults(row)
                self._sanitize_row_shape(row)
            if field_key == "shape":
                self._sanitize_row_shape(row)
            if field_key == "wall_mode":
                self._sanitize_row_wall(row)
            return
        source_value = source_row.get(row_key, "").strip()
        if not source_value:
            row[row_key] = ""
            return
        unit_group = _unit_group_for_key(field_key)
        if unit_group is None:
            row[row_key] = source_value
            return
        source_unit = source_row.get(
            _unit_row_key(field_key),
            _default_unit_for_key(field_key),
        )
        row_unit = row.get(
            _unit_row_key(field_key),
            _default_unit_for_key(field_key),
        )
        si_value = _to_si(
            _required_float(source_value, _field_label(field_key)),
            unit_group,
            source_unit,
        )
        row[row_key] = _fmt_optional(_from_si(si_value, unit_group, row_unit))

    def _sanitize_row_shape(self, row: dict[str, str]) -> None:
        if row.get("cooling_technology") == "turning":
            row["shape"] = "rectangular"
            row["width"] = ""
            row["height"] = ""
            row["diameter"] = ""
        elif row.get("shape") == "rectangular":
            row["diameter"] = ""
        elif row.get("shape") == "circular":
            row["width"] = ""
            row["height"] = ""

    def _sanitize_row_wall(self, row: dict[str, str]) -> None:
        if row.get("wall_mode") != "wall_temperature":
            row["wall_temperature"] = ""
        if row.get("wall_mode") != "heat_flux":
            row["heat_flux"] = ""
        if row.get("wall_mode") != "external_convection":
            row["external_temperature"] = ""
            row["external_htc"] = ""
            row["wall_thickness"] = ""
            row["wall_conductivity"] = ""
            row["tbc_thickness"] = ""
            row["tbc_conductivity"] = ""

    def _apply_batch_param_defaults(self, row: dict[str, str]) -> None:
        technology = _normalize_technology(row["cooling_technology"])
        for spec in TECH_PARAM_SPECS.get(technology, ()):
            row_key = _param_row_key(spec.key)
            if not row.get(row_key, "").strip() and spec.default:
                row[row_key] = spec.default

    def _refresh_after_batch_edit(self) -> None:
        self._refresh_node_tree()
        self._refresh_edge_tree()
        self._refresh_node_combos()
        self._update_dashboard_summary()
        self._sync_sweep_checkboxes()
        self._sync_batch_checkboxes()
        self._refresh_batch_field_tree()
        self._refresh_sweep_variable_tree()
        if self.selected_edge_id:
            index = self._edge_index(self.selected_edge_id)
            if index is not None:
                self.edge_tree.selection_set(str(index))
                self.edge_tree.focus(str(index))
                self._populate_edge_form(index)
        if self.selected_node_id:
            index = self._node_index(self.selected_node_id)
            if index is not None:
                self.node_tree.selection_set(str(index))
                self.node_tree.focus(str(index))
                self._populate_node_form(index)
        self._update_selected_result_panel()
        self._after_apply()

    def undo_batch_edit(self) -> None:
        if self._last_batch_snapshot is None:
            messagebox.showinfo("No undo", "There is no batch edit to undo.")
            return
        self.node_rows, self.edge_rows = deepcopy(self._last_batch_snapshot)
        self._last_batch_snapshot = None
        self.selected_layout_edge_ids = {
            edge_id
            for edge_id in self.selected_layout_edge_ids
            if self._edge_index(edge_id) is not None
        }
        self._refresh_after_batch_edit()
        self.batch_status_label.configure(text="Last batch edit was undone.")

    def _on_technology_change(self, *_args: object) -> None:
        if self._syncing_edge_form:
            return
        technology = self._edge_vars["cooling_technology"].get()
        self._apply_param_defaults(technology)
        self._render_tech_params(technology)
        self._update_shape_visibility()
        self._auto_apply_edge_form()

    def _on_shape_change(self, *_args: object) -> None:
        self._update_shape_visibility()
        self._auto_apply_edge_form()

    def _on_wall_mode_change(self, *_args: object) -> None:
        self._apply_wall_defaults()
        self._update_wall_field_visibility()
        self._auto_apply_edge_form()

    def _on_property_model_change(self, *_args: object) -> None:
        self._update_dashboard_summary()
        if hasattr(self, "notebook"):
            self._mark_results_stale()

    def _apply_wall_defaults(self) -> None:
        if self._edge_vars["wall_mode"].get() != "external_convection":
            return
        defaults = {
            "external_temperature": "1,150",
            "external_htc": "1,200",
            "wall_thickness": "0.0015",
            "wall_conductivity": "18",
            "tbc_thickness": "0.00025",
            "tbc_conductivity": "1.2",
        }
        self._suppress_auto_apply = True
        try:
            for key, value in defaults.items():
                if not self._edge_vars[key].get().strip():
                    self._edge_vars[key].set(value)
        finally:
            self._suppress_auto_apply = False

    def _on_node_kind_change(self, *_args: object) -> None:
        self._update_node_field_visibility()
        if self._node_vars["kind"].get() != "inlet":
            self._clear_node_inlet_values()
        self._auto_apply_node_form()

    def _install_form_traces(self) -> None:
        # Entry widgets commit on focus-out/Enter so typing remains uninterrupted.
        return

    def _commit_form_edit(self, form: str | None, mark_stale: bool = True) -> None:
        if (
            form is None
            or self._suppress_auto_apply
            or self._is_committing_form
        ):
            return
        self._is_committing_form = True
        previous_suppress_stale = self._suppress_stale_mark
        self._suppress_stale_mark = previous_suppress_stale or not mark_stale
        try:
            if form == "node":
                self._auto_apply_node_form()
            elif form == "edge":
                self._auto_apply_edge_form()
        finally:
            self._suppress_stale_mark = previous_suppress_stale
            self._is_committing_form = False

    def _commit_focused_form(self) -> None:
        self._commit_form_edit(self._focused_form)

    def _on_unit_change(self, key: str, form: str | None) -> None:
        unit_group = _unit_group_for_key(key)
        if unit_group is None:
            return
        variable = self._value_var_for_unit_key(key)
        if variable is None:
            self._last_unit_values[key] = self._unit_vars[key].get()
            return
        old_unit = self._last_unit_values.get(key, _default_unit_for_key(key))
        new_unit = self._unit_vars[key].get()
        raw_value = variable.get().strip()
        if raw_value:
            try:
                si_value = _to_si(_required_float(raw_value, key), unit_group, old_unit)
                display_value = _from_si(si_value, unit_group, new_unit)
            except ValueError:
                self._last_unit_values[key] = new_unit
                return
            self._suppress_auto_apply = True
            try:
                variable.set(_fmt_optional(display_value))
            finally:
                self._suppress_auto_apply = False
        self._last_unit_values[key] = new_unit
        self._commit_form_edit(form, mark_stale=False)

    def _value_var_for_unit_key(self, key: str) -> tk.StringVar | None:
        if key in self._node_vars:
            return self._node_vars[key]
        if key in self._edge_vars:
            return self._edge_vars[key]
        if key in self._tech_param_vars:
            return self._tech_param_vars[key]
        return None

    def _unit_row_values(self, keys: tuple[str, ...]) -> dict[str, str]:
        return {
            _unit_row_key(key): self._unit_vars[key].get()
            for key in keys
            if key in self._unit_vars
        }

    def _set_unit_vars_from_row(
        self,
        row: dict[str, str],
        keys: tuple[str, ...],
    ) -> None:
        for key in keys:
            if key not in self._unit_vars:
                continue
            unit_group = _unit_group_for_key(key)
            if unit_group is None:
                continue
            unit = row.get(_unit_row_key(key), _default_unit_for_key(key))
            if unit not in UNIT_OPTIONS[unit_group]:
                unit = _default_unit_for_key(key)
            self._unit_vars[key].set(unit)
            self._last_unit_values[key] = unit

    def _toggle_sweep_variable(self, form: str, field_key: str) -> None:
        target = self._current_sweep_target(form, field_key)
        checkbox = self._sweep_checkbox_vars.get(f"{form}:{field_key}")
        checked = bool(checkbox.get()) if checkbox is not None else False
        if target is None:
            if checkbox is not None:
                checkbox.set(False)
            return

        if checked:
            existing = self.sweep_variables.get(target.target_id)
            if existing is not None:
                target.start = existing.start
                target.end = existing.end
                target.step = existing.step
                target.unit = existing.unit
            else:
                current_value = self._current_sweep_display_value(target)
                target.start = current_value
                target.end = current_value
            self.sweep_variables[target.target_id] = target
        else:
            self.sweep_variables.pop(target.target_id, None)
            if self._selected_sweep_variable_id == target.target_id:
                self._selected_sweep_variable_id = None
        self._sync_sweep_checkboxes()
        self._refresh_sweep_variable_tree()

    def _current_sweep_target(
        self,
        form: str,
        field_key: str,
    ) -> SweepVariable | None:
        if form == "node":
            index = self._selected_index(self.node_tree) if hasattr(self, "node_tree") else None
            if index is None or index >= len(self.node_rows):
                return None
            row = self.node_rows[index]
            if row.get("kind") != "inlet":
                return None
            if field_key not in NODE_UNIT_KEYS:
                return None
            object_id = row["node_id"]
            row_key = field_key
            label = f"Node {object_id} / {_field_label(field_key)}"
            scope = "node"
        elif form == "edge":
            index = self._selected_index(self.edge_tree) if hasattr(self, "edge_tree") else None
            if index is None or index >= len(self.edge_rows):
                return None
            row = self.edge_rows[index]
            object_id = row["edge_id"]
            if field_key in EDGE_FIELD_UNIT_KEYS:
                row_key = field_key
                scope = "edge"
                label = f"Edge {object_id} / {_field_label(field_key)}"
            elif field_key in ALL_PARAM_KEYS:
                row_key = _param_row_key(field_key)
                scope = "param"
                label = f"Edge {object_id} / {_field_label(field_key)}"
            else:
                return None
        else:
            return None

        unit_group = _unit_group_for_key(field_key)
        unit = (
            row.get(_unit_row_key(field_key), _default_unit_for_key(field_key))
            if unit_group is not None
            else ""
        )
        return SweepVariable(
            target_id=f"{scope}:{object_id}:{field_key}",
            scope=scope,
            object_id=object_id,
            field_key=field_key,
            row_key=row_key,
            label=label,
            unit_group=unit_group,
            unit=unit,
        )

    def _current_sweep_display_value(self, target: SweepVariable) -> str:
        row = self._find_sweep_row(target)
        if row is None:
            return ""
        return row.get(target.row_key, "")

    def _find_sweep_row(self, target: SweepVariable) -> dict[str, str] | None:
        if target.scope == "node":
            return next(
                (row for row in self.node_rows if row["node_id"] == target.object_id),
                None,
            )
        return next(
            (row for row in self.edge_rows if row["edge_id"] == target.object_id),
            None,
        )

    def _sync_sweep_checkboxes(self) -> None:
        for var_key, variable in self._sweep_checkbox_vars.items():
            form, field_key = var_key.split(":", 1)
            target = self._current_sweep_target(form, field_key)
            variable.set(target is not None and target.target_id in self.sweep_variables)

    def _update_node_field_visibility(self) -> None:
        if not hasattr(self, "node_inlet_fields"):
            return
        is_inlet = self._node_vars["kind"].get() == "inlet"
        for widgets in self.node_inlet_fields:
            for widget in widgets:
                if is_inlet:
                    widget.grid()
                else:
                    widget.grid_remove()

    def _clear_node_inlet_values(self) -> None:
        if self._suppress_auto_apply:
            return
        self._suppress_auto_apply = True
        try:
            self._node_vars["inlet_mdot"].set("")
            self._node_vars["inlet_temperature"].set("")
            self._node_vars["inlet_pressure"].set("")
        finally:
            self._suppress_auto_apply = False

    def _update_shape_visibility(self) -> None:
        if not hasattr(self, "edge_geometry_fields"):
            return
        shape = self._edge_vars["shape"].get()
        technology = _normalize_technology(self._edge_vars["cooling_technology"].get())
        is_turning = technology == "turning"
        visible = {
            "length": True,
            "width": shape == "rectangular" and not is_turning,
            "height": shape == "rectangular" and not is_turning,
            "diameter": shape == "circular" and not is_turning,
        }
        for key, widgets in self.edge_geometry_fields.items():
            for widget in widgets:
                if visible.get(key, True):
                    widget.grid()
                else:
                    widget.grid_remove()

    def _update_wall_field_visibility(self) -> None:
        if not hasattr(self, "edge_wall_fields"):
            return
        wall_mode = self._edge_vars["wall_mode"].get()
        visible = {
            "wall_temperature": wall_mode == "wall_temperature",
            "heat_flux": wall_mode == "heat_flux",
            "external_temperature": wall_mode == "external_convection",
            "external_htc": wall_mode == "external_convection",
            "wall_thickness": wall_mode == "external_convection",
            "wall_conductivity": wall_mode == "external_convection",
            "tbc_thickness": wall_mode == "external_convection",
            "tbc_conductivity": wall_mode == "external_convection",
        }
        for key, widgets in self.edge_wall_fields.items():
            for widget in widgets:
                if visible.get(key, False):
                    widget.grid()
                else:
                    widget.grid_remove()

    def _auto_apply_node_form(self) -> None:
        if self._suppress_auto_apply:
            return
        index = self._selected_index(self.node_tree) if hasattr(self, "node_tree") else None
        if index is None or index >= len(self.node_rows):
            return
        row = {key: variable.get().strip() for key, variable in self._node_vars.items()}
        row.update(self._unit_row_values(NODE_UNIT_KEYS))
        if not row["node_id"] or self._id_exists(row["node_id"], self.node_rows, index, "node_id"):
            return
        if row["kind"] != "inlet":
            row["inlet_mdot"] = ""
            row["inlet_temperature"] = ""
            row["inlet_pressure"] = ""
        old_id = self.node_rows[index]["node_id"]
        self.node_rows[index] = row
        if row["node_id"] != old_id:
            if old_id in self.node_positions:
                self.node_positions[row["node_id"]] = self.node_positions.pop(old_id)
            for edge in self.edge_rows:
                if edge["from_node"] == old_id:
                    edge["from_node"] = row["node_id"]
                if edge["to_node"] == old_id:
                    edge["to_node"] = row["node_id"]
        self._refresh_after_auto_node_change(index)

    def _auto_apply_edge_form(self) -> None:
        if self._suppress_auto_apply or self._syncing_edge_form:
            return
        index = self._selected_index(self.edge_tree) if hasattr(self, "edge_tree") else None
        if index is None or index >= len(self.edge_rows):
            return
        row = self._edge_form_to_row()
        if not row["edge_id"] or self._id_exists(row["edge_id"], self.edge_rows, index, "edge_id"):
            return
        self.edge_rows[index] = row
        self.selected_edge_id = row["edge_id"]
        self.selected_node_id = None
        self._convert_source_outlet_to_internal(row["from_node"])
        self._refresh_after_auto_edge_change(index)

    def _refresh_after_auto_node_change(self, index: int) -> None:
        self._suppress_auto_apply = True
        try:
            self._ensure_node_positions()
            self._refresh_node_tree()
            self._refresh_edge_tree()
            self._refresh_node_combos()
            self._update_dashboard_summary()
            self.node_tree.selection_set(str(index))
            self.node_tree.focus(str(index))
            self.selected_node_id = self.node_rows[index]["node_id"]
            self.selected_edge_id = None
        finally:
            self._suppress_auto_apply = False
        self._update_selected_result_panel()
        self._after_apply()

    def _refresh_after_auto_edge_change(self, index: int) -> None:
        self._suppress_auto_apply = True
        try:
            self._refresh_node_tree()
            self._refresh_edge_tree()
            self._update_dashboard_summary()
            self.edge_tree.selection_set(str(index))
            self.edge_tree.focus(str(index))
        finally:
            self._suppress_auto_apply = False
        self._update_selected_result_panel()
        self._after_apply()

    def _apply_param_defaults(self, technology: str) -> None:
        for spec in TECH_PARAM_SPECS.get(technology, ()):
            variable = self._tech_param_vars[spec.key]
            if not variable.get().strip() and spec.default:
                variable.set(spec.default)

    def _render_tech_params(self, technology: str) -> None:
        for child in self.tech_param_frame.winfo_children():
            child.destroy()

        specs = TECH_PARAM_SPECS.get(technology, ())
        if not specs:
            ttk.Label(
                self.tech_param_frame,
                text="No predefined parameters for this cooling technology.",
            ).grid(row=0, column=0, sticky=tk.W)
            return

        for row, spec in enumerate(specs):
            ttk.Label(self.tech_param_frame, text=spec.label).grid(
                row=row, column=0, sticky=tk.W, pady=2
            )
            unit_group = _unit_group_for_key(spec.key)
            if unit_group is None:
                value_frame = ttk.Frame(self.tech_param_frame)
                value_frame.grid(row=row, column=1, sticky=tk.EW, pady=2, padx=(8, 0))
                value_frame.columnconfigure(0, weight=1)
                entry = ttk.Entry(
                    value_frame,
                    textvariable=self._tech_param_vars[spec.key],
                    width=20,
                )
                entry.grid(row=0, column=0, sticky=tk.EW)
                self._bind_entry_commit(entry, "edge")
                self._create_sweep_checkbutton(value_frame, 1, "edge", spec.key)
                self._create_batch_checkbutton(value_frame, 2, "edge", spec.key)
                continue

            value_frame = ttk.Frame(self.tech_param_frame)
            value_frame.grid(row=row, column=1, sticky=tk.EW, pady=2, padx=(8, 0))
            value_frame.columnconfigure(0, weight=1)
            entry = ttk.Entry(
                value_frame,
                textvariable=self._tech_param_vars[spec.key],
                width=20,
            )
            entry.grid(row=0, column=0, sticky=tk.EW)
            self._bind_entry_commit(entry, "edge")
            unit_combo = ttk.Combobox(
                value_frame,
                textvariable=self._unit_vars[spec.key],
                values=UNIT_OPTIONS[unit_group],
                state="readonly",
                width=13,
            )
            unit_combo.grid(row=0, column=1, sticky=tk.E, padx=(6, 0))
            self._bind_combobox_mousewheel(unit_combo)
            unit_combo.bind(
                "<<ComboboxSelected>>",
                lambda _event, key=spec.key: self._on_unit_change(key, "edge"),
            )
            self._create_sweep_checkbutton(value_frame, 2, "edge", spec.key)
            self._create_batch_checkbutton(value_frame, 3, "edge", spec.key)
        self.tech_param_frame.columnconfigure(1, weight=1)
        self._sync_sweep_checkboxes()
        self._sync_batch_checkboxes()

    def load_example(self) -> None:
        self._load_network(build_default_network())
        self.calculate(show_success=False)

    def _load_network(self, network: NetworkSpec) -> None:
        self.node_rows = [_node_to_row(node) for node in network.nodes]
        self.edge_rows = [_edge_to_row(edge) for edge in network.edges]
        self._ensure_node_positions()
        self._refresh_node_tree()
        self._refresh_edge_tree()
        self._refresh_node_combos()
        self._update_dashboard_summary()
        self._select_first_rows()
        self._sync_sweep_checkboxes()
        self._sync_batch_checkboxes()
        self._refresh_batch_field_tree()
        self._refresh_sweep_variable_tree()

    def _select_first_rows(self) -> None:
        if self.node_rows:
            self.node_tree.selection_set("0")
            self.node_tree.focus("0")
            self._populate_node_form(0)
            self.selected_node_id = self.node_rows[0]["node_id"]
        if self.edge_rows:
            self.edge_tree.selection_set("0")
            self.edge_tree.focus("0")
            self._populate_edge_form(0)
        self._redraw_layout_canvas()

    def _refresh_node_tree(self) -> None:
        self.node_tree.delete(*self.node_tree.get_children())
        for index, row in enumerate(self.node_rows):
            values = (
                row["node_id"],
                row["kind"],
                _fmt_row_si(row, "inlet_mdot"),
                _fmt_row_si(row, "inlet_temperature"),
                _fmt_row_si(row, "inlet_pressure"),
            )
            self.node_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=values,
            )

    def _refresh_edge_tree(self) -> None:
        self.edge_tree.delete(*self.edge_tree.get_children())
        columns = tuple(self.edge_tree["columns"])
        for index, row in enumerate(self.edge_rows):
            if columns == ("edge_id", "route", "tech", "tag", "length"):
                values = (
                    row["edge_id"],
                    f'{row["from_node"]} -> {row["to_node"]}',
                    row["cooling_technology"],
                    row.get("tag", TAG_OPTIONS[0]),
                    _fmt_row_si(row, "length"),
                )
            elif columns == ("edge_id", "route", "tech", "length"):
                values = (
                    row["edge_id"],
                    f'{row["from_node"]} -> {row["to_node"]}',
                    row["cooling_technology"],
                    _fmt_row_si(row, "length"),
                )
            elif "tag" in columns:
                values = (
                    row["edge_id"],
                    f'{row["from_node"]} -> {row["to_node"]}',
                    row["cooling_technology"],
                    row.get("tag", TAG_OPTIONS[0]),
                    _fmt_row_si(row, "length"),
                    _fmt_row_si(row, "width"),
                    _fmt_row_si(row, "height"),
                    _fmt_row_si(row, "diameter"),
                )
            else:
                values = (
                    row["edge_id"],
                    f'{row["from_node"]} -> {row["to_node"]}',
                    row["cooling_technology"],
                    _fmt_row_si(row, "length"),
                    _fmt_row_si(row, "width"),
                    _fmt_row_si(row, "height"),
                    _fmt_row_si(row, "diameter"),
                )
            self.edge_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=values,
            )
        self._refresh_dashboard_map()
        self._redraw_layout_canvas()
        if hasattr(self, "sweep_objective_edge_combo"):
            self._update_sweep_objective_controls(preserve_metric=True)

    def _refresh_dashboard_map(self) -> None:
        if not hasattr(self, "dashboard_map_tree"):
            return
        self.dashboard_map_tree.delete(*self.dashboard_map_tree.get_children())
        for row in self.edge_rows:
            self.dashboard_map_tree.insert(
                "",
                tk.END,
                values=(
                    row["edge_id"],
                    f'{row["from_node"]} -> {row["to_node"]}',
                    row["cooling_technology"],
                ),
            )

    def _refresh_node_combos(self) -> None:
        values = tuple(row["node_id"] for row in self.node_rows)
        self.edge_from_combo.configure(values=values)
        self.edge_to_combo.configure(values=values)
        if hasattr(self, "sweep_objective_node_combo"):
            self._update_sweep_objective_controls()

    def _update_sweep_objective_controls(
        self,
        preserve_metric: bool = False,
    ) -> None:
        if not hasattr(self, "sweep_objective_metric_combo"):
            return
        node_values = tuple(row["node_id"] for row in self.node_rows)
        edge_values = tuple(row["edge_id"] for row in self.edge_rows)
        self.sweep_objective_node_combo.configure(values=node_values)
        self.sweep_objective_edge_combo.configure(values=edge_values)
        if node_values and self.sweep_objective_node.get() not in node_values:
            self.sweep_objective_node.set(node_values[0])
        if edge_values and self.sweep_objective_edge.get() not in edge_values:
            self.sweep_objective_edge.set(edge_values[0])

        scope = self.sweep_objective_scope.get()
        if scope == "Node":
            metrics = NODE_OBJECTIVE_METRICS
            node_state = "readonly"
            edge_state = tk.DISABLED
        elif scope == "Edge":
            metrics = self._edge_metric_options(self.sweep_objective_edge.get())
            node_state = tk.DISABLED
            edge_state = "readonly"
        else:
            metrics = GLOBAL_OBJECTIVE_METRICS
            node_state = tk.DISABLED
            edge_state = tk.DISABLED
        self.sweep_objective_node_combo.configure(state=node_state)
        self.sweep_objective_edge_combo.configure(state=edge_state)
        self.sweep_objective_metric_combo.configure(values=metrics)
        if not preserve_metric or self.sweep_objective_metric.get() not in metrics:
            self.sweep_objective_metric.set(metrics[0] if metrics else "")

    def _edge_metric_options(self, edge_id: str) -> tuple[str, ...]:
        metrics = list(EDGE_BASE_OBJECTIVE_METRICS)
        if self.last_result is not None and edge_id in self.last_result.edges:
            edge = self.last_result.edges[edge_id]
            for key, value in edge.intermediate.items():
                if isinstance(value, (int, float)) and key not in metrics:
                    metrics.append(key)
        return tuple(metrics)

    def _refresh_sweep_variable_tree(self) -> None:
        if not hasattr(self, "sweep_variable_tree"):
            return
        self.sweep_variable_tree.delete(*self.sweep_variable_tree.get_children())
        for target_id, variable in self.sweep_variables.items():
            self.sweep_variable_tree.insert(
                "",
                tk.END,
                iid=target_id,
                values=(
                    variable.label,
                    self._current_sweep_display_value(variable),
                    variable.start,
                    variable.end,
                    variable.step,
                    variable.unit,
                ),
            )
        if (
            self._selected_sweep_variable_id
            and self._selected_sweep_variable_id in self.sweep_variables
        ):
            self.sweep_variable_tree.selection_set(self._selected_sweep_variable_id)
        self._update_sweep_case_count()
        self._update_sweep_plot_variable_combos()

    def _on_sweep_variable_select(self, _event: tk.Event) -> None:
        selection = self.sweep_variable_tree.selection()
        if not selection:
            return
        target_id = selection[0]
        variable = self.sweep_variables.get(target_id)
        if variable is None:
            return
        self._selected_sweep_variable_id = target_id
        self.sweep_selected_variable_label.configure(text=variable.label)
        self.sweep_range_start.set(variable.start)
        self.sweep_range_end.set(variable.end)
        self.sweep_range_step.set(variable.step)
        if variable.unit_group is None:
            self.sweep_range_unit_combo.configure(values=(), state=tk.DISABLED)
            self.sweep_range_unit.set("")
        else:
            self.sweep_range_unit_combo.configure(
                values=UNIT_OPTIONS[variable.unit_group],
                state="readonly",
            )
            if variable.unit not in UNIT_OPTIONS[variable.unit_group]:
                variable.unit = UNIT_OPTIONS[variable.unit_group][0]
            self.sweep_range_unit.set(variable.unit)

    def _apply_sweep_range(self) -> None:
        target_id = self._selected_sweep_variable_id
        if target_id is None or target_id not in self.sweep_variables:
            messagebox.showwarning("No sweep variable", "Select a sweep variable first.")
            return
        variable = self.sweep_variables[target_id]
        variable.start = self.sweep_range_start.get().strip()
        variable.end = self.sweep_range_end.get().strip()
        variable.step = self.sweep_range_step.get().strip()
        if variable.unit_group is not None:
            unit = self.sweep_range_unit.get().strip()
            if unit not in UNIT_OPTIONS[variable.unit_group]:
                messagebox.showerror("Invalid unit", "Select a valid unit for the sweep range.")
                return
            variable.unit = unit
        self._refresh_sweep_variable_tree()

    def _remove_selected_sweep_variable(self) -> None:
        target_id = self._selected_sweep_variable_id
        if target_id is None:
            return
        self.sweep_variables.pop(target_id, None)
        self._selected_sweep_variable_id = None
        self.sweep_selected_variable_label.configure(
            text="Select a sweep variable to edit its range."
        )
        self.sweep_range_start.set("")
        self.sweep_range_end.set("")
        self.sweep_range_step.set("")
        self.sweep_range_unit.set("")
        self._sync_sweep_checkboxes()
        self._refresh_sweep_variable_tree()

    def _clear_sweep_variables(self) -> None:
        self.sweep_variables.clear()
        self._selected_sweep_variable_id = None
        self._sync_sweep_checkboxes()
        self._refresh_sweep_variable_tree()

    def _update_sweep_case_count(self) -> None:
        if not hasattr(self, "sweep_case_count_label"):
            return
        if not self.sweep_variables:
            self.sweep_case_count_label.configure(text="Total cases: 0")
            return
        try:
            count = 1
            for variable in self.sweep_variables.values():
                count *= len(_sweep_display_values(variable.start, variable.end, variable.step))
        except ValueError:
            self.sweep_case_count_label.configure(text="Total cases: incomplete range")
            return
        self.sweep_case_count_label.configure(text=f"Total cases: {count:,}")

    def stop_sweep(self) -> None:
        self._sweep_cancel_requested = True
        if hasattr(self, "sweep_status_label"):
            self.sweep_status_label.configure(text="Stopping...")

    def run_sweep(self) -> None:
        self._commit_focused_form()
        self._apply_sweep_range_if_selected()
        if not self.sweep_variables:
            messagebox.showwarning("No sweep variables", "Select at least one sweep variable.")
            return

        try:
            sweep_grid = self._build_sweep_grid()
            constraints = self._read_sweep_constraints()
        except ValueError as exc:
            messagebox.showerror("Invalid sweep setup", str(exc))
            return

        total_cases = 1
        for values in sweep_grid.values():
            total_cases *= len(values)
        if total_cases <= 0:
            messagebox.showerror("Invalid sweep setup", "Sweep range produced no cases.")
            return

        baseline_node_rows = deepcopy(self.node_rows)
        baseline_edge_rows = deepcopy(self.edge_rows)
        variables = list(self.sweep_variables.values())
        objective_direction = self.sweep_direction.get()
        objective_label = self._objective_label()

        self._sweep_cancel_requested = False
        self.sweep_progress.configure(maximum=total_cases, value=0)
        self.sweep_status_label.configure(text=f"Running 0 / {total_cases:,}")
        self.sweep_results = []
        best_record: dict[str, Any] | None = None
        warnings: list[str] = []

        for case_index, combination in enumerate(product(*sweep_grid.values()), start=1):
            if self._sweep_cancel_requested:
                break
            node_rows = deepcopy(baseline_node_rows)
            edge_rows = deepcopy(baseline_edge_rows)
            variable_values: dict[str, float] = {}
            try:
                for variable, value_si in zip(variables, combination):
                    self._apply_sweep_value(node_rows, edge_rows, variable, value_si)
                    variable_values[variable.label] = self._value_for_variable_unit(
                        value_si,
                        variable,
                    )
                network = self._build_network_from_data(node_rows, edge_rows)
                result = self._solve_network(network)
                objective_value = self._read_objective_value(result)
                global_metrics = _global_result_metrics(result)
                feasible, constraint_text = _constraints_pass(global_metrics, constraints)
                record = {
                    "case": case_index,
                    "objective": objective_value,
                    "objective_label": objective_label,
                    "feasible": feasible,
                    "constraint": constraint_text,
                    "total_dp": global_metrics["total_dp"],
                    "outlet_T": global_metrics["outlet_T"],
                    "max_wall_T": global_metrics["max_wall_T"],
                    "status": "OK",
                    **variable_values,
                }
                if feasible and _is_better_record(
                    record,
                    best_record,
                    objective_direction,
                ):
                    best_record = record
            except Exception as exc:
                record = {
                    "case": case_index,
                    "objective": None,
                    "objective_label": objective_label,
                    "feasible": False,
                    "constraint": str(exc),
                    "total_dp": None,
                    "outlet_T": None,
                    "max_wall_T": None,
                    "status": "FAILED",
                    **variable_values,
                }
                warnings.append(f"Case {case_index}: {exc}")
            self.sweep_results.append(record)
            self.sweep_progress.configure(value=case_index)
            self.sweep_status_label.configure(
                text=f"Running {case_index:,} / {total_cases:,}"
            )
            self.update_idletasks()
            self.update()

        stopped = self._sweep_cancel_requested
        self._sweep_cancel_requested = False
        self._show_sweep_results(best_record, warnings, stopped)

    def _apply_sweep_range_if_selected(self) -> None:
        if (
            self._selected_sweep_variable_id
            and self._selected_sweep_variable_id in self.sweep_variables
        ):
            variable = self.sweep_variables[self._selected_sweep_variable_id]
            variable.start = self.sweep_range_start.get().strip()
            variable.end = self.sweep_range_end.get().strip()
            variable.step = self.sweep_range_step.get().strip()
            if variable.unit_group is not None and self.sweep_range_unit.get():
                variable.unit = self.sweep_range_unit.get()

    def _build_sweep_grid(self) -> dict[str, list[float]]:
        grid: dict[str, list[float]] = {}
        for variable in self.sweep_variables.values():
            display_values = _sweep_display_values(
                variable.start,
                variable.end,
                variable.step,
            )
            if variable.unit_group is None:
                grid[variable.target_id] = display_values
            else:
                grid[variable.target_id] = [
                    _to_si(value, variable.unit_group, variable.unit)
                    for value in display_values
                ]
        return grid

    def _read_sweep_constraints(self) -> dict[str, tuple[float | None, float | None]]:
        constraints: dict[str, tuple[float | None, float | None]] = {}
        for key, enabled in self._constraint_enabled.items():
            if not enabled.get():
                continue
            _label, unit_group = CONSTRAINT_SPECS[key]
            unit = self._constraint_units[key].get()
            min_value = _optional_float(self._constraint_min[key].get())
            max_value = _optional_float(self._constraint_max[key].get())
            if min_value is None and max_value is None:
                raise ValueError(f"{CONSTRAINT_SPECS[key][0]} constraint needs min or max.")
            constraints[key] = (
                _to_si(min_value, unit_group, unit) if min_value is not None else None,
                _to_si(max_value, unit_group, unit) if max_value is not None else None,
            )
        return constraints

    def _apply_sweep_value(
        self,
        node_rows: list[dict[str, str]],
        edge_rows: list[dict[str, str]],
        variable: SweepVariable,
        value_si: float,
    ) -> None:
        if variable.scope == "node":
            row = next(
                (item for item in node_rows if item["node_id"] == variable.object_id),
                None,
            )
        else:
            row = next(
                (item for item in edge_rows if item["edge_id"] == variable.object_id),
                None,
            )
        if row is None:
            raise ValueError(f"Sweep target not found: {variable.label}")
        if variable.unit_group is None:
            row[variable.row_key] = _fmt_optional(value_si)
            return
        row_unit = row.get(_unit_row_key(variable.field_key), _default_unit_for_key(variable.field_key))
        row[variable.row_key] = _fmt_optional(
            _from_si(value_si, variable.unit_group, row_unit)
        )

    def _value_for_variable_unit(
        self,
        value_si: float,
        variable: SweepVariable,
    ) -> float:
        if variable.unit_group is None:
            return value_si
        return _from_si(value_si, variable.unit_group, variable.unit)

    def _solve_network(self, network: NetworkSpec) -> SolverResult:
        property_model = self.property_model.get()
        try:
            return FixedFlowSolver(
                network,
                SolverOptions(property_model=property_model),
            ).solve()
        except RuntimeError as exc:
            if property_model != "coolprop" or "CoolProp" not in str(exc):
                raise
            return FixedFlowSolver(
                network,
                SolverOptions(property_model="ideal_gas"),
            ).solve()

    def _read_objective_value(self, result: SolverResult) -> float:
        scope = self.sweep_objective_scope.get()
        metric = self.sweep_objective_metric.get()
        if scope == "Global":
            metrics = _global_result_metrics(result)
            if metric not in metrics:
                raise ValueError(f"Unknown global objective metric: {metric}")
            return metrics[metric]
        if scope == "Node":
            node_id = self.sweep_objective_node.get()
            if node_id not in result.nodes:
                raise ValueError(f"Objective node not found: {node_id}")
            node = result.nodes[node_id]
            if not hasattr(node, metric):
                raise ValueError(f"Unknown node objective metric: {metric}")
            return float(getattr(node, metric))
        edge_id = self.sweep_objective_edge.get()
        if edge_id not in result.edges:
            raise ValueError(f"Objective edge not found: {edge_id}")
        edge = result.edges[edge_id]
        if hasattr(edge, metric):
            return float(getattr(edge, metric))
        if metric in edge.intermediate:
            return float(edge.intermediate[metric])
        raise ValueError(f"Unknown edge objective metric: {metric}")

    def _objective_label(self) -> str:
        scope = self.sweep_objective_scope.get()
        metric = self.sweep_objective_metric.get()
        if scope == "Global":
            return f"Global / {metric}"
        if scope == "Node":
            return f"Node {self.sweep_objective_node.get()} / {metric}"
        return f"Edge {self.sweep_objective_edge.get()} / {metric}"

    def _show_sweep_results(
        self,
        best_record: dict[str, Any] | None,
        warnings: list[str],
        stopped: bool,
    ) -> None:
        if stopped:
            self.sweep_status_label.configure(
                text=f"Stopped after {len(self.sweep_results):,} cases"
            )
        else:
            self.sweep_status_label.configure(
                text=f"Done: {len(self.sweep_results):,} cases"
            )
        if best_record is None:
            message = "No feasible case found." if self.sweep_results else "No sweep result."
            if stopped:
                message = f"Stopped. {message}"
            self._set_sweep_best_rows([("Status", message)])
        else:
            rows = [
                ("Case", str(best_record["case"])),
                ("Objective", best_record["objective_label"]),
                ("Objective value", _fmt_sweep_value(best_record["objective"])),
                ("Feasible", str(best_record["feasible"])),
                ("Constraint", best_record["constraint"]),
                ("Total dp [Pa]", _fmt_sweep_value(best_record["total_dp"])),
                ("Outlet T [K]", _fmt_sweep_value(best_record["outlet_T"])),
                ("Max wall T [K]", _fmt_sweep_value(best_record["max_wall_T"])),
            ]
            for variable in self.sweep_variables.values():
                if variable.label in best_record:
                    suffix = f" [{variable.unit}]" if variable.unit else ""
                    rows.append(
                        (
                            f"{variable.label}{suffix}",
                            _fmt_sweep_value(best_record[variable.label]),
                        )
                    )
            self._set_sweep_best_rows(rows)

        self._show_sweep_result_table()
        self._update_sweep_plot_variable_combos()
        self._update_sweep_plot()
        if warnings:
            self._show_warnings(warnings[:200])

    def _set_sweep_best_rows(self, rows: list[tuple[str, str]]) -> None:
        if not hasattr(self, "sweep_best_tree"):
            return
        self.sweep_best_tree.delete(*self.sweep_best_tree.get_children())
        for index, (item, value) in enumerate(rows):
            self.sweep_best_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(item, value),
            )

    def _show_sweep_result_table(self) -> None:
        variable_labels = [variable.label for variable in self.sweep_variables.values()]
        columns = (
            "case",
            "status",
            "feasible",
            "objective",
            *variable_labels,
            "total_dp",
            "outlet_T",
            "max_wall_T",
            "constraint",
        )
        self._set_sweep_result_columns(list(columns))
        for index, record in enumerate(self.sweep_results):
            values = []
            for column in columns:
                value = record.get(column)
                if column in {"case", "status", "feasible", "constraint"}:
                    values.append(str(value))
                else:
                    values.append(_fmt_sweep_value(value))
            self.sweep_result_tree.insert("", tk.END, iid=str(index), values=values)

    def _set_sweep_result_columns(self, columns: list[str]) -> None:
        if not hasattr(self, "sweep_result_tree"):
            return
        self.sweep_result_tree.delete(*self.sweep_result_tree.get_children())
        if not columns:
            columns = ["status"]
        self.sweep_result_tree.configure(columns=columns)
        for column in columns:
            heading = column
            if column == "total_dp":
                heading = "total_dp [Pa]"
            elif column == "outlet_T":
                heading = "outlet_T [K]"
            elif column == "max_wall_T":
                heading = "max_wall_T [K]"
            self.sweep_result_tree.heading(column, text=heading)
            width = 120 if column not in {"constraint"} else 220
            if column in {"case", "status", "feasible"}:
                width = 80
            self.sweep_result_tree.column(column, width=width, anchor=tk.W)

    def _update_sweep_plot_variable_combos(self) -> None:
        if not hasattr(self, "sweep_plot_x_combo"):
            return
        labels = tuple(variable.label for variable in self.sweep_variables.values())
        self.sweep_plot_x_combo.configure(values=labels)
        self.sweep_plot_y_combo.configure(values=labels)
        if labels and self.sweep_plot_x.get() not in labels:
            self.sweep_plot_x.set(labels[0])
        if len(labels) > 1 and self.sweep_plot_y.get() not in labels:
            self.sweep_plot_y.set(labels[1])
        elif len(labels) <= 1:
            self.sweep_plot_y.set("")

    def _update_sweep_plot(self) -> None:
        if not hasattr(self, "sweep_plot_frame"):
            return
        for child in self.sweep_plot_frame.winfo_children():
            child.destroy()
        if not self.sweep_results:
            ttk.Label(
                self.sweep_plot_frame,
                text="Run a sweep to view response plots.",
                style="Header.TLabel",
            ).pack(anchor=tk.CENTER, expand=True)
            return
        if Figure is None or FigureCanvasTkAgg is None:
            ttk.Label(
                self.sweep_plot_frame,
                text="matplotlib is required for sweep plots.",
                style="Header.TLabel",
            ).pack(anchor=tk.CENTER, expand=True)
            return

        variable_labels = [variable.label for variable in self.sweep_variables.values()]
        numeric_records = [
            record
            for record in self.sweep_results
            if isinstance(record.get("objective"), (int, float))
        ]
        if not variable_labels or not numeric_records:
            ttk.Label(
                self.sweep_plot_frame,
                text="No numeric sweep results to plot.",
                style="Header.TLabel",
            ).pack(anchor=tk.CENTER, expand=True)
            return

        plot_type = self.sweep_plot_type.get()
        if plot_type == "Auto":
            plot_type = "Line" if len(variable_labels) == 1 else "Heatmap"
        x_label = self.sweep_plot_x.get() or variable_labels[0]
        y_label = self.sweep_plot_y.get() or (
            variable_labels[1] if len(variable_labels) > 1 else ""
        )
        figure = Figure(figsize=(6.8, 4.1), dpi=110, facecolor="#fbfcfe")
        if plot_type == "Surface" and len(variable_labels) > 1 and y_label:
            axis = figure.add_subplot(111, projection="3d")
            self._draw_sweep_surface(axis, numeric_records, x_label, y_label)
        elif plot_type == "Heatmap" and len(variable_labels) > 1 and y_label:
            axis = figure.add_subplot(111)
            image = self._draw_sweep_heatmap(axis, numeric_records, x_label, y_label)
            if image is not None:
                figure.colorbar(image, ax=axis, shrink=0.82)
        elif plot_type == "Scatter" and len(variable_labels) > 1 and y_label:
            axis = figure.add_subplot(111)
            scatter = axis.scatter(
                [float(record[x_label]) for record in numeric_records],
                [float(record[y_label]) for record in numeric_records],
                c=[float(record["objective"]) for record in numeric_records],
                cmap="viridis",
                edgecolors="#111827",
                linewidths=0.3,
            )
            axis.set_xlabel(x_label)
            axis.set_ylabel(y_label)
            axis.set_title(self._objective_label())
            figure.colorbar(scatter, ax=axis, shrink=0.82)
        else:
            axis = figure.add_subplot(111)
            sorted_records = sorted(numeric_records, key=lambda record: float(record[x_label]))
            axis.plot(
                [float(record[x_label]) for record in sorted_records],
                [float(record["objective"]) for record in sorted_records],
                marker="o",
                color=ACCENT_COLOR,
            )
            axis.set_xlabel(x_label)
            axis.set_ylabel("Objective")
            axis.set_title(self._objective_label())
        figure.tight_layout()
        canvas = FigureCanvasTkAgg(figure, master=self.sweep_plot_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._sweep_plot_canvas = canvas

    def _draw_sweep_heatmap(
        self,
        axis: Any,
        records: list[dict[str, Any]],
        x_label: str,
        y_label: str,
    ) -> Any:
        x_values, y_values, z_grid = _sweep_grid_from_records(
            records,
            x_label,
            y_label,
            self.sweep_direction.get(),
        )
        if not x_values or not y_values:
            axis.text(0.5, 0.5, "Not enough data", ha="center", va="center")
            return None
        image = axis.imshow(
            z_grid,
            origin="lower",
            aspect="auto",
            cmap="viridis",
            extent=(min(x_values), max(x_values), min(y_values), max(y_values)),
        )
        axis.set_xlabel(x_label)
        axis.set_ylabel(y_label)
        axis.set_title(self._objective_label())
        return image

    def _draw_sweep_surface(
        self,
        axis: Any,
        records: list[dict[str, Any]],
        x_label: str,
        y_label: str,
    ) -> None:
        x_values, y_values, z_grid = _sweep_grid_from_records(
            records,
            x_label,
            y_label,
            self.sweep_direction.get(),
        )
        if not x_values or not y_values:
            axis.text2D(0.5, 0.5, "Not enough data", ha="center", va="center")
            return
        try:
            import numpy as np
        except ImportError:
            axis.text2D(0.5, 0.5, "numpy is required for surface plots", ha="center", va="center")
            return
        x_mesh = [[x for x in x_values] for _y in y_values]
        y_mesh = [[y for _x in x_values] for y in y_values]
        axis.plot_surface(
            np.array(x_mesh),
            np.array(y_mesh),
            np.array(z_grid),
            cmap="viridis",
            edgecolor="none",
        )
        axis.set_xlabel(x_label)
        axis.set_ylabel(y_label)
        axis.set_zlabel("Objective")
        axis.set_title(self._objective_label())

    def _on_node_select(self, _event: tk.Event) -> None:
        index = self._selected_index(self.node_tree)
        if index is not None:
            self.selected_node_id = self.node_rows[index]["node_id"]
            self.selected_edge_id = None
            self.selected_layout_edge_ids.clear()
            self._populate_node_form(index)
            self._update_selected_result_panel()
            self._update_batch_status()
            self._redraw_layout_canvas()

    def _on_edge_select(self, _event: tk.Event) -> None:
        index = self._selected_index(self.edge_tree)
        if index is not None:
            edge_id = self.edge_rows[index]["edge_id"]
            self.selected_edge_id = edge_id
            self.selected_node_id = None
            if edge_id not in self.selected_layout_edge_ids:
                self.selected_layout_edge_ids.clear()
            self._populate_edge_form(index)
            self._update_selected_result_panel()
            self._update_batch_status()
            self._redraw_layout_canvas()

    def _populate_node_form(self, index: int) -> None:
        row = self.node_rows[index]
        self._suppress_auto_apply = True
        try:
            self._set_unit_vars_from_row(row, NODE_UNIT_KEYS)
            for key, variable in self._node_vars.items():
                variable.set(row.get(key, ""))
        finally:
            self._suppress_auto_apply = False
        self._update_node_field_visibility()
        self._sync_sweep_checkboxes()

    def _populate_edge_form(self, index: int) -> None:
        row = self.edge_rows[index]
        self._syncing_edge_form = True
        self._suppress_auto_apply = True
        try:
            self._set_unit_vars_from_row(row, EDGE_UNIT_KEYS)
            for key, variable in self._edge_vars.items():
                variable.set(row.get(key, TAG_OPTIONS[0] if key == "tag" else ""))
            for key, variable in self._tech_param_vars.items():
                variable.set(row.get(_param_row_key(key), ""))
        finally:
            self._suppress_auto_apply = False
            self._syncing_edge_form = False
        self._apply_param_defaults(row["cooling_technology"])
        self._render_tech_params(row["cooling_technology"])
        self._update_shape_visibility()
        self._update_wall_field_visibility()
        self.params_text.delete("1.0", tk.END)
        self.params_text.insert("1.0", row["params_text"])
        self._sync_sweep_checkboxes()
        self._sync_batch_checkboxes()

    def apply_node(self) -> None:
        index = self._selected_index(self.node_tree)
        if index is None:
            messagebox.showwarning("No selection", "Select a node first.")
            return
        old_id = self.node_rows[index]["node_id"]
        row = {key: variable.get().strip() for key, variable in self._node_vars.items()}
        row.update(self._unit_row_values(NODE_UNIT_KEYS))
        if not row["node_id"]:
            messagebox.showerror("Invalid node", "Node ID is required.")
            return
        if self._id_exists(row["node_id"], self.node_rows, index, "node_id"):
            messagebox.showerror("Invalid node", "Node ID must be unique.")
            return
        if row["kind"] != "inlet":
            row["inlet_mdot"] = ""
            row["inlet_temperature"] = ""
            row["inlet_pressure"] = ""
        self.node_rows[index] = row
        if row["node_id"] != old_id:
            if old_id in self.node_positions:
                self.node_positions[row["node_id"]] = self.node_positions.pop(old_id)
            for edge in self.edge_rows:
                if edge["from_node"] == old_id:
                    edge["from_node"] = row["node_id"]
                if edge["to_node"] == old_id:
                    edge["to_node"] = row["node_id"]
        self._ensure_node_positions()
        self._refresh_node_tree()
        self._refresh_edge_tree()
        self._refresh_node_combos()
        self._update_dashboard_summary()
        self.node_tree.selection_set(str(index))
        self._after_apply()

    def add_node(self) -> None:
        node_id = self._next_id("N", {row["node_id"] for row in self.node_rows})
        self.node_rows.append(
            {
                "node_id": node_id,
                "kind": "internal",
                "inlet_mdot": "",
                "inlet_temperature": "",
                "inlet_pressure": "",
                **_unit_defaults_for_keys(NODE_UNIT_KEYS),
            }
        )
        self._ensure_node_positions()
        self._refresh_node_tree()
        self._refresh_node_combos()
        self._update_dashboard_summary()
        self._redraw_layout_canvas()
        index = len(self.node_rows) - 1
        self.node_tree.selection_set(str(index))
        self._populate_node_form(index)
        self._after_apply()

    def delete_node(self) -> None:
        index = self._selected_index(self.node_tree)
        if index is None:
            messagebox.showwarning("No selection", "Select a node first.")
            return
        node_id = self.node_rows[index]["node_id"]
        del self.node_rows[index]
        self.edge_rows = [
            edge
            for edge in self.edge_rows
            if edge["from_node"] != node_id and edge["to_node"] != node_id
        ]
        valid_edge_ids = {edge["edge_id"] for edge in self.edge_rows}
        self.selected_layout_edge_ids.intersection_update(valid_edge_ids)
        self.node_positions.pop(node_id, None)
        self.selected_node_id = None
        self.selected_edge_id = None
        self._ensure_node_positions()
        self._refresh_node_tree()
        self._refresh_edge_tree()
        self._refresh_node_combos()
        self._update_dashboard_summary()
        self._update_selected_result_panel()
        self._update_batch_status()
        self._redraw_layout_canvas()
        self._after_apply()

    def apply_edge(self) -> None:
        index = self._selected_index(self.edge_tree)
        if index is None:
            messagebox.showwarning("No selection", "Select an edge first.")
            return
        row = self._edge_form_to_row()
        if not row["edge_id"]:
            messagebox.showerror("Invalid edge", "Edge ID is required.")
            return
        if self._id_exists(row["edge_id"], self.edge_rows, index, "edge_id"):
            messagebox.showerror("Invalid edge", "Edge ID must be unique.")
            return
        self.edge_rows[index] = row
        self.selected_edge_id = row["edge_id"]
        self.selected_node_id = None
        self._convert_source_outlet_to_internal(row["from_node"])
        self._refresh_edge_tree()
        self._refresh_node_tree()
        self._update_dashboard_summary()
        self.edge_tree.selection_set(str(index))
        self._after_apply()

    def add_edge(self) -> None:
        node_ids = [row["node_id"] for row in self.node_rows]
        if len(node_ids) < 2:
            messagebox.showerror("Need nodes", "Add at least two nodes first.")
            return
        from_node = self._edge_vars["from_node"].get().strip() or node_ids[0]
        to_node = self._edge_vars["to_node"].get().strip() or node_ids[1]
        if from_node not in node_ids or to_node not in node_ids or from_node == to_node:
            from_node, to_node = node_ids[0], node_ids[1]
        edge_id = _unique_id(
            f"{from_node}_to_{to_node}".replace(" ", "_"),
            {row["edge_id"] for row in self.edge_rows},
        )
        self.edge_rows.append(self._default_edge_row(edge_id, from_node, to_node))
        self._convert_source_outlet_to_internal(from_node)
        self._refresh_edge_tree()
        self._refresh_node_tree()
        self._update_dashboard_summary()
        index = len(self.edge_rows) - 1
        self.edge_tree.selection_set(str(index))
        self._populate_edge_form(index)
        self._after_apply()

    def delete_edge(self) -> None:
        index = self._selected_index(self.edge_tree)
        if index is None:
            messagebox.showwarning("No selection", "Select an edge first.")
            return
        del self.edge_rows[index]
        self.selected_edge_id = None
        valid_edge_ids = {edge["edge_id"] for edge in self.edge_rows}
        self.selected_layout_edge_ids.intersection_update(valid_edge_ids)
        self._refresh_edge_tree()
        self._update_dashboard_summary()
        self._update_selected_result_panel()
        self._update_batch_status()
        self._after_apply()

    def _edge_form_to_row(self) -> dict[str, str]:
        row = {key: variable.get().strip() for key, variable in self._edge_vars.items()}
        row["cooling_technology"] = _normalize_technology(row["cooling_technology"])
        if row["cooling_technology"] == "turning":
            row["shape"] = "rectangular"
            row["width"] = ""
            row["height"] = ""
            row["diameter"] = ""
        if row["shape"] == "rectangular":
            row["diameter"] = ""
        elif row["shape"] == "circular":
            row["width"] = ""
            row["height"] = ""
        if row["wall_mode"] != "wall_temperature":
            row["wall_temperature"] = ""
        if row["wall_mode"] != "heat_flux":
            row["heat_flux"] = ""
        if row["wall_mode"] != "external_convection":
            row["external_temperature"] = ""
            row["external_htc"] = ""
            row["wall_thickness"] = ""
            row["wall_conductivity"] = ""
            row["tbc_thickness"] = ""
            row["tbc_conductivity"] = ""
        row["flow_fraction"] = ""
        row["fixed_mdot"] = ""
        for key, variable in self._tech_param_vars.items():
            row[_param_row_key(key)] = variable.get().strip()
        row.update(self._unit_row_values(EDGE_UNIT_KEYS))
        row["params_text"] = self.params_text.get("1.0", tk.END).strip()
        return row

    def _after_apply(self) -> None:
        if self._suppress_stale_mark:
            return
        if self.auto_calculate.get():
            self.calculate(show_success=False)
        else:
            self._mark_results_stale()

    def _mark_results_stale(self) -> None:
        if self.last_result is None:
            return
        self.results_stale = True
        self._set_dashboard_status("OLD DATA", WARNING_COLOR, "#fff4df")
        self._set_dashboard_warning_text(
            ["Inputs changed after the last calculation. Press Calculate to refresh results."]
        )
        self._update_selected_result_panel()
        self._redraw_layout_canvas()

    def calculate(self, show_success: bool = True) -> None:
        self._commit_focused_form()
        try:
            network = self._build_network_from_rows()
            property_model = self.property_model.get()
            result = FixedFlowSolver(
                network,
                SolverOptions(property_model=property_model),
            ).solve()
        except RuntimeError as exc:
            if self.property_model.get() != "coolprop" or "CoolProp" not in str(exc):
                self._handle_calculation_error(exc, show_success)
                return
            fallback_warning = (
                "CoolProp is not installed. Ideal gas property model was used "
                "instead."
            )
            self.property_model.set("ideal_gas")
            try:
                result = FixedFlowSolver(
                    network,
                    SolverOptions(property_model="ideal_gas"),
                ).solve()
                result = SolverResult(
                    nodes=result.nodes,
                    edges=result.edges,
                    warnings=(fallback_warning, *result.warnings),
                    reference_temperature=result.reference_temperature,
                )
            except Exception as fallback_exc:
                self._handle_calculation_error(fallback_exc, show_success)
                return
            if show_success:
                messagebox.showwarning("CoolProp unavailable", fallback_warning)
        except Exception as exc:
            self._handle_calculation_error(exc, show_success)
            return

        self.last_result = result
        self.results_stale = False
        self._show_results(result)
        self._show_dashboard(result)
        self._show_warnings(result.warnings)
        if show_success:
            self.notebook.select(self.workspace_tab)

    def _handle_calculation_error(
        self,
        exc: Exception,
        show_success: bool,
    ) -> None:
        self.last_result = None
        self.results_stale = False
        self._show_dashboard_empty()
        self._set_dashboard_status("FAILED", DANGER_COLOR, "#fde7ea")
        self._set_dashboard_warning_text([f"Calculation failed: {exc}"])
        self._show_warnings([f"Calculation failed: {exc}"])
        self.notebook.select(self.warnings_tab)
        if show_success:
            messagebox.showerror("Calculation failed", str(exc))

    def _build_network_from_rows(self) -> NetworkSpec:
        return self._build_network_from_data(self.node_rows, self.edge_rows)

    def _build_network_from_data(
        self,
        node_rows: list[dict[str, str]],
        edge_rows: list[dict[str, str]],
    ) -> NetworkSpec:
        nodes = [
            NodeSpec(
                node_id=row["node_id"],
                kind=row["kind"],  # type: ignore[arg-type]
                inlet_mdot=_optional_si(row, "inlet_mdot") if row["kind"] == "inlet" else None,
                inlet_temperature=_optional_si(row, "inlet_temperature") if row["kind"] == "inlet" else None,
                inlet_pressure=_optional_si(row, "inlet_pressure") if row["kind"] == "inlet" else None,
            )
            for row in node_rows
        ]
        edges: list[EdgeSpec] = []
        for row in edge_rows:
            geometry = Geometry(
                length=_required_si(row, "length", f'{row["edge_id"]}.length'),
                shape=row["shape"],  # type: ignore[arg-type]
                width=_optional_si(row, "width"),
                height=_optional_si(row, "height"),
                diameter=_optional_si(row, "diameter"),
            )
            wall = WallBoundary(
                mode=row["wall_mode"],  # type: ignore[arg-type]
                wall_temperature=_optional_si(row, "wall_temperature"),
                heat_flux=_optional_si(row, "heat_flux"),
                external_htc=_optional_si(row, "external_htc"),
                external_temperature=_optional_si(row, "external_temperature"),
                wall_thickness=_optional_si(row, "wall_thickness"),
                wall_conductivity=_optional_si(row, "wall_conductivity"),
                tbc_thickness=_optional_si(row, "tbc_thickness"),
                tbc_conductivity=_optional_si(row, "tbc_conductivity"),
            )
            edges.append(
                EdgeSpec(
                    edge_id=row["edge_id"],
                    from_node=row["from_node"],
                    to_node=row["to_node"],
                    geometry=geometry,
                    cooling_technology=_normalize_technology(row["cooling_technology"]),  # type: ignore[arg-type]
                    wall=wall,
                    params=_params_from_row(row),
                    flow_fraction=None,
                    fixed_mdot=None,
                )
            )
        return NetworkSpec(nodes=nodes, edges=edges)

    def _show_results(self, result: SolverResult) -> None:
        self.node_result_tree.delete(*self.node_result_tree.get_children())
        for node in result.nodes.values():
            self.node_result_tree.insert(
                "",
                tk.END,
                values=(
                    node.node_id,
                    node.kind,
                    _fmt_number(node.mass_flow, 6),
                    _fmt_number(node.temperature, 2),
                    _fmt_number(node.pressure, 1),
                ),
            )

        self.edge_result_tree.delete(*self.edge_result_tree.get_children())
        for edge in result.edges.values():
            self.edge_result_tree.insert(
                "",
                tk.END,
                values=(
                    edge.edge_id,
                    edge.cooling_technology,
                    _fmt_number(edge.mass_flow, 6),
                    _fmt_number(edge.reynolds, 0),
                    _fmt_number(edge.nusselt, 2),
                    _fmt_number(edge.htc, 2),
                    _fmt_number(edge.friction_factor_darcy, 5),
                    _fmt_number(edge.dp_total, 1),
                    _fmt_number(edge.heat_rate, 1),
                    _fmt_number(float(edge.intermediate.get("heat_flux_w_m2", 0.0)), 1),
                    _fmt_optional(edge.intermediate.get("coolant_side_wall_temperature_k")),
                    _fmt_number(edge.outlet_temperature, 2),
                    _fmt_number(edge.outlet_pressure, 1),
                ),
            )
        self._update_selected_result_panel()
        self._redraw_layout_canvas()
        self._update_sweep_objective_controls(preserve_metric=True)

    def _update_selected_result_panel(self) -> None:
        if not hasattr(self, "selected_result_tree"):
            return
        self.selected_result_tree.delete(*self.selected_result_tree.get_children())
        self.wall_stack_canvas.delete(tk.ALL)
        if self.last_result is None:
            self._set_selected_result_rows(
                [("Status", "Run calculation to view edge results.")]
            )
            self._draw_wall_stack_placeholder("No result")
            return
        if not self.selected_edge_id or self.selected_edge_id not in self.last_result.edges:
            rows = []
            if self.results_stale:
                rows.append(("Status", "OLD DATA - inputs changed after last calculation."))
            rows.append(("Selection", "Select an edge on the layout or table."))
            self._set_selected_result_rows(rows)
            self._draw_wall_stack_placeholder("Select edge")
            return

        edge = self.last_result.edges[self.selected_edge_id]
        info = edge.intermediate
        rows = []
        if self.results_stale:
            rows.append(("Status", "OLD DATA - press Calculate to refresh."))
        rows.extend([
            ("Edge", f"{edge.edge_id} ({edge.from_node} -> {edge.to_node})"),
            ("Technology", edge.cooling_technology),
            ("m_dot [kg/s]", _fmt_number(edge.mass_flow, 6)),
            ("Tout [K]", _fmt_number(edge.outlet_temperature, 2)),
            ("Pout [Pa]", _fmt_number(edge.outlet_pressure, 1)),
            ("Re [-]", _fmt_number(edge.reynolds, 0)),
            ("Nu [-]", _fmt_number(edge.nusselt, 2)),
            ("h [W/m2-K]", _fmt_number(edge.htc, 1)),
            ("dp friction [Pa]", _fmt_number(edge.dp_friction, 1)),
            ("dp rotation [Pa]", _fmt_number(edge.dp_rotation, 1)),
            ("q [W]", _fmt_number(edge.heat_rate, 1)),
            ("q'' [W/m2]", _fmt_number(float(info.get("heat_flux_w_m2", 0.0)), 1)),
        ])
        if "coolant_side_wall_temperature_k" in info:
            rows.append(
                (
                    "Coolant wall T [K]",
                    _fmt_number(float(info["coolant_side_wall_temperature_k"]), 2),
                )
            )
        if info.get("wall_mode") == "external_convection":
            rows.extend([
                (
                    "Coolant bulk T [K]",
                    _fmt_number(
                        float(
                            info.get(
                                "coolant_bulk_temperature_k",
                                info["fluid_reference_temperature_k"],
                            )
                        ),
                        2,
                    ),
                ),
                ("External gas T [K]", _fmt_number(float(info["external_temperature_k"]), 2)),
                ("TBC outer T [K]", _fmt_number(float(info["tbc_outer_temperature_k"]), 2)),
                ("Metal outer T [K]", _fmt_number(float(info["metal_outer_temperature_k"]), 2)),
                ("R total [K/W]", _fmt_number(float(info["r_total_k_w"]), 6)),
            ])
        self._set_selected_result_rows(rows)
        self._draw_wall_stack(edge.intermediate)

    def _set_selected_result_rows(self, rows: list[tuple[str, str]]) -> None:
        for index, (item, value) in enumerate(rows):
            tags = ("stale",) if item == "Status" and "OLD DATA" in value else ()
            self.selected_result_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(item, value),
                tags=tags,
            )

    def _draw_wall_stack_placeholder(self, text: str) -> None:
        canvas = self.wall_stack_canvas
        canvas.create_text(
            max(canvas.winfo_width(), 360) / 2,
            72,
            text=text,
            fill=MUTED_COLOR,
            font=("Segoe UI", 12, "bold"),
        )

    def _draw_wall_stack(self, info: dict[str, Any]) -> None:
        canvas = self.wall_stack_canvas
        width = max(canvas.winfo_width(), 420)
        height = max(canvas.winfo_height(), 150)
        if info.get("wall_mode") != "external_convection":
            label = "Wall stack is available for external_convection mode."
            if "coolant_side_wall_temperature_k" in info:
                label = (
                    "Coolant-side wall T: "
                    f"{_fmt_number(float(info['coolant_side_wall_temperature_k']), 2)} K"
                )
            canvas.create_text(
                width / 2,
                height / 2,
                text=label,
                fill=MUTED_COLOR,
                font=("Segoe UI", 11, "bold"),
            )
            return

        layers = [
            ("Gas", float(info["external_temperature_k"])),
            ("TBC outer", float(info["tbc_outer_temperature_k"])),
            ("Metal outer", float(info["metal_outer_temperature_k"])),
            ("Coolant wall", float(info["coolant_side_wall_temperature_k"])),
            (
                "Coolant bulk",
                float(
                    info.get(
                        "coolant_bulk_temperature_k",
                        info["fluid_reference_temperature_k"],
                    )
                ),
            ),
        ]
        values = [temperature for _label, temperature in layers]
        margin = 16
        gap = 6
        usable_width = width - 2 * margin
        block_width = (usable_width - gap * (len(layers) - 1)) / len(layers)
        y0, y1 = 38, 104
        for index, (label, temperature) in enumerate(layers):
            x0 = margin + index * (block_width + gap)
            x1 = x0 + block_width
            fill = _value_to_color(temperature, values)
            text_color = _contrast_text_color(fill)
            canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline=BORDER_COLOR)
            canvas.create_text(
                (x0 + x1) / 2,
                y0 + 20,
                text=label,
                fill=text_color,
                font=("Segoe UI", 9, "bold"),
            )
            canvas.create_text(
                (x0 + x1) / 2,
                y0 + 44,
                text=f"{temperature:,.1f} K",
                fill=text_color,
                font=("Segoe UI", 9),
            )
        canvas.create_text(
            margin,
            18,
            text="1D thermal resistance stack: external gas -> TBC -> blade wall -> coolant",
            anchor=tk.W,
            fill=MUTED_COLOR,
            font=("Segoe UI", 10, "bold"),
        )

    def _update_dashboard_summary(self) -> None:
        if not hasattr(self, "_summary_labels"):
            return
        inlet_rows = [row for row in self.node_rows if row["kind"] == "inlet"]
        total_flow = 0.0
        for row in inlet_rows:
            try:
                value = _optional_si(row, "inlet_mdot")
            except ValueError:
                value = None
            if value is not None:
                total_flow += value
        values = {
            "nodes": str(len(self.node_rows)),
            "edges": str(len(self.edge_rows)),
            "inlets": str(len(inlet_rows)),
            "flow": f"{total_flow:,.6f} kg/s",
            "property_model": self.property_model.get(),
        }
        for key, value in values.items():
            self._summary_labels[key].configure(text=value)

    def _show_dashboard_empty(self) -> None:
        self._update_dashboard_summary()
        if hasattr(self, "dashboard_edge_tree"):
            self.dashboard_edge_tree.delete(*self.dashboard_edge_tree.get_children())
        if hasattr(self, "metric_labels"):
            for label in self.metric_labels.values():
                label.configure(text="-", fg=TEXT_COLOR)
        if hasattr(self, "dashboard_status_label"):
            self._set_dashboard_status("READY", SAFE_COLOR, "#e7f3ec")
        if hasattr(self, "dashboard_warning_text"):
            self._set_dashboard_warning_text(["No calculation has been run yet."])
        self._update_selected_result_panel()

    def _show_dashboard(self, result: SolverResult) -> None:
        self._update_dashboard_summary()
        if hasattr(self, "dashboard_edge_tree"):
            self.dashboard_edge_tree.delete(*self.dashboard_edge_tree.get_children())
            for edge in result.edges.values():
                self.dashboard_edge_tree.insert(
                    "",
                    tk.END,
                    values=(
                        edge.edge_id,
                        edge.cooling_technology,
                        _fmt_number(edge.reynolds, 0),
                        _fmt_number(edge.nusselt, 2),
                        _fmt_number(edge.htc, 1),
                        _fmt_number(edge.dp_total, 1),
                        _fmt_number(edge.outlet_temperature, 2),
                        _fmt_number(edge.outlet_pressure, 1),
                    ),
                )

        outlet_nodes = [
            node
            for node in result.nodes.values()
            if node.kind == "outlet" or not node.outgoing_edges
        ]
        inlet_pressures = [
            node.pressure for node in result.nodes.values() if node.kind == "inlet"
        ]
        outlet_pressure = min((node.pressure for node in outlet_nodes), default=0.0)
        outlet_mdot = sum(node.mass_flow for node in outlet_nodes)
        outlet_temperature = 0.0
        if outlet_mdot > 0.0:
            outlet_temperature = (
                sum(node.mass_flow * node.temperature for node in outlet_nodes)
                / outlet_mdot
            )
        total_dp = max(inlet_pressures, default=0.0) - outlet_pressure
        total_heat = sum(edge.heat_rate for edge in result.edges.values())
        max_htc = max((edge.htc for edge in result.edges.values()), default=0.0)

        self.metric_labels["outlet_pressure"].configure(
            text=f"{outlet_pressure:,.1f} Pa",
            fg=DANGER_COLOR if outlet_pressure <= 0.0 else TEXT_COLOR,
        )
        self.metric_labels["outlet_temperature"].configure(
            text=f"{outlet_temperature:,.2f} K",
            fg=TEXT_COLOR,
        )
        self.metric_labels["total_dp"].configure(
            text=f"{total_dp:,.1f} Pa",
            fg=DANGER_COLOR if total_dp < 0.0 else TEXT_COLOR,
        )
        self.metric_labels["total_heat"].configure(
            text=f"{total_heat:,.1f} W",
            fg=TEXT_COLOR,
        )
        self.metric_labels["max_htc"].configure(
            text=f"{max_htc:,.1f} W/m2-K",
            fg=TEXT_COLOR,
        )
        self.metric_labels["warnings"].configure(
            text=str(len(result.warnings)),
            fg=WARNING_COLOR if result.warnings else SAFE_COLOR,
        )

        warning_text = list(result.warnings[:8])
        if len(result.warnings) > 8:
            warning_text.append(f"... {len(result.warnings) - 8} more warnings")
        self._set_dashboard_warning_text(warning_text or ["No warnings."])

        if any("non-positive" in warning for warning in result.warnings):
            self._set_dashboard_status("CHECK REQUIRED", DANGER_COLOR, "#fde7ea")
        elif result.warnings:
            self._set_dashboard_status("WARNINGS", WARNING_COLOR, "#fff4df")
        else:
            self._set_dashboard_status("SAFE", SAFE_COLOR, "#e7f3ec")

    def _set_dashboard_status(
        self,
        text: str,
        foreground: str,
        background: str,
    ) -> None:
        self.dashboard_status_label.configure(text=text, fg=foreground, bg=background)

    def _set_dashboard_warning_text(self, warnings: list[str]) -> None:
        self.dashboard_warning_text.configure(state=tk.NORMAL)
        self.dashboard_warning_text.delete("1.0", tk.END)
        self.dashboard_warning_text.insert(
            tk.END,
            "\n".join(f"- {item}" for item in warnings),
        )
        self.dashboard_warning_text.configure(state=tk.DISABLED)

    def _show_warnings(self, warnings: tuple[str, ...] | list[str]) -> None:
        self.warning_text.configure(state=tk.NORMAL)
        self.warning_text.delete("1.0", tk.END)
        if warnings:
            self.warning_text.insert(tk.END, "\n".join(f"- {item}" for item in warnings))
        else:
            self.warning_text.insert(tk.END, "No warnings.")
        self.warning_text.configure(state=tk.DISABLED)

    def export_results(self) -> None:
        if self.last_result is None:
            messagebox.showwarning("No results", "Run a calculation first.")
            return
        path = filedialog.asksaveasfilename(
            title="Export results",
            defaultextension=".csv",
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if not path:
            return
        _write_result_csv(Path(path), self.last_result)
        messagebox.showinfo("Export complete", f"Saved results to:\n{path}")

    @staticmethod
    def _selected_index(tree: ttk.Treeview) -> int | None:
        selection = tree.selection()
        if not selection:
            return None
        return int(selection[0])

    @staticmethod
    def _id_exists(
        value: str,
        rows: list[dict[str, str]],
        current_index: int,
        key: str,
    ) -> bool:
        return any(
            index != current_index and row[key] == value
            for index, row in enumerate(rows)
        )

    @staticmethod
    def _next_id(prefix: str, existing: set[str]) -> str:
        index = 1
        while f"{prefix}{index}" in existing:
            index += 1
        return f"{prefix}{index}"


def _unit_group_for_key(key: str | None) -> str | None:
    if key is None:
        return None
    return FIELD_UNIT_GROUPS.get(key)


def _unit_row_key(key: str) -> str:
    return f"unit.{key}"


def _default_unit_for_key(key: str) -> str:
    unit_group = _unit_group_for_key(key)
    if unit_group is None:
        return ""
    return UNIT_OPTIONS[unit_group][0]


def _unit_defaults_for_keys(keys: tuple[str, ...]) -> dict[str, str]:
    return {
        _unit_row_key(key): _default_unit_for_key(key)
        for key in keys
        if _unit_group_for_key(key) is not None
    }


def _node_to_row(node: NodeSpec) -> dict[str, str]:
    is_inlet = node.kind == "inlet"
    row = {
        "node_id": node.node_id,
        "kind": node.kind,
        "inlet_mdot": _fmt_optional(node.inlet_mdot) if is_inlet else "",
        "inlet_temperature": _fmt_optional(node.inlet_temperature) if is_inlet else "",
        "inlet_pressure": _fmt_optional(node.inlet_pressure) if is_inlet else "",
    }
    row.update(_unit_defaults_for_keys(NODE_UNIT_KEYS))
    return row


def _edge_to_row(edge: EdgeSpec) -> dict[str, str]:
    geometry = edge.geometry
    technology = _normalize_technology(edge.cooling_technology)
    row = _default_param_row(technology)
    edge_params = _normalize_edge_params(technology, edge.params)
    for key in ALL_PARAM_KEYS:
        if key in edge_params:
            row[_param_row_key(key)] = _fmt_param_value(edge_params[key])
    additional_params = {
        key: value for key, value in edge_params.items() if key not in ALL_PARAM_KEYS
    }
    row.update(
        {
            "edge_id": edge.edge_id,
            "from_node": edge.from_node,
            "to_node": edge.to_node,
            "tag": TAG_OPTIONS[0],
            "cooling_technology": technology,
            "shape": geometry.shape,
            "length": _fmt_optional(geometry.length),
            "width": _fmt_optional(geometry.width),
            "height": _fmt_optional(geometry.height),
            "diameter": _fmt_optional(geometry.diameter),
            "wall_mode": edge.wall.mode,
            "wall_temperature": _fmt_optional(edge.wall.wall_temperature),
            "heat_flux": _fmt_optional(edge.wall.heat_flux),
            "external_htc": _fmt_optional(edge.wall.external_htc),
            "external_temperature": _fmt_optional(edge.wall.external_temperature),
            "wall_thickness": _fmt_optional(edge.wall.wall_thickness),
            "wall_conductivity": _fmt_optional(edge.wall.wall_conductivity),
            "tbc_thickness": _fmt_optional(edge.wall.tbc_thickness),
            "tbc_conductivity": _fmt_optional(edge.wall.tbc_conductivity),
            "flow_fraction": _fmt_optional(edge.flow_fraction),
            "fixed_mdot": _fmt_optional(edge.fixed_mdot),
            "params_text": _format_params(additional_params),
        }
    )
    row.update(_unit_defaults_for_keys(EDGE_UNIT_KEYS))
    return row


def _param_row_key(key: str) -> str:
    return f"param.{key}"


def _default_param_row(technology: str) -> dict[str, str]:
    row = {_param_row_key(key): "" for key in ALL_PARAM_KEYS}
    for spec in TECH_PARAM_SPECS.get(technology, ()):
        row[_param_row_key(spec.key)] = spec.default
    return row


def _params_from_row(row: dict[str, str]) -> dict[str, Any]:
    params = _parse_params(row["params_text"])
    technology = _normalize_technology(row["cooling_technology"])
    for spec in TECH_PARAM_SPECS.get(technology, ()):
        value = row.get(_param_row_key(spec.key), "").strip()
        if value:
            unit_group = _unit_group_for_key(spec.key)
            if unit_group is None:
                params[spec.key] = _parse_value(value)
            else:
                unit = row.get(_unit_row_key(spec.key), _default_unit_for_key(spec.key))
                params[spec.key] = _to_si(_required_float(value, spec.key), unit_group, unit)
    return params


def _normalize_technology(technology: str) -> str:
    return "turning" if technology == "u_turn" else technology


def _normalize_edge_params(technology: str, params: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(params)
    if technology == "turning" and "c_nu" not in normalized:
        if "nu_multiplier_turn" in normalized:
            normalized["c_nu"] = normalized["nu_multiplier_turn"]
        elif "nu_multiplier" in normalized:
            normalized["c_nu"] = normalized["nu_multiplier"]
    return normalized


def _auto_node_positions(node_ids: list[str]) -> dict[str, tuple[float, float]]:
    if not node_ids:
        return {}
    if len(node_ids) == 1:
        return {node_ids[0]: (0.5, 0.5)}

    positions: dict[str, tuple[float, float]] = {}
    x_min, x_max = 0.18, 0.82
    y_min, y_max = 0.18, 0.82
    for index, node_id in enumerate(node_ids):
        fraction = index / (len(node_ids) - 1)
        positions[node_id] = (
            x_min + (x_max - x_min) * fraction,
            y_max - (y_max - y_min) * fraction,
        )
    return positions


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def _value_to_color(value: float, values: list[float]) -> str:
    if not values:
        return ACCENT_COLOR
    low = min(values)
    high = max(values)
    if high <= low:
        fraction = 0.5
    else:
        fraction = (value - low) / (high - low)
    fraction = _clamp01(fraction)
    return _interpolate_color("#2f80ed", "#d7191c", fraction)


def _interpolate_color(start: str, end: str, fraction: float) -> str:
    fraction = _clamp01(fraction)
    start_rgb = tuple(int(start[index:index + 2], 16) for index in (1, 3, 5))
    end_rgb = tuple(int(end[index:index + 2], 16) for index in (1, 3, 5))
    rgb = tuple(
        round(start_value + (end_value - start_value) * fraction)
        for start_value, end_value in zip(start_rgb, end_rgb)
    )
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _contrast_text_color(hex_color: str) -> str:
    color = hex_color.lstrip("#")
    red, green, blue = (int(color[index:index + 2], 16) for index in (0, 2, 4))
    luminance = 0.299 * red + 0.587 * green + 0.114 * blue
    return "#ffffff" if luminance < 150 else "#111827"


def _math_lines(equation: str) -> list[str]:
    lines: list[str] = []
    for raw_line in equation.splitlines():
        line = raw_line.strip()
        if not line or line in {r"\begin{aligned}", r"\end{aligned}"}:
            continue
        line = line.replace("&", "")
        if line.endswith(r"\\"):
            line = line[:-2].strip()
        lines.append(line)
    return lines


def _point_to_segment_distance(
    px: float,
    py: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> float:
    dx = x2 - x1
    dy = y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq == 0.0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = ((px - x1) * dx + (py - y1) * dy) / length_sq
    t = _clamp01(t)
    closest_x = x1 + t * dx
    closest_y = y1 + t * dy
    return ((px - closest_x) ** 2 + (py - closest_y) ** 2) ** 0.5


def _unique_id(base_id: str, existing_ids: set[str]) -> str:
    if base_id not in existing_ids:
        return base_id
    index = 2
    while f"{base_id}_{index}" in existing_ids:
        index += 1
    return f"{base_id}_{index}"


def _event_has_control(event: tk.Event) -> bool:
    return bool(getattr(event, "state", 0) & 0x0004)


def _format_params(params: dict[str, Any]) -> str:
    return "\n".join(f"{key} = {value}" for key, value in params.items())


def _parse_params(text: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Params line {line_number} must use key = value.")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Params line {line_number} has an empty key.")
        params[key] = _parse_value(value.strip())
    return params


def _parse_value(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"none", "null"}:
        return None
    try:
        number = float(value.replace(",", ""))
    except ValueError:
        return value.strip("\"'")
    if number.is_integer() and "." not in value and "e" not in lowered:
        return int(number)
    return number


def _optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return float(stripped.replace(",", ""))


def _required_float(value: str, name: str) -> float:
    parsed = _optional_float(value)
    if parsed is None:
        raise ValueError(f"{name} is required.")
    return parsed


_UNIT_FACTORS_TO_SI = {
    "length": {
        "m": 1.0,
        "cm": 1.0e-2,
        "mm": 1.0e-3,
        "um": 1.0e-6,
        "in": 0.0254,
        "ft": 0.3048,
    },
    "pressure": {
        "Pa": 1.0,
        "kPa": 1.0e3,
        "MPa": 1.0e6,
        "bar": 1.0e5,
        "psi": 6_894.757293168,
    },
    "mass_flow": {
        "kg/s": 1.0,
        "g/s": 1.0e-3,
        "kg/min": 1.0 / 60.0,
        "g/min": 1.0e-3 / 60.0,
        "lb/s": 0.45359237,
        "lb/min": 0.45359237 / 60.0,
    },
    "thermal_conductivity": {
        "W/m/K": 1.0,
        "BTU/h/ft/F": 1.730735,
    },
    "heat_flux": {
        "W/m2": 1.0,
        "kW/m2": 1.0e3,
        "MW/m2": 1.0e6,
        "BTU/h/ft2": 3.15459075,
    },
    "htc": {
        "W/m2/K": 1.0,
        "kW/m2/K": 1.0e3,
        "BTU/h/ft2/F": 5.67826334,
    },
}


def _to_si(value: float, unit_group: str, unit: str) -> float:
    if unit_group == "temperature":
        return _temperature_to_kelvin(value, unit)
    try:
        return value * _UNIT_FACTORS_TO_SI[unit_group][unit]
    except KeyError as exc:
        raise ValueError(f"Unsupported unit '{unit}' for {unit_group}.") from exc


def _from_si(value: float, unit_group: str, unit: str) -> float:
    if unit_group == "temperature":
        return _kelvin_to_temperature(value, unit)
    try:
        return value / _UNIT_FACTORS_TO_SI[unit_group][unit]
    except KeyError as exc:
        raise ValueError(f"Unsupported unit '{unit}' for {unit_group}.") from exc


def _temperature_to_kelvin(value: float, unit: str) -> float:
    if unit == "K":
        return value
    if unit == "C":
        return value + 273.15
    if unit == "F":
        return (value - 32.0) * 5.0 / 9.0 + 273.15
    if unit == "R":
        return value * 5.0 / 9.0
    raise ValueError(f"Unsupported temperature unit '{unit}'.")


def _kelvin_to_temperature(value: float, unit: str) -> float:
    if unit == "K":
        return value
    if unit == "C":
        return value - 273.15
    if unit == "F":
        return (value - 273.15) * 9.0 / 5.0 + 32.0
    if unit == "R":
        return value * 9.0 / 5.0
    raise ValueError(f"Unsupported temperature unit '{unit}'.")


def _optional_si(row: dict[str, str], key: str) -> float | None:
    value = _optional_float(row.get(key))
    if value is None:
        return None
    unit_group = _unit_group_for_key(key)
    if unit_group is None:
        return value
    unit = row.get(_unit_row_key(key), _default_unit_for_key(key))
    return _to_si(value, unit_group, unit)


def _required_si(row: dict[str, str], key: str, name: str) -> float:
    value = _optional_si(row, key)
    if value is None:
        raise ValueError(f"{name} is required.")
    return value


def _fmt_row_si(row: dict[str, str], key: str) -> str:
    try:
        value = _optional_si(row, key)
    except ValueError:
        return row.get(key, "")
    return _fmt_optional(value)


def _fmt_optional(value: float | int | None) -> str:
    if value is None:
        return ""
    return f"{value:,.6g}"


def _fmt_param_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return f"{value:,.6g}"
    return str(value)


def _fmt_number(value: float, digits: int) -> str:
    return f"{value:,.{digits}f}"


def _fmt_sweep_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:,.6g}"
    return str(value)


def _field_label(key: str) -> str:
    labels = {
        "tag": "Tag",
        "cooling_technology": "Technology",
        "shape": "Shape",
        "wall_mode": "Wall mode",
        "inlet_mdot": "Inlet m_dot",
        "inlet_temperature": "Inlet temperature",
        "inlet_pressure": "Inlet pressure",
        "length": "Length",
        "width": "Width",
        "height": "Height",
        "diameter": "Diameter",
        "wall_temperature": "Wall T",
        "heat_flux": "Heat flux",
        "external_temperature": "External gas T",
        "external_htc": "External h",
        "wall_thickness": "Blade wall thickness",
        "wall_conductivity": "Blade wall k",
        "tbc_thickness": "TBC thickness",
        "tbc_conductivity": "TBC k",
    }
    if key in labels:
        return labels[key]
    for specs in TECH_PARAM_SPECS.values():
        for spec in specs:
            if spec.key == key:
                return spec.label
    return key


def _batch_sort_key(field_key: str) -> tuple[int, str]:
    order = {
        key: index
        for index, (key, _label, _kind, _choices) in enumerate(BATCH_FIELD_SPECS)
    }
    return order.get(field_key, 999), field_key


def _sweep_display_values(start: str, end: str, step: str) -> list[float]:
    start_value = _required_float(start, "sweep start")
    end_value = _required_float(end, "sweep end")
    step_value = _optional_float(step)
    if abs(end_value - start_value) <= 1.0e-12 and step_value is None:
        return [start_value]
    if step_value is None:
        raise ValueError("Sweep step is required unless start and end are equal.")
    if step_value <= 0.0:
        raise ValueError("Sweep step must be positive.")

    direction = 1.0 if end_value >= start_value else -1.0
    signed_step = direction * step_value
    tolerance = abs(step_value) * 1.0e-9 + 1.0e-12
    values: list[float] = []
    value = start_value
    if direction > 0.0:
        while value <= end_value + tolerance:
            values.append(value)
            value += signed_step
    else:
        while value >= end_value - tolerance:
            values.append(value)
            value += signed_step
    return values


def _global_result_metrics(result: SolverResult) -> dict[str, float]:
    outlet_nodes = [
        node
        for node in result.nodes.values()
        if node.kind == "outlet" or not node.outgoing_edges
    ]
    inlet_pressures = [
        node.pressure for node in result.nodes.values() if node.kind == "inlet"
    ]
    outlet_pressure = min((node.pressure for node in outlet_nodes), default=0.0)
    outlet_mdot = sum(node.mass_flow for node in outlet_nodes)
    outlet_temperature = 0.0
    if outlet_mdot > 0.0:
        outlet_temperature = (
            sum(node.mass_flow * node.temperature for node in outlet_nodes)
            / outlet_mdot
        )
    total_dp = max(inlet_pressures, default=0.0) - outlet_pressure
    return {
        "outlet_pressure": outlet_pressure,
        "total_dp": total_dp,
        "outlet_T": outlet_temperature,
        "max_wall_T": _max_wall_temperature(result),
    }


def _max_wall_temperature(result: SolverResult) -> float:
    candidates: list[float] = []
    for edge in result.edges.values():
        for key in (
            "coolant_side_wall_temperature_k",
            "metal_outer_temperature_k",
            "tbc_outer_temperature_k",
        ):
            value = edge.intermediate.get(key)
            if isinstance(value, (int, float)):
                candidates.append(float(value))
    return max(candidates, default=0.0)


def _constraints_pass(
    metrics: dict[str, float],
    constraints: dict[str, tuple[float | None, float | None]],
) -> tuple[bool, str]:
    failures: list[str] = []
    for key, (lower, upper) in constraints.items():
        value = metrics.get(key)
        label = CONSTRAINT_SPECS[key][0]
        if value is None:
            failures.append(f"{label}: unavailable")
            continue
        if lower is not None and value < lower:
            failures.append(f"{label}: {value:,.6g} < {lower:,.6g}")
        if upper is not None and value > upper:
            failures.append(f"{label}: {value:,.6g} > {upper:,.6g}")
    return not failures, "OK" if not failures else "; ".join(failures)


def _is_better_record(
    record: dict[str, Any],
    best_record: dict[str, Any] | None,
    direction: str,
) -> bool:
    value = record.get("objective")
    if not isinstance(value, (int, float)):
        return False
    if best_record is None:
        return True
    best_value = best_record.get("objective")
    if not isinstance(best_value, (int, float)):
        return True
    if direction == "Maximize":
        return value > best_value
    return value < best_value


def _sweep_grid_from_records(
    records: list[dict[str, Any]],
    x_label: str,
    y_label: str,
    direction: str,
) -> tuple[list[float], list[float], list[list[float]]]:
    x_values = sorted({float(record[x_label]) for record in records if x_label in record})
    y_values = sorted({float(record[y_label]) for record in records if y_label in record})
    best_by_point: dict[tuple[float, float], float] = {}
    for record in records:
        if x_label not in record or y_label not in record:
            continue
        objective = record.get("objective")
        if not isinstance(objective, (int, float)):
            continue
        point = (float(record[x_label]), float(record[y_label]))
        current = best_by_point.get(point)
        if current is None:
            best_by_point[point] = float(objective)
        elif direction == "Maximize" and objective > current:
            best_by_point[point] = float(objective)
        elif direction != "Maximize" and objective < current:
            best_by_point[point] = float(objective)
    grid = [
        [best_by_point.get((x_value, y_value), float("nan")) for x_value in x_values]
        for y_value in y_values
    ]
    return x_values, y_values, grid


def _write_result_csv(path: Path, result: SolverResult) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Node results"])
        writer.writerow(["node", "kind", "m_dot_kg_s", "temperature_k", "pressure_pa"])
        for node in result.nodes.values():
            writer.writerow(
                [
                    node.node_id,
                    node.kind,
                    node.mass_flow,
                    node.temperature,
                    node.pressure,
                ]
            )
        writer.writerow([])
        writer.writerow(["Edge results"])
        writer.writerow(
            [
                "edge",
                "from_node",
                "to_node",
                "technology",
                "m_dot_kg_s",
                "reynolds",
                "nusselt",
                "htc_w_m2_k",
                "friction_factor_darcy",
                "dp_friction_pa",
                "dp_rotation_pa",
                "dp_total_pa",
                "q_w",
                "heat_flux_w_m2",
                "coolant_side_wall_temperature_k",
                "metal_outer_temperature_k",
                "tbc_outer_temperature_k",
                "tout_k",
                "pout_pa",
            ]
        )
        for edge in result.edges.values():
            writer.writerow(
                [
                    edge.edge_id,
                    edge.from_node,
                    edge.to_node,
                    edge.cooling_technology,
                    edge.mass_flow,
                    edge.reynolds,
                    edge.nusselt,
                    edge.htc,
                    edge.friction_factor_darcy,
                    edge.dp_friction,
                    edge.dp_rotation,
                    edge.dp_total,
                    edge.heat_rate,
                    edge.intermediate.get("heat_flux_w_m2"),
                    edge.intermediate.get("coolant_side_wall_temperature_k"),
                    edge.intermediate.get("metal_outer_temperature_k"),
                    edge.intermediate.get("tbc_outer_temperature_k"),
                    edge.outlet_temperature,
                    edge.outlet_pressure,
                ]
            )
        writer.writerow([])
        writer.writerow(["Warnings"])
        for warning in result.warnings:
            writer.writerow([warning])


def main() -> int:
    app = PassageApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
