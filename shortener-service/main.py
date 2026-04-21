import os
import random
import string
import threading
from contextlib import asynccontextmanager

import grpc
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone

import analytics_pb2
import analytics_pb2_grpc

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATABASE_URL       = os.getenv("DATABASE_URL", "sqlite:///./urls.db")
ANALYTICS_GRPC_URL = os.getenv("ANALYTICS_GRPC_URL", "analytics-service:50051")
BASE_URL           = os.getenv("BASE_URL", "http://localhost:8000")

# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
engine       = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(bind=engine)
Base         = declarative_base()

class URLRecord(Base):
    __tablename__ = "urls"
    short_code   = Column(String(10),  primary_key=True, index=True)
    original_url = Column(String(2048), nullable=False)
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# gRPC client helper
# ---------------------------------------------------------------------------
_grpc_channel = None
_grpc_stub    = None

def get_analytics_stub():
    global _grpc_channel, _grpc_stub
    if _grpc_stub is None:
        _grpc_channel = grpc.insecure_channel(ANALYTICS_GRPC_URL)
        _grpc_stub    = analytics_pb2_grpc.AnalyticsServiceStub(_grpc_channel)
    return _grpc_stub

def notify_click(short_code: str, ip: str, ua: str):
    try:
        stub = get_analytics_stub()
        stub.RecordClick(
            analytics_pb2.ClickRequest(short_code=short_code, ip_address=ip, user_agent=ua),
            timeout=10,
        )
    except Exception as e:
        print(f"[gRPC] RecordClick failed: {e}")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # test DB connection
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("DB connection OK")
    yield

app = FastAPI(title="Shortener Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ShortenRequest(BaseModel):
    url: str

class ShortenResponse(BaseModel):
    short_code: str
    short_url:  str
    original_url: str

# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------
def generate_code(length: int = 6) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "service": "shortener"}

@app.post("/shorten", response_model=ShortenResponse)
def shorten(body: ShortenRequest):
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    db = SessionLocal()
    try:
        # Check if URL already exists
        existing = db.query(URLRecord).filter(URLRecord.original_url == body.url).first()
        if existing:
            return ShortenResponse(
                short_code=existing.short_code,
                short_url=f"{BASE_URL}/{existing.short_code}",
                original_url=existing.original_url,
            )

        # Generate unique code
        code = None
        for _ in range(10):
            candidate = generate_code()
            if not db.query(URLRecord).filter(URLRecord.short_code == candidate).first():
                code = candidate
                break
        if code is None:
            raise HTTPException(status_code=500, detail="Could not generate a unique short code, please retry")

        record = URLRecord(short_code=code, original_url=body.url)
        db.add(record)
        db.commit()
        db.refresh(record)

        return ShortenResponse(
            short_code=record.short_code,
            short_url=f"{BASE_URL}/{record.short_code}",
            original_url=record.original_url,
        )
    finally:
        db.close()

@app.get("/urls")
def list_urls():
    db = SessionLocal()
    try:
        records = db.query(URLRecord).order_by(URLRecord.created_at.desc()).all()
        return [
            {
                "short_code":   r.short_code,
                "original_url": r.original_url,
                "short_url":    f"{BASE_URL}/{r.short_code}",
                "created_at":   r.created_at.isoformat(),
            }
            for r in records
        ]
    finally:
        db.close()

@app.get("/info/{short_code}")
def get_info(short_code: str):
    db = SessionLocal()
    try:
        record = db.query(URLRecord).filter(URLRecord.short_code == short_code).first()
        if not record:
            raise HTTPException(status_code=404, detail="Short URL not found")
        return {
            "short_code":   record.short_code,
            "original_url": record.original_url,
            "short_url":    f"{BASE_URL}/{record.short_code}",
            "created_at":   record.created_at.isoformat(),
        }
    finally:
        db.close()

@app.get("/{short_code}")
def redirect(short_code: str, request: Request):
    db = SessionLocal()
    try:
        record = db.query(URLRecord).filter(URLRecord.short_code == short_code).first()
        if not record:
            raise HTTPException(status_code=404, detail="Short URL not found")

        # Notify analytics via gRPC (fire-and-forget, truly non-blocking)
        ip = request.client.host if request.client else "unknown"
        ua = request.headers.get("user-agent", "unknown")
        threading.Thread(target=notify_click, args=(short_code, ip, ua), daemon=True).start()

        return RedirectResponse(url=record.original_url, status_code=302)
    finally:
        db.close()
