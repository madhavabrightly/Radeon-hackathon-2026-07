"""FastAPI main application for AI PC Operator.

This is the entry point for the local PC agent server.
It receives commands from the mobile remote, processes them through
the agent brain, and executes tools with proper approval flow.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional

from app.db.database import init_db, db_session, close_db
from app.agent.router import AgentRouter
from app.security.pairing import PairingManager
from app.approvals.manager import ApprovalManager
from app.tools.system_tools import SystemTools
from app.tools.file_tools import FileTools
from app.tools.browser_tools import BrowserTools
from app.tools.auth_tools import AuthTools
from app.logs.redactor import LogRedactor

# Paths
ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "ai_pc_operator" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class RedactingFilter(logging.Filter):
    """Redact secrets before records reach file/console handlers."""

    def __init__(self) -> None:
        super().__init__()
        self.redactor = LogRedactor()

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.redactor.redact(str(record.msg))
        if record.args:
            record.args = tuple(
                self.redactor.redact(str(arg)) for arg in record.args
            )
        return True

# Setup logging with redaction
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(DATA_DIR / "agent.log"),
        logging.StreamHandler(),
    ],
)
for handler in logging.getLogger().handlers:
    handler.addFilter(RedactingFilter())
logger = logging.getLogger("ai_pc_operator")

# Global state
agent_router: Optional[AgentRouter] = None
pairing_manager: Optional[PairingManager] = None
approval_manager: Optional[ApprovalManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global agent_router, pairing_manager, approval_manager

    logger.info("Starting AI PC Operator...")

    # Initialize database
    await init_db()

    # Initialize managers
    pairing_manager = PairingManager()
    approval_manager = ApprovalManager()

    # Initialize agent router
    agent_router = AgentRouter(
        approval_manager=approval_manager,
        system_tools=SystemTools(),
        file_tools=FileTools(),
        browser_tools=BrowserTools(),
        auth_tools=AuthTools(),
    )

    logger.info("AI PC Operator started successfully")

    yield

    logger.info("Shutting down AI PC Operator...")
    if agent_router:
        await agent_router.shutdown()
    await close_db()


# Create FastAPI app
app = FastAPI(
    title="AI PC Operator",
    description="Local AI PC Operator with mobile approval",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for mobile web remote
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class CommandRequest(BaseModel):
    """Command request from mobile remote."""
    text: str
    device_id: Optional[str] = None


class CommandResponse(BaseModel):
    """Command response to mobile remote."""
    command_id: int
    status: str
    result: Optional[str] = None
    requires_approval: bool = False
    approval_id: Optional[int] = None


class ApprovalRequest(BaseModel):
    """Approval request from mobile."""
    approval_id: int
    approved: bool
    master_key: Optional[str] = None  # For vault unlock


class PairingRequest(BaseModel):
    """Pairing code from mobile."""
    code: str
    device_name: str


# REST API endpoints
@app.get("/")
async def root():
    """Root endpoint - serves mobile web remote."""
    return {
        "name": "AI PC Operator",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/status")
async def status():
    """System status endpoint."""
    system_tools = SystemTools()
    return await system_tools.get_status()


@app.get("/runtime")
async def runtime_status():
    """Runtime budget and lazy model status."""
    if not agent_router:
        raise HTTPException(status_code=503, detail="Server not ready")

    budget = agent_router.resource_budget.measure()
    return {
        "memory": {
            "available_mb": budget.available_mb,
            "model_budget_mb": budget.model_budget_mb,
            "mode": budget.mode,
            "allow_ocr": budget.allow_ocr,
            "allow_detector": budget.allow_detector,
            "allow_llm": budget.allow_llm,
        },
        "models": agent_router.model_registry.status(),
        "artifacts": agent_router.artifacts.inventory(),
        "screen_cache": agent_router.screen_cache.stats(),
    }


@app.post("/pair")
async def pair(request: PairingRequest):
    """Pair a new device with pairing code."""
    if not pairing_manager:
        raise HTTPException(status_code=503, detail="Server not ready")

    device = await pairing_manager.pair_device(
        code=request.code,
        device_name=request.device_name,
    )

    if not device:
        raise HTTPException(status_code=401, detail="Invalid pairing code")

    return {
        "device_id": device["id"],
        "token": device["token"],
        "paired_at": device["paired_at"],
    }


@app.get("/pair/code")
async def get_pairing_code():
    """Get current pairing code (shown on PC)."""
    if not pairing_manager:
        raise HTTPException(status_code=503, detail="Server not ready")

    code = await pairing_manager.generate_code()
    return {"code": code, "expires_in": 300}  # 5 minutes


@app.post("/command")
async def execute_command(request: CommandRequest):
    """Execute a command from mobile remote."""
    if not agent_router:
        raise HTTPException(status_code=503, detail="Server not ready")

    # Verify device if provided
    if request.device_id:
        if not await pairing_manager.verify_device(request.device_id):
            raise HTTPException(status_code=401, detail="Device not paired")

    # Route command through agent
    result = await agent_router.process_command(
        text=request.text,
        device_id=request.device_id,
    )

    return result


@app.get("/approvals/pending")
async def get_pending_approvals(device_id: Optional[str] = None):
    """Get pending approval requests."""
    if not approval_manager:
        raise HTTPException(status_code=503, detail="Server not ready")

    approvals = await approval_manager.get_pending(device_id)
    return {"approvals": approvals}


@app.post("/approvals/resolve")
async def resolve_approval(request: ApprovalRequest):
    """Resolve an approval request."""
    if not approval_manager:
        raise HTTPException(status_code=503, detail="Server not ready")

    success = await approval_manager.resolve(
        approval_id=request.approval_id,
        approved=request.approved,
        master_key=request.master_key,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Approval not found")

    return {"status": "resolved"}


@app.post("/emergency/stop")
async def emergency_stop():
    """Emergency stop - halt all operations."""
    logger.warning("EMERGENCY STOP triggered!")

    if agent_router:
        await agent_router.emergency_stop()

    if approval_manager:
        await approval_manager.cancel_all_pending()

    return {"status": "stopped"}


@app.get("/history")
async def get_history(limit: int = 50):
    """Get command history."""
    safe_limit = min(max(limit, 1), 200)
    async with db_session() as db:
        cursor = await db.execute(
            """
            SELECT id, source, device_id, input_text, intent, risk_level,
                   status, substr(result, 1, 1000) AS result, error,
                   created_at, completed_at
            FROM commands
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        )
        rows = await cursor.fetchall()
    return {"history": [dict(row) for row in rows]}


# WebSocket for real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time communication with mobile."""
    await websocket.accept()
    logger.info("WebSocket connected")

    try:
        while True:
            # Receive command
            data = await websocket.receive_json()

            if data.get("type") == "command":
                # Process command
                result = await agent_router.process_command(
                    text=data["text"],
                    device_id=data.get("device_id"),
                )
                await websocket.send_json({
                    "type": "command_result",
                    "data": result,
                })

            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        logger.info("WebSocket disconnected")


# Serve mobile web remote
FRONTEND_DIR = ROOT / "ai_pc_operator" / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/remote", StaticFiles(directory=str(FRONTEND_DIR)), name="remote")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
