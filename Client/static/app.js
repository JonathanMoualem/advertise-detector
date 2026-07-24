/* global window, document */

const DISPLAY_W = 640;
let DISPLAY_H = 480; // updated dynamically once camera dimensions are known
const DEFAULT_BOX_SCALE = 0.6;
const MIN_BOX_SCALE = 0.2;
const MAX_BOX_SCALE = 0.95;
const MIN_ZOOM = 1;
const MAX_ZOOM = 4;
const LS_PHONE = "tv_detector_phone";
const LS_BOX = "tv_detector_box";
/** Matches `:root --accent` in style.css */
const ACCENT = "#c2410c";

// Fixed capture cadence (the former "Weak" preset): send 1 frame, then wait 30 ticks.
// At tickMs=15 that's ~one frame every 465 ms (~2.15 fps).
const FRAMES_TO_SEND = 1;
const FRAMES_TO_WAIT = 30;

/** @typedef {{sandbox_code:string, twilio_plain:string, notificationPollMs:number, tickMs:number}} Cfg */

const cfg =
  /** @type {Cfg} */ (window.__TV_DETECTOR_CFG__ || {
    sandbox_code: "",
    twilio_plain: "",
    notificationPollMs: 5000,
    tickMs: 15,
  });

let zoom = MIN_ZOOM;
let panX = 0;
let panY = 0;

// Alignment-box size as a fraction of the display, adjustable per axis so the
// box can be reshaped to fit the TV (no longer locked to the camera ratio).
let boxScaleX = DEFAULT_BOX_SCALE;
let boxScaleY = DEFAULT_BOX_SCALE;

/** @type {string} */
let phone = "";

let strictnessLevel = "Balanced";
const framesToSend = FRAMES_TO_SEND;
const framesToWait = FRAMES_TO_WAIT;

let captureRunning = false;
let capturingPhase = true;
let frameCounter = 0;

/** @type {HTMLVideoElement|null} */
let video = null;

/** @type {HTMLCanvasElement|null} */
let view = null;

/** @type {CanvasRenderingContext2D|null} */
let vctx = null;

/** @type {HTMLCanvasElement|null} */
let off = null;

/** @type {CanvasRenderingContext2D|null} */
let offCtx = null;

let pollTimerId = /** @type {ReturnType<typeof setInterval>|null} */ (null);
let tickTimerId = /** @type {ReturnType<typeof setInterval>|null} */ (null);

/**
 * Short chime played when the server tells us an ad break has ended.
 * @type {HTMLAudioElement|null}
 */
let successSound = null;

function initSuccessSound() {
  try {
    successSound = new Audio("/static/success.mp3");
    successSound.preload = "auto";
    successSound.volume = 0.7;
  } catch (_) {
    successSound = null;
  }
}

function playSuccessSound() {
  if (!successSound) return;
  try {
    // Reset so back-to-back alerts each retrigger the chime.
    successSound.currentTime = 0;
    const played = successSound.play();
    // Browsers block autoplay until the user interacts; swallow that rejection.
    if (played && typeof played.catch === "function") played.catch(() => {});
  } catch (_) {
    /* ignore playback errors */
  }
}

function getBoxCoords(w, h) {
  const boxW = w * boxScaleX;
  const boxH = h * boxScaleY;
  const cx = w / 2;
  const cy = h / 2;
  const x1 = Math.round(cx - boxW / 2);
  const y1 = Math.round(cy - boxH / 2);
  const x2 = Math.round(cx + boxW / 2);
  const y2 = Math.round(cy + boxH / 2);
  return [x1, y1, x2, y2];
}

function getZoomCropPixels(camW, camH, Z, PX, PY) {
  let cropW = camW / Z;
  let cropH = camH / Z;
  const panRangeX = (camW - cropW) / 2;
  const panRangeY = (camH - cropH) / 2;
  let centerX = camW / 2 + PX * panRangeX;
  let centerY = camH / 2 + PY * panRangeY;
  let x1 = Math.round(centerX - cropW / 2);
  let y1 = Math.round(centerY - cropH / 2);
  let x2 = Math.round(x1 + cropW);
  let y2 = Math.round(y1 + cropH);
  x1 = Math.max(0, x1);
  y1 = Math.max(0, y1);
  x2 = Math.min(camW, x2);
  y2 = Math.min(camH, y2);
  return { x1, y1, x2, y2 };
}

