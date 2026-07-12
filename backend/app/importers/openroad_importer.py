"""OpenROAD / OpenLane offline run importer.

Recursively scans a local run directory, discovers DEF/LEF/metrics/timing/
congestion files, parses what it can, and produces our internal Layout model.

Design principles (per MVP scope):
- Offline only. Does NOT execute OpenROAD or parse GDS.
- Robust partial import over perfect parsing — always return a layout + warnings.
- Do NOT render every standard cell individually; group them into a single
  `standard_cell_region` (or leave macros individual).
"""

from __future__ import annotations

import re
from pathlib import Path

from app.importers.congestion_parser import parse_congestion_report
from app.importers.def_parser import DefComponent, DefData, parse_def
from app.importers.lef_parser import LefMacro, parse_lef
from app.importers.metrics_parser import parse_metrics_files
from app.importers.timing_parser import parse_timing_report
from app.models.layout import (
    Block,
    Chip,
    ImportResponse,
    Layout,
    Pin,
    Rect,
)

_MAX_INDIVIDUAL_STDCELLS = 24  # above this, group std cells into a region

_METRIC_FILE_HINTS = ("metric", "state_out", "or_metrics", "qor")
_TIMING_HINTS = ("timing", "sta", "report_checks", "setup", "hold")
_CONGESTION_HINTS = ("congestion", "congest", "overflow", "routing_report")


def scan_directory(root: Path) -> dict[str, list[str]]:
    """Categorize relevant files under root (recursive)."""
    found: dict[str, list[str]] = {
        "def": [],
        "lef": [],
        "metrics": [],
        "timing_reports": [],
        "congestion_reports": [],
    }
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        name = p.name.lower()
        suffix = p.suffix.lower()
        if suffix == ".def":
            found["def"].append(str(p))
        elif suffix == ".lef":
            found["lef"].append(str(p))
        elif suffix == ".json" and any(h in name for h in _METRIC_FILE_HINTS):
            found["metrics"].append(str(p))
        elif suffix in (".rpt", ".log", ".txt"):
            if any(h in name for h in _CONGESTION_HINTS):
                found["congestion_reports"].append(str(p))
            elif any(h in name for h in _TIMING_HINTS):
                found["timing_reports"].append(str(p))
    return found


def import_run(path: str) -> ImportResponse:
    root = Path(path).expanduser()
    if not root.exists() or not root.is_dir():
        return ImportResponse(
            warnings=[f"Path does not exist or is not a directory: {path}"],
        )

    files = scan_directory(root)
    warnings: list[str] = []

    # --- LEF macros (for sizing/pins) -------------------------------
    macros: dict[str, LefMacro] = {}
    for lef in files["lef"]:
        try:
            macros.update(parse_lef(lef))
        except Exception as exc:  # noqa: BLE001 - never crash the import
            warnings.append(f"Failed to parse LEF {Path(lef).name}: {exc}")
    if not files["lef"]:
        warnings.append("No LEF files found; component sizes estimated from names.")

    # --- DEF (choose the one with the most components) --------------
    def_data: DefData | None = None
    if files["def"]:
        best: tuple[int, DefData] | None = None
        for d in files["def"]:
            try:
                parsed = parse_def(d)
                if best is None or len(parsed.components) > best[0]:
                    best = (len(parsed.components), parsed)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Failed to parse DEF {Path(d).name}: {exc}")
        if best:
            def_data = best[1]
            warnings.extend(def_data.warnings)
    else:
        warnings.append("No DEF files found; cannot reconstruct placement geometry.")

    if def_data is None:
        return ImportResponse(warnings=warnings + ["Import failed: no usable DEF."], files_found=files)

    design_name = def_data.design or root.name
    unit_scale = (
        f"{def_data.units_per_micron:.0f} DBU/µm" if def_data.units_per_micron else "raw DBU"
    )

    layout, layout_warnings = _build_layout(def_data, macros, design_name)
    warnings.extend(layout_warnings)

    # --- Metrics ----------------------------------------------------
    if files["metrics"]:
        metrics, mwarn = parse_metrics_files(files["metrics"])
        layout.metrics = metrics
        warnings.extend(mwarn)
    else:
        warnings.append("No metrics JSON found; QoR metrics will be estimated.")

    # --- Timing -----------------------------------------------------
    for rpt in files["timing_reports"]:
        paths, twarn = parse_timing_report(rpt)
        if paths:
            layout.timing_paths = paths
            warnings.extend(twarn)
            break
    else:
        if files["timing_reports"]:
            warnings.append("Timing reports found but no paths parsed.")

    # --- Congestion -------------------------------------------------
    for rpt in files["congestion_reports"]:
        regions, cwarn = parse_congestion_report(rpt)
        warnings.extend(cwarn)
        if regions:
            layout.congestion_regions = regions
            break

    return ImportResponse(
        layout=layout,
        warnings=warnings,
        files_found=files,
        design_name=design_name,
        unit_scale=unit_scale,
    )


