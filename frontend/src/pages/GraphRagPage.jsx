import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import {
  AlertCircle,
  Bot,
  BrainCircuit,
  ChevronDown,
  ChevronRight,
  Clock,
  Database,
  ExternalLink,
  FileText,
  Globe,
  GitBranch,
  Layers,
  Link2,
  Loader2,
  LogOut,
  Menu,
  MessageSquare,
  Network,
  Plus,
  RefreshCw,
  Route,
  Send,
  Server,
  Sparkles,
  Timer,
  Trash2,
  UserRound,
  X,
  Zap,
} from "lucide-react";
import {
  buildGraph,
  getStats,
  initDatabase,
  reindex,
  scrapeWebsite,
  sendChat,
} from "../lib/graphRagApi";
import { logout } from "../lib/api";

/* ─────────────────────────────────────────────────────────────
   CONSTANTS
───────────────────────────────────────────────────────────── */
const HISTORY_KEY = "skct_graphrag_history_v2";
const SESSION_KEY = "skct_graphrag_session_v2";

const ROUTE_META = {
  graph_rag: { label: "Graph RAG", color: "bg-violet-100 text-violet-700", icon: Network },
  graph_rag_multi: { label: "Multi-Q RAG", color: "bg-indigo-100 text-indigo-700", icon: Layers },
  website_fts: { label: "FTS Search", color: "bg-blue-100 text-blue-700", icon: Database },
  graph_relationship: { label: "Graph", color: "bg-emerald-100 text-emerald-700", icon: GitBranch },
  hybrid: { label: "Hybrid", color: "bg-amber-100 text-amber-700", icon: Sparkles },
  general_graph_chat: { label: "General", color: "bg-slate-100 text-slate-600", icon: MessageSquare },
  unsupported: { label: "Unsupported", color: "bg-red-100 text-red-600", icon: AlertCircle },
};

const STAT_META = [
  { key: "scraped_pages", label: "Pages", icon: Globe, color: "from-blue-500 to-blue-600" },
  { key: "website_chunks", label: "Chunks", icon: Layers, color: "from-violet-500 to-violet-600" },
  { key: "page_links", label: "Links", icon: Link2, color: "from-cyan-500 to-cyan-600" },
  { key: "entities", label: "Entities", icon: BrainCircuit, color: "from-emerald-500 to-emerald-600" },
  { key: "relationships", label: "Relations", icon: Network, color: "from-amber-500 to-amber-600" },
  { key: "chat_sessions", label: "Sessions", icon: MessageSquare, color: "from-pink-500 to-pink-600" },
  { key: "chat_messages", label: "Messages", icon: Bot, color: "from-rose-500 to-rose-600" },
  { key: "fts5_available", label: "FTS5", icon: Zap, color: "from-teal-500 to-teal-600" },
];

const SUGGESTIONS = [
  "Tell me about SKCT placements",
  "What departments are available?",
  "Who is the principal of SKCT?",
  "What are the sports facilities?",
  "Tell me about SKCT achievements",
];

/* ─────────────────────────────────────────────────────────────
   HELPERS
───────────────────────────────────────────────────────────── */
function loadJson(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    return v ? JSON.parse(v) : fallback;
  } catch {
    return fallback;
  }
}

function getStoredUser() {
  return loadJson("skct_user", {});
}

function initials(name = "", email = "") {
  const src = name || email || "U";
  const words = src.replace(/@.*/, "").split(/[.\s_-]+/).filter(Boolean);
  return words
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("") || "SU";
}

function formatNum(val) {
  if (val === undefined || val === null) return "—";
  if (typeof val === "boolean") return val ? "Yes" : "No";
  return String(val);
}

function elapsedLabel(sec) {
  if (!sec && sec !== 0) return null;
  return sec < 1 ? `${Math.round(sec * 1000)}ms` : `${sec.toFixed(1)}s`;
}

/* ─────────────────────────────────────────────────────────────
   SUB-COMPONENTS
───────────────────────────────────────────────────────────── */

