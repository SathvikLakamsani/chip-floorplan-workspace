# Chip Floorplan Workspace — MVP

AI-assisted backend chip floorplanning workspace built on top of OpenROAD Flow Scripts concepts.

## Overview

A "Cursor/Figma for backend chip layout" that helps physical design engineers:

- Visualize and edit chip floorplans on an interactive canvas
- Use natural-language commands to propose layout changes (with preview before apply)
- Compare layout candidates by timing, congestion, and wire length metrics
- Export layouts as JSON (Tcl/DEF planned)

## Architecture

```
chip-floorplan-workspace/
├── backend/          FastAPI + Pydantic models + mock analysis engine
├── frontend/         Next.js + React Flow + Tailwind CSS
├── examples/         Sample toy design + mock reports
├── docker-compose.yml
└── start.sh          One-command local dev startup
```

### Relationship to OpenROAD Flow Scripts (ORFS)

This is a **standalone product** that uses ORFS/OpenROAD as an *external EDA engine*,
not a fork of it. The app talks to the engine through an adapter interface
(`backend/app/adapters/base.py`):

- `MockEDAAdapter` — default; computes approximate metrics locally (no ORFS needed).
- `OpenROADAdapter` — stub for real integration; will shell out to a locally
  installed ORFS and parse its DEF/LEF/timing/congestion reports.

You do **not** need ORFS installed to run the MVP.

## Quick Start

### Option A — Docker (one command)

```bash
docker compose up --build
```

Frontend on [http://localhost:3000](http://localhost:3000), backend on
[http://localhost:8000/docs](http://localhost:8000/docs).

### Option B — local dev script

```bash
./start.sh
```

### Option C — run each service manually

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## MVP Features

- **Canvas**: Drag blocks, view nets, color-coded by type (compute, SRAM, NoC, IO, PLL, controller)
- **Inspector**: Edit block properties, lock/unlock, view connected nets
- **Command bar**: Natural-language commands with preview/apply/cancel workflow
- **Candidates**: Generate and compare 3 layout alternatives
- **Export**: Download layout as JSON

## Example Commands

- `Move SRAM closer to compute`
- `Lock the PLL`
- `Optimize for timing`
- `Reduce congestion near the top right`
- `Generate three candidate layouts`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/layouts/example` | Load toy AI accelerator design |
| POST | `/api/layouts/analyze` | Compute layout metrics |
| POST | `/api/layouts/command` | Parse natural-language command |
| POST | `/api/layouts/apply` | Apply structured actions |
| POST | `/api/layouts/generate-candidates` | Generate 3 candidates |
| POST | `/api/layouts/export` | Export layout (JSON/Tcl/DEF) |

## Future Work (TODOs in code)

- Real OpenROAD Flow Scripts integration (`OpenROADAdapter`)
- DEF parser for floorplan geometry
- LEF parser for macro dimensions
- Timing report parser (OpenSTA format)
- Congestion report parser (FastRoute format)
- Tcl constraint export for ORFS
- LLM structured-output command parser
- OpenROAD rerun pipeline (floorplan → placement → routing → STA)

## Tech Stack

- **Frontend**: Next.js 14, React, TypeScript, Tailwind CSS, React Flow, Zustand
- **Backend**: FastAPI, Pydantic v2, Python 3.10+
