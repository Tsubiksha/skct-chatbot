const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const token = localStorage.getItem("skct_token");
  
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { "Authorization": `Bearer ${token}` } : {}),
    ...(options.headers || {})
  };

  const response = await fetch(`${API_BASE_URL}${path}`, {
    mode: "cors",
    ...options,
    headers
  });

  if (!response.ok) {
    if (response.status === 401) {
      localStorage.removeItem("skct_token");
      localStorage.removeItem("skct_user");
      if (typeof window !== "undefined" && !window.location.pathname.includes("/login")) {
        window.location.href = "/login";
      }
    }
    let errMsg = response.statusText;
    try {
      const errorJson = await response.json();
      errMsg = errorJson.detail || errMsg;
    } catch (e) {
      // ignore
    }
    throw new Error(errMsg || "Request failed");
  }

  // Handle SSE streaming or empty responses
  if (response.headers.get("content-type")?.includes("text/event-stream")) {
    return response;
  }

  return response.json();
}

// --- Auth API ---
export async function login(email, password) {
  const res = await request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });
  if (res.access_token) {
    localStorage.setItem("skct_token", res.access_token);
    localStorage.setItem("skct_user", JSON.stringify(res.user));
  }
  return res;
}

export async function signup(username, email, password) {
  const res = await request("/api/auth/signup", {
    method: "POST",
    body: JSON.stringify({ username, email, password })
  });
  if (res.access_token) {
    localStorage.setItem("skct_token", res.access_token);
    localStorage.setItem("skct_user", JSON.stringify(res.user));
  }
  return res;
}

export async function getMe() {
  return request("/api/auth/me");
}

export function logout() {
  localStorage.removeItem("skct_token");
  localStorage.removeItem("skct_user");
}

// --- Chat API ---
export function getConversations() {
  return request("/api/chat/conversations");
}

export function createConversation(title = "New Chat") {
  return request("/api/chat/conversations", {
    method: "POST",
    body: JSON.stringify({ title })
  });
}

export function deleteConversation(convId) {
  return request(`/api/chat/conversations/${convId}`, {
    method: "DELETE"
  });
}

export function getMessages(convId) {
  return request(`/api/chat/conversations/${convId}/messages`);
}

// Return the fetch response object itself for reading the stream
export function postMessageStream(convId, content) {
  return request(`/api/chat/conversations/${convId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content })
  });
}

// --- GraphRAG / Admin Operations ---
export function getGraphStats() {
  return request("/api/graph-rag/stats").catch(() => request("/api/graph-rag/api/graph-rag/stats"));
}

export function getHealth() {
  return request("/api/graph-rag/health").catch(() => request("/api/graph-rag/api/graph-rag/health"));
}

export function triggerScrape({ forceReindex = false, maxPages = 30, maxDepth = 2 }) {
  const body = JSON.stringify({ force_reindex: forceReindex, max_pages: maxPages, max_depth: maxDepth });
  return request("/api/graph-rag/scrape-website", {
    method: "POST",
    body
  }).catch(() => request("/api/graph-rag/api/graph-rag/scrape-website", {
    method: "POST",
    body
  }));
}

export function getGraphData() {
  return request("/api/graph-rag/graph-data").catch(() => request("/api/graph-rag/api/graph-rag/graph-data"));
}
