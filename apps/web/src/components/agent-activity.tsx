import { useQuery } from "@tanstack/react-query";
import {
  Check,
  ChevronDown,
  LoaderCircle,
  NotebookPen,
  CircleAlert,
} from "lucide-react";
import { api } from "../api/client";
import en from "../locales/en.json";
import { SdkCredit } from "./sdk-credit";
const t = (key: keyof typeof en) => en[key];
const operations: Record<string, string> = {
  evidence_and_policy_evaluated: t("agent.evidence"),
  validated_bank_selected: t("agent.bank"),
  drafts_saved_for_review: t("agent.saved"),
};
const workflow = [
  ["read_cycle_context", t("agent.step0")],
  ["select_validated_exercises", t("agent.step1")],
  ["save_assignment_draft", t("agent.step2")],
  ["request_teacher_review", t("agent.step3")],
];
export function AgentActivity({ cycleId }: { cycleId: string }) {
  const run = useQuery({
    queryKey: ["agent-run", cycleId],
    queryFn: () => api.agentRun(cycleId),
    refetchInterval: (query) =>
      !query.state.data ||
      ["queued", "running"].includes(query.state.data.state)
        ? 1000
        : false,
  });
  if (run.isError) return <p role="alert">{t("agent.unavailable")}</p>;
  if (!run.data || run.data.state === "not_started") return null;
  const value = run.data,
    done = value.state === "completed",
    live = value.model_invoked,
    preview = value.mode === "illustrative_preview";
  return (
    <section className="agent-activity" aria-label={t("agent.activity")}>
      <div className="agent-activity-heading">
        <span className="agent-symbol">
          <NotebookPen size={21} />
        </span>
        <div>
          <h2>{t("agent.title")}</h2>
          <p>
            {done
              ? `${value.draft_count} ${t("agent.ready")}`
              : value.state === "failed"
                ? t("agent.failed")
                : t("agent.working")}
          </p>
        </div>
        <span className="agent-state">
          {done ? (
            <Check size={16} />
          ) : value.state !== "failed" ? (
            <LoaderCircle size={16} className="spin" />
          ) : null}
          {done ? t("agent.review") : value.state}
        </span>
      </div>
      <SdkCredit />
      {preview && (
        <ol className="agent-steps" aria-label={t("agent.workflow")}>
          {workflow.map(([tool, label]) => {
            const complete = value.tools.includes(tool);
            const active = value.active_tool === tool;
            return (
              <li
                key={tool}
                data-tool={tool}
                data-status={
                  complete ? "complete" : active ? "active" : "pending"
                }
                aria-current={active ? "step" : undefined}
              >
                <span className="step-icon">
                  {complete ? (
                    <Check size={15} />
                  ) : active ? (
                    <LoaderCircle size={15} className="spin" />
                  ) : (
                    <span aria-hidden="true">·</span>
                  )}
                </span>
                {label}
              </li>
            );
          })}
        </ol>
      )}
      {(done || value.state === "failed") && (
        <>
          {done && (
            <div className="agent-result">
              <Check size={16} />
              <span>{t("agent.boundary")}</span>
            </div>
          )}
          <details className="agent-trace">
            <summary>
              {preview ? t("agent.workflow") : t("agent.trace")}
              <ChevronDown size={15} />
            </summary>
            {!preview && (
              <p className="agent-mode">
                {live
                  ? t("agent.live")
                  : value.mode === "bedrock"
                    ? t("agent.noCall")
                    : t("agent.local")}
              </p>
            )}
            {live || preview ? (
              <>
                {!preview && (
                  <p className="agent-model">
                    {value.model} · {value.model_calls} {t("agent.calls")}
                  </p>
                )}
                <ol>
                  {(value.tool_events?.length
                    ? value.tool_events
                    : value.tools.map((name) => ({ name, status: "completed" }))
                  ).map((event, index) => (
                    <li key={index}>
                      {event.status === "completed" ? (
                        <Check size={14} />
                      ) : (
                        <CircleAlert size={14} />
                      )}
                      <code>{event.name}</code>
                      <span>{event.status === "completed" ? t("agent.toolCompleted") : t("agent.toolFailed")}</span>
                    </li>
                  ))}
                </ol>
              </>
            ) : (
              <ol>
                {value.operations.map((name) => (
                  <li key={name}>
                    <Check size={14} />
                    {operations[name] ?? name}
                  </li>
                ))}
              </ol>
            )}
          </details>
        </>
      )}
    </section>
  );
}
