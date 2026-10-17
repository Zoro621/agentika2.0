import { lazy, Suspense, useEffect, useRef, useState, Component } from "react";
import type { ReactNode, DragEvent } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import * as Dialog from "@radix-ui/react-dialog";
import * as m from "motion/react-m";
import { AnimatePresence, useReducedMotion } from "motion/react";
import {
  ArrowUpRight,
  ArrowRight,
  Upload,
  Plus,
  ChevronRight,
  ChevronDown,
  Check,
  CheckCheck,
  X,
  FileText,
  FileCode2,
  Database,
  Braces,
  GitBranch,
  Layers3,
  ScanLine,
  Activity,
  Settings2,
  Download,
  Search,
  ShieldCheck,
  AlertTriangle,
  Info,
  Loader2,
  Play,
  Pause,
  Network,
  Eye,
  RotateCcw,
  PanelLeftClose,
  ExternalLink,
  CheckCircle2,
  Clock3,
  Command,
  Trash2,
  BookOpen,
  Orbit,
  FlaskConical,
  Sparkles,
  Link2,
  FolderOpen,
  HelpCircle,
  WifiOff,
  ChevronLeft,
} from "lucide-react";
import { api } from "./api";
import { useUI } from "./store";
import type {
  Case,
  Artifact,
  Anchor,
  Finding,
  Graph,
  Activity as ActivityItem,
  Question,
  Capabilities,
  Provider,
  ReviewStatus,
  Run,
} from "./types";
import { activeStates, humanize } from "./types";
import { formatMetric } from "./format";
import { clusteredGraph } from "./graph";
import VirtualList from "./VirtualList";
const Scene = lazy(() => import("./Scene"));

const RunChart = lazy(() => import("./RunChart"));
const PdfSource = lazy(() => import("./PdfSource"));
const icons: Record<string, typeof FileText> = {
  paper: FileText,
  code: FileCode2,
  data: Database,
  results: Activity,
  configuration: Braces,
  documentation: BookOpen,
  claim: Sparkles,
  finding: AlertTriangle,
  decision: HelpCircle,
  execution: FlaskConical,
};
const stageNames = [
  "Inspecting",
  "Extracting",
  "Mapping",
  "Checking",
  "Investigating",
];

class GraphicsBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <div className="scene-fallback">
        <Orbit size={100} strokeWidth={0.5} />
      </div>
    ) : (
      this.props.children
    );
  }
}
function Logo({ small = false }: { small?: boolean }) {
  return (
    <span className={`brand ${small ? "brand-small" : ""}`}>
      <span className="brand-mark">
        <Orbit size={26} strokeWidth={1.6} />
        <i />
      </span>
      <span>
        claim<span className="brand-light">breaker</span>
        <sup>β</sup>
      </span>
    </span>
  );
}
function Status({ value }: { value: string }) {
  return (
    <span
      className={`status status-${activeStates.has(value) ? "active" : value === "failed" ? "error" : value === "awaiting_input" ? "question" : "done"}`}
    >
      <i />
      {humanize(value)}
    </span>
  );
}
function KindIcon({ kind, size = 16 }: { kind: string; size?: number }) {
  const Icon = icons[kind] || FileText;
  return <Icon size={size} />;
}
function Empty({
  icon: Icon = ScanLine,
  title,
  children,
}: {
  icon?: typeof ScanLine;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty-state">
      <Icon size={30} strokeWidth={1.2} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function ErrorNotice({
  message,
  dismiss,
}: {
  message: string;
  dismiss: () => void;
}) {
  return (
    <div className="error-notice" role="alert">
      <AlertTriangle size={17} />
      <span>{message}</span>
      <button onClick={dismiss} aria-label="Dismiss error">
        <X size={16} />
      </button>
    </div>
  );
}

function SettingsModal({
  capabilities,
  provider,
  onProvider,
}: {
  capabilities?: Capabilities;
  provider: Provider;
  onProvider: (v: Provider) => void;
}) {
  const { graphics, toggleGraphics } = useUI();
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <button className="icon-button" aria-label="Investigation settings">
          <Settings2 size={19} />
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content className="modal settings-modal">
          <div className="modal-heading">
            <div>
              <span className="eyebrow">YOUR OBSERVATORY</span>
              <Dialog.Title>Investigation settings</Dialog.Title>
            </div>
            <Dialog.Close className="icon-button" aria-label="Close settings">
              <X size={20} />
            </Dialog.Close>
          </div>
          <Dialog.Description className="muted">
            Choose how new investigations interpret evidence. Existing cases
            keep their selected provider.
          </Dialog.Description>
          <label className="field-label" htmlFor="provider">
            Analysis provider
          </label>
          <select
            id="provider"
            value={provider}
            onChange={(e) => onProvider(e.target.value as Provider)}
          >
            <option value="auto">Automatic · hosted, then local</option>
            <option value="openai">OpenAI · local fallback if available</option>
            <option value="ollama">Ollama · local model</option>
            <option value="deterministic">Deterministic checks only</option>
          </select>
          <div className="capability-list">
            <div>
              <span>Hosted model</span>
              <b className={capabilities?.openai.configured ? "mint" : "muted"}>
                {capabilities?.openai.configured
                  ? "Configured"
                  : "Not connected"}
              </b>
            </div>
            <div>
              <span>Local model</span>
              <b className={capabilities?.ollama.available ? "mint" : "muted"}>
                {capabilities?.ollama.available
                  ? capabilities.ollama.model
                  : "Not connected"}
              </b>
            </div>
            <div>
              <span>Isolated execution</span>
              <b className={capabilities?.runner.available ? "mint" : "muted"}>
                {capabilities?.runner.available
                  ? capabilities.runner.provider
                  : "Not available"}
              </b>
            </div>
          </div>
          <p className="settings-note">
            <Info size={15} />
            Without a connected model, source discovery and deterministic checks
            still work. Contextual claim coverage is limited.
          </p>
          <button className="toggle-row" onClick={toggleGraphics}>
            <span>
              <b>Spatial graphics</b>
              <small>3D views with an accessible 2D alternative</small>
            </span>
            <span
              className={`toggle ${graphics ? "on" : ""}`}
              aria-label={graphics ? "Enabled" : "Disabled"}
            >
              <i />
            </span>
          </button>
          {capabilities?.offline && (
            <p className="settings-note">
              <WifiOff size={15} />
              Offline mode. Upload local source archives; online acquisition is
              disabled.
            </p>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export default function App() {
  const queryClient = useQueryClient();
  const [caseId, setCaseId] = useState<string | null>(
    new URLSearchParams(location.search).get("case"),
  );
  const [provider, setProvider] = useState<Provider>("auto");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const cap = useQuery({
    queryKey: ["capabilities"],
    queryFn: api.capabilities,
    staleTime: 30000,
  });
  const recent = useQuery({ queryKey: ["recent"], queryFn: api.recent });
  const samples = useQuery({ queryKey: ["samples"], queryFn: api.samples });
  const caseQuery = useQuery({
    queryKey: ["case", caseId],
    queryFn: () => api.case(caseId!),
    enabled: !!caseId,
    refetchInterval: (q) =>
      q.state.data && activeStates.has(q.state.data.status) ? 1600 : false,
  });
  const open = (id: string | null) => {
    setCaseId(id);
    useUI.getState().setSelectedFinding(null);
    useUI.getState().setView("overview");
    history.pushState({}, "", id ? `?case=${id}` : location.pathname);
    setActivity([]);
    setError("");
    queryClient.invalidateQueries({ queryKey: ["recent"] });
  };
  useEffect(() => {
    const fn = () => {
      setCaseId(new URLSearchParams(location.search).get("case"));
      setActivity([]);
    };
    addEventListener("popstate", fn);
    return () => removeEventListener("popstate", fn);
  }, []);
  useEffect(() => {
    if (!caseId) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const close = api.events(caseId, (e) => {
      setActivity((a) =>
        a.some((x) => x.id === e.id) ? a : [...a.slice(-1999), e],
      );
      if (!timer)
        timer = setTimeout(() => {
          queryClient.invalidateQueries({ queryKey: ["case", caseId] });
          timer = undefined;
        }, 400);
    });
    return () => {
      close();
      if (timer) clearTimeout(timer);
    };
  }, [caseId, queryClient]);
  const investigate = async (files: File[], github: string) => {
    if (!files.length && !github.trim()) {
      setError("Drop a project ZIP or PDF, or add a GitHub repository.");
      return;
    }
    try {
      setError("");
      setBusy("Preparing a private investigation");
      setUploadProgress(0);
      const c = await api.create(provider);
      for (const file of files) {
        setBusy(`Uploading ${file.name}`);
        await api.upload(c.id, file, setUploadProgress);
      }
      if (github.trim()) {
        setBusy("Acquiring a pinned repository snapshot");
        await api.github(c.id, github.trim());
      }
      await api.start(c.id);
      open(c.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  const sample = async (kind: string) => {
    try {
      setError("");
      setBusy("Computing the synthetic sample and preparing its evidence");
      const c = await api.create(provider);
      await api.sample(c.id, kind);
      open(c.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <button
          className="brand-button"
          onClick={() => open(null)}
          aria-label="ClaimBreaker home"
        >
          <Logo />
        </button>
        <div className="header-center">
          <span className="header-line" />
          THE EVIDENCE OBSERVATORY<span className="version-label">V.01</span>
        </div>
        <div className="header-actions">
          <span className="connection-label">
            <i className={cap.data ? "connected" : ""} />
            {cap.data?.offline
              ? "LOCAL MODE"
              : cap.data
                ? "SYSTEM ONLINE"
                : "CONNECTING"}
          </span>
          <SettingsModal
            capabilities={cap.data}
            provider={provider}
            onProvider={setProvider}
          />
        </div>
      </header>
      {error && <ErrorNotice message={error} dismiss={() => setError("")} />}
      {cap.error && !caseId && (
        <div className="backend-notice">
          <WifiOff size={16} />
          The analysis service is unreachable. Start the backend to investigate
          a project.
        </div>
      )}
      <AnimatePresence mode="wait">
        {!caseId ? (
          <m.main
            id="main"
            key="intake"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.25 }}
          >
            <Intake
              busy={busy}
              progress={uploadProgress}
              onInvestigate={investigate}
              onSample={sample}
              samples={samples.data || []}
              recent={recent.data || []}
              open={open}
            />
          </m.main>
        ) : caseQuery.data ? (
          <m.main
            id="main"
            className="workspace"
            key="workspace"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <Workspace
              data={caseQuery.data}
              activity={activity}
              capabilities={cap.data}
              onHome={() => open(null)}
              onError={setError}
            />
          </m.main>
        ) : (
          <main id="main">
            <Empty
              icon={caseQuery.error ? AlertTriangle : Loader2}
              title={
                caseQuery.error
                  ? "Investigation unavailable"
                  : "Opening your investigation"
              }
            >
              {caseQuery.error ? (
                <>
                  <span>{(caseQuery.error as Error).message}</span>
                  <button
                    className="button secondary"
                    onClick={() => open(null)}
                  >
                    Return to observatory
                  </button>
                </>
              ) : (
                "Retrieving your private evidence snapshot."
              )}
            </Empty>
          </main>
        )}
      </AnimatePresence>
      <footer className={`footer ${caseId ? "workspace-footer" : ""}`}>
        <span>
          <span className="footer-dot" /> HUMAN JUDGMENT. MACHINE PRECISION.
        </span>
        <span>
          Built for Agentika · Alternate Clouds <ArrowUpRight size={12} />
        </span>
      </footer>
    </div>
  );
}

function Intake({
  busy,
  progress,
  onInvestigate,
  onSample,
  samples,
  recent,
  open,
}: {
  busy: string;
  progress: number;
  onInvestigate: (files: File[], url: string) => void;
  onSample: (kind: string) => void;
  samples: {
    id: string;
    title: string;
    subtitle: string;
    tags: string[];
    description: string;
  }[];
  recent: { id: string; title: string; status: string }[];
  open: (id: string) => void;
}) {
  const [files, setFiles] = useState<File[]>([]),
    [github, setGithub] = useState(""),
    [showGithub, setShowGithub] = useState(false),
    [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const [fileError, setFileError] = useState("");
  const { graphics } = useUI();
  const reduced = useReducedMotion();
  const accept = (incoming: FileList | File[]) => {
    const all = Array.from(incoming);
    const valid = all.filter(
      (f) =>
        /\.(zip|pdf)$/i.test(f.name) &&
        f.size <= (f.name.toLowerCase().endsWith(".pdf") ? 25 : 50) * 1024 ** 2,
    );
    setFiles(valid);
    setFileError(
      valid.length < all.length
        ? "Select ZIP files up to 50 MB or PDFs up to 25 MB. Other files were not accepted."
        : "",
    );
  };
  const drop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    accept(event.dataTransfer.files);
  };
  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <m.div
            className="hero-kicker"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <span className="kicker-dot" />
            RESEARCH, UNDER CROSS-EXAMINATION
            <span className="kicker-arrow">↗</span>
          </m.div>
          <h1>
            Extraordinary claims.
            <br />
            <em>Inspectable evidence.</em>
          </h1>
          <p className="hero-description">
            Put your findings to the test. An AI investigator that connects your
            paper, code, and results—
            <strong>with your judgment at the center.</strong>
          </p>
          <div className="hero-principles">
            <span>
              <Link2 size={14} />
              Source-linked findings
            </span>
            <span>
              <ShieldCheck size={14} />
              Private by default
            </span>
            <span>
              <FlaskConical size={14} />
              Real checks
            </span>
          </div>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="orbital-grid" />
          {graphics && !reduced ? (
            <GraphicsBoundary>
              <Suspense fallback={<div className="scene-loading" />}>
                <Scene hero />
              </Suspense>
            </GraphicsBoundary>
          ) : (
            <div className="scene-fallback">
              <div className="fallback-orbit" />
              <div className="fallback-sheet">
                <span>RESEARCH</span>
                <i />
                <i />
                <i />
                <b>FOLLOW THE EVIDENCE</b>
              </div>
            </div>
          )}
          <div className="art-label art-label-top">
            <span className="mint-dot" /> CLAIM → EVIDENCE
          </div>
          <div className="art-label art-label-bottom">
            <span className="coordinate">01 / OBSERVE</span>
            <span>Every finding has a source.</span>
          </div>
        </div>
      </section>
      <section className="launch-section">
        <div className="section-index">
          <span>01 / BEGIN AN INVESTIGATION</span>
          <span className="mono subtle">ZIP · PDF · GITHUB</span>
        </div>
        <form
          className="launch-panel"
          onSubmit={(e) => {
            e.preventDefault();
            onInvestigate(files, github);
          }}
        >
          <div
            className={`dropzone ${dragging ? "dragging" : ""} ${files.length ? "has-files" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={drop}
          >
            <input
              ref={input}
              id="project-files"
              tabIndex={-1}
              aria-hidden="true"
              type="file"
              accept=".zip,.pdf"
              multiple
              onChange={(e) => e.target.files && accept(e.target.files)}
              className="sr-only"
            />
            <button
              className="drop-content"
              type="button"
              aria-label={
                files.length ? "Change selected research files" : "Browse files"
              }
              onClick={() => input.current?.click()}
              disabled={!!busy}
            >
              <span className="upload-icon">
                <Upload size={22} strokeWidth={1.4} />
                <Plus className="upload-plus" size={11} />
              </span>
              <span className="drop-title">
                {files.length
                  ? `${files.length} source${files.length > 1 ? "s" : ""} ready to investigate`
                  : "Drop your research here"}
                <span className="drop-subtitle">
                  {files.length ? (
                    files.map((f) => f.name).join(" + ")
                  ) : (
                    <>
                      A project ZIP or paper PDF. We’ll find the evidence
                      inside.
                    </>
                  )}
                </span>
              </span>
              <span className="browse-label">
                {files.length ? "CHANGE FILES" : "BROWSE FILES"}
                <ArrowUpRight size={16} />
              </span>
            </button>
            <div className="drop-bottom">
              <span>Up to 50 MB · No manual file mapping</span>
              <button
                type="button"
                onClick={() => setShowGithub(!showGithub)}
                className="text-button"
              >
                <GitBranch size={14} />{" "}
                {showGithub ? "Hide repository" : "Add GitHub repository"}
                <Plus size={13} />
              </button>
            </div>
          </div>
          {showGithub && (
            <m.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              className="github-input"
            >
              <GitBranch size={17} />
              <input
                aria-label="GitHub repository URL"
                type="url"
                placeholder="https://github.com/owner/research-project"
                value={github}
                onChange={(e) => setGithub(e.target.value)}
              />
            </m.div>
          )}
          <div className="launch-actions">
            <p>
              <ScanLine size={15} />
              Discover. Trace. Test. <span>You decide what it means.</span>
            </p>
            <button
              className="button primary"
              disabled={!!busy || (!files.length && !github.trim())}
              type="submit"
            >
              {busy ? (
                <>
                  <Loader2 className="spin" size={16} />
                  {progress > 0 && progress < 100
                    ? `Uploading ${progress}%`
                    : "Preparing…"}
                </>
              ) : (
                <>
                  Start investigation
                  <ArrowRight size={17} />
                </>
              )}
            </button>
          </div>
          {busy && (
            <div className="busy-message" role="status">
              <span className="scan-progress" />
              {busy}
            </div>
          )}
          {fileError && (
            <p className="error-text intake-file-error" role="alert">
              {fileError}
            </p>
          )}
        </form>
      </section>
      <section className="samples-section">
        <div className="section-index">
          <span>02 / TAKE A CLOSER LOOK</span>
          <span className="subtle">
            No files? Follow a sample investigation.
          </span>
        </div>
        <div className="sample-grid">
          {samples.map((s, i) => (
            <button
              key={s.id}
              className={`sample-card sample-${s.id}`}
              disabled={!!busy}
              onClick={() => onSample(s.id)}
            >
              <div className="sample-top">
                <span className="sample-number">0{i + 1}</span>
                {i === 0 ? (
                  <Network size={24} strokeWidth={1.2} />
                ) : i === 1 ? (
                  <ScanLine size={24} strokeWidth={1.2} />
                ) : (
                  <ShieldCheck size={24} strokeWidth={1.2} />
                )}
              </div>
              <h2>{s.title}</h2>
              <p>{s.subtitle}</p>
              <div className="sample-bottom">
                <span>{s.tags[0]}</span>
                <ArrowUpRight size={18} />
              </div>
            </button>
          ))}
        </div>
        <p className="sample-disclaimer">
          SYNTHETIC TEACHING FIXTURES · SCORES COMPUTED FROM INCLUDED DATA ·
          NEVER PRESENTED AS PUBLISHED RESEARCH
        </p>
      </section>
      {recent.length > 0 && (
        <section className="recent-section">
          <div className="section-index">
            <span>YOUR RECENT INVESTIGATIONS</span>
            <span className="subtle">Private to this browser session</span>
          </div>
          {recent.slice(0, 4).map((c) => (
            <button
              className="recent-row"
              key={c.id}
              onClick={() => open(c.id)}
            >
              <FolderOpen size={18} />
              <span>{c.title}</span>
              <Status value={c.status} />
              <ChevronRight size={17} />
            </button>
          ))}
        </section>
      )}
      <section className="closing-line">
        <span>Good science welcomes</span>
        <em>a second look.</em>
        <span className="closing-symbol">↗</span>
      </section>
    </>
  );
}

function Workspace({
  data,
  activity,
  capabilities,
  onHome,
  onError,
}: {
  data: Case;
  activity: ActivityItem[];
  capabilities?: Capabilities;
  onHome: () => void;
  onError: (v: string) => void;
}) {
  const qc = useQueryClient();
  const { view, setView, selectedFinding, setSelectedFinding, graphics } =
    useUI();
  const [source, setSource] = useState<Anchor | Artifact | null>(null),
    [showFiles, setShowFiles] = useState(false),
    [showLog, setShowLog] = useState(false),
    [spatial, setSpatial] = useState(false);
  const [sourceFilter, setSourceFilter] = useState("");
  const active = activeStates.has(data.status),
    result = data.result,
    findings = result.findings || [],
    questions = result.questions || [],
    runs = result.executions || [],
    coverage = result.coverage || {};
  const selected = findings.find((f) => f.id === selectedFinding);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["case", data.id] });
    qc.invalidateQueries({ queryKey: ["recent"] });
  };
  const mutate = useMutation({
    mutationFn: async (action: {
      type: string;
      question?: string;
      answer?: string;
      finding?: string;
      status?: ReviewStatus;
      note?: string;
    }) => {
      if (action.type === "decision")
        return api.decision(data.id, action.question!, action.answer!);
      if (action.type === "review")
        return api.review(
          data.id,
          action.finding!,
          action.status!,
          action.note || "",
        );
      if (action.type === "cancel") return api.cancel(data.id);
      return api.rerun(data.id);
    },
    onSuccess: refresh,
    onError: (e) => onError(e.message),
  });
  const choose = (id: string) => {
    const f = findings.find((f) => f.id === id);
    if (f) {
      setSelectedFinding(id);
      history.replaceState({}, "", `?case=${data.id}#${id}`);
    } else {
      const a = data.artifacts.find((a) => a.id === id);
      const claim = result.claims?.find((c) => c.id === id);
      if (a) setSource(a);
      else if (claim) setSource(claim.anchor);
      else if (questions.some((q) => q.id === id)) setView("review");
      else if (runs.some((r) => r.id === id)) setView("runs");
    }
  };
  useEffect(() => {
    const id = location.hash.slice(1);
    if (id && findings.some((f) => f.id === id)) setSelectedFinding(id);
  }, [data.id, findings.length]);
  return (
    <>
      <div className="case-breadcrumb">
        <button onClick={onHome}>
          <ChevronLeft size={14} />
          Observatory
        </button>
        <span>/</span>
        <span>{data.id.slice(0, 8)}</span>
        <span className="case-private">
          <ShieldCheck size={12} />
          PRIVATE SESSION
        </span>
      </div>
      <section className="case-heading">
        <div>
          <div className="case-eyebrow">
            <span className="eyebrow">
              INVESTIGATION {data.id.slice(0, 4).toUpperCase()}
            </span>
            <Status value={data.status} />
            {data.sources.some((s) => s.type === "synthetic_sample") && (
              <span className="synthetic-label">SYNTHETIC DEMO</span>
            )}
          </div>
          <h1>{data.title}</h1>
          <p>
            Follow the evidence. Question the assumptions. Make the judgment.
          </p>
        </div>
        <div className="case-actions">
          {active ? (
            <button
              className="button secondary"
              disabled={mutate.isPending}
              onClick={() => mutate.mutate({ type: "cancel" })}
            >
              <Pause size={15} />
              Cancel
            </button>
          ) : (
            <button
              className="button secondary"
              disabled={mutate.isPending}
              onClick={() => mutate.mutate({ type: "rerun" })}
            >
              <RotateCcw size={15} />
              Rerun
            </button>
          )}
          <a
            className="button primary small"
            href={api.exportUrl(data.id, "pdf")}
          >
            <Download size={15} />
            Export report
          </a>
        </div>
      </section>
      {active && (
        <div className="analysis-progress" role="status">
          <Loader2 className="spin" size={16} />
          <span>{activity.at(-1)?.message || "Preparing investigation"}</span>
          <div className="stage-track">
            {stageNames.map((s, i) => (
              <span
                key={s}
                className={data.status === s.toLowerCase() ? "current" : ""}
              >
                {i + 1}
                <small>{s}</small>
              </span>
            ))}
          </div>
        </div>
      )}
      <div className="metrics-strip">
        <Metric
          label="SOURCE ARTIFACTS"
          value={coverage.files_discovered ?? data.artifacts.length}
          icon={Layers3}
        />
        <Metric
          label="CLAIMS TRACED"
          value={coverage.claims_examined ?? result.claims?.length ?? 0}
          icon={Link2}
        />
        <Metric
          label="CHECKS COMPLETED"
          value={coverage.checks_completed ?? 0}
          icon={ScanLine}
        />
        <Metric
          label="YOUR JUDGMENT"
          value={coverage.unresolved_questions ?? 0}
          icon={HelpCircle}
          accent={!!coverage.unresolved_questions}
        />
      </div>
      <div className="workbench">
        <aside className={`source-rail ${showFiles ? "mobile-open" : ""}`}>
          <div className="rail-heading">
            <span>SOURCE EXPLORER</span>
            <button
              className="icon-button"
              onClick={() => setShowFiles(false)}
              aria-label="Close source explorer"
            >
              <PanelLeftClose size={16} />
            </button>
          </div>
          <div className="source-folder">
            <FolderOpen size={15} /> Research snapshot{" "}
            <span>{data.artifacts.length}</span>
          </div>
          <div className="source-list">
            <label className="source-filter">
              <Search size={13} />
              <input
                aria-label="Filter source files"
                placeholder="Find a source…"
                value={sourceFilter}
                onChange={(e) => setSourceFilter(e.target.value)}
              />
            </label>
            <VirtualList
              items={data.artifacts.filter((a) =>
                a.path.toLowerCase().includes(sourceFilter.toLowerCase()),
              )}
              rowHeight={68}
              height={450}
              label="Source files"
              itemKey={(a) => a.id}
              renderRow={(a) => (
                <button
                  key={a.id}
                  onClick={() => {
                    setSource(a);
                    setShowFiles(false);
                  }}
                >
                  <span className={`kind-${a.kind}`}>
                    <KindIcon kind={a.kind} />
                  </span>
                  <span title={a.path}>
                    {a.path.split("/").at(-1)}
                    <small>
                      {a.path.includes("/")
                        ? a.path.substring(0, a.path.lastIndexOf("/"))
                        : a.kind}
                    </small>
                  </span>
                  <span className="file-size">
                    {a.size > 1024 ? `${(a.size / 1024).toFixed(0)}k` : a.size}
                  </span>
                </button>
              )}
            />
          </div>
          <div className="rail-footer">
            <ShieldCheck size={15} />
            <span>
              Immutable source snapshot
              <small>Every artifact has a SHA-256 hash.</small>
            </span>
          </div>
          {data.sources
            .filter((s) => s.commit)
            .map((s) => (
              <a
                key={s.commit}
                className="commit-label"
                href={`${s.url}/tree/${s.commit}`}
                target="_blank"
                rel="noreferrer"
              >
                <GitBranch size={13} />
                {s.commit?.slice(0, 12)}
                <ExternalLink size={12} />
              </a>
            ))}
        </aside>
        <section className="work-area">
          <nav className="workspace-tabs" aria-label="Investigation views">
            <button
              className="mobile-files icon-button"
              onClick={() => setShowFiles(true)}
              aria-label="Open source explorer"
            >
              <FolderOpen size={18} />
            </button>
            {(
              [
                { id: "overview", icon: Layers3, label: "Overview" },
                { id: "evidence", icon: Network, label: "Evidence" },
                { id: "runs", icon: FlaskConical, label: "Experiments" },
                { id: "review", icon: Eye, label: "Your review" },
              ] as const
            ).map((tab) => (
              <button
                key={tab.id}
                className={view === tab.id ? "selected" : ""}
                onClick={() => {
                  setView(tab.id);
                  setSelectedFinding(null);
                }}
              >
                <tab.icon size={15} />
                <span>{tab.label}</span>
                {tab.id === "review" && questions.some((q) => !q.answer) && (
                  <i className="tab-dot" />
                )}
              </button>
            ))}
          </nav>
          <div className="workspace-content">
            <AnimatePresence mode="wait">
              <m.div
                key={view}
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18 }}
              >
                {view === "overview" && (
                  <>
                    <div className="content-heading">
                      <div>
                        <span className="eyebrow">THE INVESTIGATION</span>
                        <h2>
                          What the evidence says
                          <span className="heading-period">.</span>
                        </h2>
                      </div>
                      <span className="provider-tag">
                        <span className="mint-dot" />
                        {result.provider === "deterministic"
                          ? "Deterministic checks"
                          : result.provider || "Discovering"}
                      </span>
                    </div>
                    <div className="coverage-summary">
                      <CheckCircle2 size={17} />
                      <p>
                        {active
                          ? "The investigation is in progress. Results appear as checks complete."
                          : findings.length
                            ? `${findings.length} finding${findings.length !== 1 ? "s" : ""} surfaced for your inspection.`
                            : "No discrepancies identified in completed checks."}
                        <span>
                          {coverage.files_inspected ?? 0} files inspected ·{" "}
                          {coverage.checks_skipped ?? 0} checks skipped or
                          inconclusive · Revision {data.revision}
                        </span>
                      </p>
                    </div>
                    {questions
                      .filter((q) => !q.answer || q.answer === "unknown")
                      .slice(0, 1)
                      .map((q) => (
                        <QuestionCard
                          key={q.id}
                          question={q}
                          active={active || mutate.isPending}
                          onAnswer={(answer) =>
                            mutate.mutate({
                              type: "decision",
                              question: q.id,
                              answer,
                            })
                          }
                          onSource={setSource}
                        />
                      ))}
                    <div className="subheading">
                      <span>FINDINGS</span>
                      <span>{findings.length.toString().padStart(2, "0")}</span>
                    </div>
                    {findings.length ? (
                      <div className="finding-list">
                        {findings.map((f, i) => (
                          <FindingRow
                            key={f.id}
                            finding={f}
                            index={i}
                            selected={f.id === selectedFinding}
                            onClick={() =>
                              setSelectedFinding(
                                f.id === selectedFinding ? null : f.id,
                              )
                            }
                          />
                        ))}
                      </div>
                    ) : (
                      <Empty
                        title={
                          active
                            ? "Tracing the research"
                            : coverage.checks_completed
                              ? "The evidence holds so far"
                              : "No conclusive checks yet"
                        }
                        icon={active ? ScanLine : ShieldCheck}
                      >
                        {active
                          ? "Source-anchored findings will appear here."
                          : "No discrepancy was found within completed checks. Review the coverage and incomplete checks before drawing a broader conclusion."}
                      </Empty>
                    )}
                    {selected && (
                      <FindingDetail
                        finding={selected}
                        onSource={setSource}
                        disabled={active || mutate.isPending}
                        onReview={(status, note) =>
                          mutate.mutate({
                            type: "review",
                            finding: selected.id,
                            status,
                            note,
                          })
                        }
                      />
                    )}
                    <Checks checks={result.checks || []} />
                    <Limitations warnings={result.warnings || []} />
                  </>
                )}
                {view === "evidence" && (
                  <>
                    <div className="content-heading">
                      <div>
                        <span className="eyebrow">
                          EVERY CONNECTION HAS A SOURCE
                        </span>
                        <h2>
                          The evidence constellation
                          <span className="heading-period">.</span>
                        </h2>
                      </div>
                      {graphics && (
                        <button
                          className="button secondary small"
                          onClick={() => setSpatial(!spatial)}
                        >
                          <Orbit size={15} />
                          {spatial ? "2D view" : "Spatial view"}
                        </button>
                      )}
                    </div>
                    <div className="graph-wrap">
                      {spatial && graphics ? (
                        <GraphicsBoundary>
                          <Suspense
                            fallback={<div className="scene-loading" />}
                          >
                            <Scene graph={result.graph} onSelect={choose} />
                          </Suspense>
                        </GraphicsBoundary>
                      ) : (
                        <EvidenceGraph
                          graph={result.graph || { nodes: [], edges: [] }}
                          selected={selectedFinding}
                          onSelect={choose}
                        />
                      )}
                      <div className="graph-legend">
                        <span>
                          <i className="legend-mint" />
                          Source
                        </span>
                        <span>
                          <i className="legend-blue" />
                          Claim
                        </span>
                        <span>
                          <i className="legend-red" />
                          Finding
                        </span>
                        <span>
                          <i className="legend-amber" />
                          Human judgment
                        </span>
                      </div>
                    </div>
                    {selected && (
                      <FindingDetail
                        finding={selected}
                        onSource={setSource}
                        disabled={active || mutate.isPending}
                        onReview={(status, note) =>
                          mutate.mutate({
                            type: "review",
                            finding: selected.id,
                            status,
                            note,
                          })
                        }
                      />
                    )}
                    <div className="subheading">
                      <span>CLAIMS IN THE SOURCE</span>
                      <span>{result.claims?.length || 0}</span>
                    </div>
                    <div className="claims-list">
                      {result.claims?.map((c) => (
                        <button key={c.id} onClick={() => setSource(c.anchor)}>
                          <span className="claim-number">↗</span>
                          <span>
                            {c.quote}
                            <small>
                              {c.anchor.path}
                              {c.anchor.page ? ` · page ${c.anchor.page}` : ""}
                            </small>
                          </span>
                          <ArrowUpRight size={16} />
                        </button>
                      ))}
                    </div>
                    {!result.claims?.length && (
                      <Empty title="No explicit claims extracted yet">
                        The evidence inventory remains available. Connect a
                        model for broader contextual claim extraction.
                      </Empty>
                    )}
                  </>
                )}
                {view === "runs" && (
                  <>
                    <div className="content-heading">
                      <div>
                        <span className="eyebrow">MEASURED, NOT IMAGINED</span>
                        <h2>
                          Experiments &amp; comparisons
                          <span className="heading-period">.</span>
                        </h2>
                      </div>
                      <span
                        className={`provider-tag ${capabilities?.runner.available ? "" : "amber"}`}
                      >
                        {capabilities?.runner.available
                          ? capabilities.runner.provider
                          : "Runner not connected"}
                      </span>
                    </div>
                    <p className="panel-description">
                      Supported original CPU programs execute in isolation.
                      Reconstructions and corrected protocols are labeled
                      separately, with measured provenance and support limits.
                    </p>
                    {runs.length ? (
                      <>
                        <Suspense fallback={null}>
                          <RunChart runs={runs} />
                        </Suspense>
                        <div className="runs-list">
                          {runs.map((run) => (
                            <div className="run-card" key={run.id}>
                              <div className="run-heading">
                                <div>
                                  <FlaskConical size={17} />
                                  <h3>{humanize(run.manifest.variant)}</h3>
                                </div>
                                <Status value={run.status} />
                              </div>
                              <div className="run-values">
                                {Object.entries(run.output.metrics || {}).map(
                                  ([name, value]) => (
                                    <div key={name}>
                                      <span>{humanize(name)}</span>
                                      <strong>
                                        {name === "accuracy" ||
                                        name.startsWith("f1")
                                          ? `${(value * 100).toFixed(2)}%`
                                          : value.toFixed(4)}
                                      </strong>
                                    </div>
                                  ),
                                )}
                                {run.output.entity_overlap !== undefined && (
                                  <div>
                                    <span>Entity overlap</span>
                                    <strong>{run.output.entity_overlap}</strong>
                                  </div>
                                )}
                              </div>
                              {run.output.error && (
                                <p className="error-text">{run.output.error}</p>
                              )}
                              <p className="run-meta">
                                {humanize(run.manifest.classification || "unclassified run")} ·{" "}
                                {run.output.train_rows ?? "—"} train /{" "}
                                {run.output.test_rows ?? "—"} test ·{" "}
                                {run.output.seconds ?? "—"}s
                              </p>
                              <details>
                                <summary>
                                  Inspect execution manifest{" "}
                                  <ChevronDown size={13} />
                                </summary>
                                <pre>
                                  {JSON.stringify(
                                    {
                                      manifest: run.manifest,
                                      environment: run.output.environment,
                                      limitations: run.output.limitations,
                                    },
                                    null,
                                    2,
                                  )}
                                </pre>
                              </details>
                            </div>
                          ))}
                        </div>
                      </>
                    ) : (
                      <Empty
                        icon={FlaskConical}
                        title="No isolated experiment has run"
                      >
                        {capabilities?.runner.reason ||
                          "Execution depends on a supported model/data mapping and an available isolated runner."}{" "}
                        Saved result comparisons remain available under
                        Overview.
                      </Empty>
                    )}
                    <Checks
                      checks={(result.checks || []).filter(
                        (c) =>
                          c.name.toLowerCase().includes("execution") ||
                          c.name.toLowerCase().includes("evaluation"),
                      )}
                    />
                  </>
                )}
                {view === "review" && (
                  <>
                    <div className="content-heading">
                      <div>
                        <span className="eyebrow">
                          HUMAN + AI, BETTER TOGETHER
                        </span>
                        <h2>
                          Your judgment changes the outcome
                          <span className="heading-period">.</span>
                        </h2>
                      </div>
                    </div>
                    <p className="panel-description">
                      Establish what the files cannot tell us. Every answer is
                      recorded, and affected checks are rerun.
                    </p>
                    {questions.length ? (
                      questions.map((q) => (
                        <QuestionCard
                          key={q.id}
                          question={q}
                          active={active || mutate.isPending}
                          onAnswer={(answer) =>
                            mutate.mutate({
                              type: "decision",
                              question: q.id,
                              answer,
                            })
                          }
                          onSource={setSource}
                        />
                      ))
                    ) : (
                      <Empty
                        icon={CheckCheck}
                        title="No clarification needed for completed checks"
                      >
                        You can still inspect and review each finding. A
                        complete check is not a guarantee of overall scientific
                        validity.
                      </Empty>
                    )}
                    <div className="subheading">
                      <span>REVIEW RECORD</span>
                      <span>{data.decisions.length} decisions</span>
                    </div>
                    {data.decisions.map((d, i) => (
                      <div className="decision-record" key={i}>
                        <span className="decision-dot" />
                        <div>
                          <strong>{humanize(d.question_id)}</strong>
                          <p>{humanize(d.answer)}</p>
                        </div>
                        <span className="mono subtle">REV {d.revision}</span>
                      </div>
                    ))}
                    {result.history?.length ? (
                      <details className="checks-section">
                        <summary>
                          <span>
                            <Clock3 size={16} />
                            Earlier analysis revisions
                          </span>
                          <span>
                            {result.history.length}
                            <ChevronDown size={14} />
                          </span>
                        </summary>
                        <div>
                          {result.history.map((revision, i) => (
                            <div className="check-row" key={i}>
                              <RotateCcw size={15} />
                              <div>
                                <strong>
                                  Revision {revision.revision} · superseded
                                </strong>
                                <p>
                                  {revision.findings.length} findings retained
                                  for comparison. Later human decisions may
                                  change their interpretation.
                                </p>
                                {revision.findings.map((f) => (
                                  <p key={f.id}>
                                    {f.title} · {humanize(f.evidence_status)} ·{" "}
                                    {humanize(f.review_status)}
                                  </p>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </details>
                    ) : null}
                    <div className="export-panel">
                      <div>
                        <Download size={22} />
                        <h3>Take the evidence with you.</h3>
                        <p>
                          Sources, limitations, human decisions, and run
                          provenance.
                        </p>
                      </div>
                      <div>
                        <a
                          className="button primary"
                          href={api.exportUrl(data.id, "pdf")}
                        >
                          PDF report <ArrowUpRight size={15} />
                        </a>
                        <a
                          className="button secondary"
                          href={api.exportUrl(data.id, "json")}
                        >
                          JSON
                        </a>
                        <a
                          className="button secondary"
                          href={api.exportUrl(data.id, "zip")}
                        >
                          Evidence ZIP
                        </a>
                      </div>
                    </div>
                    <DeleteCase
                      id={data.id}
                      disabled={active}
                      onDone={onHome}
                      onError={onError}
                    />
                  </>
                )}
              </m.div>
            </AnimatePresence>
          </div>
        </section>
      </div>
      <section className={`activity-console ${showLog ? "expanded" : ""}`}>
        <button
          className="console-heading"
          onClick={() => setShowLog(!showLog)}
        >
          <span>
            <Activity size={14} />
            <b>INVESTIGATION ACTIVITY</b>
            <span className="console-live">{active ? "LIVE" : "RECORDED"}</span>
          </span>
          <span className="console-latest">
            {activity.at(-1)?.message || "Waiting for investigation events"}
          </span>
          <ChevronDown size={15} />
        </button>
        {showLog && (
          <div className="console-events" aria-live="polite">
            <VirtualList
              items={activity}
              rowHeight={64}
              height={300}
              label="Investigation events"
              itemKey={(e) => e.id}
              renderRow={(e) => (
                <div key={e.id}>
                  <time>
                    {new Date(e.created_at).toLocaleTimeString([], {
                      hour12: false,
                    })}
                  </time>
                  <span
                    className={`event-stage ${e.type === "error" ? "error-text" : ""}`}
                  >
                    {e.stage}
                  </span>
                  <span title={e.message}>{e.message}</span>
                </div>
              )}
            />
          </div>
        )}
      </section>
      <SourceModal
        caseId={data.id}
        runs={runs}
        source={source}
        close={() => setSource(null)}
      />
    </>
  );
}

function Metric({
  label,
  value,
  icon: Icon,
  accent = false,
}: {
  label: string;
  value: number;
  icon: typeof ScanLine;
  accent?: boolean;
}) {
  return (
    <div className={`metric ${accent ? "metric-amber" : ""}`}>
      <div>
        <span>{label}</span>
        <Icon size={16} />
      </div>
      <strong>{value.toString().padStart(2, "0")}</strong>
      {accent && <small>Needs your perspective</small>}
    </div>
  );
}
function FindingRow({
  finding: f,
  index,
  selected,
  onClick,
}: {
  finding: Finding;
  index: number;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className={`finding-row ${selected ? "expanded" : ""}`}
      onClick={onClick}
      aria-expanded={selected}
    >
      <span
        className={`finding-indicator ${f.evidence_status.startsWith("verified") ? "verified" : f.evidence_status === "candidate" ? "candidate" : ""}`}
      >
        {f.evidence_status.startsWith("verified") ? (
          <AlertTriangle size={17} />
        ) : (
          <ScanLine size={17} />
        )}
      </span>
      <span className="finding-main">
        <span className="finding-meta">
          <span>{humanize(f.kind)}</span>
          <i /> <span>{humanize(f.evidence_status)}</span>
        </span>
        <strong>{f.title}</strong>
        <span className="finding-source">
          {f.evidence
            .map((e) => e.path)
            .filter((v, i, a) => a.indexOf(v) === i)
            .join(" ↔ ")}
        </span>
      </span>
      <span className={`impact impact-${f.impact}`}>{f.impact}</span>
      {f.review_status !== "unreviewed" && (
        <CheckCheck size={16} className="mint" />
      )}
      <ChevronRight size={16} className="finding-chevron" />
    </button>
  );
}
function FindingDetail({
  finding: f,
  onSource,
  onReview,
  disabled,
}: {
  finding: Finding;
  onSource: (v: Anchor) => void;
  onReview: (status: ReviewStatus, note: string) => void;
  disabled: boolean;
}) {
  const [note, setNote] = useState(f.review_note);
  const baselineMetrics = (f.observed.baseline_metrics || {}) as Record<
    string,
    number
  >;
  const correctedMetrics = (f.observed.corrected_metrics || {}) as Record<
    string,
    number
  >;
  useEffect(() => setNote(f.review_note), [f.id, f.review_note]);
  return (
    <m.section
      className="finding-detail"
      initial={{ opacity: 0, y: -5 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="detail-kicker">
        <ScanLine size={14} />
        EVIDENCE UNDER THE LENS<span>{humanize(f.evidence_status)}</span>
      </div>
      <h3>{f.title}</h3>
      <p>{f.explanation}</p>
      <div className="evidence-comparison">
        {f.evidence.map((e, i) => (
          <button
            className="evidence-card"
            key={e.id + i}
            onClick={() => onSource(e)}
          >
            <span>
              {e.kind === "execution"
                ? i === 0
                  ? "01 / BASELINE MEASUREMENT"
                  : "02 / CORRECTED MEASUREMENT"
                : i === 0
                  ? "01 / SOURCE CLAIM"
                  : "02 / SUPPORTING ARTIFACT"}
              <ArrowUpRight size={14} />
            </span>
            <blockquote>
              {e.text.length > 800 ? e.text.slice(0, 800) + "…" : e.text}
            </blockquote>
            <small>
              <KindIcon
                kind={e.path.endsWith(".pdf") ? "paper" : "code"}
                size={13}
              />
              {e.path}
              {e.page ? ` · p. ${e.page}` : e.pointer ? ` · ${e.pointer}` : ""}
            </small>
          </button>
        ))}
      </div>
      {typeof f.observed.reported === "number" &&
        typeof f.observed.artifact === "number" && (
          <div className="numeric-comparison">
            <div>
              <span>REPORTED</span>
              <strong>
                {formatMetric(
                  f.observed.reported,
                  String(f.observed.metric || ""),
                )}
              </strong>
            </div>
            <ArrowRight size={22} />
            <div>
              <span>ARTIFACT</span>
              <strong>
                {formatMetric(
                  f.observed.artifact,
                  String(f.observed.metric || ""),
                )}
              </strong>
            </div>
            <p>
              A saved-result comparison.
              <br />
              Not an independent reproduction.
            </p>
          </div>
        )}
      {Object.keys(baselineMetrics).length > 0 && (
        <div className="measured-comparison">
          {Object.entries(baselineMetrics)
            .filter(
              ([metric, value]) =>
                typeof value === "number" &&
                typeof correctedMetrics[metric] === "number",
            )
            .map(([metric, value]) => (
              <div key={metric}>
                <span>{humanize(metric)}</span>
                <strong>
                  {formatMetric(value, metric)} <ArrowRight size={17} />{" "}
                  {formatMetric(correctedMetrics[metric], metric)}
                </strong>
              </div>
            ))}
          <p>
            Baseline → corrected protocol. These measurements are not an
            independent reproduction of the paper.
          </p>
        </div>
      )}
      {f.alternatives.length > 0 && (
        <div className="alternatives">
          <h4>
            <HelpCircle size={14} />
            Alternative explanations
          </h4>
          {f.alternatives.map((x) => (
            <p key={x}>— {x}</p>
          ))}
        </div>
      )}
      {f.limitations.map((x) => (
        <p className="limitation-line" key={x}>
          <Info size={14} />
          {x}
        </p>
      ))}
      <div className="review-controls">
        <label htmlFor={`note-${f.id}`}>
          Your interpretation <span>Optional</span>
        </label>
        <textarea
          id={`note-${f.id}`}
          placeholder="Add context, revise the interpretation, or explain why this finding should be dismissed…"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={4000}
        />
        <div>
          <span className="review-current">{humanize(f.review_status)}</span>
          <button
            disabled={disabled}
            className="button secondary small"
            onClick={() => onReview("dismissed", note)}
          >
            Dismiss
          </button>
          <button
            disabled={disabled}
            className="button secondary small"
            onClick={() => onReview("revised", note)}
          >
            Revise
          </button>
          <button
            disabled={disabled}
            className="button primary small"
            onClick={() => onReview("accepted", note)}
          >
            <Check size={14} />
            Accept finding
          </button>
        </div>
      </div>
    </m.section>
  );
}

function QuestionCard({
  question: q,
  active,
  onAnswer,
  onSource,
}: {
  question: Question;
  active: boolean;
  onAnswer: (value: string) => void;
  onSource: (value: Anchor) => void;
}) {
  const [choice, setChoice] = useState(q.answer || "");
  useEffect(() => setChoice(q.answer || ""), [q.id, q.answer]);
  return (
    <section
      className={`question-card ${q.answer && q.answer !== "unknown" ? "answered" : ""}`}
    >
      <div className="question-kicker">
        <span>
          <HelpCircle size={15} />
          YOUR PERSPECTIVE MATTERS
        </span>
        {q.answer && (
          <span className="answered-label">
            <Check size={13} />
            Decision recorded
          </span>
        )}
      </div>
      <h3>{q.title}</h3>
      <p>{q.why}</p>
      <div className="question-options">
        {q.options.length > 12 ? (
          <div className="question-select">
            <label htmlFor={`answer-${q.id}`}>Researcher selection</label>
            <select
              id={`answer-${q.id}`}
              value={choice}
              disabled={active}
              onChange={(e) => setChoice(e.target.value)}
            >
              <option value="">Choose an option…</option>
              {q.options.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <p>{q.options.find((o) => o.value === choice)?.effect}</p>
            <button
              className="button primary"
              disabled={active || !choice}
              onClick={() => onAnswer(choice)}
            >
              Apply scientific choice <ArrowRight size={15} />
            </button>
          </div>
        ) : (
          q.options.map((o) => (
            <button
              key={o.value}
              disabled={active}
              className={q.answer === o.value ? "chosen" : ""}
              onClick={() => onAnswer(o.value)}
            >
              <span className="radio-indicator">
                {q.answer === o.value && <Check size={11} />}
              </span>
              <span>
                <strong>{o.label}</strong>
                <small>{o.effect}</small>
              </span>
              <ArrowUpRight size={14} />
            </button>
          ))
        )}
      </div>
      {q.evidence[0] && (
        <button
          className="question-source"
          onClick={() => onSource(q.evidence[0])}
        >
          <Link2 size={13} />
          Inspect the evidence behind this question
          <ArrowUpRight size={13} />
        </button>
      )}
    </section>
  );
}
function Checks({
  checks,
}: {
  checks: { id: string; name: string; status: string; detail: string }[];
}) {
  return checks.length ? (
    <details className="checks-section">
      <summary>
        <span>
          <CheckCheck size={16} />
          Completed &amp; incomplete checks
        </span>
        <span>
          {checks.length}
          <ChevronDown size={14} />
        </span>
      </summary>
      <div>
        {checks.map((c, i) => (
          <div className="check-row" key={c.id + i}>
            {c.status === "passed" ? (
              <CheckCircle2 size={16} className="mint" />
            ) : c.status === "flagged" ? (
              <AlertTriangle size={16} className="amber" />
            ) : (
              <Info size={16} className="subtle" />
            )}
            <div>
              <strong>{c.name}</strong>
              <p>{c.detail}</p>
            </div>
            <span className="mono subtle">{c.status}</span>
          </div>
        ))}
      </div>
    </details>
  ) : null;
}
function Limitations({ warnings }: { warnings: string[] }) {
  return warnings.length ? (
    <details className="limitations">
      <summary>
        <Info size={15} />
        {warnings.length} coverage &amp; capability notes
        <ChevronDown size={14} />
      </summary>
      {[...new Set(warnings)].map((w, i) => (
        <p key={i}>{w}</p>
      ))}
    </details>
  ) : null;
}
function EvidenceGraph({
  graph,
  selected,
  onSelect,
}: {
  graph: Graph;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const projection = clusteredGraph(graph, selected);
  const [cluster, setCluster] = useState<Graph["nodes"][number] | null>(null);
  const [clusterSearch, setClusterSearch] = useState("");
  const selectNode = (node: Graph["nodes"][number]) => {
    if (node.members) {
      setCluster(node);
      setClusterSearch("");
    } else onSelect(node.finding_id || node.artifact_id || node.id);
  };
  const nodes = projection.nodes,
    positions = new Map<string, { x: number; y: number }>();
  const groups = [
    ["paper", "documentation"],
    ["code", "configuration", "data", "results", "cluster"],
    ["claim"],
    ["finding", "execution", "decision"],
  ];
  groups.forEach((types, column) => {
    const items = nodes.filter((n) => types.includes(n.type));
    items.forEach((n, i) =>
      positions.set(n.id, {
        x: 70 + column * 190,
        y: 55 + ((i + 0.5) * 300) / Math.max(items.length, 1),
      }),
    );
  });
  return (
    <>
      <svg
        viewBox="0 0 750 430"
        className="evidence-svg"
        role="group"
        aria-label="Evidence graph. Select a source or finding to inspect it."
      >
        <defs>
          <pattern
            id="graph-grid"
            width="24"
            height="24"
            patternUnits="userSpaceOnUse"
          >
            <circle cx="1" cy="1" r=".65" fill="#23323a" />
          </pattern>
        </defs>
        <rect width="750" height="430" fill="url(#graph-grid)" />
        {["DOCUMENTS", "ARTIFACTS", "CLAIMS", "INVESTIGATION"].map((s, i) => (
          <text
            key={s}
            x={70 + i * 190}
            y={24}
            textAnchor="middle"
            className="graph-column-label"
          >
            {s}
          </text>
        ))}
        {projection.edges.map((e, i) => {
          const a = positions.get(e.source),
            b = positions.get(e.target);
          return a && b ? (
            <path
              key={i}
              d={`M ${a.x} ${a.y} C ${(a.x + b.x) / 2} ${a.y}, ${(a.x + b.x) / 2} ${b.y}, ${b.x} ${b.y}`}
              fill="none"
              stroke={
                e.type === "conflicts_with"
                  ? "#8c4b49"
                  : e.type === "requires_clarification"
                    ? "#6a5c34"
                    : "#284951"
              }
              strokeWidth="1"
              opacity=".7"
            />
          ) : null;
        })}
        {nodes.map((n) => {
          const p = positions.get(n.id);
          if (!p) return null;
          const color =
            n.type === "finding"
              ? "#ff766d"
              : n.type === "decision"
                ? "#f2c779"
                : n.type === "claim"
                  ? "#5cc8ff"
                  : "#70f3c2";
          return (
            <g
              key={n.id}
              role="button"
              tabIndex={0}
              aria-label={`${n.type}: ${n.label}`}
              className="graph-node"
              onClick={() => selectNode(n)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  selectNode(n);
                }
              }}
            >
              <title>{n.label}</title>
              <rect
                x={p.x - 22}
                y={p.y - 22}
                width={44}
                height={44}
                fill="transparent"
              />
              <circle
                cx={p.x}
                cy={p.y}
                r={selected === n.id ? 13 : 8}
                fill="#101a24"
                stroke={color}
                strokeWidth="1.5"
              />
              <circle cx={p.x} cy={p.y} r="2.5" fill={color} />
              <text
                x={p.x}
                y={p.y + 23}
                textAnchor="middle"
                fill="#9aaab8"
                fontSize="9"
              >
                {n.label.length > 25 ? n.label.slice(0, 23) + "…" : n.label}
              </text>
            </g>
          );
        })}
        {!nodes.length && (
          <text
            x="375"
            y="215"
            textAnchor="middle"
            fill="#6e8591"
            fontSize="13"
          >
            The graph forms from discovered evidence.
          </text>
        )}
      </svg>
      {graph.nodes.length > 64 && (
        <span className="cluster-caption">
          {graph.nodes.length} nodes · {projection.nodes.length} groups /
          focused nodes
        </span>
      )}
      {cluster && (
        <section className="cluster-inspector" aria-label="Cluster members">
          <div>
            <strong>{cluster.count} stored nodes</strong>
            <button
              className="icon-button"
              aria-label="Close cluster"
              onClick={() => setCluster(null)}
            >
              <X size={16} />
            </button>
          </div>
          <label className="sr-only" htmlFor="cluster-search">
            Filter cluster members
          </label>
          <input
            id="cluster-search"
            placeholder="Find a member…"
            value={clusterSearch}
            onChange={(e) => setClusterSearch(e.target.value)}
          />
          <VirtualList
            items={graph.nodes.filter(
              (n) =>
                cluster.members?.includes(n.id) &&
                (n.path || n.label)
                  .toLowerCase()
                  .includes(clusterSearch.toLowerCase()),
            )}
            rowHeight={48}
            height={192}
            label="Stored cluster members"
            itemKey={(n) => n.id}
            renderRow={(n) => (
              <button
                onClick={() => {
                  onSelect(n.finding_id || n.artifact_id || n.id);
                  setCluster(null);
                }}
                title={n.path || n.label}
              >
                <KindIcon kind={n.type} />
                <span>{n.path || n.label}</span>
                <ArrowUpRight size={14} />
              </button>
            )}
          />
        </section>
      )}
    </>
  );
}

function SourceModal({
  caseId,
  source,
  close,
  runs,
}: {
  caseId: string;
  source: Anchor | Artifact | null;
  close: () => void;
  runs: Run[];
}) {
  const returnFocus = useRef<HTMLElement | null>(null);
  const runId = source && "execution_id" in source ? source.execution_id : null;
  const execution = runs.find((run) => run.id === runId);
  const id = execution
    ? null
    : source
      ? "artifact_id" in source
        ? source.artifact_id
        : source.id
      : null;
  const query = useQuery({
    queryKey: ["artifact", caseId, id],
    queryFn: () => api.artifact(caseId, id!),
    enabled: !!id,
  });
  const a = query.data;
  const locationLabel =
    source && "page" in source && source.page
      ? `Page ${source.page}`
      : source && "line" in source && source.line
        ? `Line ${source.line}`
        : source && "cell" in source && source.cell !== undefined
          ? `Cell ${source.cell}`
          : "";
  return (
    <Dialog.Root open={!!source} onOpenChange={(v) => !v && close()}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay source-overlay" />
        <Dialog.Content
          className="modal source-modal"
          onOpenAutoFocus={() => {
            returnFocus.current =
              document.activeElement instanceof HTMLElement
                ? document.activeElement
                : null;
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const previous = returnFocus.current;
            if (previous?.isConnected && previous !== document.body)
              previous.focus({ preventScroll: true });
            else {
              const main = document.getElementById("main");
              if (main) {
                main.tabIndex = -1;
                main.focus({ preventScroll: true });
              }
            }
          }}
        >
          <div className="modal-heading">
            <div>
              <span className="eyebrow">
                SOURCE EVIDENCE {locationLabel && `/ ${locationLabel}`}
              </span>
              <Dialog.Title>{source?.path}</Dialog.Title>
            </div>
            <Dialog.Close className="icon-button" aria-label="Close source">
              <X size={20} />
            </Dialog.Close>
          </div>
          <Dialog.Description className="source-description">
            The immutable source behind this finding. Read its surrounding
            context before interpreting the result.
          </Dialog.Description>
          {a ? (
            <>
              <div className="source-meta">
                <span>
                  <KindIcon kind={a.kind} />
                  <span title="Role inferred from the file type, path, and parsed contents; inspect the source to verify its purpose.">
                    Inferred {a.kind}
                  </span>
                </span>
                <span>{(a.size / 1024).toFixed(1)} KB</span>
                <a
                  href={`/api/v1/cases/${caseId}/artifacts/${a.id}?raw=true`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open original
                  <ExternalLink size={13} />
                </a>
              </div>
              {source && "text" in source && source.text && (
                <div className="source-excerpt">
                  <span>
                    {source.kind === "dataset"
                      ? "COMPUTED DATA PROFILE"
                      : source.kind === "result"
                        ? "STRUCTURED RESULT"
                        : source.kind === "saved_output"
                          ? "SAVED NOTEBOOK OUTPUT"
                          : source.kind === "derived_metric"
                            ? "RECOMPUTED FROM SAVED PREDICTIONS"
                            : "SELECTED PASSAGE"}
                  </span>
                  {(source.path.endsWith(".py") && source.line) ||
                  (source.path.endsWith(".ipynb") &&
                    source.cell !== undefined &&
                    source.kind !== "saved_output") ? (
                    <pre className="numbered-source">
                      {source.text.split("\n").map((line, i) => (
                        <span
                          className={
                            (source.line || 1) + i === source.highlight_line
                              ? "highlighted-line"
                              : ""
                          }
                          key={i}
                        >
                          <i aria-hidden="true">{(source.line || 1) + i}</i>
                          {line || " "}
                        </span>
                      ))}
                    </pre>
                  ) : (
                    <pre>{source.text}</pre>
                  )}
                </div>
              )}
              {a.path.toLowerCase().endsWith(".pdf") && (
                <Suspense
                  fallback={
                    <p className="pdf-message">Opening original PDF page…</p>
                  }
                >
                  <PdfSource
                    caseId={caseId}
                    artifactId={a.id}
                    pages={a.parsed?.pages || 1}
                    initialPage={
                      source && "page" in source ? source.page || 1 : 1
                    }
                    quote={source && "text" in source ? source.text : ""}
                    box={source && "bbox" in source ? source.bbox : undefined}
                  />
                </Suspense>
              )}
              <div className="source-full">
                <span>DOCUMENT CONTEXT</span>
                <pre>
                  {a.parsed?.text ||
                    "No extractable text. Open the original source to inspect it."}
                </pre>
              </div>
              <div className="source-hash">
                <ShieldCheck size={13} />
                SHA-256 {a.sha256}
              </div>
            </>
          ) : execution ? (
            <>
              <div className="source-meta">
                <span>
                  <FlaskConical size={15} />
                  {execution.status}
                </span>
                <span>{humanize(execution.manifest.classification)}</span>
                <span>{new Date(execution.created_at).toLocaleString()}</span>
              </div>
              <div className="source-excerpt">
                <span>RECORDED EXECUTION OUTPUT</span>
                <pre>{JSON.stringify(execution.output, null, 2)}</pre>
              </div>
              <div className="source-full">
                <span>EXECUTION MANIFEST</span>
                <pre>{JSON.stringify(execution.manifest, null, 2)}</pre>
              </div>
            </>
          ) : (
            <Empty
              title={query.error ? "Source unavailable" : "Opening source"}
            >
              {query.error
                ? (query.error as Error).message
                : "Loading the original evidence."}
            </Empty>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
function DeleteCase({
  id,
  disabled,
  onDone,
  onError,
}: {
  id: string;
  disabled: boolean;
  onDone: () => void;
  onError: (s: string) => void;
}) {
  const [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button disabled={disabled} className="delete-case">
          <Trash2 size={14} />
          Delete this private investigation
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content className="modal delete-modal">
          <Dialog.Title>Delete this investigation?</Dialog.Title>
          <Dialog.Description>
            This permanently removes its source artifacts, analysis, and review
            record. Download the evidence bundle first if you want to retain it.
          </Dialog.Description>
          <div className="delete-actions">
            <Dialog.Close className="button secondary">
              Keep investigation
            </Dialog.Close>
            <button
              className="button danger"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await api.remove(id);
                  onDone();
                } catch (e) {
                  onError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {busy ? "Deleting…" : "Delete permanently"}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
