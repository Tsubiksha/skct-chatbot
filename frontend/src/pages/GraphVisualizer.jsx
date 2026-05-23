import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  useEdgesState,
  useNodesState
} from "reactflow";
import "reactflow/dist/style.css";
import {
  ArrowLeft,
  BookOpen,
  BriefcaseBusiness,
  Building2,
  GraduationCap,
  Library,
  Network,
  Search,
  UsersRound
} from "lucide-react";
import { getGraphData, getGraphStats } from "../lib/api";

const categories = [
  {
    id: "cse",
    label: "CSE Department",
    icon: BookOpen,
    color: "#2563eb",
    bg: "bg-blue-50",
    text: "text-blue-700",
    keywords: ["cse", "computer", "science", "software", "ai", "ml", "cyber", "iot"],
    children: ["Faculty", "Courses", "Labs", "Placements"]
  },
  {
    id: "ece",
    label: "ECE Department",
    icon: Network,
    color: "#16a34a",
    bg: "bg-emerald-50",
    text: "text-emerald-700",
    keywords: ["ece", "electronics", "communication", "signal", "antenna"],
    children: ["Faculty", "Courses", "Labs", "Research"]
  },
  {
    id: "placements",
    label: "Placement Cell",
    icon: BriefcaseBusiness,
    color: "#ca8a04",
    bg: "bg-amber-50",
    text: "text-amber-700",
    keywords: ["placement", "placements", "recruiter", "company", "training", "salary"],
    children: ["Recruiters", "Training", "Packages", "Career Services"]
  },
  {
    id: "admissions",
    label: "Admissions",
    icon: GraduationCap,
    color: "#9333ea",
    bg: "bg-purple-50",
    text: "text-purple-700",
    keywords: ["admission", "admissions", "tnea", "counselling", "cutoff", "intake"],
    children: ["TNEA Code", "Cutoff", "Programmes", "Contact"]
  },
  {
    id: "campus",
    label: "Campus Life",
    icon: Building2,
    color: "#dc2626",
    bg: "bg-red-50",
    text: "text-red-700",
    keywords: ["campus", "hostel", "library", "sports", "facility", "facilities", "transport"],
    children: ["Hostel", "Library", "Sports", "Facilities"]
  }
];

function KnowledgeNode({ data }) {
  return (
    <div className="min-w-[150px] rounded-lg border bg-white px-4 py-3 text-center shadow-sm transition hover:-translate-y-0.5 hover:shadow-md" style={{ borderColor: data.color }}>
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !bg-slate-400" />
      <div className="mx-auto mb-2 h-2 w-10 rounded-full" style={{ backgroundColor: data.color }} />
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{data.type}</div>
      <div className="mt-1 text-sm font-semibold leading-snug text-slate-950">{data.label}</div>
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !bg-slate-400" />
    </div>
  );
}

function buildCategoryGraph(category, graphData) {
  const allNodes = graphData?.nodes || [];
  const allEdges = graphData?.edges || [];
  const keywordRegex = new RegExp(category.keywords.join("|"), "i");

  const matchedNodes = allNodes.filter((node) => {
    const label = node.data?.label || "";
    const type = node.data?.type || "";
    return keywordRegex.test(`${label} ${type}`);
  });

  if (matchedNodes.length > 0) {
    const matchedIds = new Set(matchedNodes.map((node) => node.id));
    const relatedEdges = allEdges.filter((edge) => matchedIds.has(edge.source) || matchedIds.has(edge.target)).slice(0, 16);
    const relatedIds = new Set(matchedIds);
    relatedEdges.forEach((edge) => {
      relatedIds.add(edge.source);
      relatedIds.add(edge.target);
    });

    const nodes = allNodes
      .filter((node) => relatedIds.has(node.id))
      .slice(0, 20)
      .map((node, index) => ({
        ...node,
        type: "knowledge",
        position: node.position || {
          x: 120 + (index % 4) * 210,
          y: 90 + Math.floor(index / 4) * 150
        },
        data: {
          ...node.data,
          color: node.data?.color || category.color
        }
      }));

    return {
      nodes,
      edges: relatedEdges.map((edge) => ({
        ...edge,
        animated: true,
        style: { stroke: category.color, strokeWidth: 1.8 },
        labelStyle: { fontSize: 11, fill: "#475569" }
      }))
    };
  }

  const centerId = `${category.id}-root`;
  const nodes = [
    {
      id: centerId,
      type: "knowledge",
      position: { x: 360, y: 60 },
      data: { label: category.label, type: "Category", color: category.color }
    },
    ...category.children.map((child, index) => ({
      id: `${category.id}-${child.toLowerCase().replace(/\s+/g, "-")}`,
      type: "knowledge",
      position: { x: 90 + index * 190, y: 270 },
      data: { label: child, type: "Node", color: category.color }
    }))
  ];

  const edges = nodes.slice(1).map((node) => ({
    id: `${centerId}-${node.id}`,
    source: centerId,
    target: node.id,
    animated: true,
    label: "contains",
    style: { stroke: category.color, strokeWidth: 1.8 },
    labelStyle: { fontSize: 11, fill: "#475569" }
  }));

  return { nodes, edges };
}

