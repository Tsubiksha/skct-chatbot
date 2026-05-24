import React, { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Sparkles, AlertCircle, ExternalLink } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export default function ChatInterface() {
  const [messages, setMessages]   = useState([]);
  const [input, setInput]         = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);
  const abortRef       = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => { scrollToBottom(); }, [messages]);

  // ── Submit handler ──────────────────────────────────────────────────────────
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const question = input.trim();
    setInput('');
    setIsLoading(true);

    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: question }]);

    // Add placeholder assistant message
    const botId = `bot-${Date.now()}`;
    setMessages(prev => [...prev, { id: botId, role: 'assistant', content: '', sources: [], streaming: true }]);

    try {
      const controller = new AbortController();
      abortRef.current = controller;

      const res = await fetch(`${API_BASE}/api/graph-rag/chat/stream`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ message: question }),
        signal:  controller.signal,
      });

      if (!res.ok) {
        // Fallback to non-streaming endpoint
        const fallback = await fetch(`${API_BASE}/api/graph-rag/chat`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ message: question }),
        });
        const data = await fallback.json();
        const result = data.data || data;
        setMessages(prev =>
          prev.map(msg =>
            msg.id === botId
              ? { ...msg, content: result.answer || 'No answer returned.', sources: result.sources || [], streaming: false }
              : msg
          )
        );
        return;
      }

      // Streaming read
      const reader  = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let   buffer  = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        setMessages(prev =>
          prev.map(msg =>
            msg.id === botId ? { ...msg, content: buffer } : msg
          )
        );
      }

      // Mark streaming done
      setMessages(prev =>
        prev.map(msg =>
          msg.id === botId ? { ...msg, streaming: false } : msg
        )
      );

    } catch (err) {
      if (err.name === 'AbortError') return;
      console.error('[Chat] Error:', err);
      setMessages(prev =>
        prev.map(msg =>
          msg.id === botId
            ? { ...msg, content: '⚠️ Error: Could not connect to the backend. Please ensure the server is running.', streaming: false }
            : msg
        )
      );
    } finally {
      setIsLoading(false);
      abortRef.current = null;
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
    setIsLoading(false);
  };

  // ── Suggestion chips ────────────────────────────────────────────────────────
  const SUGGESTIONS = [
    "Who is the HOD of CSE department?",
    "What are the placement statistics?",
    "What courses does SKCT offer?",
    "How can I contact SKCT?",
  ];

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full relative z-10 w-full max-w-5xl mx-auto px-4 pb-4">

      {/* Header */}
      <header className="py-6 flex items-center justify-between border-b border-gray-800/50">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-primary/10 rounded-lg flex items-center justify-center border border-primary/20">
            <Sparkles className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">SKCT AI Assistant</h1>
            <p className="text-xs text-gray-500">Powered by Graph RAG + Ollama</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <span className="text-xs text-gray-500">Online</span>
        </div>
      </header>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto py-8 px-2 space-y-8 no-scrollbar">

        {/* Empty state */}
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center max-w-2xl mx-auto">
            <div className="w-20 h-20 bg-primary/10 rounded-2xl flex items-center justify-center mb-6 border border-primary/20 shadow-lg">
              <Sparkles className="w-10 h-10 text-primary" />
            </div>
            <h2 className="text-3xl font-semibold mb-3">How can I help you?</h2>
            <p className="text-gray-400 mb-8 text-base leading-relaxed">
              Ask anything about SKCT — departments, placements, courses,<br />
              faculty, events, contact information, and more.
            </p>
            <div className="grid grid-cols-2 gap-3 w-full max-w-lg">
              {SUGGESTIONS.map(q => (
                <button
                  key={q}
                  onClick={() => setInput(q)}
                  className="glass-panel p-4 text-sm text-left hover:border-primary/50 hover:bg-primary/5 transition-all duration-200 rounded-xl"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Message list */}
        {messages.map((msg, idx) => (
          <div key={msg.id || idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[88%] ${
              msg.role === 'user'
                ? 'bg-primary/10 border border-primary/20 text-white rounded-2xl rounded-tr-sm px-5 py-3'
                : 'w-full'
            }`}>
              {msg.role === 'assistant' ? (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center shrink-0 mt-1 border border-gray-700">
                    <Sparkles className="w-4 h-4 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    {/* Answer text */}
                    <div className="prose prose-invert prose-sm max-w-none text-gray-200">
                      <ReactMarkdown>{msg.content || ''}</ReactMarkdown>
                      {msg.streaming && (
                        <span className="inline-block w-1.5 h-4 bg-primary/60 animate-pulse ml-0.5 align-middle" />
                      )}
                    </div>
                    {/* Sources */}
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-gray-800">
                        <p className="text-xs text-gray-500 mb-2 font-medium uppercase tracking-wider">Sources</p>
                        <div className="flex flex-wrap gap-2">
                          {msg.sources.map((src, i) => (
                            <a
                              key={i}
                              href={src.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 px-2.5 py-1 bg-gray-800 hover:bg-gray-700 border border-gray-700 hover:border-primary/40 rounded-full text-xs text-gray-300 hover:text-white transition-all"
                            >
                              <ExternalLink className="w-3 h-3" />
                              {src.title?.slice(0, 30) || src.url?.slice(0, 30)}
                            </a>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <p className="text-sm leading-relaxed">{msg.content}</p>
              )}
            </div>
          </div>
        ))}

        {/* Typing indicator */}
        {isLoading && messages[messages.length - 1]?.role !== 'assistant' && (
          <div className="flex justify-start">
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center border border-gray-700">
                <Sparkles className="w-4 h-4 text-primary" />
              </div>
              <div className="flex items-center gap-1.5 text-gray-400 text-sm py-2">
                <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input bar */}
      <div className="mt-4 pt-2">
        <form onSubmit={handleSubmit} className="relative">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Ask anything about SKCT..."
            disabled={isLoading}
            className="w-full glass-input px-6 py-4 pr-24 text-base placeholder-gray-500 disabled:opacity-50 rounded-2xl"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2">
            {isLoading && (
              <button
                type="button"
                onClick={handleStop}
                className="px-3 py-1.5 bg-red-500/20 text-red-400 hover:bg-red-500/30 border border-red-500/30 rounded-lg text-xs transition-colors"
              >
                Stop
              </button>
            )}
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="p-2.5 bg-primary text-black rounded-xl hover:bg-primary/90 disabled:opacity-40 disabled:hover:bg-primary transition-all duration-200 shadow-lg"
            >
              {isLoading
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <Send className="w-4 h-4" />
              }
            </button>
          </div>
        </form>
        <p className="text-center text-xs text-gray-600 mt-2.5 flex items-center justify-center gap-1.5">
          <AlertCircle className="w-3 h-3" />
          Answers are based on skct.edu.in content. Verify critical information officially.
        </p>
      </div>
    </div>
  );
}
