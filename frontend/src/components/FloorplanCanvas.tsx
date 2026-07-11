"use client";

import { useCallback, useEffect, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type OnNodeDrag,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { BlockNode } from "./BlockNode";
import { useLayoutStore } from "@/store/layoutStore";
import type { Layout } from "@/lib/types";
import { getBlockColors } from "./BlockNode";

const nodeTypes = { block: BlockNode };

const SCALE = 0.8;

function layoutToFlow(layout: Layout): { nodes: Node[]; edges: Edge[] } {
  const blockMap = Object.fromEntries(layout.blocks.map((b) => [b.id, b]));

  const nodes: Node[] = layout.blocks.map((block) => ({
    id: block.id,
    type: "block",
    position: { x: block.x * SCALE, y: block.y * SCALE },
    data: {
      label: block.name,
      blockType: block.type,
      fixed: block.fixed,
      criticality: block.criticality,
      width: block.width * SCALE,
      height: block.height * SCALE,
    },
    draggable: !block.fixed,
    selectable: true,
  }));

  const edges: Edge[] = [];
  for (const net of layout.nets) {
    const sourceBlock = blockMap[net.source];
    if (!sourceBlock) continue;
    for (const sink of net.sinks) {
      if (!blockMap[sink]) continue;
      const strokeWidth = 1 + net.criticality * 3;
      const opacity = 0.3 + net.criticality * 0.5;
      edges.push({
        id: `${net.id}_${sink}`,
        source: net.source,
        target: sink,
        type: "straight",
        style: {
          stroke: net.criticality >= 0.8 ? "#00e5a0" : "#00b4d8",
          strokeWidth,
          opacity,
        },
        animated: net.criticality >= 0.9,
        label: net.criticality >= 0.85 ? net.id : undefined,
        labelStyle: { fill: "#6b7c93", fontSize: 8, fontFamily: "monospace" },
      });
    }
  }

  return { nodes, edges };
}

export default function FloorplanCanvas() {
  const currentLayout = useLayoutStore((s) => s.currentLayout);
  const selectedBlockId = useLayoutStore((s) => s.selectedBlockId);
  const setSelectedBlock = useLayoutStore((s) => s.setSelectedBlock);
  const moveBlock = useLayoutStore((s) => s.moveBlock);
  const pushHistory = useLayoutStore((s) => s.pushHistory);

  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () =>
      currentLayout
        ? layoutToFlow(currentLayout)
        : { nodes: [], edges: [] },
    [currentLayout]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    if (!currentLayout) return;
    const { nodes: n, edges: e } = layoutToFlow(currentLayout);
    setNodes(
      n.map((node) => ({
        ...node,
        selected: node.id === selectedBlockId,
      }))
    );
    setEdges(e);
  }, [currentLayout, selectedBlockId, setNodes, setEdges]);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      setSelectedBlock(node.id);
    },
    [setSelectedBlock]
  );

  const onPaneClick = useCallback(() => {
    setSelectedBlock(null);
  }, [setSelectedBlock]);

  const onNodeDragStop: OnNodeDrag = useCallback(
    (_, node) => {
      if (!currentLayout) return;
      const block = currentLayout.blocks.find((b) => b.id === node.id);
      if (!block || block.fixed) return;
      moveBlock(node.id, node.position.x / SCALE, node.position.y / SCALE);
      pushHistory(`Moved ${block.name}`);
    },
    [currentLayout, moveBlock, pushHistory]
  );

  if (!currentLayout) {
    return (
      <div className="flex-1 flex items-center justify-center text-chip-muted">
        Loading floorplan...
      </div>
    );
  }

  const chipW = currentLayout.chip.width * SCALE;
  const chipH = currentLayout.chip.height * SCALE;

  return (
    <div className="flex-1 relative grid-bg">
      {/* Chip outline overlay */}
      <div
        className="absolute pointer-events-none border-2 border-dashed border-chip-accent/30 rounded"
        style={{
          left: 40,
          top: 40,
          width: chipW,
          height: chipH,
          zIndex: 0,
        }}
      >
        <span className="absolute -top-5 left-0 text-[10px] font-mono text-chip-accent/60">
          {currentLayout.chip.name} ({currentLayout.chip.width}×
          {currentLayout.chip.height} {currentLayout.chip.unit})
        </span>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        onNodeDragStop={onNodeDragStop}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.3}
        maxZoom={2}
        defaultViewport={{ x: 40, y: 40, zoom: 0.9 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          variant={BackgroundVariant.Lines}
          gap={20}
          color="#1e2a3a"
          style={{ background: "transparent" }}
        />
        <Controls
          className="!bg-chip-panel !border-chip-border !shadow-none [&>button]:!bg-chip-panel [&>button]:!border-chip-border [&>button]:!text-chip-text [&>button:hover]:!bg-chip-border"
        />
        <MiniMap
          nodeColor={(node) => {
            const colors = getBlockColors(node.data?.blockType as string);
            return colors.border;
          }}
          maskColor="rgba(10, 14, 20, 0.8)"
          className="!bg-chip-panel !border-chip-border"
        />
      </ReactFlow>
    </div>
  );
}
