import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Workspace = "explain" | "repository" | "mcp" | "debug";
type ApiStatus = "checking" | "online" | "offline";
type ProjectProfile = {
  repository: string;
  project_types: string[];
  languages: string[];
  debug_languages: string[];
  unsupported_debug_languages: string[];
  message: string;
  manifests: string[];
};
type Source = {
  file?: string;
  start_line?: number;
  end_line?: number;
  line?: number;
  score?: number;
  content?: string;
};
type ApiAnswer = {
  application?: string;
  language?: string;
  explanation?: string;
  question?: string;
  answer?: string;
  sources?: Source[] | null;
  status?: string;
};
type DebugReport = {
  problem_summary: string;
  observed_error: {
    exception_lines: { line: number; text: string }[];
    stack_frames: { language: string; class?: string | null; method?: string; file: string; line?: number | null }[];
  };
  log_analysis: {
    events: { line: number; timestamp?: string | null; level?: string | null; component?: string | null; message: string }[];
    groups: { count: number; component?: string | null; signature: string; first_line: number; last_line: number }[];
    first_observed_failure?: { line: number; timestamp?: string | null; component?: string | null; message: string } | null;
    later_failures: { line: number; message: string; classification: string; causal_link_established: boolean }[];
    causality_note: string;
  };
  likely_root_cause: string;
  evidence: (Source & { line_start: number; line_end: number; description: string; excerpt: string; verified: boolean })[];
  relevant_files: string[];
  execution_flow: string[];
  recommended_fix: string[];
  proposed_code_changes: string[];
  validation_steps: string[];
  confidence: "low" | "medium" | "high";
  missing_information: string[];
  analysis_status: string;
  project?: ProjectProfile;
};
type PatchProposal = {
  proposal_id: string;
  file: string;
  explanation: string;
  diff: string;
  base_sha256: string;
  applied: boolean;
  backup_id?: string;
  applied_sha256?: string;
  reverted?: boolean;
  approval_required: true;
  validation_status: "not_run";
};

const navItems: { id: Workspace; label: string; detail: string; icon: string }[] = [
  { id: "explain", label: "Explain code", detail: "Understand a snippet", icon: "code" },
  { id: "repository", label: "Ask repository", detail: "Search with RAG", icon: "search" },
  { id: "mcp", label: "MCP explorer", detail: "Ask with repository tools", icon: "nodes" },
  { id: "debug", label: "Debug an error", detail: "Trace logs to source", icon: "search" },
];

const pageCopy: Record<Workspace, { eyebrow: string; title: string; subtitle: string }> = {
  explain: {
    eyebrow: "CODE EXPLANATION",
    title: "Make code make sense.",
    subtitle: "Paste a snippet and get a clear, grounded explanation.",
  },
  repository: {
    eyebrow: "REPOSITORY SEARCH",
    title: "Ask your codebase.",
    subtitle: "Find implementation details across the files in this project.",
  },
  mcp: {
    eyebrow: "MCP REPOSITORY TOOLS",
    title: "Explore with MCP.",
    subtitle: "Search, discover, and read project files through MCP tools.",
  },
  debug: {
    eyebrow: "DEBUGGING WORKSPACE",
    title: "Trace the failure to its source.",
    subtitle: "Inspect an error and logs, then review a proposed fix without changing project files.",
  },
};

const sampleCode = `public class Greeting {
    public static void main(String[] args) {
        System.out.println("Hello, world!");
    }
}`;

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const error = await response.json();
      message = error.detail ?? error.message ?? message;
    } catch {
      // Keep the status-based message when the server response is not JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const common = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true as const };
  if (name === "code") return <svg {...common}><path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14" /></svg>;
  if (name === "search") return <svg {...common}><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4.5 4.5" /></svg>;
  if (name === "nodes") return <svg {...common}><rect x="3" y="4" width="7" height="6" rx="2" /><rect x="14" y="14" width="7" height="6" rx="2" /><path d="M10 7h3a3 3 0 0 1 3 3v4M14 17h-3a3 3 0 0 1-3-3v-4" /></svg>;
  if (name === "spark") return <svg {...common}><path d="m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3Z" /><path d="m19 16 .8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8L19 16Z" /></svg>;
  if (name === "arrow") return <svg {...common}><path d="M5 12h14m-6-6 6 6-6 6" /></svg>;
  if (name === "copy") return <svg {...common}><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></svg>;
  if (name === "check") return <svg {...common}><path d="m5 12 4 4L19 6" /></svg>;
  if (name === "file") return <svg {...common}><path d="M13 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10Z" /><path d="M13 3v7h7M8 14h8M8 17h6" /></svg>;
  return null;
}