function drawCornerBracket(ctx, x, y, len, dx, dy) {
  ctx.beginPath();
  ctx.moveTo(x + dx * len, y);
  ctx.lineTo(x, y);
  ctx.lineTo(x, y + dy * len);
  ctx.stroke();
}

function drawOverlay(ctx) {
  const [bx1, by1, bx2, by2] = getBoxCoords(DISPLAY_W, DISPLAY_H);

  // dim outside the box
  ctx.save();
  ctx.fillStyle = "rgba(0,0,0,0.25)";
  ctx.fillRect(0, 0, DISPLAY_W, by1);
  ctx.fillRect(0, by2, DISPLAY_W, DISPLAY_H - by2);
  ctx.fillRect(0, by1, bx1, by2 - by1);
  ctx.fillRect(bx2, by1, DISPLAY_W - bx2, by2 - by1);
  ctx.restore();

  // alignment rectangle
  ctx.strokeStyle = captureRunning ? ACCENT : "rgba(255,255,255,0.85)";
  ctx.lineWidth = captureRunning ? 2 : 1.5;
  ctx.strokeRect(bx1, by1, bx2 - bx1, by2 - by1);

  // corner brackets
  ctx.strokeStyle = captureRunning ? ACCENT : "rgba(255,255,255,0.95)";
  ctx.lineWidth = 2;
  const cornerLen = 14;
  drawCornerBracket(ctx, bx1, by1, cornerLen, 1, 1);
  drawCornerBracket(ctx, bx2, by1, cornerLen, -1, 1);
  drawCornerBracket(ctx, bx1, by2, cornerLen, 1, -1);
  drawCornerBracket(ctx, bx2, by2, cornerLen, -1, -1);

  // label pill above the box
  const label = captureRunning ? "● DETECTING AD BREAKS" : "ALIGN TV HERE";
  ctx.font = '500 11px "Geist Mono", ui-monospace, Menlo, monospace';
  ctx.textAlign = "center";
  const textMetrics = ctx.measureText(label);
  const padX = 12;
  const padY = 4;
  const lh = 14;
  const lw = textMetrics.width + padX * 2;
  const lx = DISPLAY_W / 2 - lw / 2;
  const ly = by1 - lh - 10;

  ctx.fillStyle = captureRunning ? ACCENT : "rgba(0,0,0,0.55)";
  // rounded rect
  const r = lh / 2 + 2;
  ctx.beginPath();
  ctx.moveTo(lx + r, ly);
  ctx.lineTo(lx + lw - r, ly);
  ctx.quadraticCurveTo(lx + lw, ly, lx + lw, ly + r);
  ctx.lineTo(lx + lw, ly + lh + padY * 2 - r);
  ctx.quadraticCurveTo(lx + lw, ly + lh + padY * 2, lx + lw - r, ly + lh + padY * 2);
  ctx.lineTo(lx + r, ly + lh + padY * 2);
  ctx.quadraticCurveTo(lx, ly + lh + padY * 2, lx, ly + lh + padY * 2 - r);
  ctx.lineTo(lx, ly + r);
  ctx.quadraticCurveTo(lx, ly, lx + r, ly);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = "#fff";
  ctx.textBaseline = "middle";
  ctx.fillText(label, DISPLAY_W / 2, ly + lh / 2 + padY);
  ctx.textBaseline = "alphabetic";
}

function drawFrameMessage(ctx, msg) {
  ctx.fillStyle = "#1a1815";
  ctx.fillRect(0, 0, DISPLAY_W, DISPLAY_H);
  ctx.fillStyle = "rgba(255,255,255,0.55)";
  ctx.font = '500 12px "Geist Mono", ui-monospace, Menlo, monospace';
  ctx.textAlign = "center";
  ctx.fillText(msg.toUpperCase(), DISPLAY_W / 2, DISPLAY_H / 2);
}

