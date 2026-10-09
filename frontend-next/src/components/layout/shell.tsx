"use client";

import { useState, useEffect } from "react";
import { Header } from "./header";
import { Sidebar, NavTab } from "./sidebar";
import { JobDescription } from "@/types";
import { api } from "@/lib/api";

interface ShellProps {
  children: (props: {
    activeTab: NavTab;
    setActiveTab: (tab: NavTab) => void;
    jobs: JobDescription[];
    selectedJobId: string | null;
    setSelectedJobId: (id: string | null) => void;
    selectedCandidateId: string | null;
    setSelectedCandidateId: (id: string | null) => void;
    comparisonCandidateIds: string[];
    setComparisonCandidateIds: (ids: string[]) => void;
    refreshJobs: () => Promise<void>;
    refreshCandidates: () => Promise<void>;
    resetSession: () => void;
  }) => React.ReactNode;
}

export function Shell({ children }: ShellProps) {
  const [activeTab, setActiveTabState] = useState<NavTab>("pipeline");
  const [jobs, setJobs] = useState<JobDescription[]>([]);
  const [selectedJobId, setSelectedJobIdState] = useState<string | null>(null);
  const [selectedCandidateId, setSelectedCandidateIdState] = useState<string | null>(null);
  const [comparisonCandidateIds, setComparisonCandidateIdsState] = useState<string[]>([]);
  const [candidateCount, setCandidateCount] = useState<number>(0);
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(true);

  const toggleSidebar = () => {
    setIsSidebarOpen((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("atos_sidebar_open", String(next));
      } catch (err) {
        console.warn("Failed saving sidebar state:", err);
      }
      return next;
    });
  };

  const setActiveTab = (tab: NavTab) => {
    setActiveTabState(tab);
    try {
      localStorage.setItem("atos_session_active_tab", tab);
    } catch (err) {
      console.warn("Failed saving active tab to session:", err);
    }
  };

  const setSelectedJobId = (id: string | null) => {
    setSelectedJobIdState(id);
    try {
      if (id) {
        localStorage.setItem("atos_session_selected_job_id", id);
      } else {
        localStorage.removeItem("atos_session_selected_job_id");
      }
    } catch (err) {
      console.warn("Failed saving selected job to session:", err);
    }
  };

  const setSelectedCandidateId = (id: string | null) => {
    setSelectedCandidateIdState(id);
    try {
      if (id) {
        localStorage.setItem("atos_session_selected_candidate_id", id);
      } else {
        localStorage.removeItem("atos_session_selected_candidate_id");
      }
    } catch (err) {
      console.warn("Failed saving selected candidate to session:", err);
    }
  };

  const setComparisonCandidateIds = (ids: string[]) => {
    setComparisonCandidateIdsState(ids);
    try {
      localStorage.setItem("atos_session_comparison_ids", JSON.stringify(ids));
    } catch (err) {
      console.warn("Failed saving comparison IDs to session:", err);
    }
  };

  const resetSession = () => {
    try {
      localStorage.removeItem("atos_session_active_tab");
      localStorage.removeItem("atos_session_selected_job_id");
      localStorage.removeItem("atos_session_selected_candidate_id");
      localStorage.removeItem("atos_session_comparison_ids");
      localStorage.removeItem("atos_pipeline_single_extraction");
      localStorage.removeItem("atos_pipeline_active_section");
    } catch (err) {
      console.warn("Failed resetting session in storage:", err);
    }

    setActiveTabState("pipeline");
    setSelectedCandidateIdState(null);
    setComparisonCandidateIdsState([]);
    if (jobs.length > 0) {
      setSelectedJobIdState(jobs[0].id);
    } else {
      setSelectedJobIdState(null);
    }

    // Broadcast reset event to all views so they immediately reset local states
    window.dispatchEvent(new CustomEvent("atos:reset-session"));
  };

  const refreshJobs = async () => {
    try {
      const data = await api.getJobs();
      const jobList = Array.isArray(data) ? data : [];
      setJobs(jobList);

      const savedJobId = localStorage.getItem("atos_session_selected_job_id");
      if (savedJobId && jobList.some((j) => j.id === savedJobId)) {
        setSelectedJobIdState(savedJobId);
      } else if (jobList.length > 0 && !selectedJobId) {
        setSelectedJobIdState(jobList[0].id);
      }
    } catch (err) {
      console.error("Failed fetching job requisitions:", err);
    }
  };

  const refreshCandidates = async () => {
    try {
      const data = await api.getCandidates();
      setCandidateCount(Array.isArray(data) ? data.length : 0);
    } catch (err) {
      console.error("Failed fetching candidates:", err);
    }
  };

  useEffect(() => {
    // Restore persistent session from localStorage on mount/reopen
    try {
      const savedSidebar = localStorage.getItem("atos_sidebar_open");
      if (savedSidebar !== null) {
        setIsSidebarOpen(savedSidebar === "true");
      }

      const savedTab = localStorage.getItem("atos_session_active_tab") as NavTab | null;
      if (
        savedTab &&
        ["pipeline", "requisitions", "comparison", "evaluation", "interview", "settings"].includes(savedTab)
      ) {
        setActiveTabState(savedTab);
      }

      const savedCandidateId = localStorage.getItem("atos_session_selected_candidate_id");
      if (savedCandidateId) {
        setSelectedCandidateIdState(savedCandidateId);
      } else {
        const savedExtraction = localStorage.getItem("atos_pipeline_single_extraction");
        if (savedExtraction) {
          const parsed = JSON.parse(savedExtraction);
          if (parsed?.candidate_id) {
            setSelectedCandidateIdState(parsed.candidate_id);
          }
        }
      }

      const savedComparison = localStorage.getItem("atos_session_comparison_ids");
      if (savedComparison) {
        setComparisonCandidateIdsState(JSON.parse(savedComparison));
      }
    } catch (err) {
      console.warn("Failed restoring session parameters:", err);
    }

    refreshJobs();
    refreshCandidates();
  }, []);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-950 text-slate-100">
      {/* Sidebar Navigation */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        candidateCount={candidateCount}
        jobCount={jobs.length}
        onResetSession={resetSession}
        isOpen={isSidebarOpen}
      />

      {/* Main Content Area */}
      <div className="flex flex-col flex-1 min-w-0 h-full overflow-hidden">
        <Header
          jobs={jobs}
          selectedJobId={selectedJobId}
          onSelectJob={setSelectedJobId}
          onOpenUploadModal={() => setActiveTab("pipeline")}
          onNavigateToSettings={() => setActiveTab("settings")}
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={toggleSidebar}
        />

        <main className="flex-1 overflow-y-auto p-4 sm:p-6 2xl:p-8 bg-slate-950">
          {children({
            activeTab,
            setActiveTab,
            jobs,
            selectedJobId,
            setSelectedJobId,
            selectedCandidateId,
            setSelectedCandidateId,
            comparisonCandidateIds,
            setComparisonCandidateIds,
            refreshJobs,
            refreshCandidates,
            resetSession,
          })}
        </main>
      </div>
    </div>
  );
}
