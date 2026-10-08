"""
Cloud Security Alert Lamp - Main FastAPI Application.
Integrates AWS S3, Lambda, DynamoDB, SNS, and AWS IoT Core.
Provides REST API and WebSocket real-time updates for the security monitoring dashboard.
"""

import os
import json
import logging
import asyncio
from typing import List, Set
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("cloud_lamp.main")

# Import route modules
from routes.dashboard import router as dashboard_router
from routes.buckets import router as buckets_router
from routes.alerts import router as alerts_router
from routes.events import router as events_router
from routes.led import router as led_router
from routes.demo import router as demo_router

from services.led_service import led_service
from services.auditor_service import auditor_service
from aws.client_factory import aws_factory

# WebSocket Connection Manager for Real-Time Dashboard Updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        dead_connections = set()
        msg_text = json.dumps(message)
        for connection in self.active_connections:
            try:
                await connection.send_text(msg_text)
            except Exception:
                dead_connections.add(connection)
        for dead in dead_connections:
            self.active_connections.discard(dead)

manager = ConnectionManager()

# Hook the LED service callback to broadcast over WebSocket
def sync_led_broadcast(payload: dict):
    # Schedule on current event loop if running
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(manager.broadcast(payload))
    except Exception as e:
        logger.debug(f"Broadcast dispatch note: {e}")

led_service.set_broadcast_callback(sync_led_broadcast)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Check initial state and run baseline audit
    logger.info("==================================================")
    logger.info("🚀 Cloud Security Alert Lamp Backend Starting...")
    if aws_factory.is_mock:
        logger.info("⚡ Mode: LAB DEMO / SIMULATION MODE (Zero AWS cost)")
    else:
        logger.info(f"⚡ Mode: LIVE AWS MODE (Region: {aws_factory.region})")
    logger.info("==================================================")
    
    # Run initial audit
    try:
        auditor_service.run_security_scan()
    except Exception as e:
        logger.warning(f"Initial scan note: {e}")
    
    yield
    
    logger.info("🛑 Cloud Security Alert Lamp Backend Shutting down...")

# Initialize FastAPI app
app = FastAPI(
    title="Cloud Security Alert Lamp API",
    description="Backend API for AWS S3 Public Bucket Detection & Real-Time IoT Security Alert Lamp Monitoring",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Friendly Error Handling (Section 16: Return clear, human-readable errors)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error processing {request.url.path}: {exc}", exc_info=True)
    msg = str(exc)
    if "Unable to locate credentials" in msg or "NoCredentialsError" in msg:
        user_msg = "Unable to connect to AWS. Please check the backend configuration or switch to DEMO mode."
    elif "AccessDenied" in msg or "403" in msg:
        user_msg = "AWS S3 or DynamoDB permission denied. Please verify IAM role policies."
    else:
        user_msg = "The security audit service encountered an error. Please retry or check backend logs."
    
    return JSONResponse(
        status_code=500,
        content={"detail": user_msg, "errorType": exc.__class__.__name__}
    )

# Mount Routes
app.include_router(dashboard_router)
app.include_router(buckets_router)
app.include_router(alerts_router)
app.include_router(events_router)
app.include_router(led_router)
app.include_router(demo_router)

# Health Check
@app.get("/api/health", tags=["Health"])
def health_check():
    return {
        "status": "HEALTHY",
        "service": "Cloud Security Alert Lamp Backend",
        "mode": "DEMO/SIMULATION" if aws_factory.is_mock else "LIVE_AWS",
        "region": aws_factory.region,
        "ledStatus": led_service.get_status().status
    }

# WebSocket Endpoint for Live Real-Time Dashboard Updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    # Immediately send current state on connection
    try:
        initial_stats = auditor_service.get_dashboard_stats()
        await websocket.send_text(json.dumps({
            "type": "INITIAL_STATE",
            "data": initial_stats.model_dump()
        }))
        while True:
            data = await websocket.receive_text()
            # If client sends a ping or scan trigger
            try:
                parsed = json.loads(data)
                if parsed.get("action") == "SCAN":
                    res = auditor_service.run_security_scan()
                    await manager.broadcast({
                        "type": "SCAN_COMPLETED",
                        "data": res.model_dump(),
                        "stats": auditor_service.get_dashboard_stats().model_dump()
                    })
                elif parsed.get("action") == "PING":
                    await websocket.send_text(json.dumps({"type": "PONG"}))
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"WebSocket session ended: {e}")
        manager.disconnect(websocket)

# Serve compiled frontend application directly from backend root URL
from fastapi.staticfiles import StaticFiles
dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
if os.path.exists(dist_dir):
    app.mount("/", StaticFiles(directory=dist_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
