<div align="center">

# TrafficIQ

### Autonomous Multi-Agent Traffic Intelligence System

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-ff6f00?style=for-the-badge)](https://ultralytics.com)
[![ZeroMQ](https://img.shields.io/badge/ZeroMQ-Messaging-e31e24?style=for-the-badge)](https://zeromq.org)
[![Tests](https://img.shields.io/badge/tests-12%20passing-10b981?style=for-the-badge)](#contributing)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

A fully offline, locally-running traffic management system that combines computer vision, multi-agent communication, and deterministic adaptive control to replace fixed traffic timers with something that actually responds to the road in real time.

[Quick Start](#quick-start) · [Architecture](#architecture) · [Dashboard](#dashboard) · [FAQ](#faq) · [Tech Stack](#tech-stack)

---

## 🏆 GitHub Badges

This repository is also used for earning GitHub achievement badges.

### Badges Being Earned
- Quickdraw ✅
- Pull Shark ✅
- Pair Extraordinaire ✅
- YOLO (in progress)

</div>

---

## Why this exists

Most traffic signals in the world are still running on fixed timers: a 30-second green, a 3-second yellow, a 30-second red, repeat. The timing was often set decades ago and hasn't changed since, regardless of whether there are two cars at the intersection or two hundred.

The consequences aren't abstract:

| Problem | Scale |
|---|---|
| Time lost | Urban commuters lose over 100 hours per year sitting at red lights |
| Economic cost | Traffic congestion costs the global economy upward of $1 trillion annually |
| Road deaths | 1.35 million people die in road accidents each year, many at intersections |
| Emissions | Vehicles idling at signals produce roughly 30% more CO₂ than vehicles in motion |
| Emergency delays | A 10-minute delay to an ambulance increases patient mortality risk by up to 8% |

There are commercial adaptive systems, SCOOT and SCATS among them, but they typically cost $50,000 to $500,000 per intersection, require proprietary hardware buried in the road, and still don't communicate across intersections or respond to accidents automatically.

TrafficIQ is a software-only alternative. It runs entirely offline on commodity hardware, uses cameras that are already on most city streets, and coordinates intersections as a network rather than treating each one as an isolated problem.

---

## What it does

| Old approach | TrafficIQ |
|---|---|
| Fixed timers | Deterministic logic that adapts every second |
| Buried inductive sensors | Standard cameras already in place |
| Isolated intersections | Agents that share state across the network |
| Manual incident response | Automatic accident detection and emergency routing |
| No visibility | Live dashboard with map, queue charts, and an animated intersection view |
| Cloud-dependent | Runs 100% offline on local hardware |

The core idea is straightforward: a standard IP camera, a reasonably modern CPU (GPU optional), and this software stack can turn any intersection into an autonomous node in a coordinated traffic network, at the cost of commodity hardware. Instead of unpredictable black-box machine learning for signal timing, the system relies on deterministic adaptive algorithms that are robust, safe, and require zero training.

---

## Dashboard

![TrafficIQ Dashboard](docs/dashboard.png)

The dashboard at `http://localhost:8000` shows the network in real time:

- **Network map** with congestion markers that shift from green to red as density increases
- **Live Intersection view**: an animated top-down stage where the cars on each approach exactly match the queue lengths reported on the message bus, and they only cross the stop line when the adaptive controller shows GREEN
- Per-intersection queue charts updating every second
- Signal phase grid showing which directions are currently green
- Live event feed for violations, detected accidents, and variable message sign alerts
- Summary KPIs: throughput, average wait time, active violations, active incidents
- Built-in **AI City Manager** chat that answers questions against the live network state

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CAMERA FEEDS                                │
│              (Webcam / Video File / RTSP Stream)                    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    LAYER 1: COMPUTER VISION                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  YOLOv8      │  │  ByteTrack   │  │  Violation Detector      │  │
│  │  Detector    │→ │  Tracker     │→ │  Accident Detector       │  │
│  │              │  │              │  │  Congestion Map          │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ ZeroMQ Events
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   LAYER 2: MULTI-AGENT SYSTEM                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                  Coordinator (Arbiter)                      │    │
│  └──────────┬──────────────────┬──────────────┬───────────────┘    │
│             ▼                  ▼              ▼                     │
│  ┌──────────────┐   ┌──────────────┐  ┌──────────────┐             │
│  │ SignalAgent  │   │ Emergency    │  │ Congestion   │             │
│  │ (per inters.)│   │ Agent        │  │ Agent        │             │
│  └──────────────┘   └──────────────┘  └──────────────┘             │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   LAYER 3: API + DASHBOARD                          │
│                                                                     │
│   FastAPI (REST + WebSocket) → HTML/CSS/JS Dashboard               │
│   Leaflet Map · Animated Intersection Stage · Chart.js              │
└─────────────────────────────────────────────────────────────────────┘
```

DEMO_MODE runs the same three layers inside a single process: the simulator plays the vision role and publishes over the real ZeroMQ bus, so agents, API, and dashboard all behave exactly as they do with physical cameras.

---

## How it works

### Vision pipeline

Every frame from every camera passes through four stages:

1. **YOLOv8** detects all vehicles and pedestrians, returning bounding boxes with class and confidence scores.
2. **ByteTrack** assigns each vehicle a persistent ID and tracks it across frames.
3. **Speed estimation** computes pixel displacement per frame, converts to km/h using a per-camera calibration factor.
4. **Violation and anomaly detection** runs geometric checks on each tracked vehicle:
   - Red-light: vehicle center is inside the stop-line polygon while the signal is RED
   - Speeding: estimated speed exceeds the configured limit (default 50 km/h, with a 10 km/h grace margin)
   - Wrong-way: vehicle direction vector is more than 120° off from the allowed lane direction
   - Accident: two vehicles have been stationary within 80px of each other for more than 15 seconds

Congestion state per approach zone is computed as a vehicle density grid and classified as FREE, MODERATE, HEAVY, or GRIDLOCK.

### Agent decision loop

Each `SignalAgent` runs this cycle roughly every second:

```
Read current queue lengths from the vision layer
    ↓
Calculate dynamic split using deterministic Webster's logic
    ↓
Action: assign N/S and E/W green durations proportionally
    ↓
Apply the signal change
    ↓
Publish updated state to the network via ZeroMQ
```

Unlike Reinforcement Learning (which can behave unpredictably and cause critical safety failures), this deterministic approach guarantees queue clearance safely by distributing green time precisely relative to instantaneous demand. Every adaptation is logged, so you can watch the controller react:

```
Adaptive split @ INT_3: NS 42s / EW 18s (queues N=14 S=11 E=2 W=3)
```

### Emergency routing

When an accident is detected:

```
AccidentEvent published on "accidents" topic
    ↓
EmergencyAgent receives event
    ↓
ALL_RED preemption at the affected intersection
    ↓
Dijkstra's algorithm finds the shortest path through the intersection graph
    ↓
Green wave created along the emergency vehicle route
    ↓
Normal operation restored after the scene clears
```

---

## Tech stack

| Component | Technology | Notes |
|---|---|---|
| Object detection | YOLOv8n (Ultralytics) | CPU-capable, fully offline after first download |
| Multi-object tracking | ByteTrack (supervision) | Handles occlusions without a GPU |
| Agent messaging | ZeroMQ XPUB/XSUB (pyzmq) | Sub-millisecond pub/sub, no separate broker process |
| Shared state | Redis (optional) / in-process dict | Agent coordination and crash recovery |
| API | FastAPI + WebSocket | Async, auto-generates `/docs` |
| Dashboard | Vanilla HTML/CSS/JS + Canvas | No build step, zero dependencies |
| Map | OpenStreetMap via Leaflet.js | Keyless tiles, dark themed with CSS |
| Charts | Chart.js | Smooth live updates |
| Database | SQLite via SQLAlchemy | Zero config, stores violations and events |
| Logging | Loguru | Structured JSON, configurable rotation |

---

## Quick start

**Prerequisites:** Python 3.10+, Git

### 1. Clone and install

```bash
git clone https://github.com/HeetSoni26/Autonomous-Traffic-Intelligence-System.git
cd Autonomous-Traffic-Intelligence-System

python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Run the self-contained demo

```bash
# Windows (cmd)
set DEMO_MODE=1
python run.py

# Windows (Git Bash / PowerShell: $env:DEMO_MODE="1")
# Linux / macOS
DEMO_MODE=1 python run.py
```

Open **http://localhost:8000**. One command boots the API, the ZeroMQ broker, all eight agents, and the traffic simulator. The dashboard fills immediately: adaptive green splits, violations, accidents with automatic emergency preemption, and the animated intersection view. No camera required, and no part of the pipeline is mocked: the simulator publishes on the same ZeroMQ topics a real vision node uses.

Flip to the **Live Intersection** tab above the map and watch cars stack on red, flow on green, and the split lengths change with demand.

### 3. Or run the pieces separately (real cameras)

```bash
# Terminal 1: API + dashboard
python run.py

# Terminal 2: broker + agents
PYTHONPATH=. python -m agents.coordinator

# Terminal 3: a real camera or video file
PYTHONPATH=. python vision/vision_node.py --source 0            # webcam
PYTHONPATH=. python vision/vision_node.py --source video.mp4    # video file
```

### 4. Run the tests

```bash
PYTHONPATH=. pytest tests/ -v
```

### 5. Start optional infrastructure

```bash
docker compose up -d   # Redis
```

Then add `REDIS_ENABLED=True` to a `.env` file.

---

## Deploying the live demo

The repo ships a `Dockerfile` (built on `requirements-demo.txt`, which skips PyTorch and OpenCV) that runs the entire demo in one container. It deploys directly to Hugging Face Spaces as a Docker Space: the dashboard, agents, and simulator all serve from a single public URL.

---

## Project structure

```
traffic-intelligence/
├── run.py                      # One-command entry point (API; + demo stack with DEMO_MODE=1)
│
├── vision/
│   ├── detector.py             # YOLOv8 vehicle and pedestrian detection
│   ├── tracker.py              # ByteTrack tracking, speed estimation
│   ├── violation_detector.py   # Red-light, speeding, wrong-way detection
│   ├── accident_detector.py    # Stopped-vehicle collision heuristic
│   ├── congestion_map.py       # Density grid and queue length estimation
│   ├── stream_reader.py        # Multi-source OpenCV video ingestion
│   ├── anpr.py                 # Optional number plate recognition (EasyOCR)
│   └── vision_node.py          # Links YOLO/ByteTrack direct to ZeroMQ
│
├── agents/
│   ├── base_agent.py           # Abstract ZeroMQ agent with heartbeat
│   ├── signal_agent.py         # Adaptive traffic signal controller
│   ├── emergency_agent.py      # Accident response and Dijkstra routing
│   ├── congestion_agent.py     # Congestion alerts and green-wave requests
│   ├── coordinator.py          # System entry point, conflict arbitration
│   └── message_bus.py          # ZeroMQ XPUB/XSUB broker and Redis state
│
├── simulation/
│   └── sim_node.py             # Synthetic vision node: honest queue dynamics on the real bus
│
├── api/
│   ├── main.py                 # FastAPI app, demo wiring, bus-to-dashboard bridge
│   ├── schemas.py              # Pydantic models for all data types
│   ├── chatbot.py              # Optional Gemini "AI City Manager" (mock fallback without a key)
│   └── websocket_manager.py    # WebSocket broadcast manager
│
├── dashboard/
│   ├── index.html              # Standalone dark-mode dashboard
│   └── static/
│       └── traffic_sim.js      # Animated Live Intersection stage
│
├── database/
│   ├── models.py               # SQLAlchemy ORM models
│   ├── event_store.py          # SQLite violation and event persistence
│   └── influx_logger.py        # Optional time-series metrics export
│
├── config/
│   ├── settings.py             # Pydantic BaseSettings loaded from .env
│   └── logging_config.py       # Structured JSON logging via loguru
│
├── tests/                      # Vision, agent, and simulator unit tests
├── docker-compose.yml          # Optional Redis
├── Dockerfile                  # Self-contained demo container (HF Spaces ready)
├── requirements.txt            # Full install (vision included)
├── requirements-demo.txt       # Demo-only install (no PyTorch/OpenCV)
└── README.md
```

---

## Configuration

All settings live in `config/settings.py` and can be overridden with a `.env` file at the project root:

```env
LOG_LEVEL=DEBUG
YOLO_MODEL_PATH=yolov8s.pt        # swap to a larger model for better accuracy
SPEED_LIMIT_KMPH=50.0
ACCIDENT_STOP_SECONDS=15.0
ANPR_ENABLED=0                    # skip the OCR engine entirely
REDIS_ENABLED=True                # when the docker-compose Redis is running
```

---

## API reference

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Live dashboard (HTML) |
| `/intersections` | GET | All intersections and their current state |
| `/intersections/{id}/state` | GET | Detailed state for a single intersection |
| `/violations` | GET | Recent violations from the live feed |
| `/violations/history` | GET | Persisted violation history from SQLite |
| `/accidents` | GET | Currently active accident events |
| `/alerts` | GET | Recent congestion alerts from the CongestionAgent |
| `/stats` | GET | Global KPIs: throughput, wait time, counts |
| `/signals/{id}/override` | POST | Force a signal to a specific phase |
| `/chat` | POST | Ask the AI City Manager about the live network |
| `/ws/live` | WebSocket | Push stream of all events (once per second) |
| `/docs` | GET | Interactive Swagger documentation |

---

## FAQ

**Does this need an internet connection?**

No. On first launch, YOLOv8 downloads a 6 MB weights file and caches it locally. After that, everything runs from local files with no network dependency: no cloud API, no telemetry, nothing.

**Does it work without cameras?**

Yes. Start it with `DEMO_MODE=1` and a synthetic traffic simulator generates honest, self-consistent demand for all six intersections: queues build on red, drain on green, rush hours come and go, and incidents trigger real emergency preemption. Because the simulator publishes on the same ZeroMQ topics as a real vision node, the agents and dashboard behave exactly as they do in production.

**Why use deterministic logic instead of Reinforcement Learning?**

Using RL for traffic lights is fascinating for academic papers, but it is deeply problematic for real-world deployment. RL models are black boxes and can act unpredictably. If an RL agent makes an unexplainable decision and causes a fatal crash, the city is liable.

By using mathematically rigorous deterministic adaptive algorithms (like a dynamic, queue-based Webster's formula), the system achieves large efficiency gains over fixed timers while remaining 100% verifiable, provably safe, and requiring zero training time.

**How does violation detection work? Doesn't that require complex vision?**

The detection itself is simple geometry. YOLOv8 gives bounding boxes; the violation logic just does polygon checks:

```python
# Red-light violation
if stop_line_polygon.contains(Point(box.cx, box.cy)) and signal["N"] == "RED":
    → RED_LIGHT violation

# Speeding
speed_kmh = (distance_m / elapsed_seconds) * 3.6
if speed_kmh > speed_limit + 10:
    → SPEEDING violation

# Wrong-way
if dot(actual_direction, allowed_direction) < -0.5:  # > 120° off
    → WRONG_WAY violation
```

**Can this run on a Raspberry Pi or other edge hardware?**

Yes, with some tuning:

- Use `yolov8n.pt` (6 MB nano model, runs at ~15 FPS on a Pi 5)
- Reduce `TRACKER_MAX_AGE` from 30 to 15
- The API and dashboard run without issues on any ARM device with 4 GB+ RAM

**How does the system recover from crashes?**

Every agent publishes a heartbeat to the `agent.health` topic every 5 seconds. The Coordinator monitors these. If a heartbeat is missing for 15 seconds, the Coordinator logs the failure and respawns the agent; the new agent loads its last known state from Redis, or starts from scratch if Redis has no record.

**Does this have any environmental benefit?**

Vehicles idling at signals emit significantly more CO₂ than vehicles in motion. This deterministic system strictly minimizes queue lengths and idle time as part of its objective, which directly reduces emissions. The academic literature on adaptive signal control generally reports 20 to 35% reductions in intersection emissions.

**How is this different from Google Maps or Waze?**

| | Google Maps / Waze | TrafficIQ |
|---|---|---|
| What it controls | Driver routing suggestions | Infrastructure itself (the signals) |
| Cloud dependency | Fully cloud-dependent | 100% offline |
| Privacy | Tracks all users | No user data collected |
| Signal control | None | Direct signal control |
| Accident detection | Crowdsourced reports | Automatic via computer vision |
| Emergency routing | Not integrated | Automatic preemption |
| Cost | Free to end users | Open source, commodity hardware |

The two approaches are complementary. Google Maps tells drivers to take an alternate route; TrafficIQ makes that alternate route faster by coordinating the signals along it.

---

## Current state

An honest summary of where the project stands:

**Fully operational:**
- FastAPI backend: REST endpoints, WebSocket broadcast, static asset serving, violation persistence
- ZeroMQ XPUB/XSUB broker: decentralized inter-agent messaging, sub-millisecond latency
- Agent lifecycle: heartbeat monitoring, conflict arbitration, adaptive green splits driven by live queue data
- Dashboard: network map, animated intersection view, queue charts, signal phase grid, event feed, AI City Manager chat
- Computer vision pipeline: YOLOv8 detection and ByteTrack tracking wired into the main data flow
- Emergency response: automatic preemption on accidents and Dijkstra green-wave routing for emergency vehicles
- Database: SQLAlchemy models and a thread-safe EventStore log violations and accidents
- Test suite: 12 unit tests covering vision heuristics, agent logic, and simulator dynamics

**Demo Mode (simulation fallback):**
- With `DEMO_MODE=1`, a synthetic vision node feeds the real bus so the full pipeline runs on any machine, no camera or GPU needed.

---

## Roadmap

- [x] **ANPR**: automatic number plate recognition for violation ticketing
- [x] **Pedestrian crosswalk detection**: extend walk phase when pedestrians are waiting
- [x] **LLM integration**: natural language queries against live network state
- [x] **Animated intersection view**: watch the live bus state as moving traffic
- [ ] **Mobile companion app**: nearest congestion, alternate routes
- [ ] **Multi-city federation**: share aggregate learning across deployments
- [ ] **GPIO control**: real traffic light hardware on Raspberry Pi
- [ ] Custom YOLO fine-tuning on local vehicle types (auto-rickshaws, e-bikes, etc.)

---

## Contributing

Pull requests are welcome. To contribute:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Run the test suite: `PYTHONPATH=. pytest tests/ -v`
4. Open a pull request with a clear description of what changed and why

---

## License

MIT License. See [LICENSE](LICENSE). Free to use, modify, and deploy commercially.

---

## Author

**Heet Soni**
GitHub: [@HeetSoni26](https://github.com/HeetSoni26)
Repository: [Autonomous-Traffic-Intelligence-System](https://github.com/HeetSoni26/Autonomous-Traffic-Intelligence-System)
