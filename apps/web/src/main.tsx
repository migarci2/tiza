import { FormEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import katex from "katex";
import "katex/dist/katex.min.css";
import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  BookOpen,
  CalendarDays,
  Check,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  GraduationCap,
  Home,
  LoaderCircle,
  Plus,
  RefreshCw,
  Users,
  X,
} from "lucide-react";
import { api, ApiError } from "./api/client";
import { Button } from "./components/ui/button";
import { EvidencePanel, PendingReviews } from "./components/evidence";
import en from "./locales/en.json";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
} from "./components/ui/dialog";
import type {
  Brief,
  Cycle,
  Dashboard,
  DraftAssignment,
  Session,
} from "./api/types";
import "./styles.css";
import { AgentActivity } from "./components/agent-activity";
import { Welcome } from "./components/landing";

type Screen =
  "home" | "classroom" | "new-cycle" | "review" | "brief" | "practice";
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});
const t = (key: keyof typeof en) => en[key];
const nav: Array<[Screen, typeof Home, string]> = [
  ["home", Home, t("nav.overview")],
  ["classroom", Users, t("nav.classroom")],
  ["new-cycle", ClipboardList, t("nav.cycles")],
  ["brief", CalendarDays, t("nav.nextLesson")],
];
const initials = (name: string) =>
  name
    .split(" ")
    .map((word) => word[0])
    .join("")
    .slice(0, 2);
const dateTime = (value: string) =>
  new Intl.DateTimeFormat("en", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
const isNetworkIssue = (error: unknown) =>
  error instanceof TypeError ||
  (error instanceof ApiError && error.status >= 500);
const MathMark = ({ tex }: { tex: string }) => (
  <span dangerouslySetInnerHTML={{ __html: katex.renderToString(tex) }} />
);

function App() {
  const [showLanding, setShowLanding] = useState(location.pathname === "/");
  const pathAssignment =
    /^\/practice\/([^/]+)$/.exec(location.pathname)?.[1] ?? null;
  const inviteToken = /^\/invite\/([^/]+)$/.exec(location.pathname)?.[1];
  const [screen, setScreen] = useState<Screen>(
      pathAssignment ? "practice" : "home",
    ),
    [cycleId, setCycleId] = useState<string | null>(null),
    [assignmentId, setAssignmentId] = useState<string | null>(
      pathAssignment ?? sessionStorage.getItem("tiza-assignment"),
    ),
    [notice, setNotice] = useState<string | null>(null),
    [classroomOverride, setClassroomOverride] = useState<string | null>(null);
  const query = useQueryClient();
  const session = useQuery({
    queryKey: ["session"],
    queryFn: api.session,
    retry: false,
  });
  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
    enabled: !!session.data && session.data.role === "teacher",
  });
  const learnerAssignments = useQuery({
    queryKey: ["assignments", session.data?.effective_user.id],
    queryFn: api.assignments,
    enabled: !!session.data && session.data.role === "learner",
  });
  const currentCycle =
    dashboard.data?.active_cycle ?? dashboard.data?.pending_approval[0] ?? null;
  useEffect(() => {
    if (session.data?.role === "learner" && learnerAssignments.data?.[0]) {
      setAssignmentId(learnerAssignments.data[0].id);
      sessionStorage.setItem("tiza-assignment", learnerAssignments.data[0].id);
      setScreen("practice");
    }
  }, [learnerAssignments.data, session.data?.role]);
  const open = (next: Screen, id?: string) => {
    if (id) setCycleId(id);
    setScreen(next);
    setNotice(null);
  };
  const reset = useMutation({
    mutationFn: api.resetDemo,
    onSuccess: (value) => {
      query.setQueryData(["session"], value);
      query.invalidateQueries();
      setAssignmentId(null);
      sessionStorage.removeItem("tiza-assignment");
      setScreen("home");
      setNotice("Demo data restored.");
    },
  });
  if (session.isLoading && !showLanding) return <Loading />;
  if (showLanding || session.isError)
    return (
      <Welcome
        onAuthenticated={(value) => {
          query.setQueryData(["session"], value);
          history.replaceState(null, "", "/workspace");
          setShowLanding(false);
          window.scrollTo(0, 0);
        }}
        inviteToken={inviteToken}
      />
    );
  const actor = session.data!;
  const classroomId = classroomOverride ?? actor.classroom_id;
  if (actor.role === "learner" && assignmentId) {
    return (
      <PracticePage
        assignmentId={assignmentId}
        onDone={() => setNotice("Response saved.")}
        onBack={
          actor.demo
            ? () =>
                api
                  .switchDemoUser(actor.actor.id)
                  .then((value) => query.setQueryData(["session"], value))
            : undefined
        }
      />
    );
  }
  if (actor.role === "learner" && (!assignmentId || screen !== "practice"))
    return (
      <LearnerStart
        learner={actor.effective_user.display_name}
        onBack={() =>
          api.switchDemoUser(actor.actor.id).then((value) => {
            query.setQueryData(["session"], value);
            setScreen("home");
          })
        }
      />
    );
  return (
    <div className="app-shell">
      <Sidebar
        actor={actor}
        screen={screen}
        onNavigate={open}
        onReset={() => reset.mutate()}
        resetting={reset.isPending}
      />
      <main className="workspace">
        {notice && (
          <div className="toast" role="status">
            {notice}
            <button onClick={() => setNotice(null)} aria-label="Close">
              <X size={15} />
            </button>
          </div>
        )}
        {screen === "home" && (
          <HomePage
            data={dashboard.data}
            loading={dashboard.isLoading}
            error={dashboard.error}
            onCreate={() => open("new-cycle")}
            onReview={(id) => open("review", id)}
            onBrief={(id) => open("brief", id)}
            onClassroom={() => open("classroom")}
          />
        )}{" "}
        {screen === "classroom" && (
          <ClassroomPage
            classroomId={classroomId}
            onCreate={() => open("new-cycle")}
            onReview={(id) => open("review", id)}
            onSelect={setClassroomOverride}
          />
        )}{" "}
        {screen === "new-cycle" && (
          <CreateCycle
            classroomId={classroomId}
            onDone={(id) => open("review", id)}
            onCancel={() => open("home")}
          />
        )}{" "}
        {screen === "review" && cycleId && (
          <ReviewPage
            cycleId={cycleId}
            onPublished={(assignment) => {
              setAssignmentId(assignment);
              sessionStorage.setItem("tiza-assignment", assignment);
              open("home");
              setNotice("Practice published. Switch to a learner to try it.");
            }}
            onBrief={() => open("brief", cycleId)}
          />
        )}{" "}
        {screen === "brief" && (
          <BriefPage
            cycleId={cycleId ?? currentCycle?.id ?? null}
            onReview={(id) => open("review", id)}
          />
        )}{" "}
        {screen === "practice" && assignmentId && (
          <PracticePage
            assignmentId={assignmentId}
            onDone={() => setNotice("Response saved.")}
          />
        )}
      </main>
    </div>
  );
}

