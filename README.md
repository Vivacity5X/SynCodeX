# SynCodeX

SynCodeX is an AI developer assistant with a Spring Boot API, a FastAPI AI service, and a local MCP server for repository search and file reading.

## Requirements

- Python 3.10 or newer
- Java 17 or newer
- A Groq API key for AI-powered endpoints

## Run locally

From the repository root, create and install the AI service environment:

```powershell
py -3 -m venv ai-service/.venv
ai-service/.venv/Scripts/python.exe -m pip install -r ai-service/requirements.txt
```

Set `GROQ_API_KEY` in the environment or in `ai-service/.env`, then start the API:

```powershell
ai-service/.venv/Scripts/python.exe -m uvicorn main:app --app-dir ai-service --reload --host 127.0.0.1 --port 8000
```

The AI service starts the MCP server as a local subprocess using its own Python interpreter. No separate MCP server process or second virtual environment is needed.

In another terminal, start the Spring Boot API:

```powershell
cd "backend/SynCodeX Backend"
./mvnw spring-boot:run
```

The backend uses `http://127.0.0.1:8000` for the AI service by default. Its endpoints are under `/api/v1/ai`; repository questions are available at `/repository/ask` and `/repository/ask-mcp`.

In a third terminal, start the React frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The Vite development server proxies API calls to Spring Boot at `http://127.0.0.1:8080`.

## Checks

```powershell
ai-service/.venv/Scripts/python.exe -m compileall ai-service mcp-server
cd "backend/SynCodeX Backend"
./mvnw test
cd ../../frontend
npm run build
```

The database and deployment folders are placeholders at this stage.
