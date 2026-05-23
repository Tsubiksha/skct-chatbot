import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bot, Network, Search, FileText, ArrowRight } from "lucide-react";

export default function LandingPage() {
  const navigate = useNavigate();
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("skct_token");
    if (token) {
      setIsLoggedIn(true);
    }
  }, []);

  return (
    <div className="relative min-h-screen w-full bg-[#030712] text-white overflow-hidden flex flex-col font-sans">
      {/* Background glow effects */}
      <div className="absolute top-[-10%] left-[-10%] w-[50vw] h-[50vw] bg-blue-500/10 rounded-full blur-[150px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50vw] h-[50vw] bg-emerald-500/10 rounded-full blur-[150px] pointer-events-none" />
      
      {/* Navbar */}
      <header className="w-full max-w-7xl mx-auto px-6 py-6 flex items-center justify-between border-b border-white/[0.06] z-10">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-emerald-400 to-blue-500 text-black font-bold">
            <Bot size={22} />
          </div>
          <div>
            <h1 className="text-xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
              SKCT College Bot
            </h1>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          {isLoggedIn ? (
            <button
              onClick={() => navigate("/chat")}
              className="px-5 py-2 rounded-xl bg-white text-black text-sm font-bold hover:bg-slate-200 transition-all duration-300 shadow-lg shadow-white/5"
            >
              Go to Chat
            </button>
          ) : (
            <>
              <Link to="/login" className="text-sm font-semibold text-slate-300 hover:text-white transition-colors">
                Sign In
              </Link>
              <Link
                to="/signup"
                className="px-5 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 text-white text-sm font-bold hover:brightness-110 transition-all duration-300 shadow-lg shadow-emerald-500/20"
              >
                Sign Up
              </Link>
            </>
          )}
        </div>
      </header>

      {/* Hero Section */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-6 flex flex-col items-center justify-center text-center z-10 py-16">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/30 bg-emerald-500/5 text-emerald-400 text-xs font-semibold mb-6 animate-pulse">
          <Bot size={14} /> Powered by Local LLM & GraphRAG
        </div>
        
        <h2 className="text-4xl md:text-7xl font-extrabold tracking-tight max-w-4xl leading-tight bg-gradient-to-b from-white to-slate-400 bg-clip-text text-transparent">
          The Intelligent Knowledge Assistant for <span className="bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">SKCT College</span>
        </h2>
        
        <p className="mt-6 text-base md:text-xl text-slate-400 max-w-2xl leading-relaxed">
          Ask questions and explore verified documents, course syllabi, placements history, faculty information, and campus activities with citation-backed, hallucination-free AI.
        </p>

        <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center items-center">
          <button
            onClick={() => navigate(isLoggedIn ? "/chat" : "/login")}
            className="group px-8 py-4 rounded-2xl bg-gradient-to-r from-emerald-400 to-blue-500 text-black font-extrabold text-base hover:shadow-[0_0_30px_rgba(16,185,129,0.3)] transition-all duration-300 flex items-center gap-2"
          >
            Start Conversing
            <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
          </button>
          
          <button
            onClick={() => navigate("/graph")}
            className="px-8 py-4 rounded-2xl bg-slate-900 border border-white/[0.08] text-slate-200 font-bold text-base hover:bg-slate-800 hover:text-white transition-all duration-300 flex items-center gap-2"
          >
            <Network size={18} className="text-emerald-400" />
            Explore Knowledge Graph
          </button>
        </div>

        {/* Features grid */}
        <div className="mt-24 grid md:grid-cols-3 gap-8 w-full">
          <div className="p-8 rounded-2xl border border-white/[0.04] bg-white/[0.02] backdrop-blur-md hover:border-emerald-500/20 hover:bg-white/[0.04] transition-all duration-300 group">
            <div className="w-12 h-12 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-400 mb-6 group-hover:scale-110 transition-transform">
              <Network size={24} />
            </div>
            <h3 className="text-lg font-bold mb-3 text-slate-100">GraphRAG Technology</h3>
            <p className="text-sm leading-relaxed text-slate-400">
              Retrieves data through a dual-index mapping departments, course offerings, clubs, placement coordinators, and recruiter entities for structured semantic lookup.
            </p>
          </div>

          <div className="p-8 rounded-2xl border border-white/[0.04] bg-white/[0.02] backdrop-blur-md hover:border-blue-500/20 hover:bg-white/[0.04] transition-all duration-300 group">
            <div className="w-12 h-12 rounded-xl bg-blue-500/10 flex items-center justify-center text-blue-400 mb-6 group-hover:scale-110 transition-transform">
              <Search size={24} />
            </div>
            <h3 className="text-lg font-bold mb-3 text-slate-100">Hybrid Search Engine</h3>
            <p className="text-sm leading-relaxed text-slate-400">
              Combines dense semantic vector distance (ChromaDB) with keyword-focused BM25 matches (SQLite FTS5) to achieve maximum retrieval coverage and query accuracy.
            </p>
          </div>

          <div className="p-8 rounded-2xl border border-white/[0.04] bg-white/[0.02] backdrop-blur-md hover:border-purple-500/20 hover:bg-white/[0.04] transition-all duration-300 group">
            <div className="w-12 h-12 rounded-xl bg-purple-500/10 flex items-center justify-center text-purple-400 mb-6 group-hover:scale-110 transition-transform">
              <FileText size={24} />
            </div>
            <h3 className="text-lg font-bold mb-3 text-slate-100">Perplexity-style Citations</h3>
            <p className="text-sm leading-relaxed text-slate-400">
              Verifies answers with rich confidence percentage ratings, source web links, preview text cards, and matching department tags so you can double check source validity.
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="w-full max-w-7xl mx-auto px-6 py-8 flex justify-between items-center border-t border-white/[0.06] text-xs text-slate-500 z-10">
        <div>&copy; 2026 Sri Krishna College of Technology. All rights reserved.</div>
        <div className="flex gap-4">
          <a href="https://skct.edu.in" target="_blank" rel="noreferrer" className="hover:text-slate-300 transition-colors">Official Website</a>
          <span>&middot;</span>
          <span className="text-emerald-500/70 font-semibold">GraphRAG Bot v2.0</span>
        </div>
      </footer>
    </div>
  );
}