# ----------------------------------------------------------------------
# Layout construction
# ----------------------------------------------------------------------
def _build_layout(
    def_data: DefData, macros: dict[str, LefMacro], design_name: str
) -> tuple[Layout, list[str]]:
    warnings: list[str] = []

    if def_data.die:
        x1, y1, x2, y2 = def_data.die
        die = Rect(x=x1, y=y1, width=x2 - x1, height=y2 - y1)
    else:
        die = Rect(x=0, y=0, width=1000, height=1000)
        warnings.append("No DIEAREA in DEF; using a default 1000×1000 die.")

    margin = min(die.width, die.height) * 0.06
    core = Rect(
        x=die.x + margin, y=die.y + margin,
        width=die.width - 2 * margin, height=die.height - 2 * margin,
    )

    macro_blocks: list[Block] = []
    stdcells: list[DefComponent] = []

    for comp in def_data.components:
        macro = macros.get(comp.master)
        w = macro.width if macro and macro.width else 0.0
        h = macro.height if macro and macro.height else 0.0
        btype, bclass = _classify(comp, macro)

        is_macro = bclass in ("hard_macro", "memory", "io", "clock", "analog")
        if not is_macro and w * h < (core.width * core.height * 0.01):
            stdcells.append(comp)
            continue

        if w <= 0 or h <= 0:
            # Estimate size for macros without LEF dimensions.
            w = w or max(40.0, core.width * 0.12)
            h = h or max(40.0, core.height * 0.12)

        block = Block(
            id=_safe_id(comp.instance),
            name=comp.instance,
            type=btype,
            **{"class": bclass},
            x=comp.x,
            y=comp.y,
            width=w,
            height=h,
            fixed=(comp.status == "FIXED"),
            orientation=comp.orientation,
            placement_status=comp.status.lower(),
        )
        if macro and macro.pins:
            block.pins = _pins_from_lef(macro)
        macro_blocks.append(block)

    blocks = macro_blocks

    # Group standard cells into a single region.
    if stdcells:
        if len(stdcells) > _MAX_INDIVIDUAL_STDCELLS:
            region = _stdcell_region(stdcells, core)
            blocks.append(region)
            warnings.append(
                f"Grouped {len(stdcells)} standard cells into a single "
                "standard_cell_region (individual std cells are not rendered)."
            )
        else:
            warnings.append(
                f"{len(stdcells)} small instances treated as standard cells "
                "(not individually rendered)."
            )

    if not blocks:
        warnings.append("No placeable components found in DEF.")

    chip = Chip(name=design_name, die=die, core=core, width=die.width, height=die.height)
    layout = Layout(chip=chip, blocks=blocks, nets=[])
    return layout, warnings


def _stdcell_region(cells: list[DefComponent], core: Rect) -> Block:
    xs = [c.x for c in cells if c.x or c.y]
    ys = [c.y for c in cells if c.x or c.y]
    if xs and ys:
        x0, y0 = min(xs), min(ys)
        x1, y1 = max(xs), max(ys)
        w = max(x1 - x0, core.width * 0.3)
        h = max(y1 - y0, core.height * 0.3)
    else:
        x0, y0 = core.x, core.y
        w, h = core.width, core.height
    return Block(
        id="standard_cell_region",
        name=f"Standard Cell Region ({len(cells)} cells)",
        type="stdcell",
        **{"class": "standard_cell_region"},
        x=x0,
        y=y0,
        width=w,
        height=h,
        fixed=False,
        instance_count=len(cells),
        criticality=0.4,
    )


def _classify(comp: DefComponent, macro: LefMacro | None) -> tuple[str, str]:
    name = f"{comp.instance} {comp.master}".lower()
    lef_class = (macro.cls if macro else "").upper()

    if re.search(r"sram|\bram\b|mem|dff_mem|rf_", name):
        return "memory", "hard_macro"
    if re.search(r"pll|\bclk\b|clock|dco", name):
        return "clock", "hard_macro"
    if re.search(r"pad|gpio|\bio\b|iocell|bondpad", name) or "PAD" in lef_class:
        return "io", "io"
    if re.search(r"analog|adc|dac|bandgap|ldo", name):
        return "analog", "analog"
    if "BLOCK" in lef_class or "MACRO" in lef_class or "RING" in lef_class:
        return "other", "hard_macro"
    return "stdcell", "soft_logic"


def _pins_from_lef(macro: LefMacro) -> list[Pin]:
    pins: list[Pin] = []
    sides = ["left", "top", "right", "bottom"]
    signal_pins = [p for p in macro.pins if p.name.lower() not in ("vdd", "vss", "gnd", "vpwr", "vgnd")]
    for i, p in enumerate(signal_pins[:12]):
        ptype = "signal"
        if re.search(r"clk|clock", p.name.lower()):
            ptype = "clock"
        elif re.search(r"vdd|vpwr|power", p.name.lower()):
            ptype = "power"
        elif re.search(r"vss|gnd|vgnd", p.name.lower()):
            ptype = "ground"
        pins.append(
            Pin(
                name=p.name,
                side=sides[i % 4],
                offset=0.2 + 0.6 * ((i // 4) % 3) / 2,
                type=ptype,
                direction=p.direction,
            )
        )
    return pins


def _safe_id(instance: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", instance)
