// Graph RAG API — all calls go to /api/graph-rag/*
// Auth token is automatically injected from localStorage

const BASE = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000") + "/api/graph-rag";

async function req(path, options = {}) {
  const token = localStorage.getItem("skct_token");
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  const res = await fetch(`${BASE}${path}`, { mode: "cors", ...options, headers });

  if (!res.ok) {
    if (res.status === 401) {
      localStorage.removeItem("skct_token");
      localStorage.removeItem("skct_user");
      window.location.href = "/login";
    }
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = j.detail || j.message || msg;
    } catch {}
    throw new Error(msg || "Request failed");
  }
  return res.json();
}

// Unwrap backend wrapper { success, data, message } transparently
function unwrap(promise) {
  return promise.then((res) => {
    if (res && typeof res === "object" && "data" in res) return res.data ?? res;
    return res;
  });
}

/** GET /stats */
export const getStats = () => unwrap(req("/stats"));

/** POST /init */
export const initDatabase = () =>
  unwrap(req("/init", { method: "POST" }));

/** POST /scrape-website */
export const scrapeWebsite = (opts = {}) =>
  unwrap(
    req("/scrape-website", {
      method: "POST",
      body: JSON.stringify({
        force_reindex: opts.forceReindex ?? false,
        max_pages: opts.maxPages ?? null,
        max_depth: opts.maxDepth ?? null,
      }),
    })
  );

/** POST /build-graph */
export const buildGraph = () =>
  unwrap(req("/build-graph", { method: "POST" }));

/** POST /reindex */
export const reindex = (clearData = true) =>
  unwrap(req("/reindex", { method: "POST", body: JSON.stringify({ clear_data: clearData }) }));

/** POST /chat */
export const sendChat = (message, sessionId = null) =>
  unwrap(
    req("/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId }),
    })
  );
