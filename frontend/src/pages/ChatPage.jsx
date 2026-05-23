import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  createConversation,
  deleteConversation,
  getConversations,
  getMessages,
  logout,
  postMessageStream
} from "../lib/api";
import {
  Bot,
  ChevronDown,
  ExternalLink,
  FileText,
  LogOut,
  Menu,
  MessageSquare,
  Network,
  PanelLeftClose,
  Plus,
  Send,
  Settings,
  Trash2,
  UserRound,
  X
} from "lucide-react";
import ReactMarkdown from "react-markdown";

const suggestedPrompts = [
  { label: "Admissions", prompt: "Tell me about SKCT admissions" },
  { label: "Placements", prompt: "Tell me about SKCT placements" },
  { label: "Departments", prompt: "What departments are offered at SKCT?" },
  { label: "Campus facilities", prompt: "Tell me about SKCT campus facilities" }
];

const genericTitlePattern = /^(new chat|chat\s+\d+)$/i;

function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem("skct_user") || "{}");
  } catch {
    return {};
  }
}

function getInitials(name = "", email = "") {
  const source = name || email || "SKCT User";
  const words = source.replace(/@.*/, "").split(/[.\s_-]+/).filter(Boolean);
  return words.slice(0, 2).map((word) => word[0]?.toUpperCase()).join("") || "SU";
}

function generateChatTitle(message = "") {
  const text = message.toLowerCase();
  const normalized = message
    .replace(/[?!.]+$/g, "")
    .replace(/\b(please|tell me about|what is|what are|where is|who is|give me|show me|details of|information about)\b/gi, "")
    .replace(/\b(of|the|a|an|about|for|in|on)\b/gi, " ")
    .replace(/\s+/g, " ")
    .trim();

  if (/\b(location|located|address|where)\b/.test(text)) return "SKCT Location";
  if (/\b(tnea|admission|admissions|counselling|counseling|cutoff|fees)\b/.test(text)) return "Admission Details";
  if (/\b(placement|placements|recruiter|salary|package|company|companies)\b/.test(text)) return "Placement Details";
  if (/\b(cse|computer science)\b/.test(text)) return "CSE Department Info";
  if (/\b(ece|electronics)\b/.test(text)) return "ECE Department Info";
  if (/\b(eee|electrical)\b/.test(text)) return "EEE Department Info";
  if (/\b(aids|ai & ds|artificial intelligence|data science)\b/.test(text)) return "AI & DS Department";
  if (/\b(hostel|library|sports|facility|facilities|campus)\b/.test(text)) return "Campus Facilities";
  if (/\b(principal|hod|faculty|staff|professor)\b/.test(text)) return "Faculty Details";

  const words = normalized.split(" ").filter(Boolean).slice(0, 4);
  if (!words.length) return "SKCT Chat";
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}

