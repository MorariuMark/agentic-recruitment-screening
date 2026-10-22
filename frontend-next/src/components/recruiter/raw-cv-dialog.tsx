"use client";

import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { api, type CVDocument } from "@/lib/api";
import { message } from "./common";

export function RawCVDialog({document, onClose}: {document: CVDocument; onClose: () => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const text = useQuery({queryKey: ["cv-document-text", document.id], queryFn: () => api.cvDocumentText(document.id)});
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return <dialog ref={dialog} className="recruiter r-profile-dialog" aria-labelledby="raw-cv-title" onClose={onClose}>
    <header><div><span className="r-muted">Original CV · not parsed</span><h2 id="raw-cv-title">{document.filename}</h2></div>
      <button className="r-icon-button" aria-label="Close original CV" onClick={() => dialog.current?.close()}><X size={20}/></button></header>
    <div className="r-raw-cv-content">
      {text.isPending ? <p role="status">Loading original CV text…</p> : text.error ? <div className="r-alert" role="alert">{message(text.error)}<button onClick={() => text.refetch()}>Retry</button></div>
        : <pre className="r-cv-text">{text.data?.text || "No readable text was found in this original CV."}</pre>}
    </div>
  </dialog>;
}
