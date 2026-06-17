"""
config/settings.py
All configuration loaded from environment variables / .env file.
Uses Pydantic BaseSettings for validation and type safety.
"""
import os
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── Project ──────────────────────────────────────────────────
    PROJECT_NAME: str = "Autonomous Traffic Intelligence System"
    LOG_LEVEL: str = "INFO"

    # ── Redis (Shared State / PubSub) ─────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_ENABLED: bool = False   # Set True when Redis is running

    # ── ZeroMQ (Message Bus) ──────────────────────────────────────
    ZMQ_BROKER_FRONTEND: str = "tcp://127.0.0.1:5559"
    ZMQ_BROKER_BACKEND:  str = "tcp://127.0.0.1:5560"

    # ── Database ──────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./traffic_events.db"

    # ── InfluxDB (Time-series metrics) ────────────────────────────
    INFLUXDB_URL:    str = "http://localhost:8086"
    INFLUXDB_TOKEN:  str = "my-super-secret-auth-token"
    INFLUXDB_ORG:    str = "traffic_org"
    INFLUXDB_BUCKET: str = "traffic_metrics"
    INFLUXDB_ENABLED: bool = False  # Set True when InfluxDB is running

    # ── Vision / ML ───────────────────────────────────────────────
    YOLO_MODEL_PATH: str = "yolov8n.pt"     # auto-downloads on first run
    CONFIDENCE_THRESHOLD: float = 0.5
    TRACKER_MAX_AGE: int = 30
    SPEED_LIMIT_KMPH: float = 50.0          # default speed limit per lane
    ACCIDENT_STOP_SECONDS: float = 15.0     # seconds stopped → accident flag
    ACCIDENT_OVERLAP_PX: float = 80.0       # pixel proximity for collision

    # ── Intersection geometry (pixels) ────────────────────────────
    # Stop-line zones: dict[approach] = (x1,y1,x2,y2)
    STOP_LINE_N: str = "100,390,300,420"
    STOP_LINE_S: str = "400,580,600,610"
    STOP_LINE_E: str = "580,300,610,480"
    STOP_LINE_W: str = "90,300,120,480"

    # ── SUMO & RL ─────────────────────────────────────────────────
    SUMO_GUI: bool = False
    SUMO_CFG: str = "simulation/sumo_config/network.sumocfg"
    RL_CHECKPOINT_DIR: str = "./checkpoints"

    # ── API / Dashboard ───────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # ── Reward hyperparameters ────────────────────────────────────
    REWARD_ALPHA: float = 0.5   # wait-time weight
    REWARD_BETA:  float = 0.5   # queue-length weight
    REWARD_GAMMA: float = 1.0   # throughput bonus
    REWARD_DELTA: float = 5.0   # phase-switch penalty
    REWARD_EPS:   float = 0.1   # emissions proxy weight

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Singleton
settings = Settings()