export default function ChatPage() {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState("");
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingSources, setStreamingSources] = useState([]);
  const [generatedTitles, setGeneratedTitles] = useState({});

  const textareaRef = useRef(null);
  const messagesEndRef = useRef(null);
  const lastLoadedConvIdRef = useRef(null);

  const user = useMemo(() => getStoredUser(), []);
  const userName = user.username || user.name || "SKCT User";
  const userEmail = user.email || "Signed in";
  const initials = getInitials(userName, userEmail);

  useEffect(() => {
    const token = localStorage.getItem("skct_token");
    if (!token) {
      navigate("/login");
      return;
    }
    loadConversations();
    requestAnimationFrame(() => textareaRef.current?.focus());
  }, [navigate]);

  useEffect(() => {
    if (!activeConvId) {
      setMessages([]);
      lastLoadedConvIdRef.current = null;
      return;
    }

    if (lastLoadedConvIdRef.current !== activeConvId) {
      lastLoadedConvIdRef.current = activeConvId;
      loadMessages(activeConvId);
    }
  }, [activeConvId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streamingContent, loading]);

  useEffect(() => {
    if (!textareaRef.current) return;
    textareaRef.current.style.height = "auto";
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 144)}px`;
  }, [inputText]);

  const loadConversations = async () => {
    try {
      const data = await getConversations();
      setConversations(data);
      hydrateConversationTitles(data);
      if (data.length > 0 && !activeConvId) {
        setActiveConvId(data[0].id);
      }
    } catch (err) {
      console.error("Failed to load conversations:", err);
    }
  };

  const hydrateConversationTitles = async (items) => {
    const genericItems = items.filter((conv) => genericTitlePattern.test(conv.title || ""));
    if (!genericItems.length) return;

    const titleEntries = await Promise.all(
      genericItems.map(async (conv) => {
        try {
          const convMessages = await getMessages(conv.id);
          const firstUserMessage = convMessages.find((message) => message.role === "user")?.content;
          return firstUserMessage ? [conv.id, generateChatTitle(firstUserMessage)] : null;
        } catch {
          return null;
        }
      })
    );

    setGeneratedTitles((prev) => ({
      ...prev,
      ...Object.fromEntries(titleEntries.filter(Boolean))
    }));
  };

  const loadMessages = async (convId) => {
    try {
      const data = await getMessages(convId);
      setMessages(data);
    } catch (err) {
      console.error("Failed to load messages:", err);
    }
  };

  const handleCreateChat = async () => {
    setActiveConvId(null);
    setMessages([]);
    lastLoadedConvIdRef.current = null;
    setSidebarOpen(false);
    setInputText("");
    setStreamingContent("");
    setStreamingSources([]);
    requestAnimationFrame(() => textareaRef.current?.focus());
  };

  const handleDeleteChat = async (convId, event) => {
    event.stopPropagation();
    if (!window.confirm("Delete this chat?")) return;

    try {
      await deleteConversation(convId);
      const remaining = conversations.filter((conv) => conv.id !== convId);
      setConversations(remaining);
      if (activeConvId === convId) {
        setActiveConvId(remaining[0]?.id || null);
      }
    } catch (err) {
      console.error("Failed to delete chat:", err);
    }
  };

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  };

  const handleSuggestedPrompt = (prompt) => {
    setInputText(prompt);
    requestAnimationFrame(() => textareaRef.current?.focus());
  };

  const handleSend = async () => {
    const query = inputText.trim();
    if (!query || loading) return;

    setInputText("");
    setMessages((prev) => [...prev, { role: "user", content: query }]);
    setStreamingContent("");
    setStreamingSources([]);
    setLoading(true);

    let convId = activeConvId;

    try {
      if (!convId) {
        const title = generateChatTitle(query);
        const newChat = await createConversation(title);
        setConversations((prev) => [newChat, ...prev]);
        setActiveConvId(newChat.id);
        lastLoadedConvIdRef.current = newChat.id;
        convId = newChat.id;
      }

      const response = await postMessageStream(convId, query);
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;

          const rawData = trimmed.slice(6);
          if (rawData === "[DONE]") continue;

          try {
            const parsed = JSON.parse(rawData);
            if (parsed.type === "token") {
              setStreamingContent((prev) => prev + parsed.text);
            }
            if (parsed.type === "citations") {
              setStreamingSources(parsed.citations || []);
            }
          } catch (err) {
            console.error("Error parsing stream token:", err);
          }
        }
      }

      await loadMessages(convId);
    } catch (err) {
      console.error("Error during message query processing:", err);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${err.message || "Failed to generate answer"}` }
      ]);
    } finally {
      setLoading(false);
      setStreamingContent("");
      setStreamingSources([]);
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  };

  const contentOffset = sidebarCollapsed ? "lg:pl-0" : "lg:pl-72";
  const sidebarVisible = sidebarOpen ? "translate-x-0" : "-translate-x-full";

  return (
    <div className="h-screen overflow-hidden bg-slate-50 text-slate-950 antialiased">
      <header className="fixed left-0 right-0 top-0 z-40 flex h-14 items-center justify-between border-b border-slate-200 bg-white/95 px-4 backdrop-blur">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => {
              if (window.innerWidth >= 1024) {
                setSidebarCollapsed((value) => !value);
              } else {
                setSidebarOpen((value) => !value);
              }
            }}
            className="grid h-9 w-9 place-items-center rounded-lg text-slate-600 transition hover:bg-slate-100 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-blue-200"
            aria-label="Toggle sidebar"
          >
            {sidebarOpen ? <X size={19} /> : sidebarCollapsed ? <Menu size={19} /> : <PanelLeftClose size={19} />}
          </button>
          <div className="min-w-0 leading-tight">
            <div className="truncate text-sm font-semibold text-slate-950">SKCT AI Workspace | skct.edu.in</div>
          </div>
        </div>
      </header>

      <aside
        className={`fixed bottom-0 left-0 top-14 z-30 w-72 border-r border-slate-200 bg-white transition-transform duration-200 ${sidebarVisible} ${
          sidebarCollapsed ? "lg:-translate-x-full" : "lg:translate-x-0"
        }`}
      >
        <div className="flex h-full flex-col p-3">
          <div className="mb-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
            <div className="text-sm font-semibold text-slate-950">SKCT AI Workspace</div>
            <div className="mt-1 text-xs text-slate-500">AI Knowledge Assistant System</div>
          </div>

          <button
            type="button"
            onClick={handleCreateChat}
            className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-slate-950 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-300"
          >
            <Plus size={17} />
            New Chat
          </button>

          <button
            type="button"
            onClick={() => {
              setSidebarOpen(false);
              navigate("/graph");
            }}
            className="mt-3 flex h-10 w-full items-center gap-3 rounded-lg px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-100 hover:text-slate-950"
          >
            <Network size={16} className="text-slate-500" />
            Knowledge Graph
          </button>

          <div className="mt-5 min-h-0 flex-1">
            <div className="mb-2 flex items-center justify-between px-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Chat History</p>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">{conversations.length}</span>
            </div>

            <div className="h-full space-y-1 overflow-y-auto pr-1">
              {conversations.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">
                  No chats yet
                </div>
              ) : (
                conversations.map((conv) => (
                  <div
                    key={conv.id}
                    onClick={() => {
                      setActiveConvId(conv.id);
                      setSidebarOpen(false);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        setActiveConvId(conv.id);
                        setSidebarOpen(false);
                      }
                    }}
                    role="button"
                    tabIndex={0}
                    className={`group flex min-h-10 w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition ${
                      activeConvId === conv.id
                        ? "bg-blue-50 text-blue-900 ring-1 ring-blue-100"
                        : "text-slate-700 hover:bg-slate-100 hover:text-slate-950"
                    }`}
                  >
                    <MessageSquare size={15} className="shrink-0 text-slate-500" />
                    <span className="min-w-0 flex-1 truncate">{generatedTitles[conv.id] || conv.title}</span>
                    <span
                      role="button"
                      tabIndex={0}
                      onClick={(event) => handleDeleteChat(conv.id, event)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          handleDeleteChat(conv.id, event);
                        }
                      }}
                      className="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-slate-400 opacity-0 transition hover:bg-red-50 hover:text-red-600 group-hover:opacity-100"
                      aria-label={`Delete ${conv.title}`}
                    >
                      <Trash2 size={14} />
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="relative mt-3 border-t border-slate-200 pt-3">
            <button
              type="button"
              onClick={() => setProfileOpen((value) => !value)}
              className="flex w-full items-center gap-3 rounded-lg border border-slate-200 bg-white p-2 text-left transition hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-200"
              aria-expanded={profileOpen}
              aria-label="Open user profile menu"
            >
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-blue-600 text-sm font-semibold text-white">
                {initials}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold text-slate-900">{userName}</div>
                <div className="truncate text-xs text-slate-500">{userEmail}</div>
              </div>
              <ChevronDown size={16} className={`text-slate-400 transition ${profileOpen ? "rotate-180" : ""}`} />
            </button>

            {profileOpen && (
              <div className="absolute bottom-16 left-0 right-0 z-40 rounded-lg border border-slate-200 bg-white p-1 shadow-xl">
                <button
                  type="button"
                  className="flex h-10 w-full items-center gap-3 rounded-md px-3 text-sm text-slate-700 transition hover:bg-slate-100"
                >
                  <UserRound size={15} className="text-slate-500" />
                  View Profile
                </button>
                <button
                  type="button"
                  className="flex h-10 w-full items-center gap-3 rounded-md px-3 text-sm text-slate-700 transition hover:bg-slate-100"
                >
                  <Settings size={15} className="text-slate-500" />
                  Settings
                </button>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="flex h-10 w-full items-center gap-3 rounded-md px-3 text-sm font-medium text-red-600 transition hover:bg-red-50"
                >
                  <LogOut size={15} />
                  Logout
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>

      {sidebarOpen && (
        <button
          type="button"
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 top-14 z-20 bg-slate-950/30 lg:hidden"
          aria-label="Close sidebar"
        />
      )}

      <main className={`flex h-full flex-col pt-14 transition-[padding] duration-200 ${contentOffset}`}>
        <section className="flex-1 overflow-y-auto px-4 pb-6 pt-8 sm:px-6">
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
            {messages.length === 0 && !streamingContent && !loading ? (
              <EmptyState onPrompt={handleSuggestedPrompt} />
            ) : (
              messages.map((message, index) => <ChatMessage key={message.id || index} message={message} />)
            )}

            {streamingContent && <ChatMessage message={{ role: "assistant", content: streamingContent, sources: streamingSources }} />}
            {loading && !streamingContent && <ThinkingBubble />}
            <div ref={messagesEndRef} className="h-1" />
          </div>
        </section>

        <footer className="sticky bottom-0 z-30 border-t border-slate-200 bg-slate-50/95 px-4 py-4 backdrop-blur">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              handleSend();
            }}
            className="mx-auto flex max-w-3xl items-end gap-2 rounded-xl border border-slate-300 bg-white p-2 shadow-sm transition focus-within:border-blue-400 focus-within:ring-4 focus-within:ring-blue-50"
          >
            <textarea
              ref={textareaRef}
              value={inputText}
              onChange={(event) => setInputText(event.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              rows={1}
              placeholder="Ask anything about Sri Krishna College of Technology..."
              className="max-h-36 min-h-11 flex-1 resize-none border-0 bg-transparent px-3 py-3 text-[15px] leading-6 text-slate-950 outline-none placeholder:text-slate-400 disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={loading || !inputText.trim()}
              className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-blue-600 text-white transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:cursor-not-allowed disabled:bg-slate-300"
              aria-label="Send message"
            >
              <Send size={18} />
            </button>
          </form>
        </footer>
      </main>
    </div>
  );
}

