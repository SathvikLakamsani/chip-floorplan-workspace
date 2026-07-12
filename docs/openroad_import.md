# Importing an OpenROAD / OpenLane run

The workspace can reconstruct a floorplan from an existing **OpenROAD**,
**OpenROAD Flow Scripts (ORFS)**, or **OpenLane** run. Importing is fully
**offline**: the app scans a run directory for output files and parses them. It
never launches or shells out to OpenROAD, so you can run the physical-design
tools wherever you like and just point the workspace at the results.

## What gets parsed

The importer walks the run directory recursively and categorizes files:

| Kind | Matched by | Used for |
| --- | --- | --- |
| DEF (`*.def`) | file extension | die/core area, component placement, orientation, pins |
| LEF (`*.lef`) | file extension | macro dimensions and pin geometry |
| Metrics (`*.json`) | name contains `metric`, `qor`, `summary`, `report` | WNS, TNS, violating paths, wire length, utilization, congestion, power, DRC count |
| Timing report (`*.rpt`/`*.log`/`*.txt`) | name contains `timing`, `sta`, `slack`, `setup`, `hold` | worst timing paths + slack |
| Congestion report (`*.rpt`/`*.log`/`*.txt`) | name contains `congestion`, `overflow`, `grt`, `route` | congestion hotspots |

When multiple DEF files exist, the one with the **most components** is chosen
(typically the latest floorplan/placement/routing stage). If no LEF is found,
component sizes are estimated from the DEF placement and instance names, and a
warning is surfaced.

Large numbers of individual standard cells are collapsed into a single
`standard_cell_region` block so the canvas stays readable; hard macros, IOs,
memories, and clock/analog cells are rendered individually.

## Directory layout it understands

A typical ORFS results tree works out of the box:

```
my_run/
├── results/
│   └── .../6_final.def          # placement/route DEF
├── objects/
│   └── .../*.lef                # tech + macro LEF
├── reports/
│   ├── *timing*.rpt
│   └── *congestion*.rpt
└── metrics.json                 # or *_qor.json / *summary*.json
```

A minimal run only needs a **DEF** file. Everything else (LEF, metrics, timing,
congestion) enriches the result but is optional.

## How to import

### From the UI

1. Click **Import OpenROAD** in the top-right of the editor.
2. Paste the path to your run directory.
   - Paths are resolved **relative to the backend process's working directory**
     (the `backend/` folder when started via `start.sh`), or you can use an
     absolute path such as `/Users/you/designs/my_run`.
   - Click **Use bundled sample run** to load `../examples/openroad_run`, a small
     self-contained example checked into this repo.
3. Click **Import**. The panel reports the design name, unit scale, how many of
   each file type were found, and any parser warnings.
4. Click **View on canvas**. The design loads with the source badge switched to
   **IMPORTED**. Use **← Back to demo layout** in the left sidebar to return to
   the built-in demo.

### From the API

```bash
curl -s -X POST localhost:8000/api/import/openroad \
  -H 'Content-Type: application/json' \
  -d '{"path": "/absolute/path/to/run"}'
```

Response shape:

```jsonc
{
  "layout": { /* full Layout model, or null on failure */ },
  "warnings": ["No LEF files found; component sizes estimated from names."],
  "files_found": {
    "def": ["..."], "lef": ["..."], "metrics": ["..."],
    "timing_reports": ["..."], "congestion_reports": ["..."]
  },
  "design_name": "toy_accelerator_imported",
  "unit_scale": "1000 DBU/µm"
}
```

If `layout` is `null`, check `warnings` — the most common cause is that no
usable DEF was found in the directory.

## After importing

Everything in the editor works the same on imported designs:

- Natural-language commands, DRC/legality checks, and QoR analysis.
- Overlays (nets, pins, timing, congestion, power, power grid, rows, halos).
- Candidate generation and comparison.
- Export back out to **JSON**, **DEF**, or **Tcl** constraints.

## Architecture notes

Import is implemented behind an EDA-adapter abstraction so other flows can be
added later:

- `backend/app/importers/` — standalone parsers (`def_parser`, `lef_parser`,
  `metrics_parser`, `timing_parser`, `congestion_parser`) and the
  `openroad_importer` that stitches them into a `Layout`.
- `backend/app/eda/adapters.py` — `EDAAdapter` interface with
  `MockEDAAdapter` (the built-in demo engine) and `OpenROADImportAdapter`
  (offline import). The HTTP endpoint (`/api/import/openroad`) delegates to the
  adapter, so swapping in a live-tool adapter later requires no API changes.

Parsers are intentionally defensive: a malformed file adds a warning rather than
failing the whole import.
