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
  }) => React.ReactNode;
}

export function Shell({ children }: ShellProps) {
  const [activeTab, setActiveTab] = useState<NavTab>("pipeline");
  const [jobs, setJobs] = useState<JobDescription[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [comparisonCandidateIds, setComparisonCandidateIds] = useState<string[]>([]);
  const [candidateCount, setCandidateCount] = useState<number>(0);

  const refreshJobs = async () => {
    try {
      const data = await api.getJobs();
      setJobs(data);
      if (data.length > 0 && !selectedJobId) {
        setSelectedJobId(data[0].id);
      }
    } catch (err) {
      console.error("Failed fetching job requisitions:", err);
    }
  };

  const refreshCandidates = async () => {
    try {
      const data = await api.getCandidates();
      setCandidateCount(data.length);
    } catch (err) {
      console.error("Failed fetching candidates:", err);
    }
  };

  useEffect(() => {
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
      />

      {/* Main Content Area */}
      <div className="flex flex-col flex-1 min-w-0 h-full overflow-hidden">
        <Header
          jobs={jobs}
          selectedJobId={selectedJobId}
          onSelectJob={setSelectedJobId}
        />

        <main className="flex-1 overflow-y-auto p-6 bg-slate-950">
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
          })}
        </main>
      </div>
    </div>
  );
}
