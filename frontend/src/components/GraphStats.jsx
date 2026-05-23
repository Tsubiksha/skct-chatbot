import * as React from "react";
import { BarChart3 } from "lucide-react";

globalThis.__SKCT_REACT__ = React;

const statLabels = [
  ["Departments", "departments"],
  ["Faculty", "faculty"],
  ["Courses", "courses"],
  ["Companies", "companies"],
  ["Relationships", "relationships"],
  ["Chunks", "chunks"]
];

export default function GraphStats({ stats }) {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.06] p-3">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
        <BarChart3 size={16} className="text-emerald-300" />
        Graph Statistics
      </div>
      <div className="grid grid-cols-2 gap-2">
        {statLabels.map(([label, key]) => (
          <div key={key} className="rounded-xl bg-black/20 px-3 py-2">
            <div className="text-base font-bold text-white">{stats?.[key] ?? 0}</div>
            <div className="text-[11px] text-slate-400">{label}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
