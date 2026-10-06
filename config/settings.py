"""
config/settings.py
All configuration loaded from environment variables / .env file.
Uses Pydantic BaseSettings for validation and type safety.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Project ──────────────────────────────────────────────────
    PROJECT_NAME: str = "Autonomous Traffic Intelligence System"
    LOG_LEVEL: str = "INFO"

    # ── Demo mode ─────────────────────────────────────────────────
    # DEMO_MODE=1 starts the ZMQ broker, all agents, and a synthetic traffic
    # simulator inside the API process so the full pipeline runs with one
    # command and no cameras. All data still flows through the real bus.
    DEMO_MODE: bool = False
    SIM_SPEED: float = 1.0            # simulator time multiplier

    # ── Redis (Shared State / PubSub) ─────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_ENABLED: bool = False       # Set True when Redis is running

    # ── ZeroMQ (Message Bus) ──────────────────────────────────────
    ZMQ_BROKER_FRONTEND: str = "tcp://127.0.0.1:5559"
    ZMQ_BROKER_BACKEND:  str = "tcp://127.0.0.1:5560"

    # ── Database ──────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./traffic_events.db"

    # ── Vision / ML ───────────────────────────────────────────────
    YOLO_MODEL_PATH: str = "yolov8n.pt"     # auto-downloads on first run
    CONFIDENCE_THRESHOLD: float = 0.5
    TRACKER_MAX_AGE: int = 30
    ANPR_ENABLED: bool = True               # lazy-loaded; needs easyocr installed
    SPEED_LIMIT_KMPH: float = 50.0          # default speed limit per lane
    ACCIDENT_STOP_SECONDS: float = 15.0     # seconds stopped → accident flag
    ACCIDENT_OVERLAP_PX: float = 80.0       # pixel proximity for collision

    # ── Intersection geometry (pixels) ────────────────────────────
    # Stop-line zones: dict[approach] = (x1,y1,x2,y2)
    STOP_LINE_N: str = "100,390,300,420"
    STOP_LINE_S: str = "400,580,600,610"
    STOP_LINE_E: str = "580,300,610,480"
    STOP_LINE_W: str = "90,300,120,480"

    # ── API / Dashboard ───────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Singleton
settings = Settings()