/** Typing animation */
function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1">
      {[0, 120, 240].map((delay) => (
        <span
          key={delay}
          className="block h-2 w-2 rounded-full bg-violet-400 animate-bounce"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}

/** Route badge */
function RouteBadge({ route }) {
  const meta = ROUTE_META[route] || { label: route, color: "bg-slate-100 text-slate-600", icon: Route };
  const Icon = meta.icon;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${meta.color}`}
    >
      <Icon size={11} />
      {meta.label}
    </span>
  );
}

/** Collapsible JSON / graph facts */
function JsonCollapse({ label, data, icon: Icon = Network, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  if (!data || (Array.isArray(data) && !data.length)) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 transition"
      >
        <span className="flex items-center gap-2">
          <Icon size={13} />
          {label}
        </span>
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
      </button>
      {open && (
        <div className="border-t border-slate-200 bg-white px-4 py-3">
          {Array.isArray(data) && data.length > 0 && typeof data[0] === "object" && data[0].source_name ? (
            <div className="space-y-2">
              {data.slice(0, 8).map((row, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs"
                >
                  <span className="font-semibold text-violet-700 truncate max-w-[30%]">
                    {row.source_name}
                  </span>
                  <span className="shrink-0 rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-medium text-violet-600">
                    {row.relationship_type}
                  </span>
                  <span className="font-semibold text-slate-700 truncate max-w-[30%]">
                    {row.target_name}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-700">
              {JSON.stringify(data, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

/** Source list */
function SourceList({ sources }) {
  if (!sources?.length) return null;
  return (
    <div className="mt-4 space-y-2">
      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
        <FileText size={12} />
        Sources
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {sources.slice(0, 4).map((src, i) => {
          const score =
            src.score ?? src.confidence ?? 85;
          const displayScore =
            score <= 1 ? Math.round(score * 100) : Math.round(score);
          return (
            <a
              key={`${src.url}-${i}`}
              href={src.url || "https://skct.edu.in"}
              target="_blank"
              rel="noreferrer"
              className="group flex flex-col gap-1.5 rounded-xl border border-slate-200 bg-white p-3 text-xs transition hover:border-violet-300 hover:shadow-sm"
            >
              <div className="flex items-start gap-2">
                <Globe
                  size={13}
                  className="mt-0.5 shrink-0 text-violet-500 transition group-hover:text-violet-700"
                />
                <span className="line-clamp-1 flex-1 font-semibold text-slate-800">
                  {src.title || "SKCT Website"}
                </span>
                <ExternalLink
                  size={11}
                  className="shrink-0 text-slate-300 group-hover:text-violet-500"
                />
              </div>
              {displayScore > 0 && (
                <div className="flex items-center gap-2">
                  <div className="h-1 flex-1 rounded-full bg-slate-100">
                    <div
                      className="h-1 rounded-full bg-gradient-to-r from-violet-400 to-violet-600 transition-all"
                      style={{ width: `${Math.min(100, displayScore)}%` }}
                    />
                  </div>
                  <span className="text-[10px] font-semibold text-violet-600">
                    {displayScore}%
                  </span>
                </div>
              )}
              {src.chunk_text && (
                <p className="line-clamp-2 text-slate-400 leading-4">
                  {src.chunk_text}
                </p>
              )}
            </a>
          );
        })}
      </div>
    </div>
  );
}

/** Single chat message */
function ChatMessage({ message }) {
  const isUser = message.role === "user";
  return (
    <div
      className={`flex w-full gap-3 animate-[fadeIn_200ms_ease-out] ${
        isUser ? "justify-end" : "justify-start"
      }`}
    >
      {!isUser && (
        <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 text-white shadow">
          <Bot size={16} />
        </div>
      )}
      <div
        className={`max-w-[85%] overflow-hidden rounded-2xl text-sm leading-6 shadow-sm sm:max-w-[75%] ${
          isUser
            ? "rounded-br-sm bg-gradient-to-br from-violet-600 to-indigo-700 px-4 py-3 text-white"
            : "rounded-bl-sm border border-slate-200 bg-white px-5 py-4 text-slate-800"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap break-words">{message.text}</p>
        ) : (
          <div>
            {/* Header row */}
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Answer
              </span>
              {message.route && <RouteBadge route={message.route} />}
              {message.elapsed && (
                <span className="flex items-center gap-1 text-[11px] text-slate-400">
                  <Timer size={11} />
                  {elapsedLabel(message.elapsed)}
                </span>
              )}
            </div>

            {/* Markdown answer */}
            <div className="text-[15px] leading-7 text-slate-800 [&_a]:text-violet-600 [&_a]:underline [&_code]:rounded [&_code]:bg-violet-50 [&_code]:px-1 [&_code]:text-violet-700 [&_h1]:mb-2 [&_h1]:text-base [&_h1]:font-bold [&_h2]:mb-1.5 [&_h2]:text-sm [&_h2]:font-semibold [&_h3]:mb-1 [&_h3]:text-sm [&_h3]:font-semibold [&_li]:my-0.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-1 [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-5">
              <ReactMarkdown>{message.text}</ReactMarkdown>
            </div>

            {/* Sources */}
            <SourceList sources={message.sources} />

            {/* Graph context collapse */}
            {message.graphContext?.length > 0 && (
              <div className="mt-3">
                <JsonCollapse
                  label={`Graph Facts (${message.graphContext.length})`}
                  data={message.graphContext}
                  icon={Network}
                />
              </div>
            )}
          </div>
        )}
      </div>
      {isUser && (
        <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-slate-200 text-slate-600 shadow-sm">
          <UserRound size={16} />
        </div>
      )}
    </div>
  );
}

