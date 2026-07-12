"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLayoutStore } from "@/store/layoutStore";
import type { Block, Layout } from "@/lib/types";
import {
  blockClass,
  congestionColor,
  getBlockStyle,
  isSoftLogic,
  netColor,
  PIN_COLORS,
  powerColor,
} from "@/lib/blockStyles";

interface Viewport {
  scale: number;
  tx: number;
  ty: number;
}

interface Size {
  w: number;
  h: number;
}

function blockCenter(b: Block) {
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
}

function pinPoint(b: Block, side: string, offset: number) {
  switch (side) {
    case "left":
      return { x: b.x, y: b.y + b.height * offset };
    case "right":
      return { x: b.x + b.width, y: b.y + b.height * offset };
    case "top":
      return { x: b.x + b.width * offset, y: b.y };
    default:
      return { x: b.x + b.width * offset, y: b.y + b.height };
  }
}

export default function FloorplanCanvas() {
  const currentLayout = useLayoutStore((s) => s.currentLayout);
  const overlays = useLayoutStore((s) => s.overlays);
  const selectedBlockId = useLayoutStore((s) => s.selectedBlockId);
  const setSelectedBlock = useLayoutStore((s) => s.setSelectedBlock);
  const moveBlock = useLayoutStore((s) => s.moveBlock);
  const pushHistory = useLayoutStore((s) => s.pushHistory);
  const analyze = useLayoutStore((s) => s.analyze);
  const pendingCommand = useLayoutStore((s) => s.pendingCommand);

  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<Size>({ w: 800, h: 600 });
  const [view, setView] = useState<Viewport>({ scale: 0.6, tx: 40, ty: 40 });
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null);
  const fittedDesign = useRef<string>("");

  const chip = currentLayout?.chip;
  const die = chip?.die ?? { x: 0, y: 0, width: chip?.width ?? 1000, height: chip?.height ?? 800 };
  const core = chip?.core ?? die;

  // --- Sizing --------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const ro = new ResizeObserver(() => {
      setSize({ w: el.clientWidth, h: el.clientHeight });
    });
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  const fitView = useCallback(() => {
    if (!die.width || !die.height || !size.w || !size.h) return;
    const pad = 0.14;
    const availW = size.w * (1 - pad * 2);
    const availH = size.h * (1 - pad * 2);
    const scale = Math.min(availW / die.width, availH / die.height);
    const tx = (size.w - die.width * scale) / 2 - die.x * scale;
    const ty = (size.h - die.height * scale) / 2 - die.y * scale;
    setView({ scale, tx, ty });
  }, [die.width, die.height, die.x, die.y, size.w, size.h]);

  // Fit whenever a new design loads or container first sizes.
  useEffect(() => {
    if (!chip) return;
    const key = `${chip.name}:${die.width}x${die.height}`;
    if (fittedDesign.current !== key && size.w > 0) {
      fittedDesign.current = key;
      fitView();
    }
  }, [chip, die.width, die.height, size.w, fitView]);

  // --- Interaction ---------------------------------------------------
  const dragState = useRef<{
    id: string | null;
    panning: boolean;
    startX: number;
    startY: number;
    origBX: number;
    origBY: number;
    origTx: number;
    origTy: number;
    moved: boolean;
  } | null>(null);

  const onWheel = useCallback(
    (e: React.WheelEvent) => {
      e.preventDefault();
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      setView((v) => {
        const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
        const newScale = Math.min(6, Math.max(0.08, v.scale * factor));
        const wx = (mx - v.tx) / v.scale;
        const wy = (my - v.ty) / v.scale;
        return { scale: newScale, tx: mx - wx * newScale, ty: my - wy * newScale };
      });
    },
    []
  );

  const onPointerDownBlock = (e: React.PointerEvent, b: Block) => {
    e.stopPropagation();
    setSelectedBlock(b.id);
    if (b.fixed) return;
    (e.target as Element).setPointerCapture?.(e.pointerId);
    dragState.current = {
      id: b.id,
      panning: false,
      startX: e.clientX,
      startY: e.clientY,
      origBX: b.x,
      origBY: b.y,
      origTx: view.tx,
      origTy: view.ty,
      moved: false,
    };
  };

  const onPointerDownBg = (e: React.PointerEvent) => {
    (e.target as Element).setPointerCapture?.(e.pointerId);
    dragState.current = {
      id: null,
      panning: true,
      startX: e.clientX,
      startY: e.clientY,
      origBX: 0,
      origBY: 0,
      origTx: view.tx,
      origTy: view.ty,
      moved: false,
    };
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const ds = dragState.current;
    if (!ds) return;
    const dx = e.clientX - ds.startX;
    const dy = e.clientY - ds.startY;
    if (Math.abs(dx) + Math.abs(dy) > 2) ds.moved = true;
    if (ds.panning) {
      setView((v) => ({ ...v, tx: ds.origTx + dx, ty: ds.origTy + dy }));
    } else if (ds.id) {
      moveBlock(ds.id, ds.origBX + dx / view.scale, ds.origBY + dy / view.scale);
    }
  };

  const onPointerUp = () => {
    const ds = dragState.current;
    dragState.current = null;
    if (ds?.id && ds.moved) {
      pushHistory("Moved block");
      void analyze();
    } else if (!ds?.id && !ds?.moved) {
      setSelectedBlock(null);
    }
  };

  // --- Derived render data -------------------------------------------
  const blockMap = useMemo(() => {
    const m: Record<string, Block> = {};
    (currentLayout?.blocks ?? []).forEach((b) => (m[b.id] = b));
    return m;
  }, [currentLayout]);

  const previewLayout: Layout | null = pendingCommand?.preview_layout ?? null;

  const T = (n: number, off: number) => n * view.scale + off;

  if (!currentLayout || !chip) {
    return <div className="flex-1 grid-bg" ref={containerRef} />;
  }

  const g = `translate(${view.tx} ${view.ty}) scale(${view.scale})`;

  return (
    <div
      ref={containerRef}
      className="relative flex-1 overflow-hidden grid-bg select-none"
      style={{ cursor: dragState.current?.panning ? "grabbing" : "default" }}
    >
      <svg
        className="absolute inset-0 h-full w-full"
        onWheel={onWheel}
        onPointerDown={onPointerDownBg}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
      >
        <defs>
          <pattern id="keepoutHatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="8" height="8" fill="transparent" />
            <line x1="0" y1="0" x2="0" y2="8" stroke="#ff6b81" strokeWidth="1" opacity="0.5" />
          </pattern>
          <pattern id="stdcellHatch" width="6" height="6" patternUnits="userSpaceOnUse">
            <rect width="6" height="6" fill="#141b26" />
            <circle cx="1.5" cy="1.5" r="0.6" fill="#2a3a4f" />
          </pattern>
        </defs>

        <g transform={g}>
          {/* Die */}
          <rect
            x={die.x}
            y={die.y}
            width={die.width}
            height={die.height}
            fill="#080b11"
            stroke="#2a3a4f"
            strokeWidth={2 / view.scale}
          />
          {/* Core */}
          <rect
            x={core.x}
            y={core.y}
            width={core.width}
            height={core.height}
            fill="none"
            stroke="#00b4d8"
            strokeWidth={1 / view.scale}
            strokeDasharray={`${6 / view.scale} ${4 / view.scale}`}
            opacity={0.5}
          />

          {/* Standard-cell rows */}
          {overlays.rows && <Rows core={core} scale={view.scale} />}

          {/* Power grid */}
          {overlays.powerGrid && <PowerGrid core={core} scale={view.scale} />}

          {/* Congestion heatmap */}
          {overlays.congestion &&
            currentLayout.congestion_regions.map((r, i) => (
              <rect
                key={`cong-${i}`}
                x={r.x}
                y={r.y}
                width={r.width}
                height={r.height}
                fill={congestionColor(r.score)}
                stroke="rgba(255,71,87,0.5)"
                strokeWidth={0.5 / view.scale}
                onPointerEnter={(e) =>
                  setTooltip({
                    x: e.clientX,
                    y: e.clientY,
                    text: `Congestion ${r.score.toFixed(2)} — ${r.reason}`,
                  })
                }
                onPointerLeave={() => setTooltip(null)}
              />
            ))}

          {/* Power density */}
          {overlays.power &&
            currentLayout.power_regions.map((r, i) => (
              <rect
                key={`pow-${i}`}
                x={r.x}
                y={r.y}
                width={r.width}
                height={r.height}
                fill={powerColor(r.density)}
                stroke="rgba(255,140,50,0.5)"
                strokeWidth={0.5 / view.scale}
                onPointerEnter={(e) =>
                  setTooltip({
                    x: e.clientX,
                    y: e.clientY,
                    text: `Power density ${r.density.toFixed(2)} — ${r.reason}`,
                  })
                }
                onPointerLeave={() => setTooltip(null)}
              />
            ))}

          {/* Halos / keepouts */}
          {overlays.halos &&
            currentLayout.blocks.map((b) =>
              b.halo ? (
                <rect
                  key={`halo-${b.id}`}
                  x={b.x - b.halo.left}
                  y={b.y - b.halo.top}
                  width={b.width + b.halo.left + b.halo.right}
                  height={b.height + b.halo.top + b.halo.bottom}
                  fill={b.keepout ? "url(#keepoutHatch)" : "none"}
                  stroke={b.keepout ? "#ff6b81" : "#ffb020"}
                  strokeWidth={0.8 / view.scale}
                  strokeDasharray={`${4 / view.scale} ${3 / view.scale}`}
                  opacity={0.6}
                  pointerEvents="none"
                />
              ) : null
            )}

          {/* Nets */}
          {overlays.nets &&
            currentLayout.nets.map((net) => {
              const src = blockMap[net.source];
              if (!src) return null;
              const s = blockCenter(src);
              return net.sinks.map((sinkId) => {
                const dst = blockMap[sinkId];
                if (!dst) return null;
                const d = blockCenter(dst);
                const isClock = net.type === "clock";
                return (
                  <line
                    key={`${net.id}-${sinkId}`}
                    x1={s.x}
                    y1={s.y}
                    x2={d.x}
                    y2={d.y}
                    stroke={netColor(net.criticality, String(net.type))}
                    strokeWidth={(0.6 + net.criticality * 2.2) / view.scale}
                    strokeDasharray={isClock ? `${5 / view.scale} ${4 / view.scale}` : undefined}
                    opacity={0.55 + net.criticality * 0.35}
                    pointerEvents="none"
                  />
                );
              });
            })}

          {/* Timing paths */}
          {overlays.timing &&
            currentLayout.timing_paths.map((p) => {
              const a = blockMap[p.startpoint];
              const b = blockMap[p.endpoint];
              if (!a || !b) return null;
              const s = blockCenter(a);
              const d = blockCenter(b);
              const violated = p.slack < 0;
              return (
                <g key={`tp-${p.id}`} pointerEvents="none">
                  <line
                    x1={s.x}
                    y1={s.y}
                    x2={d.x}
                    y2={d.y}
                    stroke={violated ? "#ff4757" : "#00e5a0"}
                    strokeWidth={3.5 / view.scale}
                    opacity={0.9}
                    strokeLinecap="round"
                  />
                  <circle cx={s.x} cy={s.y} r={4 / view.scale} fill={violated ? "#ff4757" : "#00e5a0"} />
                  <circle cx={d.x} cy={d.y} r={4 / view.scale} fill={violated ? "#ff4757" : "#00e5a0"} />
                </g>
              );
            })}

          {/* Blocks */}
          {currentLayout.blocks.map((b) => (
            <BlockShape
              key={b.id}
              block={b}
              scale={view.scale}
              selected={b.id === selectedBlockId}
              showPins={overlays.pins || b.id === selectedBlockId}
              showLabel={overlays.labels}
              onPointerDown={(e) => onPointerDownBlock(e, b)}
            />
          ))}

          {/* Preview ghosts: moved existing blocks + newly added blocks */}
          {previewLayout &&
            previewLayout.blocks.map((pb) => {
              const orig = blockMap[pb.id];
              const isNew = !orig;
              if (!isNew && Math.abs(orig!.x - pb.x) < 0.5 && Math.abs(orig!.y - pb.y) < 0.5) {
                return null;
              }
              return (
                <g key={`ghost-${pb.id}`} pointerEvents="none">
                  <rect
                    x={pb.x}
                    y={pb.y}
                    width={pb.width}
                    height={pb.height}
                    rx={2}
                    fill={isNew ? "rgba(0,229,160,0.18)" : "rgba(0,229,160,0.12)"}
                    stroke="#00e5a0"
                    strokeWidth={(isNew ? 1.6 : 1.2) / view.scale}
                    strokeDasharray={`${5 / view.scale} ${3 / view.scale}`}
                  />
                  {isNew && pb.width * view.scale > 30 && (
                    <text
                      x={pb.x + pb.width / 2}
                      y={pb.y + pb.height / 2}
                      textAnchor="middle"
                      dominantBaseline="middle"
                      fill="#00e5a0"
                      fontSize={Math.max(pb.height * 0.12, 6 / view.scale)}
                      fontFamily="monospace"
                    >
                      + {pb.name}
                    </text>
                  )}
                </g>
              );
            })}
        </g>
      </svg>

      {/* Rulers */}
      <Rulers view={view} size={size} die={die} />

      {/* Minimap */}
      <Minimap die={die} blocks={currentLayout.blocks} view={view} size={size} />

      {/* Zoom controls */}
      <div className="absolute bottom-3 left-3 flex flex-col gap-1">
        <button className="canvas-btn" onClick={() => setView((v) => ({ ...v, scale: Math.min(6, v.scale * 1.2) }))}>
          +
        </button>
        <button className="canvas-btn" onClick={() => setView((v) => ({ ...v, scale: Math.max(0.08, v.scale / 1.2) }))}>
          −
        </button>
        <button className="canvas-btn text-[10px]" onClick={fitView} title="Fit to view">
          ⤢
        </button>
      </div>

      {/* Scale readout */}
      <div className="absolute bottom-3 right-3 rounded bg-chip-panel/80 px-2 py-1 font-mono text-[10px] text-chip-muted border border-chip-border">
        {die.width.toFixed(0)}×{die.height.toFixed(0)} µm · {(view.scale * 100).toFixed(0)}%
      </div>

      {tooltip && (
        <div
          className="pointer-events-none fixed z-50 max-w-xs rounded border border-chip-border bg-chip-panel px-2 py-1 font-mono text-[10px] text-chip-text shadow-lg"
          style={{ left: tooltip.x + 12, top: tooltip.y + 12 }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------
// Sub-components
// --------------------------------------------------------------------
function BlockShape({
  block: b,
  scale,
  selected,
  showPins,
  showLabel,
  onPointerDown,
}: {
  block: Block;
  scale: number;
  selected: boolean;
  showPins: boolean;
  showLabel: boolean;
  onPointerDown: (e: React.PointerEvent) => void;
}) {
  const style = getBlockStyle(b);
  const soft = isSoftLogic(b);
  const isRegion = blockClass(b) === "standard_cell_region";
  const cls = blockClass(b);
  const fontSize = Math.min(b.width, b.height) * 0.14;

  return (
    <g onPointerDown={onPointerDown} style={{ cursor: b.fixed ? "not-allowed" : "grab" }}>
      <rect
        x={b.x}
        y={b.y}
        width={b.width}
        height={b.height}
        rx={soft ? 4 : 1}
        fill={isRegion ? "url(#stdcellHatch)" : style.fill}
        stroke={selected ? "#ffffff" : style.stroke}
        strokeWidth={(selected ? 2.5 : 1.4) / scale}
        strokeDasharray={soft && !isRegion ? `${6 / scale} ${3 / scale}` : undefined}
        opacity={soft ? 0.82 : 0.96}
      />
      {/* Fixed indicator corner */}
      {b.fixed && (
        <rect x={b.x} y={b.y} width={Math.min(10, b.width * 0.14)} height={Math.min(10, b.height * 0.14)} fill={style.stroke} />
      )}
      {showLabel && b.width * scale > 34 && (
        <text
          x={b.x + b.width / 2}
          y={b.y + b.height / 2}
          textAnchor="middle"
          dominantBaseline="middle"
          fill="#dfe9f3"
          fontSize={Math.max(fontSize, 6 / scale)}
          fontFamily="var(--font-mono, monospace)"
          pointerEvents="none"
        >
          <tspan x={b.x + b.width / 2} dy={b.height * scale > 46 ? `-0.4em` : 0}>
            {b.name}
          </tspan>
          {b.height * scale > 46 && (
            <tspan x={b.x + b.width / 2} dy="1.2em" fill={style.stroke} fontSize={Math.max(fontSize * 0.7, 5 / scale)}>
              {cls}
            </tspan>
          )}
        </text>
      )}
      {showPins &&
        b.pins.map((p, i) => {
          const pt = pinPoint(b, String(p.side), p.offset);
          return (
            <rect
              key={i}
              x={pt.x - 2.5 / scale}
              y={pt.y - 2.5 / scale}
              width={5 / scale}
              height={5 / scale}
              fill={PIN_COLORS[String(p.type)] ?? PIN_COLORS.signal}
              stroke="#0a0e14"
              strokeWidth={0.4 / scale}
            >
              <title>{`${p.name} (${p.type})`}</title>
            </rect>
          );
        })}
    </g>
  );
}

function Rows({ core, scale }: { core: { x: number; y: number; width: number; height: number }; scale: number }) {
  const rowHeight = 14;
  const rows = Math.floor(core.height / rowHeight);
  const lines = [];
  for (let i = 1; i < rows; i++) {
    lines.push(
      <line
        key={i}
        x1={core.x}
        y1={core.y + i * rowHeight}
        x2={core.x + core.width}
        y2={core.y + i * rowHeight}
        stroke="#141c28"
        strokeWidth={0.5 / scale}
        opacity={0.6}
      />
    );
  }
  return <g pointerEvents="none">{lines}</g>;
}

function PowerGrid({ core, scale }: { core: { x: number; y: number; width: number; height: number }; scale: number }) {
  const step = 90;
  const straps = [];
  for (let x = core.x + step / 2; x < core.x + core.width; x += step) {
    const isVdd = Math.round((x - core.x) / step) % 2 === 0;
    straps.push(
      <line key={`v${x}`} x1={x} y1={core.y} x2={x} y2={core.y + core.height} stroke={isVdd ? "#ff6b3033" : "#00b4d833"} strokeWidth={4 / scale} />
    );
  }
  for (let y = core.y + step / 2; y < core.y + core.height; y += step) {
    const isVdd = Math.round((y - core.y) / step) % 2 === 0;
    straps.push(
      <line key={`h${y}`} x1={core.x} y1={y} x2={core.x + core.width} y2={y} stroke={isVdd ? "#ff6b3033" : "#00b4d833"} strokeWidth={4 / scale} />
    );
  }
  return (
    <g pointerEvents="none">
      {straps}
      <rect x={core.x} y={core.y} width={core.width} height={core.height} fill="none" stroke="#ff6b3055" strokeWidth={6 / scale} />
      <text x={core.x + 4} y={core.y + 14 / scale} fill="#ff6b81" fontSize={12 / scale} fontFamily="monospace">
        VDD/GND grid
      </text>
    </g>
  );
}

function Rulers({ view, size, die }: { view: Viewport; size: Size; die: { x: number; y: number; width: number; height: number } }) {
  const ticks = [];
  const worldStep = niceStep(200 / view.scale);
  const start = Math.ceil((0 - view.tx) / view.scale / worldStep) * worldStep;
  for (let w = start; w * view.scale + view.tx < size.w; w += worldStep) {
    const sx = w * view.scale + view.tx;
    if (sx < 28) continue;
    ticks.push(
      <div key={`x${w}`} className="absolute top-0 text-[9px] text-chip-muted font-mono" style={{ left: sx }}>
        <div className="h-1.5 w-px bg-chip-border" />
        <span className="ml-0.5">{w.toFixed(0)}</span>
      </div>
    );
  }
  const yticks = [];
  for (let w = start; w * view.scale + view.ty < size.h; w += worldStep) {
    const sy = w * view.scale + view.ty;
    if (sy < 14) continue;
    yticks.push(
      <div key={`y${w}`} className="absolute left-0 text-[9px] text-chip-muted font-mono" style={{ top: sy }}>
        <span>{w.toFixed(0)}</span>
      </div>
    );
  }
  return (
    <>
      <div className="pointer-events-none absolute left-0 top-0 h-4 w-full border-b border-chip-border/40 bg-chip-bg/40">{ticks}</div>
      <div className="pointer-events-none absolute left-0 top-0 h-full w-6 border-r border-chip-border/40 bg-chip-bg/40">{yticks}</div>
    </>
  );
}

function niceStep(raw: number): number {
  const pow = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / pow;
  const step = n >= 5 ? 5 : n >= 2 ? 2 : 1;
  return step * pow;
}

function Minimap({
  die,
  blocks,
  view,
  size,
}: {
  die: { x: number; y: number; width: number; height: number };
  blocks: Block[];
  view: Viewport;
  size: Size;
}) {
  const mmW = 130;
  const mmH = (mmW * die.height) / die.width;
  const s = mmW / die.width;
  // Visible viewport in world coords.
  const vx = (0 - view.tx) / view.scale;
  const vy = (0 - view.ty) / view.scale;
  const vw = size.w / view.scale;
  const vh = size.h / view.scale;
  return (
    <div className="absolute right-3 top-6 rounded border border-chip-border bg-chip-panel/85 p-1">
      <svg width={mmW} height={mmH}>
        <rect x={0} y={0} width={mmW} height={mmH} fill="#080b11" />
        {blocks.map((b) => {
          const st = getBlockStyle(b);
          return (
            <rect
              key={b.id}
              x={(b.x - die.x) * s}
              y={(b.y - die.y) * s}
              width={b.width * s}
              height={b.height * s}
              fill={st.stroke}
              opacity={0.7}
            />
          );
        })}
        <rect
          x={(vx - die.x) * s}
          y={(vy - die.y) * s}
          width={vw * s}
          height={vh * s}
          fill="none"
          stroke="#00e5a0"
          strokeWidth={1}
        />
      </svg>
    </div>
  );
}
