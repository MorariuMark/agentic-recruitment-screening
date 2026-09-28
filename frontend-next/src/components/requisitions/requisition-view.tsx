"use client";

import { useState, useEffect } from "react";
import { JobDescription, JobRequirement, RequirementCategory } from "@/types";
import { api } from "@/lib/api";
import {
  Briefcase,
  Check,
  CheckCircle2,
  Globe,
  Loader2,
  Minus,
  Plus,
  Save,
  Sliders,
  Sparkles,
  Star,
  Trash2,
} from "lucide-react";

interface RequisitionViewProps {
  jobs: JobDescription[];
  selectedJobId: string | null;
  onSelectJob: (id: string) => void;
  onRefreshJobs: () => Promise<void>;
}

export function RequisitionView({
  jobs,
  selectedJobId,
  onSelectJob,
  onRefreshJobs,
}: RequisitionViewProps) {
  const [activeTab, setActiveTab] = useState<"catalog" | "import_text" | "import_url">("catalog");
  const [rawText, setRawText] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [isParsing, setIsParsing] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);

  // Calibration state for current active job
  const activeJob = jobs.find((j) => j.id === selectedJobId) || jobs[0];
  const [editableReqs, setEditableReqs] = useState<JobRequirement[]>([]);
  const [isSavingCriteria, setIsSavingCriteria] = useState(false);
  const [saveCriteriaSuccess, setSaveCriteriaSuccess] = useState(false);

  // New criterion state
  const [showAddForm, setShowAddForm] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newCategory, setNewCategory] = useState<RequirementCategory>("must_have");
  const [newWeight, setNewWeight] = useState<number>(1.0);
  const [newMinExp, setNewMinExp] = useState<number | undefined>(undefined);
  const [newDescription, setNewDescription] = useState("");

  useEffect(() => {
    if (activeJob) {
      setEditableReqs(activeJob.requirements || []);
    }
  }, [activeJob?.id, activeJob?.requirements]);

  const handleParseText = async () => {
    if (!rawText.trim()) return;
    try {
      setIsParsing(true);
      setParseError(null);
      const res = await api.parseJobText(rawText);
      await onRefreshJobs();
      onSelectJob(res.job_description.id);
      setActiveTab("catalog");
      setRawText("");
    } catch (err: any) {
      setParseError(err.message || "Failed to parse job text");
    } finally {
      setIsParsing(false);
    }
  };

  const handleParseUrl = async () => {
    if (!jobUrl.trim()) return;
    try {
      setIsParsing(true);
      setParseError(null);
      const res = await api.parseJobUrl(jobUrl);
      await onRefreshJobs();
      onSelectJob(res.job_description.id);
      setActiveTab("catalog");
      setJobUrl("");
    } catch (err: any) {
      setParseError(err.message || "Failed to extract job from URL");
    } finally {
      setIsParsing(false);
    }
  };

  const toggleCategory = (reqId: string) => {
    setEditableReqs((prev) =>
      prev.map((r) => {
        if (r.id === reqId) {
          const nextCat: RequirementCategory =
            r.category === "must_have" ? "nice_to_have" : "must_have";
          return { ...r, category: nextCat };
        }
        return r;
      })
    );
  };

  const adjustWeight = (reqId: string, delta: number) => {
    setEditableReqs((prev) =>
      prev.map((r) => {
        if (r.id === reqId) {
          const newW = Math.max(0.5, Math.min(3.0, Math.round((r.weight + delta) * 10) / 10));
          return { ...r, weight: newW };
        }
        return r;
      })
    );
  };

  const deleteRequirement = (reqId: string) => {
    setEditableReqs((prev) => prev.filter((r) => r.id !== reqId));
  };

  const handleAddRequirement = () => {
    if (!newTitle.trim()) return;
    const newReq: JobRequirement = {
      id: `req_${Date.now()}`,
      title: newTitle.trim(),
      category: newCategory,
      weight: newWeight,
      minimum_years_experience: newMinExp,
      description: newDescription.trim() || newTitle.trim(),
    };
    setEditableReqs((prev) => [...prev, newReq]);
    setNewTitle("");
    setNewDescription("");
    setNewMinExp(undefined);
    setShowAddForm(false);
  };

  const handleSaveCriteria = async () => {
    if (!activeJob) return;
    try {
      setIsSavingCriteria(true);
      await api.updateJobRequirements(activeJob.id, editableReqs);
      await onRefreshJobs();
      setSaveCriteriaSuccess(true);
      setTimeout(() => setSaveCriteriaSuccess(false), 3000);
    } catch (err: any) {
      alert(`Failed to save criteria: ${err.message}`);
    } finally {
      setIsSavingCriteria(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & Modes */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            <span>Requisition & Criteria Studio</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Extract structured role requirements, calibrate criteria weights, and mandate must-haves.
          </p>
        </div>

        <div className="flex items-center gap-2 bg-slate-900 p-1 rounded-lg border border-slate-800 text-xs">
          <button
            onClick={() => setActiveTab("catalog")}
            className={`px-3 py-1.5 rounded-md transition-colors cursor-pointer ${
              activeTab === "catalog"
                ? "bg-slate-800 text-white font-medium"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Active Requisitions ({jobs.length})
          </button>
          <button
            onClick={() => setActiveTab("import_text")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-colors cursor-pointer ${
              activeTab === "import_text"
                ? "bg-slate-800 text-white font-medium"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-blue-400" />
            <span>Parse Raw Text</span>
          </button>
          <button
            onClick={() => setActiveTab("import_url")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-colors cursor-pointer ${
              activeTab === "import_url"
                ? "bg-slate-800 text-white font-medium"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Globe className="w-3.5 h-3.5 text-purple-400" />
            <span>Import from URL</span>
          </button>
        </div>
      </div>

      {/* Parse Error Display */}
      {parseError && (
        <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-500/30 text-rose-300 text-xs">
          {parseError}
        </div>
      )}

      {/* TAB: Parse Raw Text */}
      {activeTab === "import_text" && (
        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/40 space-y-4 max-w-3xl">
          <div className="text-sm font-semibold text-slate-200">
            Paste Job Description Text
          </div>
          <p className="text-xs text-slate-400">
            The Agent will extract job title, seniority, and break down requirements into atomic Must-Haves and Nice-to-Haves.
          </p>
          <textarea
            rows={8}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder="Paste role responsibilities, required qualifications, and technologies here..."
            className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs text-slate-200 focus:outline-none focus:border-blue-500 font-mono leading-relaxed"
          />
          <button
            onClick={handleParseText}
            disabled={isParsing || !rawText.trim()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition-all disabled:opacity-50 cursor-pointer"
          >
            {isParsing ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Sparkles className="w-3.5 h-3.5" />
            )}
            <span>Analyze & Extract Requisition</span>
          </button>
        </div>
      )}

      {/* TAB: Import from URL */}
      {activeTab === "import_url" && (
        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/40 space-y-4 max-w-3xl">
          <div className="text-sm font-semibold text-slate-200">
            Import Job Posting from URL
          </div>
          <p className="text-xs text-slate-400">
            Provide a public job listing URL (e.g. Greenhouse, Lever, Workday, LinkedIn).
          </p>
          <div className="flex gap-2">
            <input
              type="url"
              value={jobUrl}
              onChange={(e) => setJobUrl(e.target.value)}
              placeholder="https://company.greenhouse.io/jobs/123456"
              className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500 font-mono"
            />
            <button
              onClick={handleParseUrl}
              disabled={isParsing || !jobUrl.trim()}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 active:scale-[0.98] text-white text-xs font-semibold shadow-lg shadow-purple-600/20 transition-all disabled:opacity-50 cursor-pointer"
            >
              {isParsing ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Globe className="w-3.5 h-3.5" />
              )}
              <span>Scrape & Extract</span>
            </button>
          </div>
        </div>
      )}

      {/* TAB: Active Requisitions & Criteria Calibration */}
      {activeTab === "catalog" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Requisition Sidebar Selector */}
          <div className="space-y-2">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 px-1">
              Select Position ({jobs.length})
            </div>
            <div className="space-y-1.5 max-h-[600px] overflow-y-auto">
              {jobs.map((job) => (
                <button
                  key={job.id}
                  onClick={() => onSelectJob(job.id)}
                  className={`w-full text-left p-3 rounded-xl border transition-all cursor-pointer ${
                    activeJob?.id === job.id
                      ? "bg-slate-900 border-blue-500/50 shadow-md shadow-blue-500/5"
                      : "bg-slate-950 border-slate-800/80 hover:border-slate-700"
                  }`}
                >
                  <div className="font-semibold text-xs text-white truncate">
                    {job.title}
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-slate-500 mt-1">
                    <span>{job.seniority_level || "Standard"}</span>
                    <span>•</span>
                    <span>{job.department || "General"}</span>
                    <span>•</span>
                    <span>{job.requirements?.length || 0} Criteria</span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Criteria Weighting & Calibration Studio */}
          <div className="lg:col-span-2 space-y-4">
            {activeJob ? (
              <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/30 space-y-5">
                <div className="flex items-start justify-between">
                  <div>
                    <h2 className="text-base font-bold text-white">
                      {activeJob.title}
                    </h2>
                    <div className="flex items-center gap-2 text-xs text-slate-400 mt-1 font-mono">
                      <span>Dept: {activeJob.department || "Engineering"}</span>
                      <span>•</span>
                      <span>Seniority: {activeJob.seniority_level || "Mid-Senior"}</span>
                      <span>•</span>
                      <span>Location: {activeJob.location || "Remote"}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleSaveCriteria}
                      disabled={isSavingCriteria}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-xs font-semibold shadow-md shadow-blue-600/20 transition-all cursor-pointer disabled:opacity-50"
                    >
                      {isSavingCriteria ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Save className="w-3.5 h-3.5" />
                      )}
                      <span>Save Criteria</span>
                    </button>
                  </div>
                </div>

                {saveCriteriaSuccess && (
                  <div className="p-2 rounded-lg bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-xs flex items-center gap-2 animate-in fade-in">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>Requisition criteria calibrated and saved to database!</span>
                  </div>
                )}

                <div className="h-px bg-slate-800" />

                {/* Requirements List */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
                    <div className="flex items-center gap-2">
                      <span>Active Criteria ({editableReqs.length})</span>
                      <span className="text-[10px] text-slate-500 font-normal">
                        Click category pill to toggle Must-Have vs Nice-to-Have
                      </span>
                    </div>

                    <button
                      onClick={() => setShowAddForm(!showAddForm)}
                      className="flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300 transition-colors cursor-pointer"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>{showAddForm ? "Cancel" : "Add Criterion"}</span>
                    </button>
                  </div>

                  {/* Add Criterion Form */}
                  {showAddForm && (
                    <div className="p-4 rounded-xl border border-blue-500/30 bg-slate-950 space-y-3 animate-in fade-in">
                      <div className="text-xs font-semibold text-slate-200">
                        Add New Requirement Criterion
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                          <label className="text-[10px] font-medium text-slate-400">
                            Criterion Title *
                          </label>
                          <input
                            type="text"
                            value={newTitle}
                            onChange={(e) => setNewTitle(e.target.value)}
                            placeholder="e.g. Distributed Systems Architecture"
                            className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 mt-1"
                          />
                        </div>
                        <div>
                          <label className="text-[10px] font-medium text-slate-400">
                            Min Experience (Years)
                          </label>
                          <input
                            type="number"
                            value={newMinExp ?? ""}
                            onChange={(e) => setNewMinExp(e.target.value ? Number(e.target.value) : undefined)}
                            placeholder="e.g. 4"
                            className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 mt-1"
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                          <label className="text-[10px] font-medium text-slate-400">
                            Category Gate
                          </label>
                          <select
                            value={newCategory}
                            onChange={(e) => setNewCategory(e.target.value as RequirementCategory)}
                            className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 mt-1"
                          >
                            <option value="must_have">Must Have (Hard Gate)</option>
                            <option value="nice_to_have">Nice To Have (Bonus Score)</option>
                          </select>
                        </div>
                        <div>
                          <label className="text-[10px] font-medium text-slate-400">
                            Weight Multiplier ({newWeight}x)
                          </label>
                          <input
                            type="range"
                            min="0.5"
                            max="2.5"
                            step="0.25"
                            value={newWeight}
                            onChange={(e) => setNewWeight(Number(e.target.value))}
                            className="w-full mt-2"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="text-[10px] font-medium text-slate-400">
                          Detailed Description / Rubric
                        </label>
                        <textarea
                          rows={2}
                          value={newDescription}
                          onChange={(e) => setNewDescription(e.target.value)}
                          placeholder="Specific technologies, certifications, or competencies required..."
                          className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 mt-1"
                        />
                      </div>

                      <button
                        onClick={handleAddRequirement}
                        disabled={!newTitle.trim()}
                        className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold disabled:opacity-50 cursor-pointer"
                      >
                        Append to Criteria List
                      </button>
                    </div>
                  )}

                  {/* Requirements List */}
                  <div className="space-y-2">
                    {editableReqs.map((req) => (
                      <div
                        key={req.id}
                        className="p-3.5 rounded-lg bg-slate-950 border border-slate-800/80 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 hover:border-slate-700 transition-colors"
                      >
                        <div className="space-y-1 flex-1">
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => toggleCategory(req.id)}
                              className={`text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded cursor-pointer transition-transform hover:scale-105 ${
                                req.category === "must_have"
                                  ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                                  : "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                              }`}
                              title="Click to toggle category"
                            >
                              {req.category === "must_have" ? "Must Have" : "Nice To Have"}
                            </button>
                            <span className="font-semibold text-xs text-slate-200">
                              {req.title}
                            </span>
                            {req.minimum_years_experience && (
                              <span className="text-[10px] text-slate-500 font-mono">
                                (≥ {req.minimum_years_experience} yrs)
                              </span>
                            )}
                          </div>
                          <p className="text-[11px] text-slate-400 leading-snug">
                            {req.description}
                          </p>
                        </div>

                        {/* Interactive Weight Controls & Delete */}
                        <div className="flex items-center gap-2 shrink-0">
                          <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-0.5">
                            <button
                              onClick={() => adjustWeight(req.id, -0.25)}
                              className="p-1 hover:bg-slate-800 text-slate-400 hover:text-white rounded cursor-pointer"
                              title="Decrease weight"
                            >
                              <Minus className="w-3 h-3" />
                            </button>
                            <span className="px-2 text-xs font-bold font-mono text-slate-200">
                              {req.weight}x
                            </span>
                            <button
                              onClick={() => adjustWeight(req.id, 0.25)}
                              className="p-1 hover:bg-slate-800 text-slate-400 hover:text-white rounded cursor-pointer"
                              title="Increase weight"
                            >
                              <Plus className="w-3 h-3" />
                            </button>
                          </div>

                          <button
                            onClick={() => deleteRequirement(req.id)}
                            className="p-1.5 rounded hover:bg-rose-950/40 text-slate-500 hover:text-rose-400 transition-colors cursor-pointer"
                            title="Delete criterion"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="p-12 text-center text-slate-500 text-xs">
                No active requisition selected. Select or parse one above.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