/** Empty state / welcome screen */
function EmptyState({ onSuggestion }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <div className="mb-5 grid h-20 w-20 place-items-center rounded-3xl bg-gradient-to-br from-violet-500 to-indigo-600 text-white shadow-lg shadow-violet-200">
        <BrainCircuit size={36} />
      </div>
      <h2 className="text-2xl font-bold tracking-tight text-slate-900">
        SKCT Graph RAG Assistant
      </h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">
        Ask anything about Sri Krishna College of Technology — departments,
        placements, faculty, events, facilities, and more.
      </p>
      <div className="mt-8 flex flex-wrap justify-center gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onSuggestion(s)}
            className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:border-violet-300 hover:bg-violet-50 hover:text-violet-800"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Stats grid */
function StatsGrid({ stats, loading }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {STAT_META.map(({ key, label, icon: Icon, color }) => (
        <div
          key={key}
          className="flex flex-col gap-1 rounded-xl bg-white p-3 shadow-sm ring-1 ring-slate-100"
        >
          <div
            className={`mb-1 grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br ${color} text-white`}
          >
            <Icon size={13} />
          </div>
          <div className="text-base font-bold text-slate-900 leading-none">
            {loading ? (
              <span className="block h-4 w-8 animate-pulse rounded bg-slate-100" />
            ) : (
              formatNum(stats?.[key])
            )}
          </div>
          <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
            {label}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Admin pipeline action button */
function PipelineBtn({ label, icon: Icon, onClick, status, description, color = "violet" }) {
  const colors = {
    violet: "bg-violet-600 hover:bg-violet-700 focus:ring-violet-300",
    blue: "bg-blue-600 hover:bg-blue-700 focus:ring-blue-300",
    amber: "bg-amber-500 hover:bg-amber-600 focus:ring-amber-300",
    red: "bg-red-600 hover:bg-red-700 focus:ring-red-300",
    emerald: "bg-emerald-600 hover:bg-emerald-700 focus:ring-emerald-300",
  };
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={status === "running"}
      className={`flex w-full flex-col items-start gap-1.5 rounded-xl px-4 py-3 text-left text-white transition focus:outline-none focus:ring-2 disabled:opacity-60 ${colors[color]}`}
    >
      <span className="flex items-center gap-2 text-sm font-semibold">
        {status === "running" ? (
          <Loader2 size={15} className="animate-spin" />
        ) : status === "done" ? (
          <span>✓</span>
        ) : (
          <Icon size={15} />
        )}
        {label}
      </span>
      {description && (
        <span className="text-[11px] font-normal text-white/70">{description}</span>
      )}
      {status && status !== "idle" && status !== "running" && (
        <span
          className={`text-[11px] font-medium ${
            status === "done" ? "text-green-300" : "text-red-300"
          }`}
        >
          {status === "done" ? "Completed" : status}
        </span>
      )}
    </button>
  );
}

/* ─────────────────────────────────────────────────────────────
   MAIN PAGE
───────────────────────────────────────────────────────────── */
export default function GraphRagPage() {
  const navigate = useNavigate();

  // ── Auth guard
  useEffect(() => {
    if (!localStorage.getItem("skct_token")) navigate("/login");
  }, [navigate]);

  const user = useMemo(() => getStoredUser(), []);
  const userName = user.username || user.name || "User";
  const userEmail = user.email || "";
  const userInitials = initials(userName, userEmail);

  // ── Sidebar
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // ── Chat state
  const [messages, setMessages] = useState(() => loadJson(HISTORY_KEY, []));
  const [sessionId, setSessionId] = useState(() => loadJson(SESSION_KEY, null));
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  // ── Stats
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);

  // ── Pipeline statuses
  const [pipelineStatus, setPipelineStatus] = useState({
    init: "idle",
    scrape: "idle",
    build: "idle",
    reindex: "idle",
  });

  // ── Profile dropdown
  const [profileOpen, setProfileOpen] = useState(false);

  const textareaRef = useRef(null);
  const bottomRef = useRef(null);

  // ── Persist chat
  useEffect(() => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(messages.slice(-60)));
  }, [messages]);

  useEffect(() => {
    localStorage.setItem(SESSION_KEY, JSON.stringify(sessionId));
  }, [sessionId]);

  // ── Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // ── Auto-resize textarea
  useEffect(() => {
    if (!textareaRef.current) return;
    textareaRef.current.style.height = "auto";
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
  }, [input]);

  // ── Load stats on mount
  useEffect(() => {
    refreshStats();
  }, []);

  const refreshStats = async () => {
    setStatsLoading(true);
    try {
      const data = await getStats();
      setStats(data);
    } catch (e) {
      console.warn("Stats failed:", e.message);
    } finally {
      setStatsLoading(false);
    }
  };

  // ── Send message
  const handleSend = useCallback(async () => {
    const question = input.trim();
    if (!question || loading) return;

    setInput("");
    setLoading(true);

    const userMsg = {
      id: Date.now(),
      role: "user",
      text: question,
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const res = await sendChat(question, sessionId);
      const assistantMsg = {
        id: Date.now() + 1,
        role: "assistant",
        text: res.answer || "No answer available.",
        route: res.route || res.route_used || "",
        elapsed: res.elapsed_seconds ?? null,
        sources: res.sources || [],
        graphContext: res.graph_context || res.graph_facts || [],
      };
      if (res.session_id) setSessionId(res.session_id);
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: "assistant",
          text: `⚠️ Error: ${err.message}. Make sure the backend is running and Ollama is connected.`,
          route: "error",
        },
      ]);
    } finally {
      setLoading(false);
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  }, [input, loading, sessionId]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSuggestion = (text) => {
    setInput(text);
    requestAnimationFrame(() => textareaRef.current?.focus());
  };

  const handleNewChat = () => {
    setMessages([]);
    setSessionId(null);
    setInput("");
    setSidebarOpen(false);
    requestAnimationFrame(() => textareaRef.current?.focus());
  };

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  // ── Pipeline actions
  async function runPipeline(key, fn) {
    setPipelineStatus((s) => ({ ...s, [key]: "running" }));
    try {
      await fn();
      setPipelineStatus((s) => ({ ...s, [key]: "done" }));
      await refreshStats();
    } catch (err) {
      setPipelineStatus((s) => ({ ...s, [key]: `Failed: ${err.message}` }));
    }
    setTimeout(() => setPipelineStatus((s) => ({ ...s, [key]: "idle" })), 4000);
  }

  /* ─── Sidebar content (shared between mobile overlay + desktop) ─── */
  const sidebarContent = (
    <div className="flex h-full flex-col">
      {/* Brand */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-slate-100">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 text-white shadow">
          <BrainCircuit size={20} />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-bold text-slate-900 leading-tight">SKCT GraphRAG</div>
          <div className="text-[11px] text-violet-600 font-medium">Website AI Assistant</div>
        </div>
      </div>

      {/* New chat */}
      <div className="px-4 py-3 border-b border-slate-100">
        <button
          type="button"
          onClick={handleNewChat}
          className="flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-sm font-semibold text-white shadow transition hover:opacity-90"
        >
          <Plus size={16} />
          New Chat
        </button>
      </div>

      {/* Scrollable area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">
        {/* Stats */}
        <section>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-widest text-slate-400">
              Graph Stats
            </span>
            <button
              type="button"
              onClick={refreshStats}
              className="grid h-6 w-6 place-items-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition"
              title="Refresh stats"
            >
              <RefreshCw size={12} className={statsLoading ? "animate-spin" : ""} />
            </button>
          </div>
          <StatsGrid stats={stats} loading={statsLoading} />
        </section>

        {/* Recent chats */}
        {messages.filter((m) => m.role === "user").length > 0 && (
          <section>
            <div className="mb-2 flex items-center gap-2">
              <Clock size={11} className="text-slate-400" />
              <span className="text-[11px] font-bold uppercase tracking-widest text-slate-400">
                Current Session
              </span>
            </div>
            <div className="space-y-1">
              {messages
                .filter((m) => m.role === "user")
                .slice(-5)
                .reverse()
                .map((m) => (
                  <div
                    key={m.id}
                    className="truncate rounded-lg px-3 py-2 text-xs text-slate-600 hover:bg-slate-100 cursor-default"
                  >
                    {m.text.length > 42 ? `${m.text.slice(0, 42)}…` : m.text}
                  </div>
                ))}
            </div>
            <button
              type="button"
              onClick={handleNewChat}
              className="mt-2 flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium text-red-500 hover:bg-red-50 transition"
            >
              <Trash2 size={11} />
              Clear session
            </button>
          </section>
        )}

        {/* Admin Pipeline */}
        <section>
          <div className="mb-2 flex items-center gap-2">
            <Server size={11} className="text-slate-400" />
            <span className="text-[11px] font-bold uppercase tracking-widest text-slate-400">
              Pipeline Controls
            </span>
          </div>
          <div className="space-y-2">
            <PipelineBtn
              label="Initialize DB"
              icon={Database}
              color="blue"
              description="Create tables & FTS5 index"
              status={pipelineStatus.init}
              onClick={() => runPipeline("init", initDatabase)}
            />
            <PipelineBtn
              label="Scrape Website"
              icon={Globe}
              color="violet"
              description="Crawl & chunk skct.edu.in"
              status={pipelineStatus.scrape}
              onClick={() =>
                runPipeline("scrape", () =>
                  scrapeWebsite({ forceReindex: false, maxPages: 60, maxDepth: 3 })
                )
              }
            />
            <PipelineBtn
              label="Build Graph"
              icon={GitBranch}
              color="emerald"
              description="Extract entities & relations"
              status={pipelineStatus.build}
              onClick={() => runPipeline("build", buildGraph)}
            />
            <PipelineBtn
              label="Full Reindex"
              icon={RefreshCw}
              color="amber"
              description="Clear & rebuild everything"
              status={pipelineStatus.reindex}
              onClick={() => runPipeline("reindex", () => reindex(true))}
            />
          </div>
        </section>
      </div>

      {/* User profile */}
      <div className="border-t border-slate-100 px-4 py-3">
        <div className="relative">
          <button
            type="button"
            onClick={() => setProfileOpen((v) => !v)}
            className="flex w-full items-center gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-left transition hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-violet-200"
          >
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 text-sm font-bold text-white">
              {userInitials}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-slate-900">{userName}</div>
              <div className="truncate text-[11px] text-slate-400">{userEmail || "Signed in"}</div>
            </div>
            <ChevronDown size={14} className={`text-slate-400 transition ${profileOpen ? "rotate-180" : ""}`} />
          </button>
          {profileOpen && (
            <div className="absolute bottom-14 left-0 right-0 z-50 rounded-xl border border-slate-200 bg-white p-1 shadow-xl">
              <button
                type="button"
                onClick={handleLogout}
                className="flex h-10 w-full items-center gap-2 rounded-lg px-3 text-sm font-medium text-red-600 transition hover:bg-red-50"
              >
                <LogOut size={15} />
                Logout
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );

  /* ─── RENDER ─── */
  return (
    <div className="flex h-screen overflow-hidden bg-slate-50 font-sans antialiased">

      {/* ── Desktop sidebar (always visible on lg+) ── */}
      <aside className="hidden lg:flex lg:w-72 lg:shrink-0 flex-col border-r border-slate-200 bg-white shadow-sm">
        {sidebarContent}
      </aside>

      {/* ── Mobile sidebar overlay ── */}
      {sidebarOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-sm lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
          <aside className="fixed left-0 top-0 bottom-0 z-50 w-72 border-r border-slate-200 bg-white shadow-xl lg:hidden">
            <button
              type="button"
              onClick={() => setSidebarOpen(false)}
              className="absolute right-3 top-3 grid h-8 w-8 place-items-center rounded-lg text-slate-500 hover:bg-slate-100"
            >
              <X size={18} />
            </button>
            {sidebarContent}
          </aside>
        </>
      )}

      {/* ── Main column ── */}
      <div className="flex min-w-0 flex-1 flex-col">

        {/* ── Sticky Header ── */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4 shadow-sm">
          <div className="flex items-center gap-3">
            {/* Mobile menu toggle */}
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="grid h-9 w-9 place-items-center rounded-lg text-slate-500 hover:bg-slate-100 transition lg:hidden"
              aria-label="Open sidebar"
            >
              <Menu size={20} />
            </button>
            <div className="flex items-center gap-2">
              <BrainCircuit size={18} className="text-violet-600" />
              <span className="hidden font-semibold text-slate-800 sm:block">
                SKCT Graph RAG — Website AI
              </span>
              <span className="font-semibold text-slate-800 sm:hidden">SKCT AI</span>
            </div>
            {sessionId && (
              <span className="hidden rounded-full bg-violet-50 px-2.5 py-0.5 text-[11px] font-medium text-violet-600 sm:inline-flex">
                Session #{sessionId}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleNewChat}
              className="hidden h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-100 sm:flex"
            >
              <Plus size={15} />
              New
            </button>
            {/* Profile button in header */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setProfileOpen((v) => !v)}
                className="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 text-sm font-bold text-white shadow-sm transition hover:opacity-90"
                aria-label="User menu"
              >
                {userInitials}
              </button>
              {profileOpen && (
                <div className="absolute right-0 top-11 z-50 w-44 rounded-xl border border-slate-200 bg-white p-1 shadow-xl">
                  <div className="px-3 py-2 border-b border-slate-100 text-xs text-slate-500">
                    <div className="font-semibold text-slate-800 truncate">{userName}</div>
                    <div className="truncate">{userEmail}</div>
                  </div>
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="flex h-9 w-full items-center gap-2 rounded-lg px-3 text-sm font-medium text-red-600 hover:bg-red-50 transition"
                  >
                    <LogOut size={14} />
                    Logout
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* ── Chat message area ── */}
        <section className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
            {messages.length === 0 && !loading ? (
              <EmptyState onSuggestion={handleSuggestion} />
            ) : (
              <div className="space-y-6">
                {messages.map((msg) => (
                  <ChatMessage key={msg.id} message={msg} />
                ))}
                {loading && (
                  <div className="flex gap-3">
                    <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 text-white shadow">
                      <Bot size={16} />
                    </div>
                    <div className="flex items-center gap-3 rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-5 py-4 shadow-sm">
                      <span className="text-sm text-slate-500">Searching knowledge graph</span>
                      <TypingDots />
                    </div>
                  </div>
                )}
                <div ref={bottomRef} />
              </div>
            )}
          </div>
        </section>

        {/* ── Fixed chat input — scoped inside main column only ── */}
        <footer className="shrink-0 border-t border-slate-200 bg-white px-4 py-3">
          <form
            onSubmit={(e) => { e.preventDefault(); handleSend(); }}
            className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-2 shadow-sm transition focus-within:border-violet-400 focus-within:ring-4 focus-within:ring-violet-50"
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              rows={1}
              placeholder="Ask anything about SKCT..."
              className="max-h-40 min-h-10 flex-1 resize-none border-0 bg-transparent px-3 py-2.5 text-[15px] leading-6 text-slate-900 outline-none placeholder:text-slate-400 disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 text-white shadow transition hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-violet-300 disabled:cursor-not-allowed disabled:opacity-40"
              aria-label="Send"
            >
              {loading ? <Loader2 size={17} className="animate-spin" /> : <Send size={17} />}
            </button>
          </form>
          <p className="mt-1.5 text-center text-[11px] text-slate-400">
            Answers are grounded strictly in scraped SKCT website content
          </p>
        </footer>
      </div>
    </div>
  );
}