function drawPreview() {
  if (!video || !vctx || !view) return;
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh || video.readyState < 2) {
    drawFrameMessage(vctx, "No video signal");
    drawOverlay(vctx);
    return;
  }
  const crop = getZoomCropPixels(vw, vh, zoom, panX, panY);
  const sx = crop.x2 - crop.x1;
  const sy = crop.y2 - crop.y1;
  if (sx <= 1 || sy <= 1) {
    drawFrameMessage(vctx, "Processing error");
    return;
  }
  vctx.fillStyle = "#0e0d0b";
  vctx.fillRect(0, 0, DISPLAY_W, DISPLAY_H);
  vctx.drawImage(
    /** @type {CanvasImageSource} */ (video),
    crop.x1,
    crop.y1,
    sx,
    sy,
    0,
    0,
    DISPLAY_W,
    DISPLAY_H
  );
  drawOverlay(vctx);
}

/** Hover hints shown under each strictness option. */
const STRICT_TOOLTIPS = {
  Weak: "Might alert when there is a single long ad or ads that look like content.",
  Balanced: "Recommended for most content types.",
  Aggressive:
    "Might miss alerts when the show you are watching has a large variety of frames.",
};

function rebuildSegment(containerId, options, selected, handler, tooltips) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = "";
  for (const opt of options) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = opt;
    if (opt === selected) btn.classList.add("active");
    if (tooltips && tooltips[opt]) {
      const tip = document.createElement("span");
      tip.className = "tip-box";
      tip.setAttribute("role", "tooltip");
      tip.textContent = tooltips[opt];
      btn.appendChild(tip);
    }
    btn.addEventListener("click", () => handler(opt));
    el.appendChild(btn);
  }
}

function refreshStrictButtons() {
  rebuildSegment(
    "strict-modes",
    ["Weak", "Balanced", "Aggressive"],
    strictnessLevel,
    setStrictMode,
    STRICT_TOOLTIPS
  );
}

function setStrictMode(level) {
  strictnessLevel = level;
  refreshStrictButtons();
}

function setStatusChip(running) {
  const chip = document.getElementById("status-chip");
  const rec = document.getElementById("rec-indicator");
  if (chip) {
    chip.classList.remove("good", "live");
    chip.classList.add(running ? "live" : "good");
    chip.textContent = running ? "Capturing" : "Camera ready";
  }
  if (rec) rec.classList.toggle("hidden", !running);
}

function toggleCapture(btn) {
  captureRunning = !captureRunning;
  frameCounter = 0;
  capturingPhase = true;
  if (!btn) btn = /** @type {HTMLButtonElement} */ (document.getElementById("btn-toggle"));
  if (captureRunning) {
    btn.textContent = "■ Stop Capturing";
    btn.classList.remove("primary");
    btn.classList.add("secondary");
    showToast({ good: true, title: "Capturing started.", sub: "I'll text you the moment the ads end." });
  } else {
    btn.textContent = "▶ Start Capturing";
    btn.classList.remove("secondary");
    btn.classList.add("primary");
    showToast({ good: false, title: "Capturing stopped.", sub: "You can resume any time." });
    endSession();
  }
  setStatusChip(captureRunning);
}

function endSession() {
  if (!phone) return;
  const fd = new FormData();
  fd.append("phone_number", phone);
  fetch("/api/end_session", { method: "POST", body: fd }).catch(() => {});
}

function syncCanvasToCamera() {
  if (!video || !view) return;
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) return;
  DISPLAY_H = Math.round(DISPLAY_W * vh / vw);
  view.width = DISPLAY_W;
  view.height = DISPLAY_H;
  const stage = document.querySelector('.stage');
  if (stage) stage.style.aspectRatio = `${vw} / ${vh}`;
}

async function startCamera() {
  if (!video) return;
  stopCameraTracks();
  const stream = await navigator.mediaDevices.getUserMedia({ video: true });
  video.srcObject = stream;
  await video.play().catch(() => {});
  video.addEventListener('loadedmetadata', syncCanvasToCamera, { once: true });
  if (video.videoWidth) syncCanvasToCamera();
}

