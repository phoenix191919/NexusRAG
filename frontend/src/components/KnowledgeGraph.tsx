import { useEffect, useMemo, useRef } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { GraphData } from "../api";

const TYPE_COLORS: Record<string, string> = {
  Entity: "#3de0c5",
  Model: "#ff6b9d",
  Technique: "#7c6cff",
  Organization: "#f0b429",
  Concept: "#5eead4",
  Source: "#4da3ff",
  Reference: "#a78bfa",
};

const MAX_NODES = 200;

type KgNodeData = {
  label: string;
  type?: string;
  highlighted: boolean;
  dimmed: boolean;
  degree: number;
};

function colorForType(type?: string) {
  if (!type) return TYPE_COLORS.Entity;
  return TYPE_COLORS[type] || TYPE_COLORS.Entity;
}

function GlowNode({ data }: NodeProps) {
  const d = data as KgNodeData;
  const size = Math.min(48, 16 + d.degree * 3 + (d.highlighted ? 10 : 0));
  const color = colorForType(d.type);
  const handleStyle = {
    width: 6,
    height: 6,
    opacity: 0,
    border: "none",
    background: "transparent",
  };
  return (
    <div
      className={`kg-node ${d.highlighted ? "kg-node--lit" : ""} ${d.dimmed ? "kg-node--dim" : ""}`}
      style={{ ["--node-color" as string]: color }}
    >
      <Handle id="t" type="target" position={Position.Top} style={handleStyle} />
      <Handle id="l" type="target" position={Position.Left} style={handleStyle} />
      <div className="kg-node__disc" style={{ width: size, height: size }} />
      <div className="kg-node__label" title={d.label}>
        {d.label}
      </div>
      <Handle id="r" type="source" position={Position.Right} style={handleStyle} />
      <Handle id="b" type="source" position={Position.Bottom} style={handleStyle} />
    </div>
  );
}

const nodeTypes = { glow: GlowNode };

function FitOnce({ signature }: { signature: string }) {
  const { fitView } = useReactFlow();
  const last = useRef("");
  useEffect(() => {
    if (!signature || signature === last.current) return;
    last.current = signature;
    const t = setTimeout(() => fitView({ padding: 0.2, duration: 450 }), 80);
    return () => clearTimeout(t);
  }, [signature, fitView]);
  return null;
}

function layoutPositions(count: number) {
  if (count === 0) return [] as { x: number; y: number }[];
  const positions: { x: number; y: number }[] = [];
  let placed = 0;
  let ring = 0;
  while (placed < count) {
    const capacity = ring === 0 ? 1 : Math.min(count - placed, 6 + ring * 5);
    const radius = ring === 0 ? 0 : 160 + ring * 150;
    for (let i = 0; i < capacity && placed < count; i++) {
      const angle = (2 * Math.PI * i) / capacity - Math.PI / 2;
      positions.push({
        x: Math.cos(angle) * radius + (ring % 2 === 0 ? 0 : 24),
        y: Math.sin(angle) * radius + (ring % 3 === 0 ? 0 : 16),
      });
      placed++;
    }
    ring++;
  }
  return positions;
}

