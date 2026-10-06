"use client";

import { useState, useEffect } from "react";
import { JobDescription, JobRequirement, RequirementCategory } from "@/types";
import { api } from "@/lib/api";
import {
  Briefcase,
  Check,
  CheckCircle2,
  ChevronRight,
  Globe,
  Layers,
  Loader2,
  Minus,
  Plus,
  Save,
  Search,
  Sliders,
  Sparkles,
  Star,
  Trash2,
} from "lucide-react";
import { LiveProcessTimer, DurationBadge, useProcessTimer } from "@/components/ui/live-process-timer";

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
  const jdTimer = useProcessTimer();
  const [lastJdDuration, setLastJdDuration] = useState<number | null>(null);

  // Calibration state for current active job
  const activeJob = jobs.find((j) => j.id === selectedJobId) || jobs[0];
  const [editableReqs, setEditableReqs] = useState<JobRequirement[]>([]);
  const [isSavingCriteria, setIsSavingCriteria] = useState(false);
  const [saveCriteriaSuccess, setSaveCriteriaSuccess] = useState(false);
  const [jobSearchQuery, setJobSearchQuery] = useState("");

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

    const controller = jdTimer.startTimer();
    try {
      setIsParsing(true);
      setParseError(null);
      const res = await api.parseJobText(rawText, controller.signal);
      const duration = jdTimer.stopTimer(true);
      if (duration !== null) {
        setLastJdDuration(duration);
      }
      await onRefreshJobs();
      onSelectJob(res.job_description.id);
      setActiveTab("catalog");
      setRawText("");
    } catch (err: any) {
      if (err.name === "AbortError" || controller.signal.aborted) {
        jdTimer.stopTimer(false);
        setParseError("Job text parsing was cancelled by user.");
        return;
      }
      jdTimer.stopTimer(false);
      setParseError(err.message || "Failed to parse job description text");
    } finally {
      setIsParsing(false);
    }
  };

  const handleParseUrl = async () => {
    if (!jobUrl.trim()) return;

    const controller = jdTimer.startTimer();
    try {
      setIsParsing(true);
      setParseError(null);
      const res = await api.parseJobUrl(jobUrl, controller.signal);
      const duration = jdTimer.stopTimer(true);
      if (duration !== null) {
        setLastJdDuration(duration);
      }
      await onRefreshJobs();
      onSelectJob(res.job_description.id);
      setActiveTab("catalog");
      setJobUrl("");
    } catch (err: any) {
      if (err.name === "AbortError" || controller.signal.aborted) {
        jdTimer.stopTimer(false);
        setParseError("Job URL extraction was cancelled by user.");
        return;
      }
      jdTimer.stopTimer(false);
      setParseError(err.message || "Failed to extract job posting from URL");
    } finally {
      setIsParsing(false);
    }
  };

  const handleCancelJdParsing = () => {
    jdTimer.cancelTimer();
    setIsParsing(false);
    setParseError("Job parsing was cancelled immediately.");
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

  const mustHaveCount = editableReqs.filter((r) => r.category === "must_have").length;
  const niceToHaveCount = editableReqs.filter((r) => r.category === "nice_to_have").length;

  const filteredJobs = jobs.filter((j) => {
    if (!jobSearchQuery.trim()) return true;
    const q = jobSearchQuery.toLowerCase();
    const title = (j.title || "").toLowerCase();
    const dept = (j.department || "").toLowerCase();
    const sen = (j.seniority_level || "").toLowerCase();
    return title.includes(q) || dept.includes(q) || sen.includes(q);
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* ========================================================================= */}
      {/* 1. TOP HEADER & MODE SWITCHER                                             */}
      {/* ========================================================================= */}
      <div className="p-4 rounded-2xl border border-slate-800 bg-slate-900/80 backdrop-blur-md shadow-lg flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-base md:text-lg font-bold text-white tracking-tight flex items-center gap-2">
            <span>Requisition &amp; Criteria Studio</span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-normal">
              {jobs.length} Positions Active
            </span>
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Extract structured role requirements, calibrate criteria weights, and mandate hard Must-Haves.
          </p>
        </div>

        <div className="flex items-center gap-1.5 bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs shadow-inner">
          <button
            onClick={() => setActiveTab("catalog")}
            className={`px-3 py-1.5 rounded-lg font-medium transition-all cursor-pointer ${
              activeTab === "catalog"
                ? "bg-blue-600 text-white font-semibold shadow-md"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Active Catalog ({jobs.length})
          </button>
          <button
            onClick={() => setActiveTab("import_text")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition-all cursor-pointer ${
              activeTab === "import_text"
                ? "bg-blue-600 text-white font-semibold shadow-md"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-blue-400" />
            <span>Parse Job Text</span>
          </button>
          <button
            onClick={() => setActiveTab("import_url")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition-all cursor-pointer ${
              activeTab === "import_url"
                ? "bg-blue-600 text-white font-semibold shadow-md"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Globe className="w-3.5 h-3.5 text-purple-400" />
            <span>Import URL</span>
          </button>
        </div>
      </div>

      {/* Parse Error Alert */}
      {parseError && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-500/30 text-rose-300 text-xs">
          {parseError}
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. TAB: PARSE RAW TEXT                                                    */}
      {/* ========================================================================= */}
      {activeTab === "import_text" && (
        <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/50 space-y-4 max-w-4xl shadow-xl">
          <div className="space-y-1">
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-blue-400" />
              <span>Paste Job Description Text</span>
            </h2>
            <p className="text-xs text-slate-400">
              The Agent will extract role title, department, seniority level, and break down requirements into atomic Must-Haves and Nice-to-Haves.
            </p>
          </div>

          <textarea
            rows={10}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder="Paste role responsibilities, required qualifications, years of experience, and technologies here..."
            className="w-full bg-slate-950 border border-slate-800 rounded-xl p-4 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 font-sans leading-relaxed"
          />

          {isParsing && (
            <LiveProcessTimer
              isRunning={jdTimer.isRunning}
              elapsedSeconds={jdTimer.elapsedSeconds}
              onCancel={handleCancelJdParsing}
              label="Analyzing & Decomposing Job Description with AI..."
              estimateText="AI parsing active (typically 5 - 15s)"
              cancelLabel="Cancel Parsing"
            />
          )}

          <div className="flex items-center justify-between pt-2">
            <span className="text-xs text-slate-500">
              {rawText.length > 0 ? `${rawText.length} characters entered` : "Supports plain text or markdown"}
            </span>

            <button
              onClick={handleParseText}
              disabled={isParsing || !rawText.trim()}
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-xs font-semibold shadow-lg shadow-blue-600/30 transition-all disabled:opacity-50 cursor-pointer"
            >
              {isParsing ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Sparkles className="w-4 h-4" />
              )}
              <span>Analyze &amp; Extract Requisition Criteria</span>
            </button>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 3. TAB: IMPORT FROM URL                                                   */}
      {/* ========================================================================= */}
      {activeTab === "import_url" && (
        <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/50 space-y-4 max-w-4xl shadow-xl">
          <div className="space-y-1">
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Globe className="w-4 h-4 text-purple-400" />
              <span>Import Job Posting from URL</span>
            </h2>
            <p className="text-xs text-slate-400">
              Provide a public job listing URL (e.g. Greenhouse, Lever, Workday, LinkedIn, or company careers page).
            </p>
          </div>

          {isParsing && (
            <LiveProcessTimer
              isRunning={jdTimer.isRunning}
              elapsedSeconds={jdTimer.elapsedSeconds}
              onCancel={handleCancelJdParsing}
              label="Scraping & Extracting Job Requisition with AI..."
              estimateText="Web scraping & AI parsing active (typically 8 - 20s)"
              cancelLabel="Cancel Parsing"
            />
          )}

          <div className="flex gap-2">
            <input
              type="url"
              value={jobUrl}
              onChange={(e) => setJobUrl(e.target.value)}
              placeholder="https://company.greenhouse.io/jobs/123456"
              className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-purple-500"
            />
            <button
              onClick={handleParseUrl}
              disabled={isParsing || !jobUrl.trim()}
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 active:scale-[0.98] text-white text-xs font-semibold shadow-lg shadow-purple-600/30 transition-all disabled:opacity-50 cursor-pointer"
            >
              {isParsing ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Globe className="w-4 h-4" />
              )}
              <span>Scrape &amp; Extract</span>
            </button>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 4. TAB: CATALOG & CRITERIA CALIBRATION STUDIO                             */}
      {/* ========================================================================= */}
      {activeTab === "catalog" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column: Requisition Directory */}
          <div className="lg:col-span-4 space-y-3">
            <div className="relative">
              <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={jobSearchQuery}
                onChange={(e) => setJobSearchQuery(e.target.value)}
                placeholder="Search requisitions..."
                className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
            </div>

            <div className="space-y-2 max-h-[640px] overflow-y-auto pr-1">
              {filteredJobs.map((job) => {
                const isSelected = activeJob?.id === job.id;
                return (
                  <button
                    key={job.id}
                    onClick={() => onSelectJob(job.id)}
                    className={`w-full text-left p-4 rounded-2xl border transition-all cursor-pointer space-y-2 ${
                      isSelected
                        ? "bg-slate-900/90 border-blue-500/60 shadow-lg shadow-blue-500/10 ring-1 ring-blue-500/40"
                        : "bg-slate-950/60 border-slate-800 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="font-bold text-sm text-white truncate">
                        {job.title}
                      </div>
                      <ChevronRight
                        className={`w-4 h-4 shrink-0 transition-transform ${
                          isSelected ? "text-blue-400 rotate-90" : "text-slate-600"
                        }`}
                      />
                    </div>

                    <div className="flex items-center gap-2 text-xs text-slate-400">
                      <span>{job.department || "General"}</span>
                      <span>•</span>
                      <span>{job.seniority_level || "Standard"}</span>
                    </div>

                    <div className="flex items-center gap-2 pt-1 border-t border-slate-800/60 text-[11px] text-slate-500">
                      <span className="font-mono text-slate-400 font-semibold">
                        {job.requirements?.length || 0} Criteria
                      </span>
                      <span>•</span>
                      <span>{job.location || "Remote"}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right Column: Criteria Calibration Studio */}
          <div className="lg:col-span-8 space-y-4">
            {activeJob ? (
              <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/50 backdrop-blur-md shadow-xl space-y-5">
                {/* Requisition Header & Save Action */}
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-lg font-bold text-white tracking-tight">
                        {activeJob.title}
                      </h2>
                      {lastJdDuration && (
                        <DurationBadge duration={lastJdDuration} label="Decomposition duration" />
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-400 mt-1">
                      <span className="font-semibold text-slate-300">{activeJob.department || "General"}</span>
                      <span>•</span>
                      <span>{activeJob.seniority_level || "Standard"}</span>
                      <span>•</span>
                      <span>{activeJob.location || "Remote"}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleSaveCriteria}
                      disabled={isSavingCriteria}
                      className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 active:scale-[0.98] text-white text-xs font-semibold shadow-lg shadow-blue-600/30 transition-all cursor-pointer disabled:opacity-50"
                    >
                      {isSavingCriteria ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Save className="w-4 h-4" />
                      )}
                      <span>Save Criteria Calibration</span>
                    </button>
                  </div>
                </div>

                {saveCriteriaSuccess && (
                  <div className="p-3 rounded-xl bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-xs flex items-center gap-2 animate-in fade-in">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                    <span>Requisition criteria calibrated and saved to database successfully!</span>
                  </div>
                )}

                {/* Criteria KPI Ribbon */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800">
                    <div className="text-[10px] text-slate-400 uppercase font-semibold">Total Criteria</div>
                    <div className="text-xl font-bold text-white tabular-nums mt-0.5">
                      {editableReqs.length}
                    </div>
                  </div>
                  <div className="p-3.5 rounded-xl bg-rose-950/20 border border-rose-500/30">
                    <div className="text-[10px] text-rose-300 uppercase font-semibold">Hard Must-Haves</div>
                    <div className="text-xl font-bold text-rose-200 tabular-nums mt-0.5">
                      {mustHaveCount}
                    </div>
                  </div>
                  <div className="p-3.5 rounded-xl bg-blue-950/20 border border-blue-500/30">
                    <div className="text-[10px] text-blue-300 uppercase font-semibold">Nice-to-Haves</div>
                    <div className="text-xl font-bold text-blue-200 tabular-nums mt-0.5">
                      {niceToHaveCount}
                    </div>
                  </div>
                </div>

                {/* Criteria Management Section */}
                <div className="space-y-4">
                  <div className="flex items-center justify-between text-xs font-semibold text-slate-200">
                    <span>Configured Criteria Rubric</span>
                    <button
                      onClick={() => setShowAddForm(!showAddForm)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors cursor-pointer border border-slate-700"
                    >
                      <Plus className="w-3.5 h-3.5 text-blue-400" />
                      <span>{showAddForm ? "Cancel" : "Add Criterion"}</span>
                    </button>
                  </div>

                  {/* Add Criterion Inline Form */}
                  {showAddForm && (
                    <div className="p-5 rounded-2xl border border-blue-500/40 bg-slate-950/90 space-y-4 shadow-xl animate-in fade-in">
                      <div className="font-semibold text-sm text-white flex items-center gap-2">
                        <Plus className="w-4 h-4 text-blue-400" />
                        <span>Add New Requirement Criterion</span>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div>
                          <label className="text-xs font-medium text-slate-300">
                            Criterion Title <span className="text-rose-400">*</span>
                          </label>
                          <input
                            type="text"
                            value={newTitle}
                            onChange={(e) => setNewTitle(e.target.value)}
                            placeholder="e.g. Distributed Systems & High-Throughput APIs"
                            className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-100 mt-1 focus:outline-none focus:border-blue-500"
                          />
                        </div>

                        <div>
                          <label className="text-xs font-medium text-slate-300">
                            Min Experience (Years)
                          </label>
                          <input
                            type="number"
                            value={newMinExp ?? ""}
                            onChange={(e) => setNewMinExp(e.target.value ? Number(e.target.value) : undefined)}
                            placeholder="e.g. 4"
                            className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-100 mt-1 focus:outline-none focus:border-blue-500"
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div>
                          <label className="text-xs font-medium text-slate-300">
                            Category Gate
                          </label>
                          <select
                            value={newCategory}
                            onChange={(e) => setNewCategory(e.target.value as RequirementCategory)}
                            className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-100 mt-1 focus:outline-none focus:border-blue-500"
                          >
                            <option value="must_have">Must Have (Hard Gate)</option>
                            <option value="nice_to_have">Nice To Have (Bonus Multiplier)</option>
                          </select>
                        </div>

                        <div>
                          <label className="text-xs font-medium text-slate-300">
                            Weight Multiplier ({newWeight}x)
                          </label>
                          <div className="flex items-center gap-3 mt-2">
                            <input
                              type="range"
                              min="0.5"
                              max="2.5"
                              step="0.25"
                              value={newWeight}
                              onChange={(e) => setNewWeight(Number(e.target.value))}
                              className="flex-1"
                            />
                            <span className="font-mono text-xs font-bold text-white w-10 text-right">
                              {newWeight}x
                            </span>
                          </div>
                        </div>
                      </div>

                      <div>
                        <label className="text-xs font-medium text-slate-300">
                          Detailed Description / Rubric
                        </label>
                        <textarea
                          rows={3}
                          value={newDescription}
                          onChange={(e) => setNewDescription(e.target.value)}
                          placeholder="Specific competencies, technologies, frameworks, or certifications required..."
                          className="w-full bg-slate-900 border border-slate-800 rounded-xl p-3 text-xs text-slate-100 mt-1 focus:outline-none focus:border-blue-500 leading-relaxed"
                        />
                      </div>

                      <button
                        onClick={handleAddRequirement}
                        disabled={!newTitle.trim()}
                        className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold disabled:opacity-50 cursor-pointer shadow-md"
                      >
                        Append to Criteria Rubric
                      </button>
                    </div>
                  )}

                  {/* Requirements List */}
                  <div className="space-y-3">
                    {editableReqs.map((req) => (
                      <div
                        key={req.id}
                        className="p-4 rounded-2xl bg-slate-950/70 border border-slate-800/90 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 hover:border-slate-700 transition-all shadow-sm"
                      >
                        <div className="space-y-1.5 flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <button
                              onClick={() => toggleCategory(req.id)}
                              className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full cursor-pointer transition-transform hover:scale-105 ${
                                req.category === "must_have"
                                  ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                                  : "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                              }`}
                              title="Click to toggle category between Must-Have and Nice-to-Have"
                            >
                              {req.category === "must_have" ? "Must Have" : "Nice To Have"}
                            </button>

                            <span className="font-semibold text-sm text-white">
                              {req.title}
                            </span>

                            {req.minimum_years_experience && (
                              <span className="text-xs text-slate-400 font-mono">
                                (≥ {req.minimum_years_experience} yrs)
                              </span>
                            )}
                          </div>

                          <p className="text-sm text-slate-300 leading-relaxed font-sans">
                            {req.description}
                          </p>
                        </div>

                        {/* Interactive Weight Controls & Delete */}
                        <div className="flex items-center gap-2.5 shrink-0">
                          <div className="flex items-center bg-slate-900 border border-slate-800 rounded-xl p-0.5">
                            <button
                              onClick={() => adjustWeight(req.id, -0.25)}
                              className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-white rounded-lg cursor-pointer transition-colors"
                              title="Decrease weight"
                            >
                              <Minus className="w-3.5 h-3.5" />
                            </button>
                            <span className="px-2.5 text-xs font-bold font-mono text-slate-100">
                              {req.weight}x
                            </span>
                            <button
                              onClick={() => adjustWeight(req.id, 0.25)}
                              className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-white rounded-lg cursor-pointer transition-colors"
                              title="Increase weight"
                            >
                              <Plus className="w-3.5 h-3.5" />
                            </button>
                          </div>

                          <button
                            onClick={() => deleteRequirement(req.id)}
                            className="p-2 rounded-xl hover:bg-rose-950/40 text-slate-500 hover:text-rose-400 transition-colors cursor-pointer border border-transparent hover:border-rose-900/40"
                            title="Delete criterion"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="p-12 text-center text-slate-500 text-xs">
                No active requisition selected. Select or parse one on the left.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
