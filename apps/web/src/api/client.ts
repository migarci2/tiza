import type {
  Approval,
  Assignment,
  Attempt,
  Brief,
  Classroom,
  Cycle,
  CycleDraft,
  Dashboard,
  Session,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
let csrf = "";
const mutating = new Set(["POST", "PATCH", "PUT", "DELETE"]);

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = init.method ?? "GET";
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (mutating.has(method) && csrf) headers.set("X-CSRF-Token", csrf);
  const response = await fetch(`/api${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new ApiError(
      response.status,
      body?.detail ?? "We could not complete that action. Please try again.",
    );
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}

function rememberSession(response: Promise<Session>) {
  return response.then((value) => {
    csrf = value.csrf_token;
    return value;
  });
}
export const api = {
  agentRun: (cycleId: string) =>
    request<{
      id?: string;
      state: string;
      mode: string;
      model_invoked: boolean;
      model: string | null;
      model_calls: number;
      tools: string[];
      tool_events?: Array<{ name: string; status: string; error?: string; candidate_counts?: number[]; selected_exercise_ids?: string[] }>;
      active_tool?: string;
      operations: string[];
      draft_count: number;
    }>(`/cycles/${cycleId}/agent-run`),
  demoCode: (code: string) =>
    rememberSession(
      request<Session>("/auth/demo-code", {
        method: "POST",
        body: JSON.stringify({ code }),
      }),
    ),
  session: () => rememberSession(request<Session>("/session")),
  config: () => request<{ demo_mode: boolean; demo_reset_enabled: boolean }>("/config"),
  advanceDemoClock: () =>
    rememberSession(
      request<Session>("/demo/clock/advance", {
        method: "POST",
        body: JSON.stringify({ hours: 6 }),
      }),
    ),
  resetDemo: () =>
    rememberSession(
      request<Session>("/demo/reset", { method: "POST", body: "{}" }),
    ),
  switchDemoUser: (userId: string) =>
    rememberSession(
      request<Session>("/demo/switch", {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      }),
    ),
  dashboard: () => request<Dashboard>("/dashboard"),
  classroom: (id: string) =>
    request<Classroom & { learners: Session["learners"]; cycles: Cycle[] }>(
      `/classrooms/${id}`,
    ),
  createClassroom: (input: {
    title: string;
    language: "en";
    practice_minutes: number;
  }) =>
    request<Classroom>("/classrooms", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  invite: (classroomId: string, email: string) =>
    request<{
      id: string;
      email: string;
      expires_at: string;
      invite_token: string;
    }>(`/classrooms/${classroomId}/invitations`, {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  createCycle: (input: {
    classroom_id: string;
    objective: string;
    concepts?: string[];
    closes_at: string;
    budget_minutes: number;
  }) =>
    request<Cycle>("/cycles", { method: "POST", body: JSON.stringify(input) }),
  addMaterial: (cycleId: string, file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<{
      concept_candidates: Array<{
        id: string;
        title: string;
        reference: string;
        role: "objective" | "prerequisite" | "available";
      }>;
    }>(`/cycles/${cycleId}/materials`, { method: "POST", body: data });
  },
  confirmConcepts: (cycleId: string, conceptIds: string[]) =>
    request<Cycle>(`/cycles/${cycleId}/concepts`, {
      method: "POST",
      body: JSON.stringify({ concept_ids: conceptIds }),
    }),
  prepare: (cycleId: string) =>
    request<{ job_id: string; state: "queued"; cycle_state: "preparing" }>(
      `/cycles/${cycleId}/prepare`,
      { method: "POST", body: "{}" },
    ),
  draft: (cycleId: string) => request<CycleDraft>(`/cycles/${cycleId}/draft`),
  updateDraft: (
    cycleId: string,
    version: number,
    assignments: Array<{
      id: string;
      excluded?: boolean;
      exercise_ids?: string[];
    }>,
  ) =>
    request<CycleDraft>(`/cycles/${cycleId}/draft`, {
      method: "PATCH",
      body: JSON.stringify({ version, assignments }),
    }),
  approve: (cycleId: string, version: number, assignmentIds: string[]) =>
    request<Approval>(`/cycles/${cycleId}/approve`, {
      method: "POST",
      body: JSON.stringify({
        version,
        assignment_ids: assignmentIds,
        allow_reminder: true,
      }),
    }),
  publish: (cycleId: string, approvalId: string, version: number) =>
    request<{
      cycle: Cycle;
      assignments: Array<{
        id: string;
        learner_id: string;
        state: string;
        published: boolean;
      }>;
      deliveries: Array<{ id: string; assignment_id: string; state: string }>;
    }>(`/cycles/${cycleId}/publish`, {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ approval_id: approvalId, version }),
    }),
  assignment: (assignmentId: string) =>
    request<Assignment>(`/assignments/${assignmentId}`),
  assignments: () =>
    request<
      Array<{ id: string; cycle_id: string; learner_id: string; state: string }>
    >("/assignments"),
  hint: (assignmentId: string, itemId: string) =>
    request<{ event_id: string; hint: string }>(
      `/assignments/${assignmentId}/items/${itemId}/hint`,
      { method: "POST", body: "{}" },
    ),
  updateCycle: (
    cycleId: string,
    version: number,
    changes: { closes_at?: string; budget_minutes?: number },
  ) =>
    request<Cycle>(`/cycles/${cycleId}`, {
      method: "PATCH",
      body: JSON.stringify({ version, ...changes }),
    }),
  catalog: () =>
    request<
      Array<CycleDraft["assignments"][number]["items"][number]["exercise"]>
    >("/exercises/catalog"),
  submitAttempt: (
    assignmentId: string,
    input: { item_id: string; response: string; client_key: string },
  ) =>
    request<Attempt>(`/assignments/${assignmentId}/attempts`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  reviewAttempt: (
    attemptId: string,
    input: { outcome: "correct" | "incorrect"; feedback: string },
  ) =>
    request<void>(`/attempts/${attemptId}/review`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  brief: (cycleId: string) => request<Brief>(`/cycles/${cycleId}/brief`),
  deliveries: (cycleId: string) =>
    request<
      Array<{
        id: string;
        assignment_id: string;
        channel: string;
        provider: string;
        state: string;
        last_error: string | null;
      }>
    >(`/cycles/${cycleId}/deliveries`),
  cancelReminders: (cycleId: string) =>
    request<void>(`/cycles/${cycleId}/cancel-reminders`, {
      method: "POST",
      body: "{}",
    }),
};
