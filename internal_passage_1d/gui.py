from __future__ import annotations

import csv
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, NamedTuple

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
TECHNOLOGIES = ("smooth", "rib", "u_turn", "pin_fin")
SHAPES = ("rectangular", "circular")
WALL_MODES = ("adiabatic", "wall_temperature", "heat_flux")
PROPERTY_MODELS = ("ideal_gas", "coolprop")
ACCENT_COLOR = "#1f77b4"
TEXT_COLOR = "#31333F"
MUTED_COLOR = "#5c6670"
WINDOW_BG = "#f5f7fb"
PANEL_BG = "#ffffff"
BORDER_COLOR = "#d8e1ec"
SAFE_COLOR = "#0f7b3d"
WARNING_COLOR = "#b36b00"
DANGER_COLOR = "#b00020"


class ParamSpec(NamedTuple):
    key: str
    label: str
    default: str = ""


TECH_PARAM_SPECS: dict[str, tuple[ParamSpec, ...]] = {
    "smooth": (
        ParamSpec("user_f_multiplier", "Friction multiplier [-]", "1"),
        ParamSpec("user_K_loss", "Minor K loss [-]", "0"),
    ),
    "rib": (
        ParamSpec("e_over_dh", "Rib e/Dh [-]"),
        ParamSpec("p_over_e", "Rib pitch/e [-]"),
        ParamSpec("angle_deg", "Rib angle [deg]", "45"),
        ParamSpec("user_f_multiplier", "Friction multiplier [-]", "1"),
        ParamSpec("user_K_loss", "Minor K loss [-]", "0"),
        ParamSpec("rib_count", "Rib count"),
        ParamSpec("ribbed_walls", "Ribbed walls", "2"),
    ),
    "u_turn": (
        ParamSpec("nu_multiplier_turn", "Nu multiplier [-]", "1"),
        ParamSpec("k_turn", "Turn K loss [-]", "0"),
        ParamSpec("user_K_loss", "Additional K loss [-]", "0"),
        ParamSpec("turn_angle_deg", "Turn angle [deg]", "180"),
        ParamSpec("bend_radius_m", "Bend radius [m]"),
        ParamSpec("turn_style", "Turn style", "sharp"),
        ParamSpec("turn_clearance_m", "Turn clearance [m]"),
        ParamSpec("upstream_width_m", "Upstream width [m]"),
        ParamSpec("upstream_height_m", "Upstream height [m]"),
        ParamSpec("downstream_width_m", "Downstream width [m]"),
        ParamSpec("downstream_height_m", "Downstream height [m]"),
    ),
    "pin_fin": (
        ParamSpec("pin_diameter", "Pin diameter [m]"),
        ParamSpec("pin_height", "Pin height [m]"),
        ParamSpec("pitch_x", "Streamwise pitch X [m]"),
        ParamSpec("pitch_s", "Spanwise pitch S [m]"),
        ParamSpec("row_count", "Row count"),
        ParamSpec("pins_cross", "Pins across width"),
        ParamSpec("user_f_multiplier", "Friction multiplier [-]", "1"),
        ParamSpec("user_K_loss", "Minor K loss [-]", "0"),
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
        self.minsize(1180, 760)
        self.configure(bg=WINDOW_BG)

        self.node_rows: list[dict[str, str]] = []
        self.edge_rows: list[dict[str, str]] = []
        self.last_result: SolverResult | None = None
        self._syncing_edge_form = False

        self.property_model = tk.StringVar(value="ideal_gas")
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
            "flow_fraction": tk.StringVar(),
            "fixed_mdot": tk.StringVar(),
        }
        self._tech_param_vars = {
            key: tk.StringVar() for key in ALL_PARAM_KEYS
        }

        self._configure_style()
        self._build_widgets()
        self._edge_vars["cooling_technology"].trace_add(
            "write", self._on_technology_change
        )
        self.property_model.trace_add(
            "write", lambda *_args: self._update_dashboard_summary()
        )
        self._load_network(build_default_network())
        self.calculate(show_success=False)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        default_font = ("Segoe UI", 9)
        title_font = ("Segoe UI", 18, "bold")
        heading_font = ("Segoe UI", 10, "bold")
        small_heading_font = ("Segoe UI", 9, "bold")

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
            font=("Segoe UI", 10),
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
            padding=(14, 8),
            font=("Segoe UI", 9, "bold"),
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
            padding=(12, 7),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#17629a"), ("pressed", "#14557f")],
            foreground=[("active", "#ffffff"), ("pressed", "#ffffff")],
        )
        style.configure("TButton", padding=(10, 6))
        style.configure(
            "Treeview",
            background=PANEL_BG,
            fieldbackground=PANEL_BG,
            foreground=TEXT_COLOR,
            rowheight=25,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background="#edf3f8",
            foreground=TEXT_COLOR,
            font=("Segoe UI", 9, "bold"),
        )
        style.map("Treeview", background=[("selected", "#d7ebfb")])

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
            text="Auto calculate after Apply",
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

        self.dashboard_tab = ttk.Frame(self.notebook)
        self.nodes_tab = ttk.Frame(self.notebook)
        self.edges_tab = ttk.Frame(self.notebook)
        self.results_tab = ttk.Frame(self.notebook)
        self.warnings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.dashboard_tab, text="Dashboard")
        self.notebook.add(self.nodes_tab, text="Nodes")
        self.notebook.add(self.edges_tab, text="Edges")
        self.notebook.add(self.results_tab, text="Results")
        self.notebook.add(self.warnings_tab, text="Warnings")

        self._build_dashboard_tab()
        self._build_nodes_tab()
        self._build_edges_tab()
        self._build_results_tab()
        self._build_warnings_tab()

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
            font=("Segoe UI", 12, "bold"),
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
            font=("Segoe UI", 9, "bold"),
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
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W)
        value = tk.Label(
            card,
            text="-",
            bg="#fbfcfe",
            fg=TEXT_COLOR,
            font=("Segoe UI", 15, "bold"),
        )
        value.pack(anchor=tk.W, pady=(2, 0))
        self.metric_labels[key] = value

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
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, sticky=tk.EW, pady=3
        )

    def _labeled_combo(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Combobox(parent, textvariable=variable, values=values, width=20).grid(
            row=row, column=1, sticky=tk.EW, pady=3
        )

    def _on_technology_change(self, *_args: object) -> None:
        if self._syncing_edge_form:
            return
        technology = self._edge_vars["cooling_technology"].get()
        self._apply_param_defaults(technology)
        self._render_tech_params(technology)

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
        if self.edge_rows:
            self.edge_tree.selection_set("0")
            self.edge_tree.focus("0")
            self._populate_edge_form(0)

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
        for index, row in enumerate(self.edge_rows):
            self.edge_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(
                    row["edge_id"],
                    f'{row["from_node"]} -> {row["to_node"]}',
                    row["cooling_technology"],
                    row["length"],
                    row["width"],
                    row["height"],
                    row["diameter"],
                ),
            )
        self._refresh_dashboard_map()

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
            self._populate_node_form(index)

    def _on_edge_select(self, _event: tk.Event) -> None:
        index = self._selected_index(self.edge_tree)
        if index is not None:
            self._populate_edge_form(index)

    def _populate_node_form(self, index: int) -> None:
        row = self.node_rows[index]
        for key, variable in self._node_vars.items():
            variable.set(row[key])

    def _populate_edge_form(self, index: int) -> None:
        row = self.edge_rows[index]
        self._syncing_edge_form = True
        try:
            for key, variable in self._edge_vars.items():
                variable.set(row[key])
            for key, variable in self._tech_param_vars.items():
                variable.set(row.get(_param_row_key(key), ""))
        finally:
            self._syncing_edge_form = False
        self._apply_param_defaults(row["cooling_technology"])
        self._render_tech_params(row["cooling_technology"])
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
        self.node_rows[index] = row
        if row["node_id"] != old_id:
            for edge in self.edge_rows:
                if edge["from_node"] == old_id:
                    edge["from_node"] = row["node_id"]
                if edge["to_node"] == old_id:
                    edge["to_node"] = row["node_id"]
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
        self._refresh_node_tree()
        self._refresh_node_combos()
        self._update_dashboard_summary()
        index = len(self.node_rows) - 1
        self.node_tree.selection_set(str(index))
        self._populate_node_form(index)

    def delete_node(self) -> None:
        index = self._selected_index(self.node_tree)
        if index is None:
            messagebox.showwarning("No selection", "Select a node first.")
            return
        node_id = self.node_rows[index]["node_id"]
        if any(
            edge["from_node"] == node_id or edge["to_node"] == node_id
            for edge in self.edge_rows
        ):
            messagebox.showerror(
                "Node in use",
                "Delete or reroute connected edges before deleting this node.",
            )
            return
        del self.node_rows[index]
        self._refresh_node_tree()
        self._refresh_node_combos()
        self._update_dashboard_summary()

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
        self._refresh_edge_tree()
        self._update_dashboard_summary()
        self.edge_tree.selection_set(str(index))
        self._after_apply()

    def add_edge(self) -> None:
        node_ids = [row["node_id"] for row in self.node_rows]
        if len(node_ids) < 2:
            messagebox.showerror("Need nodes", "Add at least two nodes first.")
            return
        edge_id = self._next_id("E", {row["edge_id"] for row in self.edge_rows})
        self.edge_rows.append(
            {
                "edge_id": edge_id,
                "from_node": node_ids[0],
                "to_node": node_ids[1],
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
                "flow_fraction": "",
                "fixed_mdot": "",
                "params_text": "",
                **_default_param_row("smooth"),
            }
        )
        self._refresh_edge_tree()
        self._update_dashboard_summary()
        index = len(self.edge_rows) - 1
        self.edge_tree.selection_set(str(index))
        self._populate_edge_form(index)

    def delete_edge(self) -> None:
        index = self._selected_index(self.edge_tree)
        if index is None:
            messagebox.showwarning("No selection", "Select an edge first.")
            return
        del self.edge_rows[index]
        self._refresh_edge_tree()
        self._update_dashboard_summary()

    def _edge_form_to_row(self) -> dict[str, str]:
        row = {key: variable.get().strip() for key, variable in self._edge_vars.items()}
        for key, variable in self._tech_param_vars.items():
            row[_param_row_key(key)] = variable.get().strip()
        row["params_text"] = self.params_text.get("1.0", tk.END).strip()
        return row

    def _after_apply(self) -> None:
        if self.auto_calculate.get():
            self.calculate(show_success=False)

    def calculate(self, show_success: bool = True) -> None:
        try:
            network = self._build_network_from_rows()
            result = FixedFlowSolver(
                network,
                SolverOptions(property_model=self.property_model.get()),
            ).solve()
        except Exception as exc:
            self.last_result = None
            self._show_dashboard_empty()
            self._set_dashboard_status("FAILED", DANGER_COLOR, "#fde7ea")
            self._set_dashboard_warning_text([f"Calculation failed: {exc}"])
            self._show_warnings([f"Calculation failed: {exc}"])
            self.notebook.select(self.warnings_tab)
            if show_success:
                messagebox.showerror("Calculation failed", str(exc))
            return

        self.last_result = result
        self._show_results(result)
        self._show_dashboard(result)
        self._show_warnings(result.warnings)
        if show_success:
            self.notebook.select(self.dashboard_tab)

    def _build_network_from_rows(self) -> NetworkSpec:
        nodes = [
            NodeSpec(
                node_id=row["node_id"],
                kind=row["kind"],  # type: ignore[arg-type]
                inlet_mdot=_optional_float(row["inlet_mdot"]),
                inlet_temperature=_optional_float(row["inlet_temperature"]),
                inlet_pressure=_optional_float(row["inlet_pressure"]),
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
            )
            edges.append(
                EdgeSpec(
                    edge_id=row["edge_id"],
                    from_node=row["from_node"],
                    to_node=row["to_node"],
                    geometry=geometry,
                    cooling_technology=row["cooling_technology"],  # type: ignore[arg-type]
                    wall=wall,
                    params=_params_from_row(row),
                    flow_fraction=_optional_float(row["flow_fraction"]),
                    fixed_mdot=_optional_float(row["fixed_mdot"]),
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
                    _fmt_number(edge.outlet_temperature, 2),
                    _fmt_number(edge.outlet_pressure, 1),
                ),
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
            "flow": f"{total_flow:.6f} kg/s",
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

    def _show_dashboard(self, result: SolverResult) -> None:
        self._update_dashboard_summary()
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
    return {
        "node_id": node.node_id,
        "kind": node.kind,
        "inlet_mdot": _fmt_optional(node.inlet_mdot),
        "inlet_temperature": _fmt_optional(node.inlet_temperature),
        "inlet_pressure": _fmt_optional(node.inlet_pressure),
    }


def _edge_to_row(edge: EdgeSpec) -> dict[str, str]:
    geometry = edge.geometry
    row = _default_param_row(edge.cooling_technology)
    for key in ALL_PARAM_KEYS:
        if key in edge.params:
            row[_param_row_key(key)] = _fmt_param_value(edge.params[key])
    additional_params = {
        key: value for key, value in edge.params.items() if key not in ALL_PARAM_KEYS
    }
    row.update(
        {
            "edge_id": edge.edge_id,
            "from_node": edge.from_node,
            "to_node": edge.to_node,
            "cooling_technology": edge.cooling_technology,
            "shape": geometry.shape,
            "length": _fmt_optional(geometry.length),
            "width": _fmt_optional(geometry.width),
            "height": _fmt_optional(geometry.height),
            "diameter": _fmt_optional(geometry.diameter),
            "wall_mode": edge.wall.mode,
            "wall_temperature": _fmt_optional(edge.wall.wall_temperature),
            "heat_flux": _fmt_optional(edge.wall.heat_flux),
            "external_htc": _fmt_optional(edge.wall.external_htc),
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
    technology = row["cooling_technology"]
    for spec in TECH_PARAM_SPECS.get(technology, ()):
        value = row.get(_param_row_key(spec.key), "").strip()
        if value:
            params[spec.key] = _parse_value(value)
    return params


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
        number = float(value)
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
    return float(stripped)


def _required_float(value: str, name: str) -> float:
    parsed = _optional_float(value)
    if parsed is None:
        raise ValueError(f"{name} is required.")
    return parsed


def _fmt_optional(value: float | int | None) -> str:
    if value is None:
        return ""
    return f"{value:g}"


def _fmt_param_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return f"{value:g}"
    return str(value)


def _fmt_number(value: float, digits: int) -> str:
    return f"{value:.{digits}f}"


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
                "dp_pa",
                "q_w",
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
                    edge.dp_total,
                    edge.heat_rate,
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
