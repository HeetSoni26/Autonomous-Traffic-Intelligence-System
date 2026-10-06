"""
tests/conftest.py
Test environment. Must run before any project import so that settings
pick up the test configuration (in-memory DB, ANPR disabled, no easyocr).
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_traffic_events.db")
os.environ.setdefault("ANPR_ENABLED", "0")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("REDIS_ENABLED", "0")
