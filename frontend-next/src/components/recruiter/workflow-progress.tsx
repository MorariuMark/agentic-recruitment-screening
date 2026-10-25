"use client";

import {ArrowLeft, ArrowRight, Check} from "lucide-react";
import {workflowStages} from "@/lib/guided-workflow";

type Stage = typeof workflowStages[number]["id"];
export function WorkflowProgress({stage, complete, hints, busy, onNavigate, onNext, error, shortlistNeeded, part}: {
  part: "stages" | "footer"; stage: Stage; complete: boolean[]; hints: string[]; busy: boolean; error: string;
  onNavigate: (stage: Stage) => void; onNext: () => void; shortlistNeeded: boolean;
}) {
  const index = workflowStages.findIndex(item => item.id === stage);
  const last = index === workflowStages.length - 1;
  return <>
    {part === "stages" && <nav className="r-workflow-progress" aria-label="Guided hiring stages"><ol>
      {workflowStages.map((item, i) => <li key={item.id} className={`${i === index ? "current" : ""} ${complete[i] ? "complete" : ""}`}>
        <button type="button" aria-current={i === index ? "step" : undefined}
          disabled={busy || (i > index && (!complete.slice(index, i).every(Boolean) || (i > index + 1 && !complete[i])))}
          onClick={() => i === index + 1 ? onNext() : onNavigate(item.id)} title={`${item.label}${complete[i] ? " — complete" : ""}`}>
          <span className="r-workflow-bubble" aria-hidden="true">{complete[i] ? <Check size={16}/> : i + 1}</span>
          <span>{item.label}</span>
        </button>
      </li>)}
    </ol></nav>}
    {part === "footer" && <div className="r-workflow-footer">
      <button type="button" className="r-button" disabled={!index || busy} onClick={() => onNavigate(workflowStages[index - 1].id)}><ArrowLeft size={16}/>Back</button>
      <div aria-live="polite"><strong>{last && complete[index] ? "Ready for interviews" : `Stage ${index + 1} of ${workflowStages.length}: ${workflowStages[index].label}`}</strong>
        <small>{error || (busy ? "Waiting for the current action to finish…" : !complete[index] ? hints[index] : last ? "Your saved questions and candidate decisions are ready." : shortlistNeeded ? "Next adds up to 10 evaluated candidates to comparison." : "Your saved work carries forward to the next stage.")}</small>
      </div>
      {!last && <button type="button" className="r-button primary" disabled={busy || !complete[index]} onClick={onNext}>Next: {workflowStages[index + 1].label}<ArrowRight size={16}/></button>}
      {last && <span className="r-pill">{complete[index] ? "Ready" : "Prepare questions"}</span>}
    </div>}
  </>;
}