function stopCameraTracks() {
  if (video && video.srcObject instanceof MediaStream) {
    video.srcObject.getTracks().forEach((t) => t.stop());
    video.srcObject = null;
  }
}

function setStatus(txt) {
  const s = document.getElementById("status-text");
  if (s) s.textContent = txt;
}

function snapAndPost() {
  if (!video || !off || !offCtx) return;
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) return;

  off.width = vw;
  off.height = vh;
  offCtx.drawImage(/** @type {CanvasImageSource} */ (video), 0, 0);

  off.toBlob(
    (blob) => {
      if (!blob || !phone) return;
      const fd = new FormData();
      fd.append("image", blob, "frame.jpg");
      fd.append("phone_number", phone);
      fd.append("strictness", strictnessLevel);
      fd.append("zoom_level", String(zoom));
      fd.append("pan_x", String(panX));
      fd.append("pan_y", String(panY));
      fd.append("box_scale_x", String(boxScaleX));
      fd.append("box_scale_y", String(boxScaleY));

      fetch("/api/upload_frame", { method: "POST", body: fd }).catch((e) =>
        console.warn("Upload failed:", e)
      );
    },
    "image/jpeg",
    0.95
  );
}

function captureTickLogic() {
  if (!captureRunning || !video || video.readyState < 2 || !phone) return;
  frameCounter += 1;
  if (capturingPhase) {
    snapAndPost();
    if (frameCounter >= framesToSend) {
      capturingPhase = false;
      frameCounter = 0;
    }
  } else if (frameCounter >= framesToWait) {
    capturingPhase = true;
    frameCounter = 0;
  }
}

function showToast({ good, title, sub }) {
  const host = document.getElementById("toast-host");
  if (!host) return;
  const wrap = document.createElement("div");
  wrap.className = "toast";

  const icon = document.createElement("div");
  icon.className = "toast-icon";
  icon.style.background = good ? "var(--good)" : "var(--bg-sunken)";
  icon.style.color = good ? "#fff" : "var(--ink)";
  icon.textContent = good ? "✓" : "·";

  const body = document.createElement("div");
  const t = document.createElement("div");
  t.style.fontWeight = "500";
  t.style.fontSize = "14px";
  t.textContent = title || "";
  const s = document.createElement("div");
  s.style.fontSize = "12px";
  s.style.color = "var(--muted-2)";
  s.textContent = sub || "";
  body.appendChild(t);
  if (sub) body.appendChild(s);

  wrap.appendChild(icon);
  wrap.appendChild(body);
  host.appendChild(wrap);
  window.setTimeout(() => wrap.remove(), 3400);
}

function toastFromServer(msg) {
  playSuccessSound();
  showToast({ good: true, title: msg });
}

async function pollNotifications() {
  if (!phone) return;
  try {
    const r = await fetch(
      `/api/notifications?phone_number=${encodeURIComponent(phone)}`
    );
    if (!r.ok) return;
    const data = /** @type {{notifications?: { message: string }[]}} */ (
      await r.json()
    );
    const rows = data.notifications || [];
    for (const n of rows) {
      toastFromServer(n.message);
    }
  } catch (_) {
    /* offline */
  }
}

function canvasPointer(ev, canvas, fnDown, fnMove) {
  const rect = canvas.getBoundingClientRect();
  const x = ((ev.clientX - rect.left) / rect.width) * canvas.width;
  const y = ((ev.clientY - rect.top) / rect.height) * canvas.height;
  if (fnDown) fnDown(x, y);
  if (fnMove) fnMove(x, y);
}