function Loading() {
  return (
    <main className="boot">
      <span className="wordmark">
        <span className="story-brand-mark" aria-hidden="true">
          t
        </span>
        tiza
      </span>
      <p>Opening your class workspace…</p>
    </main>
  );
}
function LearnerStart({
  learner,
  onBack,
}: {
  learner: string;
  onBack: () => void;
}) {
  return (
    <main className="welcome">
      <span className="wordmark">
        <span className="story-brand-mark" aria-hidden="true">
          t
        </span>
        tiza
      </span>
      <h1>Hello, {learner}.</h1>
      <p>Your teacher has not opened a practice link in this browser yet.</p>
      <button className="button secondary" onClick={onBack}>
        Return to teacher view
      </button>
    </main>
  );
}
function Sidebar({
  actor,
  screen,
  onNavigate,
  onReset,
  resetting,
}: {
  actor: Session;
  screen: Screen;
  onNavigate: (s: Screen) => void;
  onReset: () => void;
  resetting: boolean;
}) {
  const switchUser = (id: string) =>
    api.switchDemoUser(id).then((value) => {
      queryClient.setQueryData(["session"], value);
      queryClient.invalidateQueries();
    });
  const advanceClock = useMutation({
    mutationFn: api.advanceDemoClock,
    onSuccess: (value) => queryClient.setQueryData(["session"], value),
  });
  return (
    <aside className="sidebar">
      <div>
        <span className="wordmark">
          <span className="story-brand-mark" aria-hidden="true">
            t
          </span>
          tiza
        </span>
        <nav>
          {nav.map(([key, Icon, label]) => (
            <button
              key={key}
              className={screen === key ? "nav-active" : ""}
              onClick={() => onNavigate(key)}
            >
              <Icon size={21} />
              {label}
            </button>
          ))}
        </nav>
      </div>
      <div className="account">
        <button className="account-button" aria-label="Change demo identity">
          <span className="avatar">{initials(actor.actor.display_name)}</span>
          <span>
            <b>{actor.effective_user.display_name}</b>
            <small>
              {actor.role === "teacher" ? "Teacher" : "Learner preview"}
            </small>
          </span>
          <ChevronRight size={17} />
        </button>
        <Dialog>
          <DialogTrigger asChild>
            <button className="identity-trigger">Demo identity</button>
          </DialogTrigger>
          <DialogContent className="dialog-content">
            <DialogTitle>Choose a demo identity</DialogTitle>
            {actor.demo && (
              <p className="demo-transparency">
                {actor.agent_mode === "deterministic_demo"
                  ? "Local demo · no model call"
                  : "Bedrock mode"}
                {actor.demo_now && ` · simulated ${dateTime(actor.demo_now)}`}
              </p>
            )}
            <button onClick={() => switchUser(actor.actor.id)}>
              Teacher: {actor.actor.display_name}
            </button>
            {actor.learners.map((user) => (
              <button key={user.id} onClick={() => switchUser(user.id)}>
                {user.display_name}
              </button>
            ))}
            <button onClick={onReset} disabled={resetting}>
              <RefreshCw size={14} />
              Reset demo
            </button>
            {actor.demo && (
              <button
                onClick={() => advanceClock.mutate()}
                disabled={advanceClock.isPending}
              >
                Advance demo clock +6h
              </button>
            )}
          </DialogContent>
        </Dialog>
      </div>
    </aside>
  );
}

