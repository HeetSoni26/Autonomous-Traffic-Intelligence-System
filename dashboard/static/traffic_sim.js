/*
 * dashboard/static/traffic_sim.js
 * Live Intersection view: an animated top-down stage driven by the same
 * WebSocket tick the rest of the dashboard uses. The number of cars waiting
 * on each approach equals the queue length reported on the ZeroMQ bus, and
 * cars only cross the stop line when the SignalAgent has that approach
 * GREEN. Nothing here is faked: this is the bus state, drawn.
 */
(function () {
  'use strict';

  const APPROACHES = ['N', 'S', 'E', 'W'];
  // Approach N comes from the top heading down, S from the bottom heading
  // up, E from the right heading left, W from the left heading right.
  // Car position p = remaining distance to the intersection center; the
  // stop line sits at p = stopGap, and cars despawn past the far side.
  const GEOM = {
    N: { axis: 'v' },
    S: { axis: 'v' },
    E: { axis: 'h' },
    W: { axis: 'h' }
  };

  const CAR_COLORS = ['#e2e8f0', '#94a3b8', '#475569', '#facc15', '#60a5fa', '#f87171', '#34d399'];
  const MAX_SPEED = 95;        // px/s
  const ACCEL = 70;            // px/s^2
  const CAR_LEN = 22;
  const CAR_GAP = 10;

  let canvas = null;
  let ctx = null;
  let selectedId = 'INT_1';
  let currentData = null;      // latest intersection payloads
  let cars = [];               // {approach, p, speed, color, len}
  let lastFrame = 0;
  let spawnAccum = 0;
  let visible = false;
  let rafId = null;

  function current() {
    if (!currentData) return null;
    return currentData.find(i => i.id === selectedId) || null;
  }

  function queueOf(approach) {
    const it = current();
    return (it && it.queue_lengths && it.queue_lengths[approach]) || 0;
  }

  function signalOf(approach) {
    const it = current();
    return (it && it.approaches && it.approaches[approach] || 'RED').toUpperCase();
  }

  // ── Geometry helpers ─────────────────────────────────────────────────
  function layout(w, h) {
    const cx = w / 2, cy = h / 2;
    const roadW = Math.max(96, Math.min(150, Math.min(w, h) * 0.30));
    const laneW = roadW / 4;
    const stopGap = roadW * 0.85;
    return { cx, cy, roadW, laneW, stopGap };
  }

  function laneCenter(L, approach) {
    // Lane offset from the road center line (left-hand traffic layout).
    const off = L.laneW / 2 + L.laneW * 0.55;
    switch (approach) {
      case 'N': return { x: L.cx + off, y: null };
      case 'S': return { x: L.cx - off, y: null };
      case 'E': return { x: null, y: L.cy - off };
      default:  return { x: null, y: L.cy + off };   // W
    }
  }

  function pathLength(L, w, h, approach) {
    // Spawn just beyond the canvas edge on this approach's axis so every
    // queued car becomes visible quickly.
    const half = GEOM[approach].axis === 'v' ? h / 2 : w / 2;
    return half + 40;
  }

  function carPos(L, car) {
    const lane = laneCenter(L, car.approach);
    if (GEOM[car.approach].axis === 'v') {
      const y = car.approach === 'N' ? L.cy - car.p : L.cy + car.p;
      return { x: lane.x + car.laneJitter, y };
    }
    const x = car.approach === 'W' ? L.cx - car.p : L.cx + car.p;
    return { x, y: lane.y + car.laneJitter };
  }

  // ── Simulation ───────────────────────────────────────────────────────
  function spawn(approach, L, w, h) {
    cars.push({
      approach,
      p: pathLength(L, w, h, approach) + Math.random() * 20,
      speed: MAX_SPEED * (0.55 + Math.random() * 0.2),
      color: CAR_COLORS[Math.floor(Math.random() * CAR_COLORS.length)],
      len: CAR_LEN * (0.85 + Math.random() * 0.35),
      laneJitter: (Math.random() - 0.5) * L.laneW * 0.22
    });
  }

  function step(dt, L, w, h) {
    const stopAt = L.stopGap;

    // Keep the reported queue depth on every approach: refill gradually.
    spawnAccum += dt;
    if (spawnAccum > 0.12) {
      spawnAccum = 0;
      for (const a of APPROACHES) {
        const active = cars.reduce((n, c) => n + (c.approach === a ? 1 : 0), 0);
        if (active < queueOf(a)) spawn(a, L, w, h);
      }
    }

    for (const a of APPROACHES) {
      // Closest to the center first: that car is everybody's leader.
      const list = cars.filter(c => c.approach === a).sort((x, y) => x.p - y.p);
      const green = signalOf(a) === 'GREEN';

      for (let i = 0; i < list.length; i++) {
        const car = list[i];
        const leader = list[i - 1];
        let target = MAX_SPEED;

        // Stop line: brake so the front stops at the line while RED.
        // Cars already inside the box keep crossing.
        if (!green && car.p > stopAt) {
          const d = car.p - stopAt - 2;
          target = Math.min(target, Math.sqrt(2 * ACCEL * Math.max(0, d)));
        }

        // Car ahead: never closer than a safe gap behind its tail.
        if (leader) {
          const limit = leader.p + leader.len + CAR_GAP;
          if (car.p <= limit + 0.5) target = 0;
          else target = Math.min(target, Math.sqrt(2 * ACCEL * (car.p - limit)));
        }

        car.speed += Math.sign(target - car.speed) *
                     Math.min(Math.abs(target - car.speed), ACCEL * dt);
        car.p -= car.speed * dt;

        // Despawn once the car has traveled most of the way off the far side.
        const exit = pathLength(L, w, h, car.approach) - 60;
        if (car.p < -exit) car._dead = true;
      }
    }

    cars = cars.filter(c => !c._dead);
    if (cars.length > 240) cars.length = 240;   // absolute safety cap
  }

  // ── Drawing ──────────────────────────────────────────────────────────
  function roundRect(c, x, y, rw, rh, r) {
    c.beginPath();
    c.moveTo(x + r, y);
    c.arcTo(x + rw, y, x + rw, y + rh, r);
    c.arcTo(x + rw, y + rh, x, y + rh, r);
    c.arcTo(x, y + rh, x, y, r);
    c.arcTo(x, y, x + rw, y, r);
    c.closePath();
  }

  function drawCar(c, car, L) {
    const { x, y } = carPos(L, car);
    c.fillStyle = car.color;
    if (GEOM[car.approach].axis === 'v') {
      roundRect(c, x - 7, y - car.len / 2, 14, car.len, 3);
    } else {
      roundRect(c, x - car.len / 2, y - 7, car.len, 14, 3);
    }
    c.fill();
  }

  function drawSignals(c, L) {
    // One head per approach, at the stop line beside that approach's lane.
    const e = L.roadW / 2 + 9;
    const heads = [
      { a: 'N', x: L.cx + e, y: L.cy - L.stopGap },
      { a: 'S', x: L.cx - e, y: L.cy + L.stopGap },
      { a: 'E', x: L.cx + L.stopGap, y: L.cy - e },
      { a: 'W', x: L.cx - L.stopGap, y: L.cy + e }
    ];
    for (const h of heads) {
      const col = signalOf(h.a) === 'GREEN' ? '#10b981' : '#ef4444';
      c.beginPath();
      c.arc(h.x, h.y, 5, 0, Math.PI * 2);
      c.fillStyle = col;
      c.shadowColor = col;
      c.shadowBlur = 10;
      c.fill();
      c.shadowBlur = 0;
    }
  }

  function render(L, w, h) {
    ctx.clearRect(0, 0, w, h);

    // Ground
    ctx.fillStyle = '#0c111d';
    ctx.fillRect(0, 0, w, h);

    // Roads
    ctx.fillStyle = '#1b2437';
    ctx.fillRect(L.cx - L.roadW / 2, 0, L.roadW, h);
    ctx.fillRect(0, L.cy - L.roadW / 2, w, L.roadW);

    // Lane divider dashes
    ctx.strokeStyle = '#2b3a58';
    ctx.lineWidth = 2;
    ctx.setLineDash([10, 12]);
    ctx.beginPath();
    ctx.moveTo(L.cx, 0); ctx.lineTo(L.cx, h);
    ctx.moveTo(0, L.cy); ctx.lineTo(w, L.cy);
    ctx.stroke();
    ctx.setLineDash([]);

    // Stop lines
    ctx.strokeStyle = 'rgba(226,232,240,.75)';
    ctx.lineWidth = 4;
    const s = L.stopGap, rw2 = L.roadW / 2;
    ctx.beginPath();
    ctx.moveTo(L.cx - rw2, L.cy - s); ctx.lineTo(L.cx + rw2, L.cy - s);
    ctx.moveTo(L.cx - rw2, L.cy + s); ctx.lineTo(L.cx + rw2, L.cy + s);
    ctx.moveTo(L.cx - s, L.cy - rw2); ctx.lineTo(L.cx - s, L.cy + rw2);
    ctx.moveTo(L.cx + s, L.cy - rw2); ctx.lineTo(L.cx + s, L.cy + rw2);
    ctx.stroke();

    // Intersection box outline
    ctx.strokeStyle = '#26334f';
    ctx.lineWidth = 1.5;
    ctx.strokeRect(L.cx - s, L.cy - s, s * 2, s * 2);

    // Cars (far from center drawn first for stable overlap)
    const ordered = cars.slice().sort((a, b) => b.p - a.p);
    for (const car of ordered) drawCar(ctx, car, L);

    drawSignals(ctx, L);

    // Heading (below the view-tab bar so they never overlap)
    const it = current();
    ctx.fillStyle = '#e2e8f0';
    ctx.font = '700 14px Inter, sans-serif';
    ctx.fillText(it ? it.name : selectedId, 14, 78);
    ctx.fillStyle = '#64748b';
    ctx.font = '600 11px "JetBrains Mono", monospace';
    const phase = it ? it.phase.replace('_', ' ') : '';
    ctx.fillText(`${selectedId}  PHASE: ${phase}`, 14, 96);
  }

  function frame(ts) {
    if (!visible || !canvas) return;
    const rect = canvas.getBoundingClientRect();
    const bw = Math.max(0, Math.floor(rect.width));
    const bh = Math.max(0, Math.floor(rect.height));
    if (bw && bh && (canvas.width !== bw || canvas.height !== bh)) {
      canvas.width = bw;
      canvas.height = bh;
      cars = [];
    }
    const dt = Math.min(0.05, (ts - lastFrame) / 1000 || 0.016);
    lastFrame = ts;
    const L = layout(canvas.width, canvas.height);
    step(dt, L, canvas.width, canvas.height);
    render(L, canvas.width, canvas.height);
    rafId = requestAnimationFrame(frame);
  }

  function start() {
    if (rafId == null) {
      lastFrame = performance.now();
      rafId = requestAnimationFrame(frame);
    }
  }

  function stopLoop() {
    if (rafId != null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  }

  // ── Public API ───────────────────────────────────────────────────────
  window.TrafficStage = {
    update(intersections) {
      currentData = intersections;
    },
    setSelected(id) {
      if (selectedId !== id) {
        selectedId = id;
        cars = [];
      }
    },
    show() {
      visible = true;
      if (!canvas) {
        canvas = document.getElementById('stage');
        ctx = canvas.getContext('2d');
      }
      start();
    },
    hide() {
      visible = false;
      stopLoop();
    }
  };
})();
