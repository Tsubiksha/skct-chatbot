import * as React from "react";
import { Clock3, Database, GraduationCap, Plus } from "lucide-react";

import GraphStats from "./GraphStats.jsx";
import SystemStatus from "./SystemStatus.jsx";

globalThis.__SKCT_REACT__ = React;

export default function Sidebar({
  recentChats,
  onNewChat,
  onRestoreChat,
  services,
  backendOnline,
  graphStats
}) {
  return (
    <aside className="hidden h-screen border-r border-white/10 bg-[#06101d] text-white lg:flex lg:w-[310px] lg:flex-col">
      <div className="px-5 py-5">
        <div className="flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-emerald-300 to-teal-500 text-slate-950 shadow-lg shadow-emerald-500/25">
            <GraduationCap size={25} />
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-emerald-300">SKCT</p>
            <h1 className="text-lg font-bold tracking-normal">GraphRAG Assistant</h1>
          </div>
        </div>
      </div>

      <div className="space-y-2 px-3">
        <button
          type="button"
          onClick={onNewChat}
          className="flex w-full items-center gap-3 rounded-2xl bg-white px-4 py-3 text-left text-sm font-bold text-slate-950 shadow-lg shadow-black/20 transition hover:bg-emerald-50"
        >
          <Plus size={18} className="text-emerald-600" />
          New Chat
        </button>
      </div>

      <div className="mt-5 px-3">
        <div className="mb-2 flex items-center gap-2 px-2 text-xs font-bold uppercase tracking-wide text-slate-400">
          <Clock3 size={14} />
          Recent Chats
        </div>
        <div className="space-y-1">
          {recentChats.length === 0 && (
            <p className="rounded-2xl border border-white/10 bg-white/[0.04] px-3 py-3 text-xs leading-5 text-slate-400">
              Recent conversations will appear here after you ask a question.
            </p>
          )}
          {recentChats.slice(0, 5).map((chat) => (
            <button
              key={chat.id}
              type="button"
              onClick={() => onRestoreChat(chat)}
              className="flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left text-sm text-slate-300 transition hover:bg-white/[0.08] hover:text-white"
            >
              <Database size={15} className="shrink-0 text-slate-500" />
              <span className="line-clamp-1">{chat.title}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="mt-auto space-y-3 p-3">
        <SystemStatus services={services} backendOnline={backendOnline} />
        <GraphStats stats={graphStats} />
      </div>
    </aside>
  );
}
