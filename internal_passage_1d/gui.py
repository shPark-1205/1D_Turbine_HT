from __future__ import annotations

import csv
import tkinter as tk
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
OVERLAY_METRICS = (
    "Technology",
    "Edge Tout [K]",
    "Edge HTC [W/m2-K]",
    "Edge dp [Pa]",
    "Edge q [W]",
    "Node T [K]",
    "Node P [Pa]",
)
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


TECH_PARAM_SPECS: dict[str, tuple[ParamSpec, ...]] = {
    "smooth": (
        ParamSpec("c_nu", "C_Nu [-]", "1"),
    ),
    "rib": (
        ParamSpec("e_over_dh", "Rib e/Dh [-]"),
        ParamSpec("p_over_e", "Rib pitch/e [-]"),
        ParamSpec("angle_deg", "Rib angle [deg]", "45"),
        ParamSpec("radius_m", "Blade radius [m]", "1.23"),
        ParamSpec("rpm", "Blade RPM", "3000"),
        ParamSpec("c_rotation", "C_rotation [-]", "1.056"),
        ParamSpec("ribbed_walls", "Ribbed walls", "2"),
    ),
    "turning": (
        ParamSpec("c_nu", "C_Nu [-]", "1.5"),
        ParamSpec("turn_angle_deg", "Turn angle [deg]", "180"),
    ),
    "pin_fin": (
        ParamSpec("pin_diameter", "Pin diameter [m]"),
        ParamSpec("pin_height", "Pin height [m]"),
        ParamSpec("pitch_x", "Streamwise pitch X [m]"),
        ParamSpec("pitch_s", "Spanwise pitch S [m]"),
    ),
}
ALL_PARAM_KEYS = tuple(
    dict.fromkeys(
        spec.key
        for specs in TECH_PARAM_SPECS.values()
        for spec in specs
    )
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
        self.selected_node_id: str | None = None
        self.selected_edge_id: str | None = None
        self._layout_mode = tk.StringVar(value="select")
        self._pending_edge_from: str | None = None
        self._drag_node_id: str | None = None
        self._drag_started = False
        self._workspace_scroll_canvas: tk.Canvas | None = None
        self._correlations_scroll_canvas: tk.Canvas | None = None
        self._formula_images: list[Any] = []
        self.results_stale = False

        self.property_model = tk.StringVar(value="ideal_gas")
        self.overlay_metric = tk.StringVar(value="Technology")
        self.auto_calculate = tk.BooleanVar(value=False)

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
        ttk.Combobox(
            toolbar,
            textvariable=self.property_model,
            values=PROPERTY_MODELS,
            state="readonly",
            width=12,
        ).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Export CSV", command=self.export_results).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        self.workspace_tab = ttk.Frame(self.notebook)
        self.correlations_tab = ttk.Frame(self.notebook)
        self.results_tab = ttk.Frame(self.notebook)
        self.warnings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.workspace_tab, text="Workspace")
        self.notebook.add(self.correlations_tab, text="Correlations")
        self.notebook.add(self.results_tab, text="Results")
        self.notebook.add(self.warnings_tab, text="Warnings")

        self._build_workspace_tab()
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
        ttk.Combobox(
            canvas_toolbar,
            textvariable=self.overlay_metric,
            values=OVERLAY_METRICS,
            state="readonly",
            width=18,
        ).pack(side=tk.LEFT)
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
        self._build_selected_result_panel(right)
        self._build_workspace_tables(right)

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
        self._labeled_entry(node_panel, 1, "Node ID", self._node_vars["node_id"])
        ttk.Label(node_panel, text="Kind", style="Header.TLabel").grid(
            row=2, column=0, sticky=tk.W, pady=3
        )
        ttk.Combobox(
            node_panel,
            textvariable=self._node_vars["kind"],
            values=NODE_KINDS,
            state="readonly",
            width=20,
        ).grid(row=2, column=1, sticky=tk.EW, pady=3)
        self.node_inlet_fields = []
        self.node_inlet_fields.append(self._labeled_entry(
            node_panel,
            3,
            "Inlet m_dot [kg/s]",
            self._node_vars["inlet_mdot"],
        ))
        self.node_inlet_fields.append(self._labeled_entry(
            node_panel,
            4,
            "Inlet temperature [K]",
            self._node_vars["inlet_temperature"],
        ))
        self.node_inlet_fields.append(self._labeled_entry(
            node_panel,
            5,
            "Inlet pressure [Pa]",
            self._node_vars["inlet_pressure"],
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
        self._labeled_entry(edge_panel, row, "Edge ID", self._edge_vars["edge_id"])
        row += 1
        self._labeled_combo(edge_panel, row, "From node", self._edge_vars["from_node"], ())
        self.edge_from_combo = edge_panel.grid_slaves(row=row, column=1)[0]
        row += 1
        self._labeled_combo(edge_panel, row, "To node", self._edge_vars["to_node"], ())
        self.edge_to_combo = edge_panel.grid_slaves(row=row, column=1)[0]
        row += 1
        self._labeled_combo(
            edge_panel,
            row,
            "Technology",
            self._edge_vars["cooling_technology"],
            TECHNOLOGIES,
        )
        row += 1
        self._labeled_combo(edge_panel, row, "Shape", self._edge_vars["shape"], SHAPES)
        row += 1
        self.edge_geometry_fields = {}
        for label, key in (
            ("Length [m]", "length"),
            ("Width [m]", "width"),
            ("Height [m]", "height"),
            ("Diameter [m]", "diameter"),
        ):
            self.edge_geometry_fields[key] = self._labeled_entry(
                edge_panel,
                row,
                label,
                self._edge_vars[key],
            )
            row += 1
        self._labeled_combo(edge_panel, row, "Wall mode", self._edge_vars["wall_mode"], WALL_MODES)
        row += 1
        self.edge_wall_fields = {}
        for label, key in (
            ("Wall T [K]", "wall_temperature"),
            ("Heat flux [W/m2]", "heat_flux"),
            ("External gas T [K]", "external_temperature"),
            ("External h [W/m2-K]", "external_htc"),
            ("Blade wall thickness [m]", "wall_thickness"),
            ("Blade wall k [W/m-K]", "wall_conductivity"),
            ("TBC thickness [m]", "tbc_thickness"),
            ("TBC k [W/m-K]", "tbc_conductivity"),
        ):
            self.edge_wall_fields[key] = self._labeled_entry(
                edge_panel,
                row,
                label,
                self._edge_vars[key],
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
        edge_columns = ("edge_id", "route", "tech", "length")
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
        for row in self.edge_rows:
            from_pos = self.node_positions.get(row["from_node"])
            to_pos = self.node_positions.get(row["to_node"])
            if from_pos is None or to_pos is None:
                continue
            x1, y1 = self._layout_to_canvas(from_pos)
            x2, y2 = self._layout_to_canvas(to_pos)
            is_selected = row["edge_id"] == self.selected_edge_id
            overlay_value = metric_values.get(row["edge_id"])
            color = ACCENT_COLOR
            if overlay_value is not None:
                color = _value_to_color(overlay_value, list(metric_values.values()))
            canvas.create_line(
                x1,
                y1,
                x2,
                y2,
                fill=WARNING_COLOR if is_selected else color,
                width=7 if overlay_value is not None else (5 if is_selected else 3),
                arrow=tk.LAST,
                arrowshape=(14, 16, 6),
            )
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2
            label = self._edge_overlay_label(row, metric, overlay_value)
            label_fill = "#ffffff"
            label_text = TEXT_COLOR
            if overlay_value is not None:
                label_fill = WARNING_COLOR if is_selected else color
                label_text = _contrast_text_color(label_fill)
            label_half_width = max(34, 4.4 * len(label) + 8)
            canvas.create_rectangle(
                mid_x - label_half_width,
                mid_y - 13,
                mid_x + label_half_width,
                mid_y + 13,
                fill="#fff8e8" if is_selected and overlay_value is None else label_fill,
                outline=WARNING_COLOR if is_selected else BORDER_COLOR,
            )
            canvas.create_text(
                mid_x,
                mid_y,
                text=label,
                fill=TEXT_COLOR if is_selected and overlay_value is None else label_text,
                font=("Segoe UI", 9, "bold"),
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
            self._select_edge_by_id(edge_id)
            return

        self.selected_node_id = None
        self.selected_edge_id = None
        self._update_selected_result_panel()
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
            if distance <= 9 and distance < nearest_distance:
                nearest_edge = row["edge_id"]
                nearest_distance = distance
        return nearest_edge

    def _select_node_by_id(self, node_id: str) -> None:
        index = self._node_index(node_id)
        if index is None:
            return
        self.selected_node_id = node_id
        self.selected_edge_id = None
        self.node_tree.selection_set(str(index))
        self.node_tree.focus(str(index))
        self._populate_node_form(index)
        if hasattr(self, "edge_tree"):
            self.edge_tree.selection_remove(self.edge_tree.selection())
        self._update_selected_result_panel()
        self._redraw_layout_canvas()

    def _select_edge_by_id(self, edge_id: str) -> None:
        index = self._edge_index(edge_id)
        if index is None:
            return
        self.selected_edge_id = edge_id
        self.selected_node_id = None
        self.edge_tree.selection_set(str(index))
        self.edge_tree.focus(str(index))
        self._populate_edge_form(index)
        if hasattr(self, "node_tree"):
            self.node_tree.selection_remove(self.node_tree.selection())
        self._update_selected_result_panel()
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
    ) -> tuple[ttk.Label, ttk.Entry]:
        label_widget = ttk.Label(parent, text=label)
        label_widget.grid(row=row, column=0, sticky=tk.W, pady=3)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(
            row=row, column=1, sticky=tk.EW, pady=3
        )
        return label_widget, entry

    def _labeled_combo(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
    ) -> tuple[ttk.Label, ttk.Combobox]:
        label_widget = ttk.Label(parent, text=label)
        label_widget.grid(row=row, column=0, sticky=tk.W, pady=3)
        combo = ttk.Combobox(parent, textvariable=variable, values=values, width=20)
        combo.grid(
            row=row, column=1, sticky=tk.EW, pady=3
        )
        return label_widget, combo

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
        for key, variable in self._node_vars.items():
            if key != "kind":
                variable.trace_add("write", lambda *_args: self._auto_apply_node_form())
        for key, variable in self._edge_vars.items():
            if key not in {"cooling_technology", "shape", "wall_mode"}:
                variable.trace_add("write", lambda *_args: self._auto_apply_edge_form())
        for variable in self._tech_param_vars.values():
            variable.trace_add("write", lambda *_args: self._auto_apply_edge_form())

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
            ttk.Entry(
                self.tech_param_frame,
                textvariable=self._tech_param_vars[spec.key],
                width=20,
            ).grid(row=row, column=1, sticky=tk.EW, pady=2, padx=(8, 0))
        self.tech_param_frame.columnconfigure(1, weight=1)

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
            self.node_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(
                    row["node_id"],
                    row["kind"],
                    row["inlet_mdot"],
                    row["inlet_temperature"],
                    row["inlet_pressure"],
                ),
            )

    def _refresh_edge_tree(self) -> None:
        self.edge_tree.delete(*self.edge_tree.get_children())
        columns = tuple(self.edge_tree["columns"])
        for index, row in enumerate(self.edge_rows):
            if columns == ("edge_id", "route", "tech", "length"):
                values = (
                    row["edge_id"],
                    f'{row["from_node"]} -> {row["to_node"]}',
                    row["cooling_technology"],
                    row["length"],
                )
            else:
                values = (
                    row["edge_id"],
                    f'{row["from_node"]} -> {row["to_node"]}',
                    row["cooling_technology"],
                    row["length"],
                    row["width"],
                    row["height"],
                    row["diameter"],
                )
            self.edge_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=values,
            )
        self._refresh_dashboard_map()
        self._redraw_layout_canvas()

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

    def _on_node_select(self, _event: tk.Event) -> None:
        index = self._selected_index(self.node_tree)
        if index is not None:
            self.selected_node_id = self.node_rows[index]["node_id"]
            self.selected_edge_id = None
            self._populate_node_form(index)
            self._update_selected_result_panel()
            self._redraw_layout_canvas()

    def _on_edge_select(self, _event: tk.Event) -> None:
        index = self._selected_index(self.edge_tree)
        if index is not None:
            self.selected_edge_id = self.edge_rows[index]["edge_id"]
            self.selected_node_id = None
            self._populate_edge_form(index)
            self._update_selected_result_panel()
            self._redraw_layout_canvas()

    def _populate_node_form(self, index: int) -> None:
        row = self.node_rows[index]
        self._suppress_auto_apply = True
        try:
            for key, variable in self._node_vars.items():
                variable.set(row[key])
        finally:
            self._suppress_auto_apply = False
        self._update_node_field_visibility()

    def _populate_edge_form(self, index: int) -> None:
        row = self.edge_rows[index]
        self._syncing_edge_form = True
        self._suppress_auto_apply = True
        try:
            for key, variable in self._edge_vars.items():
                variable.set(row[key])
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

    def apply_node(self) -> None:
        index = self._selected_index(self.node_tree)
        if index is None:
            messagebox.showwarning("No selection", "Select a node first.")
            return
        old_id = self.node_rows[index]["node_id"]
        row = {key: variable.get().strip() for key, variable in self._node_vars.items()}
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
        self.node_positions.pop(node_id, None)
        self.selected_node_id = None
        self.selected_edge_id = None
        self._ensure_node_positions()
        self._refresh_node_tree()
        self._refresh_edge_tree()
        self._refresh_node_combos()
        self._update_dashboard_summary()
        self._update_selected_result_panel()
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
        self._refresh_edge_tree()
        self._update_dashboard_summary()
        self._update_selected_result_panel()
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
        row["params_text"] = self.params_text.get("1.0", tk.END).strip()
        return row

    def _after_apply(self) -> None:
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
        nodes = [
            NodeSpec(
                node_id=row["node_id"],
                kind=row["kind"],  # type: ignore[arg-type]
                inlet_mdot=_optional_float(row["inlet_mdot"]) if row["kind"] == "inlet" else None,
                inlet_temperature=_optional_float(row["inlet_temperature"]) if row["kind"] == "inlet" else None,
                inlet_pressure=_optional_float(row["inlet_pressure"]) if row["kind"] == "inlet" else None,
            )
            for row in self.node_rows
        ]
        edges: list[EdgeSpec] = []
        for row in self.edge_rows:
            geometry = Geometry(
                length=_required_float(row["length"], f'{row["edge_id"]}.length'),
                shape=row["shape"],  # type: ignore[arg-type]
                width=_optional_float(row["width"]),
                height=_optional_float(row["height"]),
                diameter=_optional_float(row["diameter"]),
            )
            wall = WallBoundary(
                mode=row["wall_mode"],  # type: ignore[arg-type]
                wall_temperature=_optional_float(row["wall_temperature"]),
                heat_flux=_optional_float(row["heat_flux"]),
                external_htc=_optional_float(row["external_htc"]),
                external_temperature=_optional_float(row["external_temperature"]),
                wall_thickness=_optional_float(row["wall_thickness"]),
                wall_conductivity=_optional_float(row["wall_conductivity"]),
                tbc_thickness=_optional_float(row["tbc_thickness"]),
                tbc_conductivity=_optional_float(row["tbc_conductivity"]),
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
            ("Coolant bulk", float(info["fluid_reference_temperature_k"])),
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
                value = _optional_float(row["inlet_mdot"])
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


def _node_to_row(node: NodeSpec) -> dict[str, str]:
    is_inlet = node.kind == "inlet"
    return {
        "node_id": node.node_id,
        "kind": node.kind,
        "inlet_mdot": _fmt_optional(node.inlet_mdot) if is_inlet else "",
        "inlet_temperature": _fmt_optional(node.inlet_temperature) if is_inlet else "",
        "inlet_pressure": _fmt_optional(node.inlet_pressure) if is_inlet else "",
    }


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
            params[spec.key] = _parse_value(value)
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
    if fraction < 0.5:
        local = fraction / 0.5
        return _interpolate_color("#2f80ed", "#f2c94c", local)
    return _interpolate_color("#f2c94c", "#d7191c", (fraction - 0.5) / 0.5)


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