function wireCanvasPanZoom() {
  if (!view) return;
  let drag = false;
  let lastX = 0;
  let lastY = 0;

  view.addEventListener("mousedown", (e) => {
    drag = true;
    canvasPointer(e, /** @type {HTMLCanvasElement} */ (view), (x, y) => {
      lastX = x;
      lastY = y;
    });
  });

  window.addEventListener(
    "mousemove",
    (e) => {
      if (!drag || !view) return;
      canvasPointer(e, view, null, (x, y) => {
        let dx = x - lastX;
        let dy = y - lastY;
        lastX = x;
        lastY = y;
        panX -= dx / DISPLAY_W;
        panY -= dy / DISPLAY_H;
        panX = Math.max(-1, Math.min(1, panX));
        panY = Math.max(-1, Math.min(1, panY));
      });
    },
    false
  );

  window.addEventListener("mouseup", () => {
    drag = false;
  });

  view.addEventListener(
    "wheel",
    (ev) => {
      ev.preventDefault();
      const d = /** @type {WheelEvent} */ (ev).deltaY;
      if (d > 0) zoom -= 0.1;
      else zoom += 0.1;
      zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom));
      if (zoom === MIN_ZOOM) {
        panX = 0;
        panY = 0;
      }
    },
    { passive: false }
  );
}

function clampBoxScale(v) {
  if (!Number.isFinite(v)) return DEFAULT_BOX_SCALE;
  return Math.max(MIN_BOX_SCALE, Math.min(MAX_BOX_SCALE, v));
}

function loadBoxScale() {
  try {
    const raw = localStorage.getItem(LS_BOX);
    if (!raw) return;
    const saved = JSON.parse(raw);
    if (saved && typeof saved.x === "number") boxScaleX = clampBoxScale(saved.x);
    if (saved && typeof saved.y === "number") boxScaleY = clampBoxScale(saved.y);
  } catch (_) {
    /* ignore malformed storage */
  }
}

function saveBoxScale() {
  try {
    localStorage.setItem(LS_BOX, JSON.stringify({ x: boxScaleX, y: boxScaleY }));
  } catch (_) {
    /* ignore quota/unavailable */
  }
}

function wireBoxSizeControls() {
  const wEl = /** @type {HTMLInputElement|null} */ (document.getElementById("box-width"));
  const hEl = /** @type {HTMLInputElement|null} */ (document.getElementById("box-height"));
  const wOut = document.getElementById("box-width-val");
  const hOut = document.getElementById("box-height-val");
  const pct = (v) => `${Math.round(v * 100)}%`;

  // Reflect current state into the inputs (e.g. values restored from storage).
  if (wEl) wEl.value = String(boxScaleX);
  if (hEl) hEl.value = String(boxScaleY);
  if (wOut) wOut.textContent = pct(boxScaleX);
  if (hOut) hOut.textContent = pct(boxScaleY);

  if (wEl) {
    wEl.addEventListener("input", () => {
      boxScaleX = clampBoxScale(parseFloat(wEl.value));
      if (wOut) wOut.textContent = pct(boxScaleX);
      saveBoxScale();
    });
  }
  if (hEl) {
    hEl.addEventListener("input", () => {
      boxScaleY = clampBoxScale(parseFloat(hEl.value));
      if (hOut) hOut.textContent = pct(boxScaleY);
      saveBoxScale();
    });
  }
}

function showSetup(show) {
  const ps = document.getElementById("panel-setup");
  const pm = document.getElementById("panel-monitor");
  if (ps) ps.classList.toggle("hidden", !show);
  if (pm) pm.classList.toggle("hidden", show);
}

function loadPhoneInput() {
  const saved = localStorage.getItem(LS_PHONE);
  const input = /** @type {HTMLInputElement|null} */ (
    document.getElementById("phone-input")
  );
  if (input && saved) input.value = saved;
}

function savePhoneContinue() {
  const input = /** @type {HTMLInputElement|null} */ (
    document.getElementById("phone-input")
  );
  if (!input) return;
  const num = input.value.trim().replace(/\s+/g, "");
  if (!num.startsWith("+") || num.length < 10) {
    input.focus();
    input.style.borderColor = "var(--accent)";
    showToast({ good: false, title: "Enter a valid number", sub: "Must start with + and country code." });
    setTimeout(() => { input.style.borderColor = ""; }, 1600);
    return;
  }
  phone = num;
  localStorage.setItem(LS_PHONE, phone);
  showSetup(false);
  setStatusChip(false);
  setStatus(`${phone} · camera initializing…`);

  Promise.resolve()
    .then(() => startCamera())
    .then(() => setStatus(`${phone} · camera active`))
    .catch((e) => {
      console.error(e);
      setStatus(`${phone} · camera blocked`);
      drawPreview();
    });

  beginTimers();
}

