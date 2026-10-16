import { FileCheck2 } from "lucide-react";

export const message = (error: unknown) => error instanceof Error ? error.message : "Something went wrong. Please try again.";
export const candidateName = (id: string, candidates: {id: string; masked_name?: string | null}[]) => candidates.find(c => c.id === id)?.masked_name || `Candidate ${id.slice(0, 8)}`;

export function Empty({title, children}: {title: string; children: React.ReactNode}) {
  return <div className="r-empty"><FileCheck2 size={32}/><h3>{title}</h3><p>{children}</p></div>;
}

export function downloadJson(value: unknown, name: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type: "application/json"}));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
