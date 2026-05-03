/* global window, document */

const DISPLAY_W = 640;
const DISPLAY_H = 480;
const BOX_SCALE = 0.6;
const MIN_ZOOM = 1;
const MAX_ZOOM = 4;
const LS_PHONE = "tv_detector_phone";
/** Matches `:root --accent` in style.css */
const ACCENT_PURPLE = "#8b5cf6";

const MODE_PARAMS = {
  Weak: [1, 30],
  Balanced: [3, 10],
  Aggressive: [10, 2],
};

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

/** @type {string} */
let phone = "";

let perfMode = "Balanced";
let strictnessLevel = "Balanced";
let framesToSend = MODE_PARAMS.Balanced[0];
let framesToWait = MODE_PARAMS.Balanced[1];

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

function getBoxCoords(w, h) {
  const boxW = w * BOX_SCALE;
  const boxH = h * BOX_SCALE;
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

function drawOverlay(ctx) {
  const [bx1, by1, bx2, by2] = getBoxCoords(DISPLAY_W, DISPLAY_H);
  ctx.strokeStyle = ACCENT_PURPLE;
  ctx.lineWidth = 3;
  ctx.strokeRect(bx1, by1, bx2 - bx1, by2 - by1);
  ctx.fillStyle = ACCENT_PURPLE;
  ctx.font = "bold 13px Segoe UI, system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("Align TV Here", DISPLAY_W / 2, by1 - 10);
}

function drawFrameMessage(ctx, msg) {
  ctx.fillStyle = "#1a1a1a";
  ctx.fillRect(0, 0, DISPLAY_W, DISPLAY_H);
  ctx.fillStyle = "#ff6b6b";
  ctx.font = "bold 14px Segoe UI, system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(msg, DISPLAY_W / 2, DISPLAY_H / 2);
}

function drawPreview() {
  if (!video || !vctx || !view) return;
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh || video.readyState < 2) {
    drawFrameMessage(vctx, "No Video Signal");
    return;
  }
  const crop = getZoomCropPixels(vw, vh, zoom, panX, panY);
  const sx = crop.x2 - crop.x1;
  const sy = crop.y2 - crop.y1;
  if (sx <= 1 || sy <= 1) {
    drawFrameMessage(vctx, "Processing error");
    return;
  }
  vctx.fillStyle = "#1a1a1a";
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

function rebuildSegment(containerId, options, selected, handler) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = "";
  for (const opt of options) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = opt;
    btn.className =
      "btn " +
      (opt === selected ? "active" : "inactive");
    btn.addEventListener("click", () => handler(opt));
    el.appendChild(btn);
  }
}

function refreshPerfButtons() {
  rebuildSegment(
    "perf-modes",
    ["Weak", "Balanced", "Aggressive"],
    perfMode,
    setPerfMode
  );
}

function refreshStrictButtons() {
  rebuildSegment(
    "strict-modes",
    ["Weak", "Balanced", "Aggressive"],
    strictnessLevel,
    setStrictMode
  );
}

function setPerfMode(mode) {
  perfMode = mode;
  [framesToSend, framesToWait] = MODE_PARAMS[mode];
  frameCounter = 0;
  capturingPhase = true;
  refreshPerfButtons();
}

function setStrictMode(level) {
  strictnessLevel = level;
  refreshStrictButtons();
}

function toggleCapture(btn) {
  captureRunning = !captureRunning;
  frameCounter = 0;
  capturingPhase = true;
  if (!btn) btn = /** @type {HTMLButtonElement} */ (document.getElementById("btn-toggle"));
  if (captureRunning) {
    btn.textContent = "⏸ Stop Capturing";
    btn.classList.add("capturing-on");
  } else {
    btn.textContent = "▶ Start Capturing";
    btn.classList.remove("capturing-on");
  }
}

async function startCamera() {
  if (!video) return;
  stopCameraTracks();
  const stream = await navigator.mediaDevices.getUserMedia({ video: true });
  video.srcObject = stream;
  await video.play().catch(() => {});
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

function toast(msg) {
  const host = document.getElementById("toast-host");
  if (!host) return;
  const wrap = document.createElement("div");
  wrap.className = "toast";
  const bell = document.createElement("span");
  bell.textContent = "\u2757 ";
  const text = document.createElement("span");
  text.textContent = msg;
  wrap.appendChild(bell);
  wrap.appendChild(text);
  host.appendChild(wrap);
  window.setTimeout(() => wrap.remove(), 3000);
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
      toast(n.message);
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
    alert("Enter a valid number starting with +");
    return;
  }
  phone = num;
  localStorage.setItem(LS_PHONE, phone);
  showSetup(false);
  setStatus(`Logged in as: ${phone} | Camera initializing…`);

  Promise.resolve()
    .then(() => startCamera())
    .then(() => setStatus(`Logged in as: ${phone} | Camera active`))
    .catch((e) => {
      console.error(e);
      setStatus(`Logged in as: ${phone} | Camera blocked or unavailable`);
      drawPreview();
    });

  beginTimers();
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
  setStatus(`Logged in as: ${phone} | Starting camera…`);
  Promise.resolve()
    .then(() => startCamera())
    .then(() => setStatus(`Logged in as: ${phone} | Camera active`))
    .catch((e) => {
      console.error(e);
      showSetup(false);
      setStatus("Camera unavailable — grant permission and reload.");
    });
  beginTimers();
}

document.addEventListener("DOMContentLoaded", () => {
  video = /** @type {HTMLVideoElement} */ (document.getElementById("video"));
  view = /** @type {HTMLCanvasElement} */ (document.getElementById("view"));
  vctx = view ? view.getContext("2d") : null;

  off = document.createElement("canvas");
  offCtx = off.getContext("2d");

  refreshPerfButtons();
  refreshStrictButtons();
  wireCanvasPanZoom();

  const wa = /** @type {HTMLAnchorElement|null} */ (
    document.getElementById("wa-link")
  );
  if (wa && cfg.twilio_plain && cfg.sandbox_code) {
    const enc =
      encodeURIComponent(cfg.sandbox_code);
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

  document.getElementById("btn-toggle")?.addEventListener("click", (e) => {
    toggleCapture(/** @type {HTMLButtonElement} */ (e.currentTarget));
  });

  document.getElementById("btn-logout")?.addEventListener("click", () => {
    stopTimers();
    stopCameraTracks();
    localStorage.removeItem(LS_PHONE);
    phone = "";
    showSetup(true);
    setStatus("");
  });

  bootstrapFromStorage();
});
