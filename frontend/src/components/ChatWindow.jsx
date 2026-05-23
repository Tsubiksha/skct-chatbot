import * as React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Bot, GraduationCap, Link2, Network, Send, UserRound } from "lucide-react";

import SuggestedQuestions from "./SuggestedQuestions.jsx";

globalThis.__SKCT_REACT__ = React;

function MarkdownText({ text }) {
  const html = useMemo(() => {
    const escaped = String(text)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");

    return escaped
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

function GraphContext({ graphContext }) {
  if (!graphContext.length) return null;

  return (
    <section className="rounded-3xl border border-slate-200 bg-white/80 p-4 shadow-sm backdrop-blur">
      <div className="mb-4 flex items-center gap-2 text-sm font-bold text-slate-800">
        <Network size={16} className="text-emerald-600" />
        Graph Context Visualization
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {graphContext.slice(0, 6).map((row, index) => (
          <div key={index} className="rounded-2xl bg-slate-50 px-4 py-3 text-center text-xs text-slate-600">
            <div className="font-bold text-slate-900">{row.source}</div>
            <div className="py-1 text-emerald-600">↓</div>
            <div className="font-semibold uppercase tracking-wide text-slate-500">{row.relationship}</div>
            <div className="py-1 text-emerald-600">↓</div>
            <div className="font-bold text-slate-900">{row.target}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function SourceCitations({ sources }) {
  if (!sources.length) return null;

  return (
    <section className="rounded-3xl border border-slate-200 bg-white/80 p-4 shadow-sm backdrop-blur">
      <div className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-800">
        <Link2 size={16} className="text-emerald-600" />
        Source Citations
      </div>
      <div className="grid gap-2">
        {sources.map((source, index) => (
          <a
            key={`${source.url}-${index}`}
            href={source.url}
            target="_blank"
            rel="noreferrer"
            className="rounded-2xl border border-slate-200 bg-white px-3 py-3 text-sm transition hover:border-emerald-300 hover:shadow-sm"
          >
            <span className="block font-bold text-slate-800">{source.title || `Source ${index + 1}`}</span>
            <span className="mt-1 line-clamp-2 block text-xs leading-5 text-slate-500">{source.snippet}</span>
          </a>
        ))}
      </div>
    </section>
  );
}

export default function ChatWindow({
  messages,
  input,
  setInput,
  loading,
  sources,
  graphContext,
  backendOnline,
  onAsk,
  onSubmit
}) {
  const bottomRef = useRef(null);
  const [isComposing, setIsComposing] = useState(false);
  const showHero = messages.length <= 1;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <main className="flex h-screen min-w-0 flex-col bg-[#f5f7fb]">
      <header className="border-b border-slate-200/80 bg-[#f5f7fb]/85 px-4 py-4 backdrop-blur-xl md:px-8">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-2xl bg-slate-950 text-emerald-300 lg:hidden">
              <GraduationCap size={21} />
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-emerald-700">SKCT College Knowledge</p>
              <h2 className="text-xl font-bold tracking-normal text-slate-950 md:text-2xl">GraphRAG Assistant</h2>
            </div>
          </div>
          <span className={`rounded-full px-3 py-2 text-xs font-bold ${backendOnline ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
            {backendOnline ? "Backend Online" : "Backend Offline"}
          </span>
        </div>
      </header>

      <section className="flex-1 overflow-y-auto px-4 py-6 md:px-8">
        <div className="mx-auto flex max-w-5xl flex-col gap-7">
          {showHero && (
            <motion.section
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45 }}
              className="mx-auto w-full max-w-3xl py-8 text-center md:py-14"
            >
              <div className="mx-auto mb-6 grid h-16 w-16 place-items-center rounded-3xl bg-gradient-to-br from-emerald-300 via-teal-400 to-cyan-500 text-slate-950 shadow-2xl shadow-emerald-500/25">
                <Bot size={31} />
              </div>
              <h1 className="text-3xl font-bold tracking-normal text-slate-950 md:text-5xl">
                AI-Powered College GraphRAG Assistant
              </h1>
              <p className="mx-auto mt-4 max-w-2xl text-base leading-7 text-slate-600 md:text-lg">
                Ask anything about departments, faculty, placements, courses, events, and research.
              </p>
              <SuggestedQuestions onAsk={onAsk} />
            </motion.section>
          )}

          <div className="space-y-5">
            {messages.map((message) => (
              <motion.article
                key={message.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex gap-3 ${message.role === "user" ? "justify-end" : "justify-start"}`}
              >
                {message.role === "assistant" && (
                  <div className="mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-emerald-300 to-teal-500 text-slate-950">
                    <Bot size={18} />
                  </div>
                )}
                <div
                  className={`max-w-[84%] rounded-3xl px-5 py-3 text-sm leading-6 shadow-sm md:max-w-[72%] ${
                    message.role === "user"
                      ? "rounded-br-lg bg-slate-950 text-white"
                      : "rounded-bl-lg border border-slate-200 bg-white/90 text-slate-700 backdrop-blur"
                  }`}
                >
                  <MarkdownText text={message.text} />
                </div>
                {message.role === "user" && (
                  <div className="mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-slate-200 text-slate-700">
                    <UserRound size={18} />
                  </div>
                )}
              </motion.article>
            ))}

            {loading && (
              <motion.article initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
                <div className="mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-emerald-300 to-teal-500 text-slate-950">
                  <Bot size={18} />
                </div>
                <div className="rounded-3xl rounded-bl-lg border border-slate-200 bg-white/90 px-5 py-4 shadow-sm">
                  <TypingDots />
                </div>
              </motion.article>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="grid gap-4 pb-4 md:grid-cols-2">
            <SourceCitations sources={sources} />
            <GraphContext graphContext={graphContext} />
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-200/80 bg-[#f5f7fb]/90 px-4 py-4 backdrop-blur-xl md:px-8">
        <form
          onSubmit={onSubmit}
          className="mx-auto flex max-w-5xl items-end gap-3 rounded-3xl border border-slate-200 bg-white p-2 shadow-2xl shadow-slate-200/70"
        >
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onCompositionStart={() => setIsComposing(true)}
            onCompositionEnd={() => setIsComposing(false)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !isComposing) {
                event.preventDefault();
                onAsk(input);
              }
            }}
            rows={1}
            placeholder="Ask anything about SKCT..."
            className="max-h-32 min-h-11 flex-1 resize-none rounded-2xl border-0 bg-transparent px-4 py-3 text-sm leading-6 text-slate-900 outline-none placeholder:text-slate-400"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-emerald-400 to-teal-500 text-slate-950 shadow-lg shadow-emerald-500/20 transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Send message"
          >
            <Send size={19} />
          </button>
        </form>
      </footer>
    </main>
  );
}
