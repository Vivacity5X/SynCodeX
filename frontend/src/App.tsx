import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Workspace = "explain" | "repository" | "mcp";
type ApiStatus = "checking" | "online" | "offline";
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

const navItems: { id: Workspace; label: string; detail: string; icon: string }[] = [
  { id: "explain", label: "Explain code", detail: "Understand a snippet", icon: "code" },
  { id: "repository", label: "Ask repository", detail: "Search with RAG", icon: "search" },
  { id: "mcp", label: "MCP explorer", detail: "Ask with repository tools", icon: "nodes" },
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
  const [answer, setAnswer] = useState<ApiAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");
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

  const answerText = useMemo(
    () => answer?.explanation ?? answer?.answer ?? "",
    [answer],
  );

  function changeWorkspace(next: Workspace) {
    setWorkspace(next);
    setAnswer(null);
    setError("");
    setCopied(false);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setAnswer(null);
    setCopied(false);
    setBusy(true);

    try {
      if (workspace === "explain") {
        setAnswer(await request<ApiAnswer>("/api/v1/ai/explain", { code, language }));
      } else {
        const endpoint = workspace === "mcp" ? "/api/v1/ai/repository/ask-mcp" : "/api/v1/ai/repository/ask";
        setAnswer(await request<ApiAnswer>(endpoint, { question }));
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Something went wrong. Please try again.");
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

  const canSubmit = workspace === "explain" ? code.trim().length > 0 : question.trim().length > 0;

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
                  <h2>{workspace === "explain" ? "Your code" : "Your question"}</h2>
                </div>
                {workspace === "explain" && (
                  <label className="language-select">
                    <span className="sr-only">Programming language</span>
                    <select value={language} onChange={(event) => setLanguage(event.target.value)}>
                      {["Java", "Python", "JavaScript", "TypeScript", "C++", "C#", "Go", "Rust", "SQL", "Other"].map((item) => <option key={item}>{item}</option>)}
                    </select>
                  </label>
                )}
                {workspace !== "explain" && <span className="context-pill"><Icon name={workspace === "mcp" ? "nodes" : "search"} size={14} /> {workspace === "mcp" ? "MCP tools" : "Whole project"}</span>}
              </div>

              {workspace === "explain" ? (
                <div className="editor-wrap">
                  <div className="editor-toolbar"><span className="editor-dots"><i /><i /><i /></span><span>{language.toLowerCase()}</span><button type="button" className="text-button" onClick={() => setCode(sampleCode)}>Load sample</button></div>
                  <textarea className="code-editor" value={code} onChange={(event) => setCode(event.target.value)} placeholder="Paste code here…" spellCheck={false} aria-label="Code to explain" />
                  <div className="input-meta"><span>{code.length.toLocaleString()} characters</span><span>Tip: be specific about what you want to understand</span></div>
                </div>
              ) : (
                <div className="question-wrap">
                  <textarea className="question-input" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={workspace === "mcp" ? "Which MCP tools are available, and how do they work?" : "Where is the AI service URL configured?"} aria-label="Question about the repository" />
                  <div className="suggestion-row"><span>Try asking</span><button type="button" onClick={() => setQuestion("Where is the AI service URL configured?")}>Where is a setting configured?</button><button type="button" onClick={() => setQuestion("Which MCP tools are available?")}>Which tools are available?</button></div>
                </div>
              )}

              {error && <div className="error-banner" role="alert">{error}</div>}

              <div className="form-footer">
                <span className="privacy-note"><span className="lock-icon">⌑</span> Your code stays in this workspace</span>
                <button className="primary-button" type="submit" disabled={!canSubmit || busy || apiStatus === "offline"}>
                  {busy ? <><span className="spinner" /> Working…</> : <>{workspace === "explain" ? "Explain code" : "Ask SynCodeX"}<Icon name="arrow" size={17} /></>}
                </button>
              </div>
            </form>

            <section className={`output-card ${answer || busy || error ? "has-content" : ""}`} aria-live="polite">
              <div className="card-heading output-heading">
                <div><span className="step-label">02 <span>RESULT</span></span><h2>{busy ? "Working on it" : answer ? "Here’s what I found" : "Your answer"}</h2></div>
                {answerText && <button className="icon-button" type="button" onClick={() => void copyAnswer()} aria-label={copied ? "Copied answer" : "Copy answer"}><Icon name={copied ? "check" : "copy"} size={16} /><span>{copied ? "Copied" : "Copy"}</span></button>}
              </div>
              {busy ? (
                <div className="loading-state"><span className="loading-orbit"><Icon name="spark" size={21} /></span><strong>{workspace === "explain" ? "Reading your code" : "Searching your repository"}</strong><span>Finding the most useful context…</span><div className="loading-bars"><i /><i /><i /></div></div>
              ) : answer ? (
                <div className="answer-content">
                  <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{answerText}</ReactMarkdown></div>
                  {answer.sources && answer.sources.length > 0 && <SourceList sources={answer.sources} />}
                </div>
              ) : (
                <div className="empty-state"><span className="empty-icon"><Icon name="spark" size={22} /></span><strong>Good answers start with good context.</strong><span>{workspace === "explain" ? "Your explanation will appear here, with the important details called out." : "Ask a question and SynCodeX will trace it back to the files that matter."}</span><div className="empty-rule" /></div>
              )}
              {answer && <div className="answer-footer"><span><span className="status-dot" /> Grounded in your project</span><span>SynCodeX AI</span></div>}
            </section>
          </section>

          <footer className="page-footer"><span>Built for clear thinking.</span><span>SynCodeX <b>·</b> Developer workspace</span></footer>
        </div>
      </main>
    </div>
  );
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
