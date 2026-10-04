import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import get_driver, close_driver
from app.routes import papers, graph
import certifi

@asynccontextmanager
async def lifespan(app: FastAPI):
    get_driver()          # warm up connection
    yield
    close_driver()


app = FastAPI(title="Research Paper KG", lifespan=lifespan)
os.environ["SSL_CERT_FILE"] = certifi.where()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://kg-research-papers-frontend-ex9pr4hla-nilas-projects-0730eb23.vercel.app"],   # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(papers.router, prefix="/papers", tags=["papers"])
app.include_router(graph.router, prefix="/graph", tags=["graph"])


@app.get("/health")
def health():
    return {"status": "ok"}