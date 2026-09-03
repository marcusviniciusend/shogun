"""Entrypoint do servidor central do Shogun."""

from fastapi import FastAPI

app = FastAPI(title="Shogun Server", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
