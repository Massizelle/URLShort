import os
import threading
from concurrent import futures
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import grpc
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, String, Integer, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker

import analytics_pb2
import analytics_pb2_grpc

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./analytics.db")
GRPC_PORT    = int(os.getenv("GRPC_PORT", "50051"))

# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
engine       = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(bind=engine)
Base         = declarative_base()

class ClickRecord(Base):
    __tablename__ = "clicks"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    short_code = Column(String(10),   nullable=False, index=True)
    ip_address = Column(String(64),   nullable=True)
    user_agent = Column(String(512),  nullable=True)
    clicked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class URLStats(Base):
    __tablename__ = "url_stats"
    short_code   = Column(String(10), primary_key=True)
    click_count  = Column(Integer,    default=0)
    created_at   = Column(DateTime,   default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# gRPC Servicer
# ---------------------------------------------------------------------------
class AnalyticsServicer(analytics_pb2_grpc.AnalyticsServiceServicer):

    def RecordClick(self, request, context):
        db = SessionLocal()
        try:
            # Insert raw click
            click = ClickRecord(
                short_code=request.short_code,
                ip_address=request.ip_address,
                user_agent=request.user_agent,
            )
            db.add(click)

            # Upsert aggregated counter
            stats = db.query(URLStats).filter(URLStats.short_code == request.short_code).first()
            if stats:
                stats.click_count += 1
            else:
                db.add(URLStats(short_code=request.short_code, click_count=1))

            db.commit()
            return analytics_pb2.ClickResponse(success=True, message="Recorded")
        except Exception as e:
            db.rollback()
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return analytics_pb2.ClickResponse(success=False, message=str(e))
        finally:
            db.close()

    def GetStats(self, request, context):
        db = SessionLocal()
        try:
            stats = db.query(URLStats).filter(URLStats.short_code == request.short_code).first()
            if not stats:
                return analytics_pb2.StatsResponse(
                    short_code=request.short_code,
                    click_count=0,
                    created_at="",
                )
            return analytics_pb2.StatsResponse(
                short_code=stats.short_code,
                click_count=stats.click_count,
                created_at=stats.created_at.isoformat(),
            )
        finally:
            db.close()

# ---------------------------------------------------------------------------
# gRPC server (runs in background thread)
# ---------------------------------------------------------------------------
grpc_server = None

def start_grpc_server():
    global grpc_server
    grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    analytics_pb2_grpc.add_AnalyticsServiceServicer_to_server(AnalyticsServicer(), grpc_server)
    grpc_server.add_insecure_port(f"[::]:{GRPC_PORT}")
    grpc_server.start()
    print(f"gRPC server listening on port {GRPC_PORT}")
    grpc_server.wait_for_termination()

# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("DB connection OK")

    thread = threading.Thread(target=start_grpc_server, daemon=True)
    thread.start()

    yield

    if grpc_server:
        grpc_server.stop(grace=5)

app = FastAPI(title="Analytics Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# REST Routes
# ---------------------------------------------------------------------------
class ClickRequest(BaseModel):
    short_code: str
    ip_address: str = ""
    user_agent: str = ""

@app.get("/health")
def health():
    return {"status": "ok", "service": "analytics"}

@app.post("/record-click")
def record_click(body: ClickRequest):
    db = SessionLocal()
    try:
        db.add(ClickRecord(short_code=body.short_code, ip_address=body.ip_address, user_agent=body.user_agent))
        stats = db.query(URLStats).filter(URLStats.short_code == body.short_code).first()
        if stats:
            stats.click_count += 1
        else:
            db.add(URLStats(short_code=body.short_code, click_count=1))
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/stats/{short_code}")
def get_stats(short_code: str):
    db = SessionLocal()
    try:
        stats = db.query(URLStats).filter(URLStats.short_code == short_code).first()
        clicks = db.query(ClickRecord).filter(ClickRecord.short_code == short_code).all()

        return {
            "short_code":  short_code,
            "click_count": stats.click_count if stats else 0,
            "created_at":  stats.created_at.isoformat() if stats else None,
            "recent_clicks": [
                {
                    "ip_address": c.ip_address,
                    "user_agent": c.user_agent,
                    "clicked_at": c.clicked_at.isoformat(),
                }
                for c in sorted(clicks, key=lambda x: x.clicked_at, reverse=True)[:10]
            ],
        }
    finally:
        db.close()

@app.get("/stats")
def get_all_stats():
    db = SessionLocal()
    try:
        all_stats = db.query(URLStats).order_by(URLStats.click_count.desc()).all()
        return [
            {
                "short_code":  s.short_code,
                "click_count": s.click_count,
                "created_at":  s.created_at.isoformat(),
            }
            for s in all_stats
        ]
    finally:
        db.close()