function buildGraphElements(data: GraphData, highlightedIds: Set<string>) {
  const queryActive = highlightedIds.size > 0;
  const raw = (data.nodes || []).filter((n) => n.type !== "Source").slice(0, MAX_NODES);
  const idSet = new Set(raw.map((n) => n.id));

  const degree = new Map<string, number>();
  for (const e of data.edges || []) {
    if (!idSet.has(e.source) || !idSet.has(e.target)) continue;
    degree.set(e.source, (degree.get(e.source) || 0) + 1);
    degree.set(e.target, (degree.get(e.target) || 0) + 1);
  }

  const positions = layoutPositions(raw.length);
  const nodes: Node[] = raw.map((n, i) => {
    const lit = highlightedIds.has(n.id);
    return {
      id: n.id,
      type: "glow",
      position: positions[i] || { x: i * 40, y: i * 20 },
      data: {
        label: n.label,
        type: n.type,
        highlighted: lit,
        dimmed: queryActive && !lit,
        degree: degree.get(n.id) || 1,
      } satisfies KgNodeData,
      draggable: true,
    };
  });

  const edges: Edge[] = (data.edges || [])
    .filter((e) => idSet.has(e.source) && idSet.has(e.target))
    .slice(0, 400)
    .map((e, i) => {
      const bothLit = highlightedIds.has(e.source) && highlightedIds.has(e.target);
      const eitherLit = highlightedIds.has(e.source) || highlightedIds.has(e.target);
      const srcType = raw.find((n) => n.id === e.source)?.type;
      const baseColor = colorForType(srcType);
      const stroke = bothLit ? "#ffffff" : eitherLit ? baseColor : "rgba(150, 175, 230, 0.55)";
      return {
        id: `e-${i}-${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        sourceHandle: "r",
        targetHandle: "l",
        label: e.label || "related",
        type: "default",
        animated: bothLit,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: stroke,
          width: 16,
          height: 16,
        },
        style: {
          stroke,
          strokeWidth: bothLit ? 2.6 : eitherLit ? 1.8 : 1.35,
          opacity: queryActive && !eitherLit ? 0.2 : 0.95,
        },
        labelStyle: {
          fill: bothLit || !queryActive ? "#e8eefc" : "#9aa8c7",
          fontSize: 10,
          fontWeight: 500,
        },
        labelBgStyle: { fill: "#0a1020", fillOpacity: 0.85 },
        labelBgPadding: [4, 6] as [number, number],
        labelBgBorderRadius: 4,
      };
    });

  return { nodes, edges, signature: raw.map((n) => n.id).sort().join("|") };
}

export default function KnowledgeGraph({
  data,
  highlightedIds,
  onNodeSelect,
}: {
  data: GraphData;
  highlightedIds: Set<string>;
  onNodeSelect?: (nodeId: string) => void;
}) {
  const built = useMemo(() => buildGraphElements(data, highlightedIds), [data, highlightedIds]);
  const [nodes, setNodes, onNodesChange] = useNodesState(built.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(built.edges);

  // Sync from data/highlights while preserving user-dragged positions
  useEffect(() => {
    setNodes((prev) => {
      const pos = new Map(prev.map((n) => [n.id, n.position]));
      return built.nodes.map((n) => ({
        ...n,
        position: pos.get(n.id) || n.position,
      }));
    });
    setEdges(built.edges);
  }, [built, setNodes, setEdges]);

  if (!built.nodes.length) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[var(--muted)]">
        Upload sources to grow the knowledge constellation.
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={(_evt, node) => onNodeSelect?.(node.id)}
      nodeTypes={nodeTypes}
      fitView
      minZoom={0.15}
      maxZoom={3}
      panOnDrag
      panOnScroll={false}
      zoomOnScroll
      zoomOnPinch
      zoomOnDoubleClick
      selectionOnDrag={false}
      nodesDraggable
      nodesConnectable={false}
      elementsSelectable
      proOptions={{ hideAttribution: true }}
      colorMode="dark"
      defaultEdgeOptions={{
        type: "default",
        style: { stroke: "rgba(150, 175, 230, 0.55)", strokeWidth: 1.35 },
      }}
    >
      <Background
        id="dots"
        variant={BackgroundVariant.Dots}
        gap={22}
        size={1.2}
        color="rgba(120,140,190,0.28)"
        bgColor="#050814"
      />
      <MiniMap
        pannable
        zoomable
        nodeColor={(n) => colorForType((n.data as KgNodeData)?.type)}
        maskColor="rgba(5,8,20,0.7)"
      />
      <Controls position="top-right" showInteractive />
      <FitOnce signature={built.signature} />
    </ReactFlow>
  );
}
