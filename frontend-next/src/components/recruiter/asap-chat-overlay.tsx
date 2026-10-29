"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  Minus,
  Plus,
  Send,
  X,
  User,
  Briefcase,
  Play,
} from "lucide-react";
import { api } from "@/lib/api";
import "./asap-chat-overlay.css";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  model?: string;
  provider?: string;
  sources?: Array<{ type: string; id: string; title: string }>;
  action?: any;
  isStreaming?: boolean;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
}

const GREETINGS = [
  "Hello, I'm ASAP, your candidate screening assistant, how may I assist you today?",
  "Hi! I'm ASAP, your candidate screening assistant. What jobs, candidates, or evaluations can I help you explore today?",
  "Greetings! I'm ASAP, your candidate screening assistant. How can I assist your recruitment workflow today?",
  "Hello there! I'm ASAP, your screening and talent intelligence assistant. How may I help you evaluate your pipeline today?",
  "Hi! I'm ASAP, your candidate screening assistant. Ready to help you review applicant qualifications, match scores, and job criteria. What's on your mind?",
  "Welcome! I'm ASAP, your candidate screening partner. How may I assist you with your hiring data and candidate files right now?",
  "Hello! I'm ASAP, your AI screening companion. Feel free to ask about any candidate, job description, or evaluation file in the app. How can I help you?",
  "Hi there! I'm ASAP, your candidate screening assistant. How may I assist you with candidate benchmarking and criteria checks today?",
];

function getRandomGreeting(): string {
  return GREETINGS[Math.floor(Math.random() * GREETINGS.length)];
}

const QUICK_PROMPTS = [
  "What was our latest screening run?",
  "What candidates were recently added?",
  "What are the latest active jobs in the app?",
  "Who is shortlisted for Lead AI Engineer?",
];

/** Simplified static ghost face SVG icon (no animations) for the chat header */
export function StaticGhostAvatar({ size = 26 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="asap-static-ghost-icon"
      aria-hidden="true"
    >
      <circle cx="50" cy="50" r="46" fill="url(#static-ghost-bg)" />
      <circle cx="50" cy="50" r="45" stroke="#93c5fd" strokeWidth="1.5" strokeOpacity="0.7" />
      {/* Blush */}
      <ellipse cx="26" cy="58" rx="8" ry="4.5" fill="#f472b6" fillOpacity="0.5" />
      <ellipse cx="74" cy="58" rx="8" ry="4.5" fill="#f472b6" fillOpacity="0.5" />
      {/* Cute smile mouth */}
      <path d="M 44 65 Q 50 71 56 65" stroke="#1e293b" strokeWidth="2.5" strokeLinecap="round" fill="none" />
      {/* Eyes */}
      <ellipse cx="38" cy="48" rx="7.5" ry="14" fill="#0f172a" />
      <ellipse cx="62" cy="48" rx="7.5" ry="14" fill="#0f172a" />
      {/* Eye shine highlights */}
      <ellipse cx="36" cy="41" rx="2.5" ry="4.5" fill="#ffffff" />
      <circle cx="41" cy="50" r="1.5" fill="#ffffff" />
      <ellipse cx="60" cy="41" rx="2.5" ry="4.5" fill="#ffffff" />
      <circle cx="65" cy="50" r="1.5" fill="#ffffff" />
      <defs>
        <radialGradient id="static-ghost-bg" cx="40%" cy="35%" r="65%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="70%" stopColor="#f1f5f9" />
          <stop offset="100%" stopColor="#bfdbfe" />
        </radialGradient>
      </defs>
    </svg>
  );
}

interface AsapChatOverlayProps {
  currentJobId?: string | null;
  currentCandidateId?: string | null;
  activeStep?: string | null;
}