function EmptyState({ onPrompt }) {
  return (
    <div className="mx-auto flex min-h-[58vh] w-full max-w-2xl flex-col items-center justify-center text-center">
      <div className="mb-5 grid h-16 w-16 place-items-center rounded-full border border-slate-200 bg-white text-3xl shadow-sm">
        🤖
      </div>
      <h1 className="text-2xl font-semibold tracking-tight text-slate-950">Hi, I'm SKCT AI Assistant</h1>
      <p className="mt-2 max-w-lg text-sm leading-6 text-slate-600">Ask me anything about SKCT</p>
      <div className="mt-8 grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
        {suggestedPrompts.map((item) => (
          <button
            key={item.label}
            type="button"
            onClick={() => onPrompt(item.prompt)}
            className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-left text-sm font-medium text-slate-800 shadow-sm transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-900 focus:outline-none focus:ring-2 focus:ring-blue-200"
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function ThinkingBubble() {
  return (
    <div className="flex justify-start">
      <div className="flex max-w-[70%] items-center gap-3 rounded-xl rounded-bl-md border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 shadow-sm max-sm:max-w-[88%]">
        <span className="grid h-8 w-8 animate-[robotPulse_1.4s_ease-in-out_infinite] place-items-center rounded-full bg-blue-50 text-lg">
          🤖
        </span>
        <span>SKCT AI is analyzing knowledge graph...</span>
        <span className="inline-flex items-center gap-1" aria-hidden="true">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-blue-500" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-blue-500 [animation-delay:120ms]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-blue-500 [animation-delay:240ms]" />
        </span>
      </div>
    </div>
  );
}

function cleanAnswerText(content = "") {
  const lines = String(content)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  const answerLines = [];
  for (const line of lines) {
    if (/^(📌\s*)?sources?:/i.test(line) || /^(📊\s*)?sources?:/i.test(line)) break;
    if (/^[-*]?\s*https?:\/\//i.test(line)) continue;
    const cleaned = line
      .replace(/^(?:🎓|📍)?\s*answer:\s*/i, "")
      .replace(/^[-*]\s*/, "")
      .trim();
    if (cleaned) answerLines.push(cleaned);
    if (answerLines.length >= 8) break;
  }

  return answerLines.join("\n") || "I could not find a clean answer in the available SKCT knowledge base.";
}

function extractUrlSources(content = "") {
  const urls = String(content).match(/https?:\/\/[^\s)]+/g) || [];
  return [...new Set(urls)].map((url, index) => ({
    title: sourceTitleFromUrl(url),
    url,
    score: Math.max(72, 90 - index * 6),
    snippet: "Relevant SKCT website source used for this answer."
  }));
}

function sourceTitleFromUrl(url = "") {
  try {
    const path = new URL(url).pathname.split("/").filter(Boolean).pop() || "SKCT Website";
    return path
      .replace(/-/g, " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  } catch {
    return "SKCT Website";
  }
}

function normalizeSources(message) {
  const rawSources = Array.isArray(message.sources) && message.sources.length
    ? message.sources
    : extractUrlSources(message.content);

  return rawSources.slice(0, 4).map((source, index) => {
    const rawScore = Number(source.score ?? 90 - index * 6);
    const score = rawScore <= 1 ? Math.round(rawScore * 100) : Math.round(rawScore);
    return {
      title: source.title || sourceTitleFromUrl(source.url) || "SKCT Website Page",
      url: source.url || "https://skct.edu.in",
      score: Math.max(0, Math.min(100, Number.isFinite(score) ? score : 85)),
      snippet: source.snippet || source.chunk_text || "Relevant SKCT website source used for this answer."
    };
  });
}

function SourceCards({ sources }) {
  if (!sources.length) return null;

  return (
    <div className="mt-4 border-t border-slate-200 pt-4">
      <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">📊 Sources</div>
      <div className="grid gap-3 sm:grid-cols-2">
        {sources.map((source, index) => (
          <a
            key={`${source.url}-${index}`}
            href={source.url}
            target="_blank"
            rel="noreferrer"
            className="group rounded-lg border border-slate-200 bg-slate-50 p-3 transition hover:border-blue-200 hover:bg-blue-50"
          >
            <div className="flex items-start gap-2">
              <FileText size={16} className="mt-0.5 shrink-0 text-blue-600" />
              <div className="min-w-0 flex-1">
                <div className="line-clamp-1 text-sm font-semibold text-slate-950">{source.title}</div>
                <div className="mt-1 text-xs font-medium text-emerald-700">Confidence: {source.score}%</div>
              </div>
              <ExternalLink size={14} className="shrink-0 text-slate-400 transition group-hover:text-blue-600" />
            </div>
            <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-600">{source.snippet}</p>
            <div className="mt-2 truncate text-xs text-slate-400">{source.url.replace(/^https?:\/\//, "")}</div>
          </a>
        ))}
      </div>
    </div>
  );
}

function ChatMessage({ message }) {
  const isUser = message.role === "user";
  const answerText = !isUser ? cleanAnswerText(message.content) : "";
  const sources = !isUser ? normalizeSources(message) : [];

  return (
    <div className={`flex w-full animate-[fadeIn_180ms_ease-out] ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`overflow-hidden rounded-xl px-4 py-3 text-[15px] leading-7 shadow-sm max-sm:max-w-[88%] ${
          isUser
            ? "max-w-[70%] rounded-br-md bg-blue-600 text-white"
            : "w-full max-w-[86%] rounded-bl-md border border-slate-200 bg-white text-slate-900"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        ) : (
          <div className="break-words">
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              <Bot size={15} className="text-blue-600" />
              🎓 Answer
            </div>
            <div className="space-y-2 text-slate-900 [&_a]:text-blue-600 [&_a]:underline [&_li]:my-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-0 [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:pl-5">
              <ReactMarkdown>{answerText}</ReactMarkdown>
            </div>
            <SourceCards sources={sources} />
          </div>
        )}
      </div>
    </div>
  );
}
