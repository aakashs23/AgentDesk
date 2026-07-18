"""Phase 0 app shell — just enough for `docker compose up` to come up green.

Phase 2 (Backend Foundation) replaces this with the real application: settings,
DB session dependency, structured logging, module routers, exception handlers,
CORS, rate limiting, and the proper /health + /health/ready pair.
"""

from fastapi import FastAPI

app = FastAPI(title="AgentDesk API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
