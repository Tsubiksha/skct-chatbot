import * as React from "react";
import { CheckCircle2, CircleOff, Server } from "lucide-react";

globalThis.__SKCT_REACT__ = React;

function statusTone(value) {
  return value && (value.includes("optional-unavailable") || (!value.includes("unavailable") && !value.includes("offline")));
}

export default function SystemStatus({ services, backendOnline }) {
  const rows = [
    ["FastAPI", backendOnline ? "running" : "offline"],
    ["Ollama", services?.ollama || "checking"],
    ["ChromaDB", services?.chroma || "checking"],
    ["SQLite", services?.sqlite || "checking"],
    ["SQLite Graph", services?.sqlite_graph || "checking"],
    ["Indexing", services?.query === "indexing" ? services?.indexing || "indexing" : services?.query || "checking"]
  ];

  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.06] p-3">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
        <Server size={16} className="text-emerald-300" />
        System Status
      </div>
      <div className="space-y-2">
        {rows.map(([label, value]) => {
          const healthy = statusTone(value);
          return (
            <div key={label} className="flex items-center justify-between gap-3 text-xs">
              <span className="text-slate-300">{label}</span>
              <span className={`inline-flex items-center gap-1 font-semibold ${healthy ? "text-emerald-300" : "text-rose-300"}`}>
                {healthy ? <CheckCircle2 size={13} /> : <CircleOff size={13} />}
                {value}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