function HomePage({
  data,
  loading,
  error,
  onCreate,
  onReview,
  onBrief,
  onClassroom,
}: {
  data?: Dashboard;
  loading: boolean;
  error: Error | null;
  onCreate: () => void;
  onReview: (id: string) => void;
  onBrief: (id: string) => void;
  onClassroom: () => void;
}) {
  const classData = useQuery({
    queryKey: ["classroom", data?.classroom.id],
    queryFn: () => api.classroom(data!.classroom.id),
    enabled: !!data,
  });
  const cycle = data?.active_cycle ?? data?.pending_approval[0];
  const brief = useQuery({
    queryKey: ["brief", cycle?.id],
    queryFn: () => api.brief(cycle!.id),
    enabled: !!cycle && cycle.state === "active",
  });
  const assignments = useQuery({
    queryKey: ["draft", cycle?.id],
    queryFn: () => api.draft(cycle!.id),
    enabled: !!cycle && cycle.state === "active",
  });
  const deliveries = useQuery({
    queryKey: ["deliveries", cycle?.id],
    queryFn: () => api.deliveries(cycle!.id),
    enabled: !!cycle && cycle.state === "active",
  });
  if (loading) return <PageLoading />;
  if (error || !data) return <PageError error={error} />;
  const learners = classData.data?.learners ?? [];
  return (
    <>
      <Header crumb="Workspace / Overview" />
      <section className="headline">
        <div>
          <h1>{t("dashboard.headline")}</h1>
          <p>
            {new Intl.DateTimeFormat("en", {
              weekday: "long",
              day: "numeric",
              month: "long",
            }).format(new Date())}
          </p>
        </div>
        {cycle && (
          <button className="button primary" onClick={onCreate}>
            <Plus />
            {t("actions.createCycle")}
          </button>
        )}
      </section>
      {cycle ? (
        <>
          <section className="attention">
            <span className="check-mark">
              <Check />
            </span>
            <div>
              <b>
                {cycle.state === "review_ready"
                  ? "Practice is ready for your review."
                  : t("dashboard.inMotion")}
              </b>
              <p>
                {data.decisions[0]?.label ??
                  "Review the current cycle and learner responses."}
              </p>
            </div>
            <button
              className="button secondary"
              onClick={() => onReview(cycle.id)}
            >
              {cycle.state === "review_ready"
                ? "Review practice"
                : "View cycle"}
            </button>
          </section>
          <section className="home-grid">
            <ClassroomCard
              classroom={data.classroom}
              cycle={cycle}
              learners={learners}
              brief={brief.data}
              assignments={assignments.data?.assignments ?? []}
              onOpen={onClassroom}
            />
            <aside className="right-rail">
              <ReviewCard
                cycle={cycle}
                learners={learners}
                onReview={() => onReview(cycle.id)}
              />
              {deliveries.data && (
                <DeliveryStates deliveries={deliveries.data} />
              )}
              <NextLesson onOpen={() => onBrief(cycle.id)} />
            </aside>
          </section>
        </>
      ) : (
        <EmptyCycle onCreate={onCreate} classroom={data.classroom.title} />
      )}
    </>
  );
}
function Header({ crumb }: { crumb: string }) {
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  return (
    <header className="topbar">
      <p>{crumb}</p>
      {config.data?.demo_mode && (
        <span className="demo-pill">
          <GraduationCap size={18} />
          Demo workspace
        </span>
      )}
    </header>
  );
}
function ClassroomCard({
  classroom,
  cycle,
  learners,
  brief,
  assignments,
  onOpen,
}: {
  classroom: Dashboard["classroom"];
  cycle: Cycle;
  learners: Session["learners"];
  brief?: Brief;
  assignments: DraftAssignment[];
  onOpen: () => void;
}) {
  const complete = brief?.completion;
  const responded = complete
    ? complete.completed + complete.in_progress + complete.review_needed
    : 0;
  return (
    <section className="panel classroom-card">
      <button className="eyebrow link-button" onClick={onOpen}>
        {t("dashboard.classroom")}
      </button>
      <h2>{classroom.title}</h2>
      <p>{learners.length} learners · Fractions</p>
      <div className="avatars">
        {learners.slice(0, 5).map((user) => (
          <span key={user.id} className="avatar">
            {initials(user.display_name)}
          </span>
        ))}
        {learners.length > 5 && (
          <span className="avatar neutral">+{learners.length - 5}</span>
        )}
      </div>
      <hr />
      <div className="cycle-row">
        <span>
          <small>{t("dashboard.currentCycle")}</small>
          <b>{cycle.objective}</b>
        </span>
        <span>
          {brief
            ? `${responded} of ${complete!.total} have responded`
            : "Responses appear here as they arrive"}
        </span>
      </div>
      <div className="progress">
        <i
          style={{
            width: `${complete?.total ? (100 * responded) / complete.total : 0}%`,
          }}
        />
      </div>
      <div className="stat-row">
        <span>
          <b>{responded}</b>responded
        </span>
        <span>
          <b className="amber">{complete?.review_needed ?? 0}</b>need review
        </span>
        <span>
          <b className="red">{complete?.not_started ?? learners.length}</b>not
          started
        </span>
      </div>
      <button className="table-row full" onClick={onOpen}>
        <span>Open classroom</span>
        <ChevronRight size={17} />
      </button>
      {assignments.length > 0 && (
        <div className="mini-roster" aria-label="Learner participation">
          {assignments.slice(0, 5).map((assignment) => (
            <div key={assignment.id}>
              <span className="avatar">
                {initials(assignment.learner.display_name)}
              </span>
              <b>{assignment.learner.display_name}</b>
              <small>{assignment.state.replaceAll("_", " ")}</small>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
function ReviewCard({
  cycle,
  learners,
  onReview,
}: {
  cycle: Cycle;
  learners: Session["learners"];
  onReview: () => void;
}) {
  return (
    <section className="panel review-card">
      <span className="status-chip">{cycle.state.replaceAll("_", " ")}</span>
      <h2>
        {cycle.state === "review_ready"
          ? "Tomorrow's practice"
          : "Current practice"}
      </h2>
      <p>{learners.length} individual practice plans.</p>
      <dl>
        <div>
          <dt>
            <CircleHelp />
            Goal
          </dt>
          <dd>{cycle.objective}</dd>
        </div>
        <div>
          <dt>
            <ClipboardList />
            Practice
          </dt>
          <dd>{cycle.budget_minutes} min per learner</dd>
        </div>
        <div>
          <dt>
            <CalendarDays />
            Closes
          </dt>
          <dd>{dateTime(cycle.closes_at)}</dd>
        </div>
      </dl>
      <button className="button primary full" onClick={onReview}>
        {cycle.state === "review_ready" ? "Review & approve" : "Open cycle"}
      </button>
    </section>
  );
}
function NextLesson({ onOpen }: { onOpen: () => void }) {
  return (
    <section className="panel lesson-card">
      <img className="lesson-art" src="/art/tiza-return.png" alt="" />
      <h3>Plan your next lesson</h3>
      <p>Review the responses and choose an activity to open the next class.</p>
      <div className="fraction-sketch">
        <MathMark tex={String.raw`\frac{1}{2}`} />
        <MathMark tex={String.raw`\frac{1}{4}+\frac{1}{4}`} />
      </div>
      <button className="text-action" onClick={onOpen}>
        Open lesson brief <ChevronRight size={16} />
      </button>
    </section>
  );
}
function DeliveryStates({
  deliveries,
}: {
  deliveries: Array<{ id: string; state: string; last_error: string | null }>;
}) {
  const counts = deliveries.reduce<Record<string, number>>(
    (all, item) => ({ ...all, [item.state]: (all[item.state] ?? 0) + 1 }),
    {},
  );
  return (
    <section className="panel delivery-panel">
      <h3>{t("dashboard.delivery")}</h3>
      <p>
        {Object.entries(counts)
          .map(([state, count]) => `${count} ${state.replaceAll("_", " ")}`)
          .join(" · ") || "No deliveries yet."}
      </p>
      {deliveries.some((item) => item.last_error) && (
        <p className="form-error">
          A delivery needs attention. Practice participation stays separate.
        </p>
      )}
    </section>
  );
}
function EmptyCycle({
  onCreate,
  classroom,
}: {
  onCreate: () => void;
  classroom: string;
}) {
  return (
    <section className="empty-panel">
      <img className="empty-art" src="/art/tiza-practice.png" alt="" />
      <h2>Create your first practice cycle</h2>
      <p>
        {classroom} has no practice scheduled. Add a goal and choose when
        learners should finish.
      </p>
      <button className="button primary" onClick={onCreate}>
        <Plus />
        {t("actions.createCycle")}
      </button>
    </section>
  );
}
function PageLoading() {
  return (
    <div className="page-state">
      <LoaderCircle className="spin" />
      Loading your workspace…
    </div>
  );
}
function PageError({ error }: { error: Error | null }) {
  return (
    <div className="page-state">
      <CircleHelp />
      <b>We could not load this page.</b>
      <p>{error?.message ?? "Try refreshing the workspace."}</p>
      <button
        className="button secondary"
        onClick={() => queryClient.invalidateQueries()}
      >
        Try again
      </button>
    </div>
  );
}

function ClassroomPage({
  classroomId,
  onCreate,
  onReview,
  onSelect,
}: {
  classroomId: string;
  onCreate: () => void;
  onReview: (id: string) => void;
  onSelect: (id: string) => void;
}) {
  const [email, setEmail] = useState("");
  const [title, setTitle] = useState("");
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const invite = useMutation({
    mutationFn: () => api.invite(classroomId, email),
    onSuccess: (value) =>
      setInviteLink(`${location.origin}/invite/${value.invite_token}`),
  });
  const createClassroom = useMutation({
    mutationFn: () =>
      api.createClassroom({ title, language: "en", practice_minutes: 15 }),
    onSuccess: (value) => {
      onSelect(value.id);
      setTitle("");
    },
  });
  const classroom = useQuery({
    queryKey: ["classroom", classroomId],
    queryFn: () => api.classroom(classroomId),
  });
  if (classroom.isLoading) return <PageLoading />;
  if (classroom.isError || !classroom.data)
    return <PageError error={classroom.error} />;
  return (
    <>
      <Header crumb="Workspace / My classroom" />
      <section className="headline compact">
        <div>
          <p className="eyebrow">Your classroom</p>
          <h1>{classroom.data.title}</h1>
          <p>
            {classroom.data.learners.length} synthetic learners ·{" "}
            {classroom.data.practice_minutes} minute practice budget
          </p>
        </div>
        <span className="header-actions">
          <Dialog>
            <DialogTrigger asChild>
              <button className="button secondary">Create class</button>
            </DialogTrigger>
            <DialogContent className="dialog-content">
              <DialogTitle>Create a classroom</DialogTitle>
              <label>
                Class name
                <input
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </label>
              <button
                disabled={!title || createClassroom.isPending}
                onClick={() => createClassroom.mutate()}
              >
                Create classroom
              </button>
            </DialogContent>
          </Dialog>
          <button className="button primary" onClick={onCreate}>
            <Plus />
            Create cycle
          </button>
        </span>
      </section>
      <section className="two-column">
        <section className="panel">
          <h2>Learners</h2>
          <Dialog>
            <DialogTrigger asChild>
              <button className="text-action">Invite learner</button>
            </DialogTrigger>
            <DialogContent className="dialog-content">
              <DialogTitle>Invite a learner</DialogTitle>
              <label>
                Email
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </label>
              <button
                disabled={!email || invite.isPending}
                onClick={() => invite.mutate()}
              >
                Create single-use invitation
              </button>
              {inviteLink && <p className="invite-link">{inviteLink}</p>}
              {invite.error && <ErrorText error={invite.error} />}
            </DialogContent>
          </Dialog>
          <div className="learner-list">
            {classroom.data.learners.map((learner) => (
              <div key={learner.id} className="learner-line">
                <span className="avatar">{initials(learner.display_name)}</span>
                <span>
                  <b>{learner.display_name}</b>
                  <small>{learner.email}</small>
                </span>
              </div>
            ))}
          </div>
        </section>
        <section className="panel">
          <h2>Practice cycles</h2>
          {classroom.data.cycles.length ? (
            classroom.data.cycles.map((cycle) => (
              <button
                className="cycle-list-item"
                key={cycle.id}
                onClick={() => onReview(cycle.id)}
              >
                <span>
                  <b>{cycle.objective}</b>
                  <small>
                    {cycle.state.replaceAll("_", " ")} · closes{" "}
                    {dateTime(cycle.closes_at)}
                  </small>
                </span>
                <ChevronRight />
              </button>
            ))
          ) : (
            <p className="muted">No cycles yet.</p>
          )}
        </section>
      </section>
    </>
  );
}

function CreateCycle({
  classroomId,
  onDone,
  onCancel,
}: {
  classroomId: string;
  onDone: (id: string) => void;
  onCancel: () => void;
}) {
  const [objective, setObjective] = useState(""),
    [closesAt, setClosesAt] = useState(""),
    [budget, setBudget] = useState(12),
    [file, setFile] = useState<File | null>(null),
    [cycle, setCycle] = useState<Cycle | null>(null),
    [candidates, setCandidates] = useState<
      Array<{ id: string; title: string; reference: string }>
    >([]),
    [selected, setSelected] = useState<string[]>([]);
  const create = useMutation({
      mutationFn: api.createCycle,
      onSuccess: setCycle,
    }),
    upload = useMutation({
      mutationFn: ({ id, file }: { id: string; file: File }) =>
        api.addMaterial(id, file),
      onSuccess: (data) => {
        setCandidates(data.concept_candidates);
        setSelected(data.concept_candidates.map((c) => c.id));
      },
    }),
    confirm = useMutation({
      mutationFn: () => api.confirmConcepts(cycle!.id, selected),
      onSuccess: () => api.prepare(cycle!.id).then(() => onDone(cycle!.id)),
    });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (closesAt)
      create.mutate({
        classroom_id: classroomId,
        objective,
        closes_at: new Date(closesAt).toISOString(),
        budget_minutes: budget,
      });
  };
  const extract = () =>
    upload.mutate({
      id: cycle!.id,
      file:
        file ??
        new File([objective], "objective.md", { type: "text/markdown" }),
    });
  return (
    <>
      <Header crumb="Workspace / Create a practice cycle" />
      <section className="form-wrap">
        <div>
          <p className="eyebrow">Close today’s class</p>
          <h1>
            {cycle
              ? "Confirm the learning focus"
              : "Set up a small practice cycle"}
          </h1>
          <p className="muted">
            Tiza only works from the objective, concepts and material you
            approve.
          </p>
        </div>
        {!cycle ? (
          <form className="panel cycle-form" onSubmit={submit}>
            <label>
              What should learners be able to do next?
              <textarea
                required
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                placeholder="For the next session I want them to add fractions with unlike denominators."
              />
            </label>
            <div className="field-pair">
              <label>
                Closes at
                <input
                  required
                  type="datetime-local"
                  value={closesAt}
                  onChange={(e) => setClosesAt(e.target.value)}
                />
              </label>
              <label>
                Practice budget (minutes)
                <input
                  type="number"
                  min="5"
                  max="45"
                  value={budget}
                  onChange={(e) => setBudget(Number(e.target.value))}
                />
              </label>
            </div>
            <label>
              Lesson material{" "}
              <span className="label-note">
                optional · .txt, .md or text PDF
              </span>
              <input
                type="file"
                accept=".txt,.md,.pdf,text/markdown,text/plain,application/pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
            {create.error && <ErrorText error={create.error} />}
            <div className="form-actions">
              <button type="button" className="button quiet" onClick={onCancel}>
                Cancel
              </button>
              <button className="button primary" disabled={create.isPending}>
                {create.isPending && <LoaderCircle className="spin" />}Continue
              </button>
            </div>
          </form>
        ) : !candidates.length ? (
          <section className="panel upload-panel">
            <h2>Add your material</h2>
            <p>
              Use a text-layer PDF, Markdown, or text file. Or use the objective
              alone to propose a narrow concept list.
            </p>
            <input
              type="file"
              accept=".txt,.md,.pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            {upload.error && <ErrorText error={upload.error} />}
            <button
              className="button primary"
              disabled={upload.isPending}
              onClick={extract}
            >
              {upload.isPending && <LoaderCircle className="spin" />}
              {file ? "Extract concepts" : "Use objective and extract concepts"}
            </button>
          </section>
        ) : (
          <section className="panel concepts-panel">
            <h2>Check the concepts before planning</h2>
            <p>
              These came from your material. Tiza will not add a topic without
              your confirmation.
            </p>
            {candidates.map((candidate) => (
              <label className="concept-option" key={candidate.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(candidate.id)}
                  onChange={() =>
                    setSelected((value) =>
                      value.includes(candidate.id)
                        ? value.filter((id) => id !== candidate.id)
                        : [...value, candidate.id],
                    )
                  }
                />
                <span>
                  <b>{candidate.title}</b>
                  <small>{candidate.reference}</small>
                </span>
              </label>
            ))}
            {confirm.error && <ErrorText error={confirm.error} />}
            <button
              className="button primary"
              disabled={!selected.length || confirm.isPending}
              onClick={() => confirm.mutate()}
            >
              {confirm.isPending && <LoaderCircle className="spin" />}Confirm
              and prepare practice
            </button>
          </section>
        )}
      </section>
    </>
  );
}

function ReviewPage({
  cycleId,
  onPublished,
  onBrief,
}: {
  cycleId: string;
  onPublished: (assignment: string) => void;
  onBrief: () => void;
}) {
  const draft = useQuery({
    queryKey: ["draft", cycleId],
    queryFn: () => api.draft(cycleId),
    retry: (count, error) =>
      error instanceof ApiError && error.status === 409 && count < 40,
    retryDelay: 500,
    refetchInterval: (query) =>
      query.state.data?.cycle.state === "preparing" ? 1200 : false,
  });
  const catalog = useQuery({
    queryKey: ["exercise-catalog"],
    queryFn: api.catalog,
  });
  const [approval, setApproval] = useState<string | null>(null);
  const [closesAt, setClosesAt] = useState("");
  const [budget, setBudget] = useState<number | null>(null);
  const change = useMutation({
      mutationFn: (
        items: Array<{
          id: string;
          excluded?: boolean;
          exercise_ids?: string[];
        }>,
      ) => api.updateDraft(cycleId, draft.data!.cycle.version, items),
      onSuccess: (value) => {
        queryClient.setQueryData(["draft", cycleId], value);
        setApproval(null);
      },
    }),
    approve = useMutation({
      mutationFn: () =>
        api.approve(
          cycleId,
          draft.data!.cycle.version,
          draft.data!.assignments.filter((a) => !a.excluded).map((a) => a.id),
        ),
      onSuccess: (data) => setApproval(data.id),
    }),
    publish = useMutation({
      mutationFn: () =>
        api.publish(cycleId, approval!, draft.data!.cycle.version),
      onSuccess: (result) => {
        queryClient.invalidateQueries({ queryKey: ["dashboard"] });
        const first = result.assignments.find((item) => item.published);
        if (first) onPublished(first.id);
        else onBrief();
      },
    });
  const deadline = useMutation({
    mutationFn: () =>
      api.updateCycle(cycleId, draft.data!.cycle.version, {
        closes_at: new Date(closesAt).toISOString(),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["draft", cycleId] });
      setApproval(null);
    },
  });
  const practiceBudget = useMutation({
    mutationFn: () =>
      api.updateCycle(cycleId, draft.data!.cycle.version, {
        budget_minutes: budget ?? draft.data!.cycle.budget_minutes,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["draft", cycleId] });
      setApproval(null);
      setBudget(null);
    },
  });
  if (
    draft.isLoading ||
    draft.isFetching ||
    draft.data?.cycle.state === "preparing"
  )
    return (
      <>
        <Header crumb="Workspace / Practice cycles" />
        <AgentActivity cycleId={cycleId} />
      </>
    );
  if (draft.isError || !draft.data) return <PageError error={draft.error} />;
  const data = draft.data;
  return (
    <>
      <Header crumb="Workspace / Review practice" />
      <section className="headline compact">
        <div>
          <h1>Review {data.assignments.length} practice plans</h1>
          <p>
            {data.cycle.objective} · {data.cycle.budget_minutes} minutes per
            learner
          </p>
        </div>
        <span className="status-chip">Version {data.cycle.version}</span>
      </section>
      <AgentActivity cycleId={cycleId} />
      <section className="review-layout">
        <section className="panel assignment-table">
          <div className="table-heading">
            <span>Learner</span>
            <span>Why this path</span>
            <span>Practice</span>
            <span />
          </div>
          {data.assignments.map((assignment) => (
            <DraftRow
              key={assignment.id}
              assignment={assignment}
              catalog={catalog.data ?? []}
              onExclude={() =>
                change.mutate([
                  { id: assignment.id, excluded: !assignment.excluded },
                ])
              }
              onReplace={(itemId, exerciseId) =>
                change.mutate([
                  {
                    id: assignment.id,
                    exercise_ids: assignment.items.map((item) =>
                      item.id === itemId ? exerciseId : item.exercise.id,
                    ),
                  },
                ])
              }
            />
          ))}
        </section>
        <aside className="panel approval-panel">
          <h2>Review this version</h2>
          <p className="approval-intro">
            Approval is tied to these learners and this exact version. Editing a
            path invalidates it.
          </p>
          <div className="approval-total">
            <b>{data.assignments.filter((a) => !a.excluded).length}</b>
            <span>learners included</span>
          </div>
          <div className="review-settings">
            <div className="review-setting">
              <label className="deadline-edit">
                Change closing time
                <input
                  type="datetime-local"
                  value={closesAt}
                  onChange={(event) => setClosesAt(event.target.value)}
                />
              </label>
              <button
                className="button secondary deadline-save"
                disabled={!closesAt || deadline.isPending}
                onClick={() => deadline.mutate()}
              >
                Save
              </button>
            </div>
            <div className="review-setting">
              <label className="deadline-edit">
                Practice budget (minutes)
                <input
                  type="number"
                  min="5"
                  max="60"
                  value={budget ?? data.cycle.budget_minutes}
                  onChange={(event) => setBudget(Number(event.target.value))}
                />
              </label>
              <button
                className="button secondary deadline-save"
                disabled={
                  budget === null ||
                  budget === data.cycle.budget_minutes ||
                  practiceBudget.isPending
                }
                onClick={() => practiceBudget.mutate()}
              >
                Save
              </button>
            </div>
          </div>
          {deadline.error && <ErrorText error={deadline.error} />}
          {practiceBudget.error && <ErrorText error={practiceBudget.error} />}
          {approve.error && <ErrorText error={approve.error} />}{" "}
          {publish.error && <ErrorText error={publish.error} />}{" "}
          <div className="approval-footer">
            {!approval ? (
              <button
                className="button primary full"
                onClick={() => approve.mutate()}
                disabled={
                  approve.isPending ||
                  !data.assignments.some((a) => !a.excluded)
                }
              >
                {approve.isPending && <LoaderCircle className="spin" />}Approve
                this version
              </button>
            ) : (
              <button
                className="button primary full"
                onClick={() => publish.mutate()}
                disabled={publish.isPending}
              >
                {publish.isPending && <LoaderCircle className="spin" />}Approve
                & send
              </button>
            )}
            <p className="tiny">
              Delivery is reported after the provider accepts it. Publishing
              never marks practice complete.
            </p>
          </div>
        </aside>
      </section>
    </>
  );
}
function DraftRow({
  assignment,
  catalog,
  onExclude,
  onReplace,
}: {
  assignment: DraftAssignment;
  catalog: DraftAssignment["items"][number]["exercise"][];
  onExclude: () => void;
  onReplace: (itemId: string, exerciseId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`draft-row ${assignment.excluded ? "excluded" : ""}`}>
      <button className="draft-main" onClick={() => setOpen(!open)}>
        <span className="avatar">
          {initials(assignment.learner.display_name)}
        </span>
        <span className="draft-person">
          <b>{assignment.learner.display_name}</b>
        </span>
        <small className="draft-reason">{assignment.reason}</small>
        <span>{assignment.estimated_minutes} min</span>
        <ChevronRight className={open ? "rotate" : ""} />
      </button>
      <button className="exclude" onClick={onExclude}>
        {assignment.excluded ? "Include" : "Exclude"}
      </button>
      {open && (
        <div className="exercise-preview">
          <p className="draft-reason-full">{assignment.reason}</p>
          {assignment.items.map((item) => (
            <div key={item.id}>
              <span>
                {item.position}. {item.exercise.kind.replace("_", " ")}
              </span>
              <p>{item.exercise.prompt}</p>
              <small>
                {item.exercise.source ?? "Reviewed fraction bank"} ·{" "}
                {item.exercise.estimated_minutes} min
              </small>
              <label className="exercise-replace">
                Replace exercise
                <select
                  value={item.exercise.id}
                  onChange={(event) => onReplace(item.id, event.target.value)}
                >
                  {catalog
                    .filter(
                      (candidate) =>
                        candidate.concept_id === item.exercise.concept_id,
                    )
                    .map((candidate) => (
                      <option key={candidate.id} value={candidate.id}>
                        {candidate.prompt}
                      </option>
                    ))}
                </select>
              </label>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function BriefPage({
  cycleId,
  onReview,
}: {
  cycleId: string | null;
  onReview: (id: string) => void;
}) {
  const brief = useQuery({
    queryKey: ["brief", cycleId],
    queryFn: () => api.brief(cycleId!),
    enabled: !!cycleId,
  });
  if (!cycleId)
    return (
      <>
        <Header crumb="Workspace / Next lesson" />
        <EmptyCycle classroom="Your classroom" onCreate={() => {}} />
      </>
    );
  if (brief.isLoading) return <PageLoading />;
  if (brief.isError || !brief.data) return <PageError error={brief.error} />;
  return <BriefView brief={brief.data} onReview={() => onReview(cycleId)} />;
}
function BriefView({
  brief,
  onReview,
}: {
  brief: Brief;
  onReview: () => void;
}) {
  const completion = brief.completion;
  return (
    <>
      <Header crumb="Workspace / Next lesson" />
      <section className="headline compact">
        <div>
          <p className="eyebrow">Lesson brief</p>
          <h1>Plan your next lesson</h1>
          <p>Every observation below links to recorded attempts.</p>
        </div>
        <button className="button secondary" onClick={onReview}>
          Review practice
        </button>
      </section>
      <section className="brief-grid">
        <section className="panel">
          <h2>Participation</h2>
          <div className="big-number">
            {completion.completed}
            <span>of {completion.total} completed</span>
          </div>
          <div className="stat-row">
            <span>
              <b>{completion.in_progress}</b>in progress
            </span>
            <span>
              <b className="amber">{completion.review_needed}</b>need review
            </span>
            <span>
              <b className="red">{completion.not_started}</b>not started
            </span>
          </div>
        </section>
        <section className="panel">
          <h2>Start here</h2>
          {brief.opening_activity ? (
            <>
              <b>{brief.opening_activity.title}</b>
              <p>{brief.opening_activity.reason}</p>
            </>
          ) : (
            <p className="muted">
              Tiza will suggest an opening activity after it has practice
              responses to support it.
            </p>
          )}
        </section>
        <section className="panel full-span">
          <h2>What the attempts show</h2>
          {brief.patterns.length ? (
            brief.patterns.map((pattern) => (
              <article className="evidence-row" key={pattern.text}>
                <span className="check-mark small">
                  <Check />
                </span>
                <div>
                  <b>{pattern.text}</b>
                  <small>
                    {pattern.attempt_ids.length} supporting attempt
                    {pattern.attempt_ids.length === 1 ? "" : "s"}
                  </small>
                </div>
                <ChevronRight />
                <EvidencePanel attemptIds={pattern.attempt_ids} />
              </article>
            ))
          ) : (
            <p className="muted">
              There are no response patterns yet. Absence of a response is kept
              separate from an incorrect answer.
            </p>
          )}
        </section>
        <PendingReviews cycleId={brief.cycle_id} />
      </section>
    </>
  );
}

function PracticePage({
  assignmentId,
  onDone,
  onBack,
}: {
  assignmentId: string;
  onDone: () => void;
  onBack?: () => void;
}) {
  const assignment = useQuery({
    queryKey: ["assignment", assignmentId],
    queryFn: () => api.assignment(assignmentId),
  });
  const [answer, setAnswer] = useState(""),
    [hint, setHint] = useState<string | null>(null),
    [result, setResult] = useState<{
      feedback: string;
      correct?: boolean;
      review?: boolean;
    } | null>(null),
    [clientKey, setClientKey] = useState(() => crypto.randomUUID());
  const hintMutation = useMutation({
      mutationFn: (itemId: string) => api.hint(assignmentId, itemId),
      onSuccess: (value) => setHint(value.hint),
    }),
    attempt = useMutation({
      mutationFn: (input: {
        item_id: string;
        response: string;
        client_key: string;
      }) => api.submitAttempt(assignmentId, input),
      onSuccess: (value) => {
        setResult({
          feedback: value.feedback,
          correct: value.result === "correct",
          review: value.result === "review_needed",
        });
        queryClient.invalidateQueries({
          queryKey: ["assignment", assignmentId],
        });
        onDone();
      },
    });
  if (assignment.isLoading) return <PageLoading />;
  if (assignment.isError || !assignment.data)
    return <PageError error={assignment.error} />;
  const data = assignment.data,
    item = data.items.find((value) => !value.attempt);
  if (!item)
    return (
      <main className="practice-screen">
        <p className="eyebrow">Practice complete</p>
        <h1>
          {data.state === "review_needed"
            ? "Your teacher will review one response."
            : "You’re all caught up."}
        </h1>
        <p>Your responses are saved for your teacher.</p>
      </main>
    );
  const save = () =>
    attempt.mutate({
      item_id: item.id,
      response: answer,
      client_key: clientKey,
    });
  const next = () => {
    setAnswer("");
    setHint(null);
    setResult(null);
    setClientKey(crypto.randomUUID());
    queryClient.invalidateQueries({ queryKey: ["assignment", assignmentId] });
  };
  return (
    <main className="practice-screen">
      <header className="practice-header">
        <span className="wordmark">
          <span className="story-brand-mark" aria-hidden="true">
            t
          </span>
          tiza
        </span>
        <span>
          {data.progress.answered + 1} of {data.progress.total}
        </span>
        {onBack && (
          <button className="text-action" onClick={onBack}>
            Return to teacher view
          </button>
        )}
      </header>
      <div className="practice-progress">
        <i
          style={{
            width: `${(data.progress.answered / data.progress.total) * 100}%`,
          }}
        />
      </div>
      <article className="practice-card">
        <p className="eyebrow">Your goal</p>
        <h1>{data.cycle.objective}</h1>
        <hr />
        <p className="question">{item.exercise.prompt}</p>
        {item.exercise.options ? (
          <div className="options">
            {item.exercise.options.map((option) => (
              <button
                type="button"
                className={answer === option.id ? "selected" : ""}
                onClick={() => setAnswer(option.id)}
                key={option.id}
              >
                {option.text}
              </button>
            ))}
          </div>
        ) : (
          <label className="answer-field">
            <span className="sr-only">Your answer</span>
            <input
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder={
                item.exercise.kind === "short_answer" ||
                item.exercise.kind === "short"
                  ? "Write a short explanation"
                  : "Type your answer"
              }
            />
          </label>
        )}
        {hint ? (
          <div className="hint">
            <CircleHelp size={17} />
            {hint}
          </div>
        ) : (
          <button
            className="text-action"
            disabled={hintMutation.isPending}
            onClick={() => hintMutation.mutate(item.id)}
          >
            <CircleHelp size={17} />
            Need a hint?
          </button>
        )}
        {result ? (
          <div className={`feedback ${result.correct ? "correct" : "review"}`}>
            <p role="status">Your answer was saved.</p>
            <b>
              {result.correct
                ? "Nice work."
                : result.review
                  ? "Your teacher will review this."
                  : "Keep practising."}
            </b>
            <p>{result.feedback}</p>
            <button className="button primary" onClick={next}>
              Continue
            </button>
          </div>
        ) : (
          <button
            className="button primary full"
            disabled={!answer || attempt.isPending}
            onClick={save}
          >
            {attempt.isPending && <LoaderCircle className="spin" />}
            {t("practice.save")}
          </button>
        )}
        {attempt.error && <ErrorText error={attempt.error} />}
      </article>
      <p className="save-note">
        Answers are saved only when you see a confirmation.
      </p>
    </main>
  );
}
function ErrorText({ error }: { error: Error | null }) {
  return error ? (
    <p className="form-error" role="alert">
      {error.message}
    </p>
  ) : null;
}
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={queryClient}>
    <App />
  </QueryClientProvider>,
);
