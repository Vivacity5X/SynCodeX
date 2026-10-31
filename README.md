# SynCodeX

SynCodeX is an AI developer assistant with a Spring Boot API, a FastAPI AI service, and a local MCP server for repository inspection. MCP supports bounded source listing and reading, case-insensitive search, text-pattern symbol declarations, textual references, project structure, and dependency manifest inspection. Symbol/reference results are heuristic text matches, not compiler-verified semantics.

## Requirements

- Python 3.10 or newer
- Java 17 or newer
- Node.js and npm for the React frontend
- A Groq API key for provider-backed analysis (optional; deterministic analysis works without it)

## Run locally

From the repository root, create and install the AI service environment:

```powershell
py -3 -m venv ai-service/.venv
ai-service/.venv/Scripts/python.exe -m pip install -r ai-service/requirements.txt
```

For provider-backed analysis, set `GROQ_API_KEY` in the environment or in `ai-service/.env`. It is optional for deterministic analysis. Start the API:

```powershell
ai-service/.venv/Scripts/python.exe -m uvicorn main:app --app-dir ai-service --reload --host 127.0.0.1 --port 8000
```

To inspect a different checkout, set the root before starting the service:

```powershell
$env:SYNCODEX_PROJECT_ROOT = 'D:\path\to\project'
```

The AI service starts the MCP server as a local subprocess using its own Python interpreter. No separate MCP server process or second virtual environment is needed.

The `SYNCODEX_PROJECT_ROOT` environment variable sets the initial repository. You can switch repositories at runtime in the workspace using **Repository directory on this machine**. Enter the absolute local directory path and select **Use repository**; the choice is stored in that browser's Spring `HttpSession`. Different browser sessions keep separate selections, and switching does not restart the services. Each repository question, debug request, patch operation, and MCP subprocess receives the selected root from that session.

The MCP server lists supported source and text files, skips hidden and generated directories, and rejects paths outside the selected root, symbolic links, sensitive filenames, unsupported extensions, and files over its configured read limit. It redacts common secret-like key/value assignments in file contents and search snippets. Repository content is read as text and is never executed by the MCP server. The user-selected directory is the authorized boundary for repository inspection and approved patches.

Project families are detected from dependency manifests and source files. The current classifiers recognize Java/Spring Boot, Python/FastAPI, and React/TypeScript. Repository search and context retrieval also work over the listed text/source extensions. Stack-trace parsing is implemented for Java and Python; React/TypeScript source can be retrieved as context, but TypeScript stack frames are not parsed. Unsupported frameworks and languages receive an explicit capability or missing-context message. This is not universal language support.

## Stack trace debugging

Send a `POST` request to `/api/v1/debug/analyze` with any of `error`, `question`, `logs`, and `project_context` through Spring's `/api/v1/ai/debug/analyze`. Spring supplies the browser session's selected repository root. The service parses Java and Python stack frames, attempts to match frames to source files in that root, and returns a structured report with detected project type, evidence, likely cause, suggested fixes, validation steps, confidence, and missing information. It also extracts log timestamps, levels, components, repeated failure signatures, and the first observed failure. Later failures are ordered by appearance, but the report does not claim that earlier events caused them. Each input field has a size limit. With `GROQ_API_KEY` configured, the report includes provider analysis; without it, the endpoint still returns deterministic parsing and repository evidence with low confidence. Provider output is schema-validated, and evidence paths and line ranges come only from retrieved repository files.

Example request:

```json
{
  "question": "Why does this request fail?",
  "error": "java.lang.NullPointerException: service was null\n    at com.example.ApiController.handle(ApiController.java:42)"
}
```

To request a patch proposal, send `POST /api/v1/debug/propose-fix` with `file`, `instructions`, and optional `error` and `question`. The service returns a one-file unified diff and a hash of the source version used to generate it. It rejects unsupported paths, oversized files, and source files containing likely secret assignments. The frontend displays the diff and marks validation as not run. Applying and reverting are separate actions that require explicit approval; apply also refuses a source file that changed after the diff was generated. Original content is backed up under `.syncodex/backups/`, and revert refuses to overwrite a file changed after apply. These workflows do not run tests or other commands.

In another terminal, start the Spring Boot API:

```powershell
Set-Location 'D:\SynCodeX\backend\SynCodeX Backend'
.\mvnw.cmd spring-boot:run
```

The backend uses `http://127.0.0.1:8000` for the AI service by default. Its endpoints are under `/api/v1/ai`; repository questions are available at `/repository/ask` and `/repository/ask-mcp`.

Repository context endpoints are `/api/v1/ai/repository/context` (read the current session's selection) and `/api/v1/ai/repository/select` (POST `{"path":"D:\\Projects\\my-app"}`). The selected root is validated as an existing directory and is stored per Spring session. Direct AI-service calls may supply `repository_root` for development/testing; normal UI requests get it from Spring's session context.

In a third terminal, start the React frontend:

```powershell
Set-Location 'D:\SynCodeX\frontend'
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The Vite development server proxies API calls to Spring Boot at `http://127.0.0.1:8080`.

## Checks

```powershell
ai-service/.venv/Scripts/python.exe -m compileall ai-service/main.py ai-service/debugging.py ai-service/patches.py ai-service/mcp_client.py ai-service/retrieval.py mcp-server/server.py
ai-service/.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -v
Set-Location 'D:\SynCodeX\backend\SynCodeX Backend'
.\mvnw.cmd test
Set-Location 'D:\SynCodeX\frontend'
npm run build
```

The log analyzer accepts pasted log text; file upload is not implemented. The database and deployment folders are placeholders. Automated verification covers the FastAPI logic and OpenAPI shape, Spring-to-FastAPI request contracts, and the frontend production build. A live browser-to-Spring-to-FastAPI smoke test has not been verified in this environment. MCP symbol and reference results are text heuristics, and the MCP tools are not part of the debug/patch request path.