export function AsapChatOverlay({
  currentJobId,
  currentCandidateId,
  activeStep,
}: AsapChatOverlayProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [position, setPosition] = useState<{ x: number; y: number }>({ x: 280, y: 70 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef<{ mouseX: number; mouseY: number; startX: number; startY: number } | null>(null);

  // Minimized drag tracking
  const [isMinimizedDragging, setIsMinimizedDragging] = useState(false);
  const minDragStartRef = useRef<{ mouseX: number; mouseY: number; startX: number; startY: number; moved: boolean } | null>(null);

  // Sessions state
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    if (typeof window !== "undefined") {
      try {
        const saved = sessionStorage.getItem("atos_asap_chat_sessions_v2");
        if (saved) {
          const parsed = JSON.parse(saved);
          if (Array.isArray(parsed) && parsed.length > 0) return parsed;
        }
      } catch {}
    }
    const initialId = crypto.randomUUID();
    return [
      {
        id: initialId,
        title: "Session 1",
        createdAt: Date.now(),
        messages: [
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: getRandomGreeting(),
            timestamp: Date.now(),
          },
        ],
      },
    ];
  });

  const [activeSessionId, setActiveSessionId] = useState<string>(() => {
    return sessions[0]?.id || "";
  });

  const [agentStatus, setAgentStatus] = useState<"active" | "inactive">("active");
  const [inputValue, setInputValue] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Save sessions to sessionStorage
  useEffect(() => {
    try {
      sessionStorage.setItem("atos_asap_chat_sessions_v2", JSON.stringify(sessions));
    } catch {}
  }, [sessions]);

  // Center/clamp initial position
  useEffect(() => {
    if (typeof window !== "undefined") {
      const defaultX = Math.max(20, Math.min(window.innerWidth - 430, 270));
      const defaultY = Math.max(20, Math.min(window.innerHeight - 600, 75));
      setPosition({ x: defaultX, y: defaultY });
    }
  }, []);

  // Listen for open event dispatched when clicking the GhostMascot animated face SVG
  useEffect(() => {
    const handleOpen = () => {
      setIsOpen((prev) => {
        if (!prev) {
          setIsMinimized(false);
          return true;
        }
        if (isMinimized) {
          setIsMinimized(false);
          return true;
        }
        return prev;
      });
      setTimeout(() => inputRef.current?.focus(), 100);
    };

    window.addEventListener("open-asap-chat", handleOpen);
    window.addEventListener("atos-open-asap-chat", handleOpen);
    return () => {
      window.removeEventListener("open-asap-chat", handleOpen);
      window.removeEventListener("atos-open-asap-chat", handleOpen);
    };
  }, [isMinimized]);

  // Auto-scroll messages during streaming
  useEffect(() => {
    if (isOpen && !isMinimized) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [sessions, activeSessionId, isStreaming, isOpen, isMinimized]);

  const activeSession = sessions.find((s) => s.id === activeSessionId) || sessions[0];

  // Dragging mechanics for full chat window
  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest("button")) return;
    setIsDragging(true);
    dragStartRef.current = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      startX: position.x,
      startY: position.y,
    };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging || !dragStartRef.current) return;
    const deltaX = e.clientX - dragStartRef.current.mouseX;
    const deltaY = e.clientY - dragStartRef.current.mouseY;

    const width = 410;
    const height = 570;
    const maxX = Math.max(0, window.innerWidth - width - 10);
    const maxY = Math.max(0, window.innerHeight - height - 10);

    const nextX = Math.max(10, Math.min(maxX, dragStartRef.current.startX + deltaX));
    const nextY = Math.max(10, Math.min(maxY, dragStartRef.current.startY + deltaY));
    setPosition({ x: nextX, y: nextY });
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    setIsDragging(false);
    dragStartRef.current = null;
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {}
  };

  // Dragging mechanics for minimized floating icon
  const handleMinimizedPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    setIsMinimizedDragging(true);
    minDragStartRef.current = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      startX: position.x,
      startY: position.y,
      moved: false,
    };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handleMinimizedPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isMinimizedDragging || !minDragStartRef.current) return;
    const deltaX = e.clientX - minDragStartRef.current.mouseX;
    const deltaY = e.clientY - minDragStartRef.current.mouseY;

    if (Math.hypot(deltaX, deltaY) > 5) {
      minDragStartRef.current.moved = true;
    }

    const maxX = Math.max(0, window.innerWidth - 130);
    const maxY = Math.max(0, window.innerHeight - 60);

    const nextX = Math.max(10, Math.min(maxX, minDragStartRef.current.startX + deltaX));
    const nextY = Math.max(10, Math.min(maxY, minDragStartRef.current.startY + deltaY));
    setPosition({ x: nextX, y: nextY });
  };

  const handleMinimizedPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    setIsMinimizedDragging(false);
    const wasMoved = minDragStartRef.current?.moved;
    minDragStartRef.current = null;
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {}

    // If pointer was clicked without dragging, expand the window!
    if (!wasMoved) {
      setIsMinimized(false);
      setTimeout(() => inputRef.current?.focus(), 80);
    }
  };

  // Start new conversation session tab with random greeting
  const handleNewSession = useCallback(() => {
    const newId = crypto.randomUUID();
    const newSession: ChatSession = {
      id: newId,
      title: `Session ${sessions.length + 1}`,
      createdAt: Date.now(),
      messages: [
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: getRandomGreeting(),
          timestamp: Date.now(),
        },
      ],
    };
    setSessions((prev) => [...prev, newSession]);
    setActiveSessionId(newId);
    setTimeout(() => inputRef.current?.focus(), 60);
  }, [sessions.length]);

  // Close session tab
  const handleCloseSession = (e: React.MouseEvent, idToClose: string) => {
    e.stopPropagation();
    if (sessions.length <= 1) {
      const newGreeting = getRandomGreeting();
      setSessions([
        {
          id: crypto.randomUUID(),
          title: "Session 1",
          createdAt: Date.now(),
          messages: [
            {
              id: crypto.randomUUID(),
              role: "assistant",
              content: newGreeting,
              timestamp: Date.now(),
            },
          ],
        },
      ]);
      return;
    }

    const remaining = sessions.filter((s) => s.id !== idToClose);
    setSessions(remaining);
    if (activeSessionId === idToClose) {
      setActiveSessionId(remaining[remaining.length - 1].id);
    }
  };

  // Send message with real-time ChatGPT-style streaming
  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || inputValue).trim();
    if (!text || isStreaming) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      timestamp: Date.now(),
    };

    const assistantMsgId = crypto.randomUUID();
    const initialAssistantMsg: ChatMessage = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      timestamp: Date.now(),
      isStreaming: true,
    };

    // Update active tab title on first message if still default name
    setSessions((prev) =>
      prev.map((s) => {
        if (s.id === activeSessionId) {
          const isDefaultTitle = s.title.startsWith("Session ");
          const newTitle = isDefaultTitle ? text.slice(0, 20) + (text.length > 20 ? "…" : "") : s.title;
          return {
            ...s,
            title: newTitle,
            messages: [...s.messages, userMsg, initialAssistantMsg],
          };
        }
        return s;
      })
    );

    setInputValue("");
    setIsStreaming(true);

    // Notify mascot to play curious animation
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("asap-chat-reaction", { detail: { expression: "curious" } }));
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const historyToSend = [
        ...(activeSession?.messages || []).map((m) => ({
          role: m.role as "user" | "assistant",
          content: m.content,
        })),
        { role: "user" as const, content: text },
      ];

      await api.chatWithAsapStream(
        historyToSend,
        {
          current_job_id: currentJobId,
          current_candidate_id: currentCandidateId,
          active_step: activeStep,
        },
        {
          onStart: (sources) => {
            setAgentStatus("active");
            setSessions((prev) =>
              prev.map((s) => {
                if (s.id === activeSessionId) {
                  return {
                    ...s,
                    messages: s.messages.map((m) =>
                      m.id === assistantMsgId ? { ...m, sources } : m
                    ),
                  };
                }
                return s;
              })
            );
          },
          onAction: (action) => {
            setSessions((prev) =>
              prev.map((s) => {
                if (s.id === activeSessionId) {
                  return {
                    ...s,
                    messages: s.messages.map((m) =>
                      m.id === assistantMsgId ? { ...m, action } : m
                    ),
                  };
                }
                return s;
              })
            );

            // Notify app components of executed live actions
            if (typeof window !== "undefined") {
              if (action?.action_type === "run_screening" && action?.success) {
                window.dispatchEvent(new CustomEvent("atos-screening-started", { detail: action }));
                window.dispatchEvent(new CustomEvent("atos-refresh-pipeline", { detail: action }));
              } else if (action?.action_type === "navigate" && action?.success) {
                window.dispatchEvent(new CustomEvent("atos-navigate", { detail: action }));
              }
            }
          },
          onChunk: (chunkText) => {
            setSessions((prev) =>
              prev.map((s) => {
                if (s.id === activeSessionId) {
                  return {
                    ...s,
                    messages: s.messages.map((m) =>
                      m.id === assistantMsgId
                        ? { ...m, content: m.content + chunkText }
                        : m
                    ),
                  };
                }
                return s;
              })
            );
          },
          onDone: (meta) => {
            setAgentStatus("active");
            setSessions((prev) =>
              prev.map((s) => {
                if (s.id === activeSessionId) {
                  return {
                    ...s,
                    messages: s.messages.map((m) =>
                      m.id === assistantMsgId
                        ? {
                            ...m,
                            model: meta.model || m.model,
                            provider: meta.provider || m.provider,
                            sources: meta.sources || m.sources,
                            action: meta.action || m.action,
                            isStreaming: false,
                          }
                        : m
                    ),
                  };
                }
                return s;
              })
            );
          },
        },
        controller.signal
      );

      // Trigger happy mascot reaction on complete
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("asap-chat-reaction", { detail: { expression: "happy" } }));
      }
    } catch (err: any) {
      if (err?.name === "AbortError") return;
      setAgentStatus("inactive");
      setSessions((prev) =>
        prev.map((s) => {
          if (s.id === activeSessionId) {
            return {
              ...s,
              messages: s.messages.map((m) =>
                m.id === assistantMsgId
                  ? {
                      ...m,
                      content:
                        m.content ||
                        `⚠️ Failed to get reply: ${err?.message || "Unknown error"}. The failover engine attempted all configured models.`,
                      isStreaming: false,
                    }
                  : m
              ),
            };
          }
          return s;
        })
      );
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
      setTimeout(() => inputRef.current?.focus(), 60);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  if (!isOpen) return null;

  // Minimized Draggable Floating View: strictly the glowing ghost PNG, status dot (green when active, red when inactive), and session count bubble
  if (isMinimized) {
    return (
      <div
        className="asap-minimized-floating"
        style={{ left: `${position.x}px`, top: `${position.y}px` }}
        onPointerDown={handleMinimizedPointerDown}
        onPointerMove={handleMinimizedPointerMove}
        onPointerUp={handleMinimizedPointerUp}
        title="Drag to reposition · Click to expand ASAP Screening Assistant"
        role="button"
        tabIndex={0}
      >
        <div className="asap-minimized-ghost-wrapper">
          <img
            src="/ghost-avatar.png"
            alt="ASAP Assistant"
            className="asap-minimized-ghost-img"
            draggable={false}
          />
          <span
            className={`asap-minimized-status-dot ${agentStatus}`}
            title={`Status: ${agentStatus === "active" ? "Active" : "Inactive"}`}
          />
          <span
            className="asap-minimized-session-bubble"
            title={`${sessions.length} open conversation session${sessions.length > 1 ? "s" : ""}`}
          >
            {sessions.length}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`asap-chat-window ${isDragging ? "dragging" : ""}`}
      style={{
        left: `${position.x}px`,
        top: `${position.y}px`,
      }}
      role="dialog"
      aria-label="ASAP Candidate Screening AI Assistant"
    >
      {/* Header bar with Drag Handle and Static Ghost Face Icon */}
      <div
        className="asap-chat-header"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        <div className="asap-header-title">
          {/* Simplified static ghost face SVG icon */}
          <StaticGhostAvatar size={28} />
          <div className="asap-header-text">
            <div className="asap-header-name">
              ASAP
              <span className="asap-badge">AI AGENT</span>
            </div>
            <div className="asap-header-status">
              <span className="asap-status-dot" />
              Live Candidate Screening Assistant
            </div>
          </div>
        </div>

        <div className="asap-header-controls">
          <button
            type="button"
            className="asap-control-btn"
            onClick={() => setIsMinimized(true)}
            title="Minimize chat (draggable)"
            aria-label="Minimize chat overlay"
          >
            <Minus size={14} />
          </button>
          <button
            type="button"
            className="asap-control-btn close"
            onClick={() => setIsOpen(false)}
            title="Close chat"
            aria-label="Close chat"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Sessions / Tabs Strip */}
      <div className="asap-tabs-bar" role="tablist">
        {sessions.map((s) => {
          const isActive = s.id === activeSessionId;
          return (
            <button
              key={s.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              className={`asap-tab ${isActive ? "active" : ""}`}
              onClick={() => setActiveSessionId(s.id)}
            >
              <span className="asap-tab-title">{s.title}</span>
              <span
                role="button"
                className="asap-tab-close"
                onClick={(e) => handleCloseSession(e, s.id)}
                title="Close session"
                aria-label={`Close ${s.title}`}
              >
                <X size={10} />
              </span>
            </button>
          );
        })}

        <button
          type="button"
          className="asap-new-tab-btn"
          onClick={handleNewSession}
          title="Start new conversation session"
        >
          <Plus size={12} />
          <span>New</span>
        </button>
      </div>

      {/* Messages Stream */}
      <div className="asap-messages-list">
        {activeSession?.messages.map((m) => {
          const isUser = m.role === "user";
          return (
            <div key={m.id} className={`asap-message-row ${isUser ? "user" : "assistant"}`}>
              {/* Executed Action Live Card */}
              {!isUser && m.action && m.action.action_type === "run_screening" && m.action.success && (
                <div className="asap-action-card">
                  <div className="asap-action-card-header">
                    <span className="asap-action-badge">
                      <span className="asap-action-live-indicator" />
                      SCREENING RUN EXECUTED
                    </span>
                    <span className="asap-action-version">
                      {m.action.pipeline_version?.toUpperCase() || "V2"} PIPELINE
                    </span>
                  </div>
                  <div className="asap-action-card-grid">
                    <div className="asap-action-item">
                      <span className="asap-action-label">Job Requisition:</span>
                      <span className="asap-action-val job">{m.action.job_title}</span>
                    </div>
                    <div className="asap-action-item">
                      <span className="asap-action-label">Cohort Size:</span>
                      <span className="asap-action-val">{m.action.cohort_size} candidates</span>
                    </div>
                    <div className="asap-action-item">
                      <span className="asap-action-label">Deep Screening:</span>
                      <span className="asap-action-val">{m.action.deep_count} candidates</span>
                    </div>
                    <div className="asap-action-item">
                      <span className="asap-action-label">Run ID:</span>
                      <code className="asap-action-code">{m.action.run_id}</code>
                    </div>
                  </div>
                </div>
              )}

              <div className="asap-bubble">
                {m.content ? (
                  <>
                    <FormattedContent content={m.content} />
                    {m.isStreaming && <span className="asap-streaming-cursor" />}
                  </>
                ) : (
                  <div className="asap-typing-indicator" aria-label="ASAP is thinking">
                    <span className="asap-typing-dot" />
                    <span className="asap-typing-dot" />
                    <span className="asap-typing-dot" />
                  </div>
                )}
              </div>

              {!isUser && m.content && (
                <div className="asap-meta-footer">
                  {m.model && (
                    <span className="asap-model-pill" title={`Engine: ${m.provider || "failover"}`}>
                      ⚡ {m.model.replace(/^.*\//, "")}
                    </span>
                  )}
                  {m.sources && m.sources.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {m.sources.slice(0, 3).map((src, i) => (
                        <span key={i} className="asap-source-tag" title={src.title}>
                          {src.type === "job" ? (
                            <Briefcase size={9} />
                          ) : src.type === "run" ? (
                            <Play size={9} />
                          ) : (
                            <User size={9} />
                          )}
                          <span>{src.title.length > 22 ? src.title.slice(0, 20) + "…" : src.title}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {/* Quick prompt suggestions for initial conversation */}
        {activeSession?.messages.length === 1 && !isStreaming && (
          <div className="asap-chips-row">
            {QUICK_PROMPTS.map((promptText) => (
              <button
                key={promptText}
                type="button"
                className="asap-chip"
                onClick={() => handleSendMessage(promptText)}
              >
                {promptText}
              </button>
            ))}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input bar */}
      <div className="asap-input-bar">
        <textarea
          ref={inputRef}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask ASAP about latest runs, jobs, or candidates…"
          rows={1}
          className="asap-input-textarea"
          disabled={isStreaming}
        />
        <button
          type="button"
          onClick={() => handleSendMessage()}
          disabled={!inputValue.trim() || isStreaming}
          className="asap-send-btn"
          title="Send message (Enter)"
          aria-label="Send message"
        >
          <Send size={15} />
        </button>
      </div>
    </div>
  );
}

/** Formats simple markdown into clean HTML (bolding, lists, code, paragraphs) */
function FormattedContent({ content }: { content: string }) {
  if (!content) return null;

  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];
  let currentList: string[] = [];

  const flushList = () => {
    if (currentList.length > 0) {
      elements.push(
        <ul key={`ul-${elements.length}`} className="list-disc ml-4 space-y-1 my-1">
          {currentList.map((item, i) => (
            <li key={i}>{formatInline(item)}</li>
          ))}
        </ul>
      );
      currentList = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) {
      flushList();
      continue;
    }

    if (line.startsWith("• ") || line.startsWith("- ") || line.startsWith("* ")) {
      currentList.push(line.slice(2).trim());
      continue;
    }

    if (/^\d+\.\s/.test(line)) {
      flushList();
      elements.push(
        <p key={i} className="my-1 font-semibold text-blue-200">
          {formatInline(line)}
        </p>
      );
      continue;
    }

    flushList();
    elements.push(
      <p key={i} className="my-1">
        {formatInline(line)}
      </p>
    );
  }

  flushList();
  return <>{elements}</>;
}

function formatInline(text: string): React.ReactNode {
  const parts = text.split(/(\*\*.*?\*\*|`.*?`)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    return part;
  });
}
