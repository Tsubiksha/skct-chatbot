import * as React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  CheckCircle2,
  Clock3,
  Database,
  GraduationCap,
  Loader2,
  Network,
  Plus,
  RotateCw,
  Search,
  Send,
  Server,
  UserRound,
} from "lucide-react";

globalThis.__SKCT_GRAPH_RAG_REACT__ = React;

const API_BASE = "http://127.0.0.1:8000/api/graph-rag";
const ACTIVE_KEY = "skct-sqlite-graphrag-active-chat";
const RECENT_KEY = "skct-sqlite-graphrag-recent-chats";

const initialMessage = {
  id: 1,
  role: "assistant",
  text: "Hi, I am the SKCT SQLite GraphRAG assistant. Scrape the college website, then ask about departments, placements, faculty, recruiters, training, events, regulations, and contact details.",
};

const suggestions = [
  "Tell me about placements",
  "What departments are available?",
  "Who is the principal?",
  "Show recruiter information",
  "Tell me about SKCT training",
];

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    mode: "cors",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || "Request failed");
  }
  return response.json();
}

function loadJson(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
}

function titleFromMessages(messages) {
  const first = messages.find((message) => message.role === "user");
  if (!first) return "New GraphRAG Chat";
  return first.text.length > 36 ? `${first.text.slice(0, 36)}...` : first.text;
}

function MarkdownText({ text }) {
  const html = useMemo(() => {
    return String(text)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\n/g, "<br />");
  }, [text]);
  return <div className="message-markdown" dangerouslySetInnerHTML={{ __html: html }} />;
}

function TypingDots() {
  return (
    <div className="flex gap-1.5 px-1 py-1">
      <span className="h-2 w-2 animate-bounce rounded-full bg-emerald-500" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-emerald-500 [animation-delay:120ms]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-emerald-500 [animation-delay:240ms]" />
    </div>
  );
}