function App() {
  const [workspace, setWorkspace] = useState<Workspace>("explain");
  const [code, setCode] = useState("");
  const [language, setLanguage] = useState("Java");
  const [question, setQuestion] = useState("");
  const [errorInput, setErrorInput] = useState("");
  const [logsInput, setLogsInput] = useState("");
  const [answer, setAnswer] = useState<ApiAnswer | null>(null);
  const [debugReport, setDebugReport] = useState<DebugReport | null>(null);
  const [patchProposal, setPatchProposal] = useState<PatchProposal | null>(null);
  const [selectedPatchFile, setSelectedPatchFile] = useState("");
  const [fixInstructions, setFixInstructions] = useState("");
  const [proposalBusy, setProposalBusy] = useState(false);
  const [approvalBusy, setApprovalBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");
  const [projectProfile, setProjectProfile] = useState<ProjectProfile | null>(null);
  const [repositoryPath, setRepositoryPath] = useState("");
  const [repositoryBusy, setRepositoryBusy] = useState(false);
  const [repositoryError, setRepositoryError] = useState("");
  const repositoryEpoch = useRef(0);
  const [copied, setCopied] = useState(false);
  const copy = pageCopy[workspace];

  const checkApi = useCallback(async () => {
    try {
      await request("/api/v1/health");
      setApiStatus("online");
    } catch {
      setApiStatus("offline");
    }
  }, []);

  useEffect(() => {
    void checkApi();
    const timer = window.setInterval(() => void checkApi(), 30_000);
    return () => window.clearInterval(timer);
  }, [checkApi]);

  useEffect(() => {
    let active = true;
    void request<ProjectProfile>("/api/v1/ai/repository/context")
      .then((profile) => {
        if (!active) return;
        setProjectProfile(profile);
        setRepositoryPath(profile.repository);
      })
      .catch((cause) => {
        if (active) setRepositoryError(cause instanceof Error ? cause.message : "Could not load repository context.");
      });
    return () => { active = false; };
  }, []);

  const answerText = useMemo(
    () => answer?.explanation ?? answer?.answer ?? "",
    [answer],
  );

  function changeWorkspace(next: Workspace) {
    setWorkspace(next);
    setAnswer(null);
    setDebugReport(null);
    setPatchProposal(null);
    setError("");
    setCopied(false);
  }

  async function selectRepository(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const selectionEpoch = ++repositoryEpoch.current;
    setRepositoryError("");
    setAnswer(null);
    setDebugReport(null);
    setPatchProposal(null);
    setSelectedPatchFile("");
    setProposalBusy(false);
    setApprovalBusy(false);
    setError("");
    setCopied(false);
    setRepositoryBusy(true);
    try {
      const profile = await request<ProjectProfile>("/api/v1/ai/repository/select", { path: repositoryPath });
      if (selectionEpoch !== repositoryEpoch.current) return;
      setProjectProfile(profile);
      setRepositoryPath(profile.repository);
    } catch (cause) {
      if (selectionEpoch === repositoryEpoch.current) {
        setRepositoryError(cause instanceof Error ? cause.message : "Could not select that repository.");
      }
    } finally {
      if (selectionEpoch === repositoryEpoch.current) setRepositoryBusy(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const requestEpoch = repositoryEpoch.current;
    setError("");
    setAnswer(null);
    setDebugReport(null);
    setPatchProposal(null);
    setCopied(false);
    setBusy(true);

    try {
      if (workspace === "explain") {
        setAnswer(await request<ApiAnswer>("/api/v1/ai/explain", { code, language }));
      } else if (workspace === "debug") {
        const report = await request<DebugReport>("/api/v1/ai/debug/analyze", {
          error: errorInput,
          question,
          logs: logsInput,
        });
        if (requestEpoch !== repositoryEpoch.current) return;
        setDebugReport(report);
        setSelectedPatchFile(report.evidence[0]?.file ?? "");
      } else {
        const endpoint = workspace === "mcp" ? "/api/v1/ai/repository/ask-mcp" : "/api/v1/ai/repository/ask";
        const result = await request<ApiAnswer>(endpoint, { question });
        if (requestEpoch !== repositoryEpoch.current) return;
        setAnswer(result);
      }
    } catch (cause) {
      if (requestEpoch === repositoryEpoch.current) {
        setError(cause instanceof Error ? cause.message : "Something went wrong. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function copyAnswer() {
    if (!answerText) return;
    try {
      await navigator.clipboard.writeText(answerText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setError("Clipboard access is unavailable in this browser.");
    }
  }

  async function proposePatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!debugReport || !selectedPatchFile || !fixInstructions.trim()) return;
    setError("");
    setPatchProposal(null);
    const requestEpoch = repositoryEpoch.current;
    setProposalBusy(true);
    try {
      const proposal = await request<PatchProposal>("/api/v1/ai/debug/propose-fix", {
        file: selectedPatchFile,
        instructions: fixInstructions,
        error: [errorInput, logsInput].filter(Boolean).join("\n").slice(0, 12000),
        question,
      });
      if (requestEpoch === repositoryEpoch.current) setPatchProposal(proposal);
    } catch (cause) {
      if (requestEpoch === repositoryEpoch.current) {
        setError(cause instanceof Error ? cause.message : "Could not generate a patch proposal.");
      }
    } finally {
      if (requestEpoch === repositoryEpoch.current) setProposalBusy(false);
    }
  }

  async function copyDebugReport() {
    if (!debugReport) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(debugReport, null, 2));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setError("Clipboard access is unavailable in this browser.");
    }
  }

  async function copyPatch() {
    if (!patchProposal) return;
    try {
      await navigator.clipboard.writeText(patchProposal.diff);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setError("Clipboard access is unavailable in this browser.");
    }
  }

  async function applyPatch() {
    if (!patchProposal || patchProposal.applied || patchProposal.reverted) return;
    const approved = window.confirm(
      `Apply this exact proposal to ${patchProposal.file}? A backup will be saved. No tests will run.`,
    );
    if (!approved) return;
    setError("");
    const requestEpoch = repositoryEpoch.current;
    setApprovalBusy(true);
    try {
      const result = await request<{ applied: boolean; backup_id: string; applied_sha256: string }>(
        "/api/v1/ai/debug/apply-fix",
        { proposal_id: patchProposal.proposal_id, approved: true },
      );
      if (requestEpoch === repositoryEpoch.current) setPatchProposal({ ...patchProposal, ...result });
    } catch (cause) {
      if (requestEpoch === repositoryEpoch.current) setError(cause instanceof Error ? cause.message : "Could not apply the approved patch.");
    } finally {
      if (requestEpoch === repositoryEpoch.current) setApprovalBusy(false);
    }
  }

  async function revertPatch() {
    if (!patchProposal?.backup_id || !patchProposal.applied_sha256 || !patchProposal.applied) return;
    const approved = window.confirm(
      `Restore the saved version of ${patchProposal.file}? Revert is refused if the file has changed since the patch was applied.`,
    );
    if (!approved) return;
    setError("");
    const requestEpoch = repositoryEpoch.current;
    setApprovalBusy(true);
    try {
      await request("/api/v1/ai/debug/revert-fix", {
        backup_id: patchProposal.backup_id,
        file: patchProposal.file,
        expected_current_sha256: patchProposal.applied_sha256,
        approved: true,
      });
      if (requestEpoch === repositoryEpoch.current) setPatchProposal({ ...patchProposal, applied: false, reverted: true });
    } catch (cause) {
      if (requestEpoch === repositoryEpoch.current) setError(cause instanceof Error ? cause.message : "Could not revert the approved patch.");
    } finally {
      if (requestEpoch === repositoryEpoch.current) setApprovalBusy(false);
    }
  }

  const canSubmit = workspace === "explain"
    ? code.trim().length > 0
    : workspace === "debug"
      ? Boolean(errorInput.trim() || logsInput.trim() || question.trim())
      : question.trim().length > 0;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#home" aria-label="SynCodeX home" onClick={(event) => { event.preventDefault(); changeWorkspace("explain"); }}>
          <span className="brand-mark"><Icon name="spark" size={22} /></span>
          <span className="brand-name">SynCode<span>X</span></span>
        </a>

        <div className="sidebar-label">WORKSPACE</div>
        <nav className="workspace-nav" aria-label="Workspace">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${workspace === item.id ? "active" : ""}`}
              onClick={() => changeWorkspace(item.id)}
              aria-current={workspace === item.id ? "page" : undefined}
            >
              <span className="nav-icon"><Icon name={item.icon} /></span>
              <span className="nav-copy"><span>{item.label}</span><small>{item.detail}</small></span>
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className={`connection-card ${apiStatus}`}>
            <span className="status-dot" />
            <span><strong>{apiStatus === "online" ? "Backend connected" : apiStatus === "offline" ? "Backend offline" : "Checking backend"}</strong><small>{apiStatus === "online" ? "SynCodeX API is ready" : apiStatus === "offline" ? "Start Spring Boot on port 8080" : "Connecting to local API"}</small></span>
          </div>
          <div className="sidebar-footnote">A quiet space for better code.</div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb"><span>Workspace</span><span className="breadcrumb-slash">/</span><strong>{navItems.find((item) => item.id === workspace)?.label}</strong></div>
          <div className="topbar-right"><span className="local-badge"><span className="status-dot" /> Local workspace</span></div>
        </header>

        <div className="content-wrap">
          <section className="repository-picker" aria-label="Selected repository">
            <form className="repository-picker-form" onSubmit={selectRepository}>
              <label htmlFor="repository-path">Repository directory on this machine</label>
              <div className="repository-picker-controls">
                <input id="repository-path" value={repositoryPath} onChange={(event) => setRepositoryPath(event.target.value)} maxLength={2000} placeholder="D:\\Projects\\my-app" />
                <button type="submit" disabled={!repositoryPath.trim() || repositoryBusy}>{repositoryBusy ? "Selecting…" : "Use repository"}</button>
              </div>
              {repositoryError && <small className="repository-error" role="alert">{repositoryError}</small>}
              {projectProfile && <div className="repository-profile">
                <span className="repository-types">{projectProfile.project_types.length ? projectProfile.project_types.join(" · ") : "Unclassified project"}</span>
                <span>{projectProfile.languages.length ? projectProfile.languages.join(", ") : "No supported source language detected"}</span>
                <small>{projectProfile.message}</small>
              </div>}
            </form>
          </section>
          <section className="page-intro">
            <span className="eyebrow"><span className="eyebrow-line" />{copy.eyebrow}</span>
            <h1>{copy.title}</h1>
            <p>{copy.subtitle}</p>
          </section>

          <section className="work-grid" aria-label={copy.title}>
            <form className="input-card" onSubmit={submit}>
              <div className="card-heading">
                <div>
                  <span className="step-label">01 <span>INPUT</span></span>
                  <h2>{workspace === "explain" ? "Your code" : workspace === "debug" ? "Error and logs" : "Your question"}</h2>
                </div>
                {workspace === "explain" && (
                  <label className="language-select">
                    <span className="sr-only">Programming language</span>
                    <select value={language} onChange={(event) => setLanguage(event.target.value)}>
                      {["Java", "Python", "JavaScript", "TypeScript", "C++", "C#", "Go", "Rust", "SQL", "Other"].map((item) => <option key={item}>{item}</option>)}
                    </select>
                  </label>
                )}
                {workspace !== "explain" && <span className="context-pill"><Icon name={workspace === "mcp" ? "nodes" : "search"} size={14} /> {workspace === "mcp" ? "MCP tools" : workspace === "debug" ? "Source evidence" : "Whole project"}</span>}
              </div>

              {workspace === "explain" ? (
                <div className="editor-wrap">
                  <div className="editor-toolbar"><span className="editor-dots"><i /><i /><i /></span><span>{language.toLowerCase()}</span><button type="button" className="text-button" onClick={() => setCode(sampleCode)}>Load sample</button></div>
                  <textarea className="code-editor" value={code} onChange={(event) => setCode(event.target.value)} placeholder="Paste code here…" spellCheck={false} aria-label="Code to explain" />
                  <div className="input-meta"><span>{code.length.toLocaleString()} characters</span><span>Tip: be specific about what you want to understand</span></div>
                </div>
              ) : workspace === "debug" ? (
                <div className="debug-inputs">
                  <label className="debug-field">
                    <span>What are you trying to understand?</span>
                    <input value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={2000} placeholder="Why does this request return 500?" />
                  </label>
                  <label className="debug-field">
                    <span>Error or stack trace</span>
                    <textarea value={errorInput} onChange={(event) => setErrorInput(event.target.value)} maxLength={12000} placeholder="Paste the exception and stack trace…" />
                    <small>{errorInput.length.toLocaleString()} / 12,000 characters</small>
                  </label>
                  <label className="debug-field debug-logs-field">
                    <span>Related logs <em>optional</em></span>
                    <textarea value={logsInput} onChange={(event) => setLogsInput(event.target.value)} maxLength={12000} placeholder="Paste nearby application logs…" />
                    <small>{logsInput.length.toLocaleString()} / 12,000 characters</small>
                  </label>
                </div>
              ) : (
                <div className="question-wrap">
                  <textarea className="question-input" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={workspace === "mcp" ? "Which MCP tools are available, and how do they work?" : "Where is the AI service URL configured?"} aria-label="Question about the repository" />
                  <div className="suggestion-row"><span>Try asking</span><button type="button" onClick={() => setQuestion("Where is the AI service URL configured?")}>Where is a setting configured?</button><button type="button" onClick={() => setQuestion("Which MCP tools are available?")}>Which tools are available?</button></div>
                </div>
              )}

              {error && !debugReport && <div className="error-banner" role="alert">{error}</div>}

              <div className="form-footer">
                <span className="privacy-note"><span className="lock-icon">⌑</span> {workspace === "debug" ? "Patch proposals never modify files" : "Your code stays in this workspace"}</span>
                <button className="primary-button" type="submit" disabled={!canSubmit || busy || apiStatus === "offline"}>
                  {busy ? <><span className="spinner" /> Working…</> : <>{workspace === "explain" ? "Explain code" : workspace === "debug" ? "Analyze error" : "Ask SynCodeX"}<Icon name="arrow" size={17} /></>}
                </button>
              </div>
            </form>

            <section className={`output-card ${answer || debugReport || busy || error ? "has-content" : ""}`} aria-live="polite">
              <div className="card-heading output-heading">
                <div><span className="step-label">02 <span>{workspace === "debug" ? "DIAGNOSIS" : "RESULT"}</span></span><h2>{busy ? "Working on it" : workspace === "debug" ? debugReport ? "Debugging report" : "Diagnosis" : answer ? "Here’s what I found" : "Your answer"}</h2></div>
                {workspace === "debug" && debugReport ? <button className="icon-button" type="button" onClick={() => void copyDebugReport()} aria-label={copied ? "Copied report" : "Copy report"}><Icon name={copied ? "check" : "copy"} size={16} /><span>{copied ? "Copied" : "Copy report"}</span></button> : answerText && <button className="icon-button" type="button" onClick={() => void copyAnswer()} aria-label={copied ? "Copied answer" : "Copy answer"}><Icon name={copied ? "check" : "copy"} size={16} /><span>{copied ? "Copied" : "Copy"}</span></button>}
              </div>
              {busy ? (
                <div className="loading-state"><span className="loading-orbit"><Icon name="spark" size={21} /></span><strong>{workspace === "explain" ? "Reading your code" : workspace === "debug" ? "Tracing the failure" : "Searching your repository"}</strong><span>Finding the most useful context…</span><div className="loading-bars"><i /><i /><i /></div></div>
              ) : workspace === "debug" && debugReport ? (
                <DebugReportView
                  report={debugReport}
                  selectedFile={selectedPatchFile}
                  onSelectFile={(file) => { setSelectedPatchFile(file); setPatchProposal(null); }}
                  instructions={fixInstructions}
                  onChangeInstructions={(value) => { setFixInstructions(value); setPatchProposal(null); }}
                  onPropose={proposePatch}
                  proposalBusy={proposalBusy}
                  approvalBusy={approvalBusy}
                  proposal={patchProposal}
                  copied={copied}
                  onCopyPatch={copyPatch}
                  onApply={applyPatch}
                  onRevert={revertPatch}
                  error={error}
                />
              ) : answer ? (
                <div className="answer-content">
                  <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{answerText}</ReactMarkdown></div>
                  {answer.sources && answer.sources.length > 0 && <SourceList sources={answer.sources} />}
                </div>
              ) : (
                <div className="empty-state"><span className="empty-icon"><Icon name="spark" size={22} /></span><strong>{workspace === "debug" ? "Start with the failure details." : "Good answers start with good context."}</strong><span>{workspace === "explain" ? "Your explanation will appear here, with the important details called out." : workspace === "debug" ? "Add an error or logs to get a grounded report and source evidence." : "Ask a question and SynCodeX will trace it back to the files that matter."}</span><div className="empty-rule" /></div>
              )}
              {(answer || debugReport) && <div className="answer-footer"><span><span className="status-dot" /> {debugReport ? "Review only · files unchanged" : "Grounded in your project"}</span><span>SynCodeX AI</span></div>}
            </section>
          </section>

          <footer className="page-footer"><span>Built for clear thinking.</span><span>SynCodeX <b>·</b> Developer workspace</span></footer>
        </div>
      </main>
    </div>
  );
}

function DebugReportView({
  report,
  selectedFile,
  onSelectFile,
  instructions,
  onChangeInstructions,
  onPropose,
  proposalBusy,
  approvalBusy,
  proposal,
  copied,
  onCopyPatch,
  onApply,
  onRevert,
  error,
}: {
  report: DebugReport;
  selectedFile: string;
  onSelectFile: (file: string) => void;
  instructions: string;
  onChangeInstructions: (value: string) => void;
  onPropose: (event: FormEvent<HTMLFormElement>) => void;
  proposalBusy: boolean;
  approvalBusy: boolean;
  proposal: PatchProposal | null;
  copied: boolean;
  onCopyPatch: () => void;
  onApply: () => void;
  onRevert: () => void;
  error: string;
}) {
  const diffLines = proposal?.diff.split("\n") ?? [];
  const patchFiles = [...new Set(report.evidence.map((item) => item.file))];
  const sourceCards: Source[] = report.evidence.map((item) => ({
    file: item.file,
    start_line: item.line_start,
    end_line: item.line_end,
    content: item.excerpt,
  }));

  return (
    <div className="debug-report">
      <section className="debug-summary">
        <div className="debug-report-kicker">PROBLEM SUMMARY</div>
        <p>{report.problem_summary}</p>
        <span className={`confidence-badge ${report.confidence}`}>{report.confidence} confidence</span>
        {report.analysis_status !== "ai_analyzed" && <span className="analysis-status">{report.analysis_status.replaceAll("_", " ")}</span>}
        {report.project && <p className="project-capability-note">{report.project.message}</p>}
      </section>

      <section className="debug-report-section root-cause-section">
        <h3>Likely root cause</h3>
        <p>{report.likely_root_cause}</p>
      </section>

      {report.observed_error.exception_lines.length > 0 && <section className="debug-report-section">
        <h3>Observed errors</h3>
        <ul>{report.observed_error.exception_lines.map((item) => <li key={`${item.line}-${item.text}`}><span className="debug-line-number">L{item.line}</span><code>{item.text}</code></li>)}</ul>
      </section>}

      {report.execution_flow.length > 0 && <section className="debug-report-section">
        <h3>Execution flow from the trace</h3>
        <ol className="execution-flow">{report.execution_flow.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ol>
      </section>}

      {report.evidence.length > 0 ? <section className="debug-report-section">
        <h3>Repository evidence</h3>
        <SourceList sources={sourceCards} />
      </section> : <p className="debug-empty-evidence">No source file could be matched to the submitted stack frames.</p>}

      <section className="debug-report-section">
        <h3>Log sequence</h3>
        {report.log_analysis.first_observed_failure ? <p className="first-failure"><strong>First observed failure · line {report.log_analysis.first_observed_failure.line}</strong><br />{report.log_analysis.first_observed_failure.message}</p> : <p>No failure-level log event was detected.</p>}
        {report.log_analysis.groups.length > 0 && <ul className="log-groups">{report.log_analysis.groups.map((group) => <li key={`${group.first_line}-${group.signature}`}><strong>{group.count}×</strong> {group.component ?? "Unknown component"} · lines {group.first_line}{group.last_line !== group.first_line ? `–${group.last_line}` : ""}<code>{group.signature}</code></li>)}</ul>}
        {report.log_analysis.later_failures.length > 0 && <ul className="later-failures">{report.log_analysis.later_failures.map((item, index) => <li key={`${item.line}-${index}`}>Line {item.line}: {item.classification.replaceAll("_", " ")} — {item.message}</li>)}</ul>}
        <small>{report.log_analysis.causality_note}</small>
      </section>

      <ReportList title="Recommended fix" items={report.recommended_fix} />
      {report.proposed_code_changes.length > 0 && <ReportList title="Suggested code changes" items={report.proposed_code_changes} />}
      <ReportList title="Validation steps" items={report.validation_steps} />
      {report.missing_information.length > 0 && <ReportList title="Missing information" items={report.missing_information} />}

      <section className="patch-proposal-section">
        <div className="debug-report-kicker">REVIEWABLE PATCH</div>
        <p className="patch-safety-note">A proposal produces a diff only. SynCodeX will not change or run project files.</p>
        <form className="patch-request-form" onSubmit={onPropose}>
          <label className="debug-field">
            <span>Evidence file</span>
            <select value={selectedFile} onChange={(event) => onSelectFile(event.target.value)} disabled={!patchFiles.length}>
              {patchFiles.map((file) => <option key={file} value={file}>{file}</option>)}
            </select>
          </label>
          <label className="debug-field">
            <span>What change should the diff propose?</span>
            <textarea value={instructions} onChange={(event) => onChangeInstructions(event.target.value)} maxLength={2000} placeholder="Describe the targeted change you want to review…" />
          </label>
          {error && <div className="error-banner" role="alert">{error}</div>}
          <button className="primary-button patch-button" type="submit" disabled={!report.evidence.length || !selectedFile || !instructions.trim() || proposalBusy}>
            {proposalBusy ? <><span className="spinner" /> Generating…</> : "Generate review diff"}
          </button>
        </form>

        {proposal && <section className="patch-review" aria-live="polite">
          <div className="patch-review-header"><div><span className="debug-report-kicker">PATCH PROPOSAL</span><strong>{proposal.file}</strong></div><span className={proposal.applied ? "patch-applied" : proposal.reverted ? "patch-reverted" : "patch-not-applied"}>{proposal.applied ? "APPLIED" : proposal.reverted ? "REVERTED" : "NOT APPLIED"}</span></div>
          <p>{proposal.explanation}</p>
          <div className="patch-meta">Validation not run · Base file SHA-256: <code>{proposal.base_sha256.slice(0, 12)}…</code></div>
          {proposal.applied && <div className="patch-applied-notice">A backup is available. Tests were not run.</div>}
          {proposal.reverted && <div className="patch-applied-notice">The saved source version was restored.</div>}
          {!proposal.applied && !proposal.reverted && <button className="apply-patch-button" type="button" onClick={onApply} disabled={approvalBusy}>{approvalBusy ? "Applying…" : "Apply after review…"}</button>}
          {proposal.applied && <button className="revert-patch-button" type="button" onClick={onRevert} disabled={approvalBusy}>{approvalBusy ? "Restoring…" : "Revert to saved version…"}</button>}
          <div className="diff-toolbar"><strong>Unified diff</strong><button className="icon-button" type="button" onClick={onCopyPatch}><Icon name={copied ? "check" : "copy"} size={15} /><span>{copied ? "Copied" : "Copy diff"}</span></button></div>
          <pre className="diff-view">{diffLines.map((line, index) => <span className={line.startsWith("+") && !line.startsWith("+++") ? "diff-added" : line.startsWith("-") && !line.startsWith("---") ? "diff-removed" : line.startsWith("@@") ? "diff-hunk" : ""} key={`${index}-${line}`}>{line}{index < diffLines.length - 1 ? "\n" : ""}</span>)}</pre>
        </section>}
      </section>
    </div>
  );
}

function ReportList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return <section className="debug-report-section"><h3>{title}</h3><ul>{items.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul></section>;
}

function SourceList({ sources }: { sources: Source[] }) {
  return (
    <section className="sources-section">
      <div className="sources-title"><span>Sources</span><span>{sources.length} {sources.length === 1 ? "file" : "files"}</span></div>
      <div className="source-list">
        {sources.map((source, index) => (
          <details className="source-item" key={`${source.file ?? "source"}-${source.start_line ?? source.line ?? index}-${index}`}>
            <summary><span className="source-file-icon"><Icon name="file" size={15} /></span><span className="source-path">{source.file ?? "Repository source"}</span><span className="source-lines">{source.start_line ? `L${source.start_line}${source.end_line && source.end_line !== source.start_line ? `–${source.end_line}` : ""}` : source.line ? `L${source.line}` : ""}</span></summary>
            {source.content && <pre>{source.content}</pre>}
          </details>
        ))}
      </div>
    </section>
  );
}

export default App;
