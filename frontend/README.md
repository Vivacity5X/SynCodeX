# SynCodeX frontend

React + TypeScript workspace for the Spring Boot API.

## Run locally

```powershell
npm install
npm run dev
```

Open the Vite URL shown in the terminal (normally `http://127.0.0.1:5173`). The Vite development server proxies `/api` requests to Spring Boot at `http://127.0.0.1:8080`.

The backend and AI service must both be running. AI requests also require a configured `GROQ_API_KEY`.
