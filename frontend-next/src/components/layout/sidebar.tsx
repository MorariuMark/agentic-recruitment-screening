"use client";

import {
  Briefcase,
  FileCheck2,
  FileText,
  MessageSquareCode,
  Settings2,
  ShieldAlert,
  Users2,
} from "lucide-react";

export type NavTab = "pipeline" | "requisitions" | "evaluation" | "interview" | "settings";

interface SidebarProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  candidateCount?: number;
  jobCount?: number;
}

export function Sidebar({
  activeTab,
  onTabChange,
  candidateCount = 0,
  jobCount = 0,
}: SidebarProps) {
  const navItems = [
    {
      id: "pipeline" as NavTab,
      label: "Candidate Pipeline",
      icon: Users2,
      badge: candidateCount > 0 ? candidateCount : undefined,
      description: "Batch screening & ranking",
    },
    {
      id: "requisitions" as NavTab,
      label: "Requisition Studio",
      icon: Briefcase,
      badge: jobCount > 0 ? jobCount : undefined,
      description: "Job descriptions & criteria",
    },
    {
      id: "evaluation" as NavTab,
      label: "Verification & HITL",
      icon: FileCheck2,
      description: "Citations & human gate",
    },
    {
      id: "interview" as NavTab,
      label: "Interview Studio",
      icon: MessageSquareCode,
      description: "Tailored STAR guides",
    },
    {
      id: "settings" as NavTab,
      label: "Model & Agent Config",
      icon: Settings2,
      description: "LLM providers & latency",
    },
  ];

  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-950 flex flex-col justify-between shrink-0 select-none">
      <div className="p-3 space-y-4">
        {/* Brand Header */}
        <div className="px-3 py-2 flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center font-bold text-white shadow-lg shadow-blue-500/20">
            A
          </div>
          <div>
            <div className="text-sm font-bold tracking-tight text-white flex items-center gap-1.5">
              <span>Antigravity</span>
              <span className="text-[10px] uppercase font-mono px-1 py-0.2 bg-blue-500/20 text-blue-400 rounded">
                B2B
              </span>
            </div>
            <div className="text-[11px] text-slate-500">Autonomous Talent AI</div>
          </div>
        </div>

        {/* Navigation list */}
        <nav className="space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onTabChange(item.id)}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-left transition-all ${
                  isActive
                    ? "bg-blue-600/10 border border-blue-500/30 text-white font-medium shadow-sm"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent"
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon
                    className={`w-4 h-4 shrink-0 ${
                      isActive ? "text-blue-400" : "text-slate-500"
                    }`}
                  />
                  <div>
                    <div className="text-xs">{item.label}</div>
                    <div className="text-[10px] text-slate-500 leading-tight">
                      {item.description}
                    </div>
                  </div>
                </div>

                {item.badge !== undefined && (
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${
                      isActive
                        ? "bg-blue-500/20 text-blue-300"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Bottom Compliance & Security Badge */}
      <div className="p-3 border-t border-slate-900">
        <div className="px-3 py-2.5 rounded-lg bg-slate-900/60 border border-slate-800/80 flex items-start gap-2.5">
          <ShieldAlert className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
          <div>
            <div className="text-[11px] font-medium text-slate-300">
              EU AI Act Compliant
            </div>
            <div className="text-[10px] text-slate-500 leading-tight mt-0.5">
              PII Redacted • Asymmetric RAG • Deterministic Verifier Gate
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
