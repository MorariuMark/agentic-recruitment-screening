"use client";

import {
  Briefcase,
  FileCheck2,
  MessageSquareCode,
  RotateCcw,
  Scale,
  Settings2,
  Users2,
} from "lucide-react";
import { ModelSelector } from "./model-selector";

export type NavTab = "pipeline" | "requisitions" | "comparison" | "evaluation" | "interview" | "settings";

interface SidebarProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  candidateCount?: number;
  jobCount?: number;
  onResetSession?: () => void;
  isOpen?: boolean;
  onClose?: () => void;
}

export function Sidebar({
  activeTab,
  onTabChange,
  candidateCount = 0,
  jobCount = 0,
  onResetSession,
  isOpen = true,
}: SidebarProps) {
  if (!isOpen) {
    return null;
  }

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
      id: "comparison" as NavTab,
      label: "Comparison Matrix",
      icon: Scale,
      description: "Side-by-side benchmarking",
    },
    {
      id: "interview" as NavTab,
      label: "Interview Studio",
      icon: MessageSquareCode,
      description: "Tailored STAR guides",
    },
  ];

  return (
    <aside className="w-72 border-r border-slate-800 bg-slate-950 flex flex-col justify-between shrink-0 select-none animate-in slide-in-from-left duration-200">
      <div className="p-3 pt-3 space-y-3">
        {/* Model Selector at Top of Sidebar */}
        <div className="pb-1 border-b border-slate-900/80">
          <ModelSelector
            onNavigateToSettings={() => onTabChange("settings")}
            align="left"
            className="w-full"
          />
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
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-left transition-all cursor-pointer ${
                  isActive
                    ? "bg-blue-600/10 border border-blue-500/30 text-blue-700 dark:text-white font-semibold shadow-sm"
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

      {/* Bottom Action Bar: Settings & Reset Session */}
      <div className="p-3 border-t border-slate-900">
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => onTabChange("settings")}
            className={`flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer border ${
              activeTab === "settings"
                ? "bg-blue-600/15 border-blue-500/40 text-blue-700 dark:text-blue-300 font-semibold shadow-sm"
                : "bg-slate-900/60 hover:bg-slate-900 text-slate-400 hover:text-slate-200 border-slate-800/80"
            }`}
            title="Model & Agent Configuration"
          >
            <Settings2 className="w-3.5 h-3.5 shrink-0" />
            <span>Settings</span>
          </button>

          <button
            onClick={() => onResetSession && onResetSession()}
            className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer border bg-slate-900/60 hover:bg-rose-950/30 hover:border-rose-500/40 text-slate-400 hover:text-rose-300 border-slate-800/80"
            title="Reset current session and workspace to fresh state"
          >
            <RotateCcw className="w-3.5 h-3.5 shrink-0" />
            <span>Reset</span>
          </button>
        </div>
      </div>
    </aside>
  );
}
