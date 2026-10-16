"use client";

import { Shell } from "@/components/layout/shell";
import { PipelineView } from "@/components/pipeline/pipeline-view";
import { RequisitionView } from "@/components/requisitions/requisition-view";
import { ComparisonView } from "@/components/comparison/comparison-view";
import { EvaluationView } from "@/components/evaluation/evaluation-view";
import { InterviewView } from "@/components/interview/interview-view";
import { SettingsView } from "@/components/settings/settings-view";

import { useState } from "react";

export default function Home() {
  const [evaluationAutoRun, setEvaluationAutoRun] = useState<boolean>(false);

  return (
    <Shell>
      {({
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
      }) => (
        <div className="relative w-full h-full">
          <div className={activeTab === "pipeline" ? "block" : "hidden"}>
            <PipelineView
              selectedJobId={selectedJobId}
              jobs={jobs}
              onSelectCandidate={(id) => setSelectedCandidateId(id)}
              onSelectJob={(id) => setSelectedJobId(id)}
              onRefreshCandidates={refreshCandidates}
              onOpenEvaluation={(id, targetJobId, autoRun) => {
                setSelectedCandidateId(id);
                const effectiveJobId = targetJobId || selectedJobId || (jobs[0]?.id ?? null);
                if (effectiveJobId) {
                  setSelectedJobId(effectiveJobId);
                }
                setEvaluationAutoRun(Boolean(autoRun));
                setActiveTab("evaluation");
              }}
              onOpenInterview={(id) => {
                setSelectedCandidateId(id);
                setActiveTab("interview");
              }}
              onOpenComparison={(ids) => {
                setComparisonCandidateIds(ids);
                setActiveTab("comparison");
              }}
              onOpenSettings={() => setActiveTab("settings")}
            />
          </div>

          <div className={activeTab === "requisitions" ? "block" : "hidden"}>
            <RequisitionView
              jobs={jobs}
              selectedJobId={selectedJobId}
              onSelectJob={(id) => setSelectedJobId(id)}
              onRefreshJobs={refreshJobs}
            />
          </div>

          <div className={activeTab === "evaluation" ? "block" : "hidden"}>
            <EvaluationView
              candidateId={selectedCandidateId}
              selectedJobId={selectedJobId}
              jobs={jobs}
              autoRun={evaluationAutoRun}
              onResetAutoRun={() => setEvaluationAutoRun(false)}
              onSelectCandidate={(id) => setSelectedCandidateId(id)}
              onSelectJob={(id) => setSelectedJobId(id)}
              onBackToPipeline={() => setActiveTab("pipeline")}
            />
          </div>

          <div className={activeTab === "comparison" ? "block" : "hidden"}>
            <ComparisonView
              candidateIds={comparisonCandidateIds}
              selectedJobId={selectedJobId}
              jobs={jobs}
              onBackToPipeline={() => setActiveTab("pipeline")}
              onOpenEvaluation={(id) => {
                setSelectedCandidateId(id);
                setActiveTab("evaluation");
              }}
              onOpenInterview={(id) => {
                setSelectedCandidateId(id);
                setActiveTab("interview");
              }}
              onSelectCandidateIds={(ids) => setComparisonCandidateIds(ids)}
              onSelectJob={(id) => setSelectedJobId(id)}
            />
          </div>

          <div className={activeTab === "interview" ? "block" : "hidden"}>
            <InterviewView
              candidateId={selectedCandidateId}
              selectedJobId={selectedJobId}
              jobs={jobs}
              onSelectCandidate={(id) => setSelectedCandidateId(id)}
              onSelectJob={(id) => setSelectedJobId(id)}
              onBackToPipeline={() => setActiveTab("pipeline")}
            />
          </div>

          <div className={activeTab === "settings" ? "block" : "hidden"}>
            <SettingsView />
          </div>
        </div>
      )}
    </Shell>
  );
}