function copySandbox() {
  const code = (cfg && cfg.sandbox_code) || "";
  if (!code) return;
  const btn = document.getElementById("btn-copy-sandbox");
  const restore = () => { if (btn) btn.textContent = "Copy"; };
  const after = () => {
    if (btn) btn.textContent = "Copied";
    setTimeout(restore, 1600);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(code).then(after).catch(() => {
      window.prompt("Copy this message:", code);
    });
  } else {
    window.prompt("Copy this message:", code);
    after();
  }
}

function beginTimers() {
  if (!tickTimerId) {
    tickTimerId = window.setInterval(() => {
      drawPreview();
      captureTickLogic();
    }, cfg.tickMs || 15);
  }
  if (!pollTimerId) {
    pollTimerId = window.setInterval(() => pollNotifications(), cfg.notificationPollMs || 5000);
    void pollNotifications();
  }
}

function stopTimers() {
  if (tickTimerId) {
    clearInterval(tickTimerId);
    tickTimerId = null;
  }
  if (pollTimerId) {
    clearInterval(pollTimerId);
    pollTimerId = null;
  }
}

function bootstrapFromStorage() {
  const saved = localStorage.getItem(LS_PHONE);
  if (!saved || !saved.startsWith("+")) {
    loadPhoneInput();
    showSetup(true);
    return;
  }
  phone = saved;
  showSetup(false);
  const input = /** @type {HTMLInputElement|null} */ (
    document.getElementById("phone-input")
  );
  if (input) input.value = phone;
  setStatusChip(false);
  setStatus(`${phone} · starting camera…`);
  Promise.resolve()
    .then(() => startCamera())
    .then(() => setStatus(`${phone} · camera active`))
    .catch((e) => {
      console.error(e);
      showSetup(false);
      setStatus("camera unavailable — grant permission and reload");
    });
  beginTimers();
}

document.addEventListener("DOMContentLoaded", () => {
  video = /** @type {HTMLVideoElement} */ (document.getElementById("video"));
  view = /** @type {HTMLCanvasElement} */ (document.getElementById("view"));
  vctx = view ? view.getContext("2d") : null;

  off = document.createElement("canvas");
  offCtx = off.getContext("2d");

  refreshStrictButtons();
  loadBoxScale();
  wireBoxSizeControls();
  wireCanvasPanZoom();

  initSuccessSound();
  // Autoplay policies require a prior user gesture; prime the audio element on
  // the first interaction so the chime can fire when a server cue arrives.
  const unlockAudio = () => {
    if (!successSound) return;
    successSound.play().then(
      () => {
        successSound.pause();
        successSound.currentTime = 0;
      },
      () => {}
    );
  };
  window.addEventListener("pointerdown", unlockAudio, { once: true });
  window.addEventListener("keydown", unlockAudio, { once: true });

  const wa = /** @type {HTMLAnchorElement|null} */ (
    document.getElementById("wa-link")
  );
  if (wa && cfg.twilio_plain && cfg.sandbox_code) {
    const enc = encodeURIComponent(cfg.sandbox_code);
    wa.href =
      `https://wa.me/${cfg.twilio_plain.replace(/[^\d]/g, "")}?text=${enc}`;
  }

  loadPhoneInput();
  document
    .getElementById("btn-continue-setup")
    ?.addEventListener("click", savePhoneContinue);

  document.getElementById("phone-input")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      savePhoneContinue();
    }
  });

  document.getElementById("btn-copy-sandbox")?.addEventListener("click", copySandbox);

  document.getElementById("btn-toggle")?.addEventListener("click", (e) => {
    toggleCapture(/** @type {HTMLButtonElement} */ (e.currentTarget));
  });

  document.getElementById("btn-logout")?.addEventListener("click", () => {
    if (captureRunning) endSession();
    stopTimers();
    stopCameraTracks();
    localStorage.removeItem(LS_PHONE);
    phone = "";
    captureRunning = false;
    showSetup(true);
    setStatus("");
  });

  bootstrapFromStorage();
});
