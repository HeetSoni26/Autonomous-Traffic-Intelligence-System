# Dockerfile for Hugging Face Spaces (Demo Mode)
FROM python:3.10-slim

# Install system dependencies required for OpenCV, EasyOCR, and SQLite
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables for Hugging Face Spaces
ENV HOST=0.0.0.0
ENV PORT=7860
# Force SIM_MODE=1 so the dashboard runs perfectly without needing a live GPU camera feed
ENV SIM_MODE=1
ENV PYTHONPATH=/app

# Hugging Face exposes port 7860
EXPOSE 7860

# Start the FastAPI server
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860"]
