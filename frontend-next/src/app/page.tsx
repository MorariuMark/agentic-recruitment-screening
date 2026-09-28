"use client";

import { Shell } from "@/components/layout/shell";
import { PipelineView } from "@/components/pipeline/pipeline-view";
import { RequisitionView } from "@/components/requisitions/requisition-view";
import { EvaluationView } from "@/components/evaluation/evaluation-view";
import { InterviewView } from "@/components/interview/interview-view";
import { SettingsView } from "@/components/settings/settings-view";

export default function Home() {
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
        refreshJobs,
      }) => {
        switch (activeTab) {
          case "pipeline":
            return (
              <PipelineView
                selectedJobId={selectedJobId}
                jobs={jobs}
                onSelectCandidate={(id) => setSelectedCandidateId(id)}
                onOpenEvaluation={(id) => {
                  setSelectedCandidateId(id);
                  setActiveTab("evaluation");
                }}
                onOpenInterview={(id) => {
                  setSelectedCandidateId(id);
                  setActiveTab("interview");
                }}
              />
            );

          case "requisitions":
            return (
              <RequisitionView
                jobs={jobs}
                selectedJobId={selectedJobId}
                onSelectJob={(id) => setSelectedJobId(id)}
                onRefreshJobs={refreshJobs}
              />
            );

          case "evaluation":
            return (
              <EvaluationView
                candidateId={selectedCandidateId}
                selectedJobId={selectedJobId}
                jobs={jobs}
                onBackToPipeline={() => setActiveTab("pipeline")}
              />
            );

          case "interview":
            return (
              <InterviewView
                candidateId={selectedCandidateId}
                selectedJobId={selectedJobId}
                jobs={jobs}
                onBackToPipeline={() => setActiveTab("pipeline")}
              />
            );

          case "settings":
            return <SettingsView />;

          default:
            return null;
        }
      }}
    </Shell>
  );
}