export default function GraphVisualizer() {
  const navigate = useNavigate();
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [stats, setStats] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const nodeTypes = useMemo(() => ({ knowledge: KnowledgeNode }), []);

  useEffect(() => {
    const token = localStorage.getItem("skct_token");
    if (!token) {
      navigate("/login");
      return;
    }
    loadGraph();
  }, [navigate]);

  useEffect(() => {
    if (!selectedCategory) return;
    const nextGraph = buildCategoryGraph(selectedCategory, graphData);
    setNodes(nextGraph.nodes);
    setEdges(nextGraph.edges);
    setSelectedNode(null);
  }, [selectedCategory, graphData, setNodes, setEdges]);

  const loadGraph = async () => {
    const [graphResult, statsResult] = await Promise.allSettled([getGraphData(), getGraphStats()]);
    if (graphResult.status === "fulfilled") {
      setGraphData({
        nodes: graphResult.value.nodes || [],
        edges: graphResult.value.edges || []
      });
    }
    if (statsResult.status === "fulfilled") {
      setStats(statsResult.value);
    }
  };

  const filteredCategories = categories.filter((category) =>
    category.label.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const onNodeClick = useCallback((event, node) => {
    setSelectedNode(node);
  }, []);

  const nodeConnections = useMemo(() => {
    if (!selectedNode) return [];
    return edges
      .filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id)
      .map((edge) => {
        const otherId = edge.source === selectedNode.id ? edge.target : edge.source;
        const otherNode = nodes.find((node) => node.id === otherId);
        return {
          label: edge.label || "related",
          target: otherNode?.data?.label || otherId
        };
      });
  }, [selectedNode, edges, nodes]);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-950">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 px-4 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => navigate("/chat")}
              className="grid h-9 w-9 place-items-center rounded-lg text-slate-600 transition hover:bg-slate-100 hover:text-slate-950"
              aria-label="Back to chat"
            >
              <ArrowLeft size={18} />
            </button>
            <div>
              <h1 className="text-sm font-semibold text-slate-950">SKCT Knowledge Graph</h1>
              <p className="text-xs text-slate-500">Explore departments, admissions, placements, and campus life</p>
            </div>
          </div>
          <div className="relative hidden w-full max-w-xs sm:block">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search graph categories..."
              className="h-10 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-sm outline-none transition focus:border-blue-400 focus:ring-4 focus:ring-blue-50"
            />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8">
        <section>
          <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight">Choose a knowledge area</h2>
              <p className="mt-1 text-sm text-slate-600">Select a card to open an interactive graph view with clickable nodes.</p>
            </div>
            {stats && (
              <div className="flex gap-2 text-xs text-slate-600">
                <span className="rounded-full border border-slate-200 bg-white px-3 py-1">{stats.entities ?? 0} nodes</span>
                <span className="rounded-full border border-slate-200 bg-white px-3 py-1">{stats.relationships ?? 0} links</span>
              </div>
            )}
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {filteredCategories.map((category) => {
              const Icon = category.icon;
              const isActive = selectedCategory?.id === category.id;
              return (
                <button
                  key={category.id}
                  type="button"
                  onClick={() => setSelectedCategory(category)}
                  className={`group rounded-lg border bg-white p-4 text-left shadow-sm transition hover:-translate-y-1 hover:border-slate-300 hover:shadow-md ${
                    isActive ? "border-blue-300 ring-4 ring-blue-50" : "border-slate-200"
                  }`}
                >
                  <div className={`grid h-11 w-11 place-items-center rounded-lg ${category.bg} ${category.text}`}>
                    <Icon size={21} />
                  </div>
                  <div className="mt-4 text-sm font-semibold text-slate-950">{category.label}</div>
                  <div className="mt-2 text-xs leading-5 text-slate-500">{category.children.join(" • ")}</div>
                </button>
              );
            })}
          </div>
        </section>

        <section className="mt-7 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          {!selectedCategory ? (
            <div className="grid min-h-[460px] place-items-center px-6 text-center">
              <div>
                <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-slate-100 text-slate-600">
                  <Library size={24} />
                </div>
                <h3 className="mt-4 text-lg font-semibold">Select a category to explore</h3>
                <p className="mt-2 max-w-md text-sm leading-6 text-slate-600">
                  The graph panel stays separate from chat, so conversations remain clean while knowledge exploration gets its own focused space.
                </p>
              </div>
            </div>
          ) : (
            <div className="grid min-h-[560px] lg:grid-cols-[minmax(0,1fr)_300px]">
              <div className="relative h-[560px] border-b border-slate-200 lg:border-b-0 lg:border-r">
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  onNodeClick={onNodeClick}
                  nodeTypes={nodeTypes}
                  fitView
                  minZoom={0.25}
                  maxZoom={1.8}
                >
                  <Background color="#e2e8f0" gap={18} size={1} />
                  <Controls className="!border-slate-200 !bg-white !shadow-sm [&>button]:!border-slate-100 [&>button]:!bg-white [&>button]:!fill-slate-700 hover:[&>button]:!bg-slate-50" />
                  <MiniMap nodeColor={(node) => node.data?.color || "#64748b"} maskColor="rgba(248, 250, 252, 0.72)" />
                </ReactFlow>
              </div>

              <aside className="p-5">
                <div className="flex items-center gap-3">
                  <div className={`grid h-11 w-11 place-items-center rounded-lg ${selectedCategory.bg} ${selectedCategory.text}`}>
                    <selectedCategory.icon size={21} />
                  </div>
                  <div>
                    <div className="text-sm font-semibold">{selectedCategory.label}</div>
                    <div className="text-xs text-slate-500">{nodes.length} visible nodes</div>
                  </div>
                </div>

                <div className="mt-6">
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Selected Node</div>
                  {selectedNode ? (
                    <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
                      <div className="text-sm font-semibold text-slate-950">{selectedNode.data.label}</div>
                      <div className="mt-1 text-xs text-slate-500">{selectedNode.data.type}</div>
                      <div className="mt-4 space-y-2">
                        {nodeConnections.length ? (
                          nodeConnections.map((connection) => (
                            <div key={`${connection.label}-${connection.target}`} className="rounded-md bg-white px-3 py-2 text-xs text-slate-600">
                              <span className="font-medium text-slate-900">{connection.label}</span> → {connection.target}
                            </div>
                          ))
                        ) : (
                          <p className="text-sm text-slate-500">No visible connected nodes.</p>
                        )}
                      </div>
                    </div>
                  ) : (
                    <p className="mt-3 rounded-lg border border-dashed border-slate-200 p-4 text-sm leading-6 text-slate-500">
                      Click any node in the graph to inspect its connected faculty, courses, labs, placements, or related entities.
                    </p>
                  )}
                </div>

                <div className="mt-6">
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Included</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {selectedCategory.children.map((child) => (
                      <span key={child} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600">
                        {child}
                      </span>
                    ))}
                  </div>
                </div>
              </aside>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
