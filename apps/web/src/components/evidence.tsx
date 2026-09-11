import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { evidenceCopy as copy } from "./evidence-copy";

type RecordedAttempt = {
  id: string;
  learner: string;
  question: string;
  response: string;
  result: string;
  used_hint: boolean;
  submitted_at: string;
  revisions: Array<{ id: string; outcome: string; evaluator: string; revision: number; created_at: string }>;
};

async function read<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`, { credentials: "include" });
  if (!response.ok) throw new Error(copy.error);
  return response.json();
}

function AttemptReview({ id }: { id: string }) {
  const query = useQueryClient();
  const [feedback, setFeedback] = useState("");
  const record = useQuery({ queryKey: ["recorded-attempt", id], queryFn: () => read<RecordedAttempt>(`/attempts/${id}`) });
  const review = useMutation({
    mutationFn: (outcome: "correct" | "incorrect") => api.reviewAttempt(id, { outcome, feedback }),
    onSuccess: () => query.invalidateQueries(),
  });
  if (record.isPending) return <p role="status">{copy.loading}</p>;
  if (record.isError) return <p role="alert" className="form-error">{record.error.message}</p>;
  const value = record.data;
  return <article className="panel" style={{ marginTop: 12 }}>
    <strong>{value.learner}</strong>
    <p>{value.question}</p>
    <p className="eyebrow">{copy.answer}</p>
    <blockquote style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", marginInline: 0 }}>{value.response}</blockquote>
    <p className="muted">{value.result.replaceAll("_", " ")} · {value.used_hint ? copy.hint : copy.independent}</p>
    <small>{new Date(value.submitted_at).toLocaleString()}</small>
    <details style={{ marginBlock: 12 }}><summary>{copy.history}</summary>
      <ul>{value.revisions.map(revision => <li key={revision.id}>
        {revision.revision}: {revision.outcome} · {revision.evaluator} · {new Date(revision.created_at).toLocaleString()}
      </li>)}</ul>
    </details>
    <label style={{ display: "grid", gap: 8 }}>{copy.feedback}
      <textarea maxLength={2000} value={feedback} onChange={event => setFeedback(event.target.value)} />
    </label>
    <div className="form-actions" style={{ marginTop: 12 }}>
      <button className="button secondary" disabled={review.isPending} onClick={() => review.mutate("incorrect")}>{copy.incorrect}</button>
      <button className="button primary" disabled={review.isPending} onClick={() => review.mutate("correct")}>{copy.correct}</button>
    </div>
    {review.isError && <p role="alert" className="form-error">{review.error.message}</p>}
    {review.isSuccess && <p role="status">{copy.saved}</p>}
  </article>;
}

export function EvidencePanel({ attemptIds }: { attemptIds: string[] }) {
  const [open, setOpen] = useState(false);
  return <details style={{ gridColumn: "1 / -1", width: "100%" }} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="text-action">{copy.open}</summary>
    {open && attemptIds.map(id => <AttemptReview id={id} key={id} />)}
  </details>;
}

export function PendingReviews({ cycleId }: { cycleId: string }) {
  const pending = useQuery({ queryKey: ["pending-reviews", cycleId], queryFn: () => read<string[]>(`/cycles/${cycleId}/pending-reviews`) });
  return <section className="panel full-span"><h2>{copy.pending}</h2>
    {pending.isPending ? <p>{copy.loading}</p> : pending.isError ? <p role="alert">{pending.error.message}</p> :
      pending.data.length ? pending.data.map(id => <AttemptReview id={id} key={id} />) : <p className="muted">{copy.empty}</p>}
  </section>;
}
