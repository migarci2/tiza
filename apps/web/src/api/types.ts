export type User = {
  id: string;
  email: string;
  display_name: string;
  synthetic: boolean;
};
export type Session = {
  csrf_token: string;
  actor: User;
  effective_user: User;
  role: "teacher" | "learner";
  demo: boolean;
  demo_now?: string;
  agent_mode?: string;
  classroom_id: string;
  learners: User[];
};
export type CycleState =
  | "draft"
  | "preparing"
  | "review_ready"
  | "approved"
  | "active"
  | "closed"
  | "failed"
  | "cancelled";
export type AssignmentState =
  "not_started" | "in_progress" | "submitted" | "review_needed" | "completed";
export type Classroom = {
  id: string;
  title: string;
  language: string;
  practice_minutes: number;
};
export type Cycle = {
  id: string;
  classroom_id: string;
  objective: string;
  concepts: string[];
  closes_at: string;
  budget_minutes: number;
  state: CycleState;
  version: number;
};
export type Exercise = {
  id: string;
  concept_id: string;
  kind: "multiple_choice" | "numeric" | "fraction" | "short_answer" | "short";
  prompt: string;
  options?: Array<{ id: string; text: string }>;
  explanation?: string;
  hint?: string;
  estimated_minutes: number;
  source?: string;
};
export type DraftItem = {
  id: string;
  position: number;
  branch_after_item_id?: string;
  branch_on?: string;
  exercise: Exercise;
};
export type DraftAssignment = {
  id: string;
  learner: User;
  version: number;
  reason: string;
  estimated_minutes: number;
  state: AssignmentState;
  excluded: boolean;
  items: DraftItem[];
};
export type CycleDraft = { cycle: Cycle; assignments: DraftAssignment[] };
export type Dashboard = {
  classroom: Classroom;
  active_cycle: Cycle | null;
  pending_approval: Cycle[];
  decisions: Array<{ kind: string; label: string; cycle_id: string }>;
};
export type Approval = {
  id: string;
  version: number;
  batch_hash: string;
  recipient_ids: string[];
  permissions: string[];
  created_at: string;
};
export type Attempt = {
  id: string;
  item_id: string;
  result: "correct" | "incorrect" | "review_needed";
  score: number | null;
  feedback: string;
  used_hint: boolean;
  submitted_at: string;
};
export type Assignment = {
  id: string;
  cycle: Pick<Cycle, "id" | "objective" | "closes_at">;
  learner: User;
  state: AssignmentState;
  progress: { answered: number; total: number };
  items: Array<DraftItem & { attempt?: Attempt }>;
};
export type Brief = {
  cycle_id: string;
  completion: {
    total: number;
    completed: number;
    in_progress: number;
    not_started: number;
    review_needed: number;
  };
  patterns: Array<{ text: string; attempt_ids: string[] }>;
  missing_learners: User[];
  opening_activity: { title: string; reason: string } | null;
};
