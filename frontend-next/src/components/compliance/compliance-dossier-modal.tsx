"use client";

import { useState, useEffect } from "react";
import { ComplianceDossier } from "@/types";
import { api } from "@/lib/api";
import {
  CheckCircle2,
  Copy,
  Download,
  FileCheck2,
  Fingerprint,
  Loader2,
  Lock,
  Scale,
  ShieldAlert,
  ShieldCheck,
  UserCheck,
  X,
} from "lucide-react";

interface ComplianceDossierModalProps {
  evaluationId: string;
  isOpen: boolean;
  onClose: () => void;
}

export function ComplianceDossierModal({
  evaluationId,
  isOpen,
  onClose,
}: ComplianceDossierModalProps) {
  const [dossier, setDossier] = useState<ComplianceDossier | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [copiedHash, setCopiedHash] = useState(false);

  useEffect(() => {
    if (!isOpen || !evaluationId) return;

    let mounted = true;
    setLoading(true);

    api
      .getComplianceDossier(evaluationId)
      .then((data) => {
        if (mounted) setDossier(data);
      })
      .catch((err) => {
        console.error("Failed to load compliance dossier:", err);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [isOpen, evaluationId]);

  if (!isOpen) return null;

  const handleCopyHash = () => {
    if (!dossier?.record_metadata.cryptographic_sha256_seal) return;
    navigator.clipboard.writeText(dossier.record_metadata.cryptographic_sha256_seal);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2500);
  };

  const handleDownloadMarkdown = async () => {
    try {
      setDownloading(true);
      const mdContent = await api.getComplianceDossierMarkdown(evaluationId);
      const blob = new Blob([mdContent], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `EU_AI_Act_Dossier_${evaluationId.slice(0, 8)}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(`Download failed: ${err.message}`);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
      <div className="relative w-full max-w-4xl max-h-[90vh] flex flex-col bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 bg-slate-950/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
              <Scale className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-white tracking-tight">
                  EU AI Act Compliance & Audit Dossier
                </h2>
                <span className="text-xs font-mono px-2.5 py-0.5 rounded-full bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 font-medium">
                  Annex III Point 4(a)
                </span>
              </div>
              <p className="text-xs text-slate-300 mt-0.5">
                Regulation (EU) 2024/1689 High-Risk Technical Documentation & Human Oversight Package
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {loading ? (
            <div className="py-20 flex flex-col items-center justify-center gap-3 text-slate-400 text-sm">
              <Loader2 className="w-7 h-7 animate-spin text-indigo-500" />
              <span>Generating cryptographic compliance certificate...</span>
            </div>
          ) : !dossier ? (
            <div className="py-16 text-center text-slate-400 text-sm">
              Unable to generate compliance certificate. Please ensure the evaluation was persisted.
            </div>
          ) : (
            <>
              {/* Top Banner: Verification Status & Cryptographic Hash */}
              <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/40 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-2.5">
                    {dossier.article_14_human_oversight.is_decision_finalized_by_human ? (
                      <div className="flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-semibold">
                        <ShieldCheck className="w-4 h-4" />
                        <span>CERTIFIED — Human Oversight Sign-Off Completed</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-semibold">
                        <ShieldAlert className="w-4 h-4" />
                        <span>PROVISIONAL — Awaiting Recruiter Sign-Off</span>
                      </div>
                    )}
                  </div>
                  <div className="text-xs text-slate-300 font-mono">
                    Candidate: <span className="text-white font-semibold text-sm">{dossier.record_metadata.candidate_alias}</span>
                  </div>
                </div>

                {/* Cryptographic SHA-256 Seal */}
                <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2.5 overflow-hidden">
                    <Fingerprint className="w-4 h-4 text-indigo-400 shrink-0" />
                    <div className="overflow-hidden">
                      <div className="text-[10px] text-slate-400 uppercase tracking-wider font-bold">
                        SHA-256 Cryptographic Tamper-Proof Seal (Article 12 Integrity)
                      </div>
                      <div className="text-xs font-mono text-indigo-300 truncate mt-0.5">
                        {dossier.record_metadata.cryptographic_sha256_seal}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={handleCopyHash}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium shrink-0 transition-colors cursor-pointer"
                  >
                    {copiedHash ? (
                      <>
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-emerald-400 font-semibold">Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5 text-slate-400" />
                        <span>Copy Digest</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Grid of Articles */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Article 10: Data Governance & De-Biasing */}
                <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/20 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                      <Lock className="w-4 h-4 text-blue-400" />
                      <span>Article 10: Data Governance & De-Biasing</span>
                    </h3>
                    <span className="text-xs font-mono px-2 py-0.5 rounded font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      COMPLIANT
                    </span>
                  </div>
                  <ul className="text-xs text-slate-300 space-y-2 list-disc pl-4 leading-relaxed">
                    <li>
                      <span className="text-white font-semibold">PII Redaction:</span> Full name, contact details, and URLs scrubbed prior to semantic matching.
                    </li>
                    <li>
                      <span className="text-white font-semibold">Protected Attributes:</span> Gender, nationality, age indicators strictly excluded from ChromaDB vector space.
                    </li>
                    <li>
                      <span className="text-white font-semibold">Vector Store Cleanliness:</span> {dossier.article_10_data_governance.vector_store_cleanliness}
                    </li>
                  </ul>
                </div>

                {/* Article 13: Transparency & Citation Grounding */}
                <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/20 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                      <FileCheck2 className="w-4 h-4 text-purple-400" />
                      <span>Article 13: Transparency & CVS</span>
                    </h3>
                    <span className="text-xs font-mono px-2 py-0.5 rounded font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      COMPLIANT
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800 text-center">
                      <div className="text-[10px] text-slate-400 uppercase font-semibold">Match Score</div>
                      <div className="text-base font-bold text-white tabular-nums">
                        {dossier.article_13_transparency_and_explainability.overall_match_score.toFixed(0)}%
                      </div>
                    </div>
                    <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800 text-center">
                      <div className="text-[10px] text-slate-400 uppercase font-semibold">Must-Have</div>
                      <div className="text-base font-bold text-blue-400 tabular-nums">
                        {dossier.article_13_transparency_and_explainability.must_have_score.toFixed(0)}%
                      </div>
                    </div>
                    <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800 text-center">
                      <div className="text-[10px] text-slate-400 uppercase font-semibold">CVS Score</div>
                      <div className="text-base font-bold text-emerald-400 tabular-nums">
                        {(dossier.article_13_transparency_and_explainability.citation_verification_score * 100).toFixed(0)}%
                      </div>
                    </div>
                  </div>
                  <div className="text-xs text-slate-300 leading-relaxed">
                    <span className="text-white font-semibold">Verbatim Citations:</span>{" "}
                    {dossier.article_13_transparency_and_explainability.verbatim_verified_citations} of{" "}
                    {dossier.article_13_transparency_and_explainability.total_citations_extracted} exact substrings verified against CV text.
                  </div>
                </div>

                {/* Article 14: Human Oversight Audit Trail */}
                <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/20 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                      <UserCheck className="w-4 h-4 text-emerald-400" />
                      <span>Article 14: Human-in-the-Loop Gate</span>
                    </h3>
                    <span className="text-xs font-mono px-2 py-0.5 rounded font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      MANDATORY
                    </span>
                  </div>
                  <div className="text-xs text-slate-300 space-y-1.5">
                    <div>
                      <span className="text-slate-400">Recruiter Decision:</span>{" "}
                      <span className="font-bold uppercase text-white">
                        {dossier.article_14_human_oversight.recruiter_decision}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400">Override Exercised:</span>{" "}
                      <span className="text-slate-200 font-medium">
                        {dossier.article_14_human_oversight.human_override_exercised ? "Yes" : "No"}
                      </span>
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-sm text-slate-200 italic leading-relaxed">
                    &ldquo;{dossier.article_14_human_oversight.recruiter_audit_notes}&rdquo;
                  </div>
                </div>

                {/* Article 11 & 15: Technical Documentation & Robustness */}
                <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/20 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                      <ShieldCheck className="w-4 h-4 text-amber-400" />
                      <span>Articles 11 & 15: Tech Architecture & Failover</span>
                    </h3>
                    <span className="text-xs font-mono px-2 py-0.5 rounded font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      COMPLIANT
                    </span>
                  </div>
                  <ul className="text-xs text-slate-300 space-y-2 list-disc pl-4 leading-relaxed">
                    <li>
                      <span className="text-white font-semibold">Inference:</span> {dossier.article_11_technical_documentation.inference_model} (Deterministic Temp 0.0)
                    </li>
                    <li>
                      <span className="text-white font-semibold">Failover Chain:</span> Multi-tier automated failover (Cloud API → OpenRouter → Local Ollama)
                    </li>
                    <li>
                      <span className="text-white font-semibold">Cybersecurity:</span> System prompt boundary isolation &amp; Flat PDF scanned integrity check
                    </li>
                  </ul>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-950/80 flex items-center justify-between gap-4">
          <div className="text-xs text-slate-400">
            Compliant with Annex III High-Risk requirements under EU AI Act (Regulation (EU) 2024/1689).
          </div>
          <div className="flex items-center gap-2.5">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
            >
              Close
            </button>
            <button
              onClick={handleDownloadMarkdown}
              disabled={downloading || !dossier}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 active:scale-[0.98] text-white text-xs font-semibold shadow-lg shadow-indigo-600/20 transition-all cursor-pointer disabled:opacity-50"
            >
              {downloading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Download className="w-4 h-4" />
              )}
              <span>Download Markdown Certificate (.md)</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