export default function GraphRagChat() {
  const [messages, setMessages] = useState(() => loadJson(ACTIVE_KEY, [initialMessage]));
  const [recentChats, setRecentChats] = useState(() => loadJson(RECENT_KEY, []));
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [scraping, setScraping] = useState(false);
  const [scrapeStage, setScrapeStage] = useState("");
  const [status, setStatus] = useState({});
  const [stats, setStats] = useState({ pages: 0, chunks: 0, entities: 0, relationships: 0 });
  const [sources, setSources] = useState([]);
  const [graphContext, setGraphContext] = useState([]);
  const [retrievedChunks, setRetrievedChunks] = useState([]);
  const [routeUsed, setRouteUsed] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    refreshMeta();
  }, []);

  useEffect(() => {
    localStorage.setItem(ACTIVE_KEY, JSON.stringify(messages));
  }, [messages]);

  useEffect(() => {
    localStorage.setItem(RECENT_KEY, JSON.stringify(recentChats.slice(0, 5)));
  }, [recentChats]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function refreshMeta() {
    try {
      const [health, graphStats] = await Promise.all([api("/health"), api("/stats")]);
      setStatus(health);
      setStats(graphStats);
    } catch {
      setStatus({ fastapi: "offline", ollama: "unavailable", sqlite: "unavailable", fts5: "unavailable" });
    }
  }

  function addAssistant(text) {
    setMessages((current) => [...current, { id: Date.now() + Math.random(), role: "assistant", text }]);
  }

  function archiveChat() {
    if (!messages.some((message) => message.role === "user")) return;
    const chat = { id: Date.now(), title: titleFromMessages(messages), messages };
    setRecentChats((current) => [chat, ...current.filter((item) => item.title !== chat.title)].slice(0, 5));
  }

  function newChat() {
    archiveChat();
    setMessages([initialMessage]);
    setInput("");
    setSources([]);
    setGraphContext([]);
    setRetrievedChunks([]);
    setRouteUsed("");
    localStorage.removeItem(ACTIVE_KEY);
  }

  async function scrapeWebsite() {
    if (scraping) return;
    setScraping(true);
    setScrapeStage("Scraping website...");
    addAssistant("Starting SKCT website scraping. I will clean pages, chunk content, store SQLite FTS records, and build lightweight graph relationships.");

    const timer = window.setInterval(() => {
      setScrapeStage((current) => {
        if (current === "Scraping website...") return "Cleaning and chunking text...";
        if (current === "Cleaning and chunking text...") return "Building SQLite graph...";
        return "Building SQLite graph...";
      });
    }, 2500);

    try {
      const result = await api("/scrape-website", {
        method: "POST",
        body: JSON.stringify({ force_reindex: false, max_pages: 30, max_depth: 2 }),
      });
      addAssistant(`Website scrape finished: ${result.pages_saved} pages saved, ${result.pages_updated} updated, ${result.chunks_created} chunks created.`);
      setScrapeStage("Scrape complete");
      await refreshMeta();
    } catch (error) {
      addAssistant(`Website scrape failed: ${error.message}`);
      setScrapeStage("Scrape failed");
    } finally {
      window.clearInterval(timer);
      setScraping(false);
      window.setTimeout(() => setScrapeStage(""), 4500);
    }
  }

  async function sendQuestion(questionText) {
    const question = questionText.trim();
    if (!question || loading) return;

    setInput("");
    setLoading(true);
    setSources([]);
    setGraphContext([]);
    setRetrievedChunks([]);
    setRouteUsed("");
    setMessages((current) => [...current, { id: Date.now(), role: "user", text: question }]);

    try {
      const result = await api("/query", {
        method: "POST",
        body: JSON.stringify({ question }),
      });
      setSources(result.sources || []);
      setGraphContext(result.graph_context || []);
      setRetrievedChunks(result.retrieved_chunks || []);
      setRouteUsed(result.route_used || "graph_rag");
      addAssistant(result.answer || "I could not find this in the scraped SKCT website data.");
    } catch (error) {
      addAssistant(`I could not answer that yet: ${error.message}. Try scraping the website first and make sure Ollama is running.`);
    } finally {
      setLoading(false);
    }
  }

  function submit(event) {
    event.preventDefault();
    sendQuestion(input);
  }

  const statusRows = [
    ["FastAPI Running", status.fastapi],
    ["Ollama Connected", status.ollama],
    ["SQLite Active", status.sqlite],
    ["FTS5 Enabled", status.fts5],
  ];

  return (
    <div className="grid min-h-screen bg-[#f5f7fb] text-slate-950 lg:grid-cols-[310px_minmax(0,1fr)]">
      <aside className="hidden h-screen border-r border-white/10 bg-[#06101d] p-4 text-white lg:flex lg:flex-col">
        <div className="mb-5 flex items-center gap-3 px-1">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-emerald-300 to-teal-500 text-slate-950">
            <GraduationCap size={25} />
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-emerald-300">SKCT</p>
            <h1 className="text-lg font-bold">GraphRAG</h1>
          </div>
        </div>

        <div className="space-y-2">
          <button onClick={newChat} className="flex w-full items-center gap-3 rounded-2xl bg-white px-4 py-3 text-sm font-bold text-slate-950">
            <Plus size={17} className="text-emerald-600" />
            New Chat
          </button>
          <button
            onClick={scrapeWebsite}
            disabled={scraping}
            className="flex w-full items-center gap-3 rounded-2xl bg-gradient-to-r from-emerald-400 to-teal-500 px-4 py-3 text-sm font-bold text-slate-950 disabled:opacity-60"
          >
            {scraping ? <Loader2 size={17} className="animate-spin" /> : <RotateCw size={17} />}
            Scrape Website
          </button>
          {scrapeStage && <p className="px-2 text-xs font-semibold text-emerald-200">{scrapeStage}</p>}
        </div>

        <div className="mt-5">
          <div className="mb-2 flex items-center gap-2 px-2 text-xs font-bold uppercase tracking-wide text-slate-400">
            <Clock3 size={14} />
            Recent Chats
          </div>
          <div className="space-y-1">
            {recentChats.length === 0 && <p className="rounded-2xl bg-white/[0.05] px-3 py-3 text-xs text-slate-400">No recent chats yet.</p>}
            {recentChats.map((chat) => (
              <button key={chat.id} onClick={() => setMessages(chat.messages)} className="w-full rounded-2xl px-3 py-3 text-left text-sm text-slate-300 hover:bg-white/[0.08]">
                {chat.title}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-auto space-y-3">
          <section className="rounded-2xl border border-white/10 bg-white/[0.06] p-3">
            <div className="mb-3 flex items-center gap-2 text-sm font-bold">
              <Server size={16} className="text-emerald-300" />
              System Status
            </div>
            <div className="space-y-2">
              {statusRows.map(([label, value]) => (
                <div key={label} className="flex items-center justify-between gap-3 text-xs">
                  <span className="text-slate-300">{label}</span>
                  <span className="inline-flex items-center gap-1 text-emerald-300">
                    <CheckCircle2 size={13} />
                    {value || "checking"}
                  </span>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border border-white/10 bg-white/[0.06] p-3">
            <div className="mb-3 flex items-center gap-2 text-sm font-bold">
              <Database size={16} className="text-emerald-300" />
              Graph Stats
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              {Object.entries(stats).filter(([key]) => !key.includes("enabled") && !key.includes("active")).map(([key, value]) => (
                <div key={key} className="rounded-xl bg-black/20 px-3 py-2">
                  <div className="text-base font-bold">{String(value)}</div>
                  <div className="capitalize text-slate-400">{key}</div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </aside>

      <main className="flex h-screen min-w-0 flex-col">
        <section className="flex-1 overflow-y-auto px-4 py-8 md:px-8">
          <div className="mx-auto max-w-5xl">
            {messages.length <= 1 && (
              <div className="mx-auto max-w-3xl py-10 text-center">
                <div className="mx-auto mb-6 grid h-16 w-16 place-items-center rounded-3xl bg-gradient-to-br from-emerald-300 to-teal-500 text-slate-950">
                  <Bot size={30} />
                </div>
                <h2 className="text-3xl font-bold md:text-5xl">AI-Powered College GraphRAG Assistant</h2>
                <p className="mx-auto mt-4 max-w-2xl text-slate-600">Ask anything about SKCT departments, faculty, placements, courses, events, and research.</p>
                <div className="mt-8 flex flex-wrap justify-center gap-3">
                  {suggestions.map((question) => (
                    <button key={question} onClick={() => sendQuestion(question)} className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:border-emerald-300">
                      {question}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="space-y-5">
              {messages.map((message) => (
                <div key={message.id} className={`flex gap-3 ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                  {message.role === "assistant" && <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-emerald-400 text-slate-950"><Bot size={18} /></div>}
                  <div className={`max-w-[82%] rounded-3xl px-5 py-3 text-sm leading-6 shadow-sm ${message.role === "user" ? "rounded-br-lg bg-slate-950 text-white" : "rounded-bl-lg bg-white text-slate-700"}`}>
                    <MarkdownText text={message.text} />
                  </div>
                  {message.role === "user" && <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-slate-200 text-slate-700"><UserRound size={18} /></div>}
                </div>
              ))}
              {loading && (
                <div className="flex gap-3">
                  <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-emerald-400 text-slate-950"><Bot size={18} /></div>
                  <div className="rounded-3xl rounded-bl-lg bg-white px-5 py-4"><TypingDots /></div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {(sources.length > 0 || graphContext.length > 0 || retrievedChunks.length > 0 || routeUsed) && (
              <div className="mt-7 grid gap-4 md:grid-cols-2">
                {routeUsed && (
                  <section className="rounded-3xl bg-white p-4 shadow-sm md:col-span-2">
                    <div className="text-xs font-bold uppercase tracking-wide text-emerald-700">Route Used</div>
                    <div className="mt-1 text-sm font-semibold text-slate-700">{routeUsed}</div>
                  </section>
                )}
                {sources.length > 0 && (
                  <section className="rounded-3xl bg-white p-4 shadow-sm">
                    <div className="mb-3 flex items-center gap-2 text-sm font-bold"><Search size={16} className="text-emerald-600" /> Source Citations</div>
                    {sources.map((source, index) => (
                      <a key={`${source.url}-${index}`} href={source.url} target="_blank" rel="noreferrer" className="mb-2 block rounded-2xl border border-slate-200 px-3 py-3 text-sm">
                        <strong>{source.title}</strong>
                        <span className="mt-1 block text-xs font-semibold uppercase tracking-wide text-emerald-700">{source.page_type || "general"}</span>
                        <span className="line-clamp-2 block text-xs text-slate-500">{source.chunk_text}</span>
                      </a>
                    ))}
                  </section>
                )}
                {graphContext.length > 0 && (
                  <section className="rounded-3xl bg-white p-4 shadow-sm">
                    <div className="mb-3 flex items-center gap-2 text-sm font-bold"><Network size={16} className="text-emerald-600" /> Graph Context</div>
                    {graphContext.map((row, index) => (
                      <div key={index} className="mb-2 rounded-2xl bg-slate-50 px-3 py-3 text-center text-xs">
                        <b>{row.source_name}</b><div className="text-emerald-600">-&gt;</div>{row.relationship_type}<div className="text-emerald-600">-&gt;</div><b>{row.target_name}</b>
                      </div>
                    ))}
                  </section>
                )}
                {retrievedChunks.length > 0 && (
                  <section className="rounded-3xl bg-white p-4 shadow-sm md:col-span-2">
                    <div className="mb-3 flex items-center gap-2 text-sm font-bold"><Database size={16} className="text-emerald-600" /> Retrieved Chunks</div>
                    <div className="grid gap-3 md:grid-cols-2">
                      {retrievedChunks.slice(0, 4).map((chunk, index) => (
                        <div key={`${chunk.id}-${index}`} className="rounded-2xl border border-slate-200 px-3 py-3 text-sm">
                          <div className="font-bold text-slate-800">{chunk.title}</div>
                          <div className="mt-1 text-xs font-semibold uppercase tracking-wide text-emerald-700">{chunk.page_type || "general"}</div>
                          <p className="mt-2 line-clamp-4 text-xs leading-5 text-slate-500">{chunk.chunk_text}</p>
                        </div>
                      ))}
                    </div>
                  </section>
                )}
              </div>
            )}
          </div>
        </section>

        <footer className="border-t border-slate-200 bg-[#f5f7fb]/90 px-4 py-4 backdrop-blur md:px-8">
          <form onSubmit={submit} className="mx-auto flex max-w-5xl items-end gap-3 rounded-3xl border border-slate-200 bg-white p-2 shadow-xl">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  sendQuestion(input);
                }
              }}
              rows={1}
              placeholder="Ask anything about SKCT..."
              className="min-h-11 flex-1 resize-none rounded-2xl border-0 bg-transparent px-4 py-3 text-sm outline-none"
            />
            <button disabled={loading || !input.trim()} className="grid h-11 w-11 place-items-center rounded-2xl bg-emerald-400 text-slate-950 disabled:opacity-50">
              <Send size={19} />
            </button>
          </form>
        </footer>
      </main>
    </div>
  );
}
