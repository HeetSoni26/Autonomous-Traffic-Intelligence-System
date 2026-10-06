# TrafficIQ live demo, deployable to Hugging Face Spaces (or any container host).
# Uses the minimal demo dependency set: API + ZeroMQ broker + multi-agent layer
# + traffic simulator. No PyTorch / OpenCV: the simulator drives the same bus
# the real vision nodes use, so the demo exercises the genuine pipeline.
FROM python:3.11-slim

WORKDIR /app

COPY requirements-demo.txt .
RUN pip install --no-cache-dir -r requirements-demo.txt

COPY . .

# DEMO_MODE boots the broker, every agent, and the simulator in-process.
ENV DEMO_MODE=1 \
    PYTHONPATH=/app \
    ANPR_ENABLED=0 \
    LOG_LEVEL=INFO

# Hugging Face Spaces routes to port 7860; run.py also honors $PORT/$HOST.
EXPOSE 7860

CMD ["python", "run.py"]
