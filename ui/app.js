const api = () => window.pywebview.api;

let items = [];
let steamGames = [];
let addingFolder = false;
let selectedId = null;
let graphData = null;
let selectedNode = null;
let graphLoadId = 0;
let summaryKey = "";
let summaryLoadId = 0;
let summarySlots = [];
let summarySlotIndex = null;
let hideAuto = localStorage.getItem("gb-auto-notes") === "0";
let showRemarks = localStorage.getItem("gb-remarks") !== "0";
let curveEdges = localStorage.getItem("gb-curve") !== "0";
let showSide = localStorage.getItem("gb-side") !== "0";
let cam = { x: 40, y: 40, k: 1 };
let graphSize = { w: 1, h: 1 };
let nodePos = {};
let lastFitItem = null;
let startIds = new Set();
let spaceDown = false;
let panning = false;
let didPan = false;
let panLast = { x: 0, y: 0 };

const $ = (id) => document.getElementById(id);

let swallowEnterUntil = 0;

function ask(opts) {
  return new Promise((resolve) => {
    $("menu").hidden = true;
    const box = $("dlg");
    const inp = $("dlgInput");
    const cancel = $("dlgCancel");
    $("dlgMsg").textContent = opts.message;
    const isPrompt = opts.kind === "prompt";
    const isAlert = opts.kind === "alert";
    $("dlgOk").textContent = opts.okLabel || "确定";
    cancel.textContent = opts.cancelLabel || "取消";
    inp.hidden = !isPrompt;
    cancel.hidden = isAlert;
    if (isPrompt) inp.value = opts.value || "";
    inp.placeholder = isPrompt ? (opts.placeholder || "") : "";
    const need = opts.need || "";
    const matchesNeed = () => !need || inp.value.trim() === need;
    const syncOk = () => {
      $("dlgOk").disabled = isPrompt && need && !matchesNeed();
    };
    box.hidden = false;
    (isPrompt ? inp : $("dlgOk")).focus();
    if (isPrompt) inp.select();
    let done = false;
    const finish = (val) => {
      if (done) return;
      done = true;
      box.hidden = true;
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("keyup", onKey, true);
      inp.oninput = null;
      $("dlgOk").onclick = null;
      $("dlgOk").disabled = false;
      cancel.onclick = null;
      box.onclick = null;
      swallowEnterUntil = Date.now() + 600;
      const ae = document.activeElement;
      if (ae && ae.blur) ae.blur();
      resolve(val);
    };
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopImmediatePropagation();
        if (e.type === "keydown") finish(isAlert ? undefined : isPrompt ? null : false);
      } else if (e.key === "Enter" && !e.isComposing && e.keyCode !== 229) {
        e.preventDefault();
        e.stopImmediatePropagation();
        if (e.type !== "keydown") return;
        if (isPrompt && !matchesNeed()) return;
        finish(isPrompt ? inp.value : isAlert ? undefined : true);
      }
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("keyup", onKey, true);
    inp.oninput = syncOk;
    syncOk();
    $("dlgOk").onclick = () => {
      if (isPrompt && !matchesNeed()) return;
      finish(isPrompt ? inp.value : isAlert ? undefined : true);
    };
    cancel.onclick = () => finish(isPrompt ? null : false);
    box.onclick = (e) => {
      if (e.target === box) finish(isPrompt ? null : isAlert ? undefined : false);
    };
  });
}
function askYes(msg) {
  return ask({ kind: "confirm", message: msg });
}
function askText(msg, def) {
  return ask({ kind: "prompt", message: msg, value: def });
}
function askOk(msg) {
  return ask({ kind: "alert", message: msg });
}

function setBusy(on, text) {
  if (text) $("busyText").textContent = text;
  $("busy").hidden = !on;
}

function onReady(fn) {
  if (window.pywebview) fn();
  else window.addEventListener("pywebviewready", fn);
}

function formatBytes(n) {
  n = Math.max(0, Number(n) || 0);
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  if (n < 1024 * 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + " MB";
  return (n / (1024 * 1024 * 1024)).toFixed(1) + " GB";
}

async function refreshItems() {
  items = await api().list_items();
  renderSteamGames();
  const ul = $("itemList");
  ul.innerHTML = "";
  items.forEach((it) => {
    const li = document.createElement("li");
    li.className = "item" + (it.id === selectedId ? " active" : "") + (it.available ? "" : " missing");
    const size = it.size_text || formatBytes(it.size_bytes);
    const sub = it.available ? it.path_short : "找不到这个文件夹了";
    li.innerHTML = `<div>${escapeHtml(it.name)}</div><div class="size">占用 ${escapeHtml(size)}</div><div class="sub">${escapeHtml(sub)}</div>`;
    li.onclick = () => selectItem(it.id);
    li.oncontextmenu = (e) => {
      e.preventDefault();
      showMenu(e.clientX, e.clientY, [
        { label: "打开存档文件夹", run: async () => {
          const r = await api().open_item_folder(it.id);
          if (!r.ok) await askOk(r.error);
        } },
        { label: "改名字", run: () => renameItem(it.id, it.name) },
        { label: it.paused ? "继续自动备份" : "暂停自动备份", run: () => api().pause_item(it.id, !it.paused).then(loadGraph) },
        { label: "删除", run: () => removeItem(it.id, it.name) },
      ]);
    };
    ul.appendChild(li);
  });
  const totalEl = $("sideTotal");
  if (totalEl) {
    const total = items.reduce((s, it) => s + (Number(it.size_bytes) || 0), 0);
    totalEl.hidden = items.length === 0;
    totalEl.textContent = items.length ? "总占用 " + formatBytes(total) : "";
  }
  $("empty").hidden = items.length > 0 && !!selectedId;
  if (!selectedId && items[0]) selectItem(items[0].id);
  else if (items.length === 0) {
    selectedId = null;
    hideSaveSummary();
    $("empty").hidden = false;
    $("graphWrap").hidden = true;
    $("btnFit").hidden = true;
  }
}

async function selectItem(id) {
  if (selectedId !== id) {
    hideSaveSummary();
    summarySlotIndex = null;
    graphData = null;
    $("graphWrap").hidden = true;
    $("btnFit").hidden = true;
  }
  selectedId = id;
  selectedNode = null;
  await refreshItems();
  await loadGraph();
}

async function loadGraph() {
  if (!selectedId) return;
  const itemId = selectedId;
  const request = ++graphLoadId;
  const g = await api().graph(itemId, hideAuto);
  if (request !== graphLoadId || itemId !== selectedId) return;
  if (!g.ok) {
    hideSaveSummary();
    $("empty").hidden = false;
    $("graphWrap").hidden = true;
    $("btnFit").hidden = true;
    return;
  }
  graphData = g;
  if (selectedNode) {
    selectedNode = (g.nodes || []).find((n) => n.id === selectedNode.id) || null;
  }
  $("empty").hidden = true;
  $("graphWrap").hidden = false;
  $("btnFit").hidden = false;
  renderGraph(g);
  if (lastFitItem !== selectedId) {
    lastFitItem = selectedId;
    fitView();
  }
}

function hideSaveSummary() {
  $("saveSummary").hidden = true;
  summaryKey = "";
  summaryLoadId++;
}

function showSaveSummaryMessage(message, retry = false) {
  $("saveSummaryStatus").textContent = message;
  $("saveSummaryStatus").hidden = false;
  $("saveSummaryRetry").hidden = !retry;
  $("saveSummarySlotLabel").hidden = true;
  $("saveSummaryBody").replaceChildren();
}

function formatSummaryDelta(delta) {
  return delta > 0 ? "+" + delta.toLocaleString() : delta.toLocaleString();
}

function renderSaveSlot(slot) {
  const facts = [
    ["游玩时长", slot.play_time],
    ["地点", slot.location],
    ["难度", slot.difficulty],
    ["游戏保存时间", slot.saved_at],
  ].filter(([, value]) => value);
  if (Number.isFinite(slot.souls)) {
    facts.push(["红魂", slot.souls.toLocaleString()]);
  }
  const carried = (slot.items || []).filter((item) => item.quantity > 0);
  const changed = (slot.items || []).filter((item) => Number.isFinite(item.delta) && item.delta !== 0);
  const changes = [];
  if (slot.previous_goal && slot.previous_goal !== slot.goal) {
    changes.push(`<li><span>上一版目标</span><span>${escapeHtml(slot.previous_goal)}</span></li>`);
  }
  if (Number.isFinite(slot.souls_delta) && slot.souls_delta !== 0) {
    changes.push(`<li><span>红魂</span><span class="save-summary-number">${formatSummaryDelta(slot.souls_delta)}</span></li>`);
  }
  for (const item of changed) {
    changes.push(`<li><span>${escapeHtml(item.name)}</span><span class="save-summary-number">${formatSummaryDelta(item.delta)}</span></li>`);
  }
  const changeContent = !slot.has_previous ? "<p>没有可对照的同一存档槽。</p>" :
    changes.length ? `<ul>${changes.join("")}</ul>` : "<p>已显示的字段与上一版相同。</p>";
  $("saveSummaryBody").innerHTML = `
    <p class="save-summary-meta">当前目标</p>
    <p class="save-summary-goal">${escapeHtml(slot.goal || "暂无目标记录")}</p>
    <dl class="save-summary-facts">${facts.map(([label, value]) =>
      `<dt>${label}</dt><dd>${escapeHtml(value)}</dd>`
    ).join("")}</dl>
    <details class="save-summary-section" open>
      <summary>与上一备份的变化</summary>
      <div class="save-summary-delta">${changeContent}</div>
    </details>
    <details class="save-summary-section">
      <summary>背包（${carried.length} 种）</summary>
      ${carried.length ? `<ul>${carried.map((item) =>
        `<li><span>${escapeHtml(item.name)}</span><span class="save-summary-number">×${item.quantity.toLocaleString()}</span></li>`
      ).join("")}</ul>` : "<p>这个存档槽没有携带物品。</p>"}
    </details>`;
}

async function loadSaveSummary(g) {
  const itemId = selectedId;
  const node = selectedNode || (g.nodes || []).find((n) => n.id === g.current_id);
  if (!g.summary_supported || !itemId || !node) {
    hideSaveSummary();
    return;
  }
  const key = itemId + ":" + node.id;
  if (summaryKey === key) return;
  summaryKey = key;
  const request = ++summaryLoadId;
  $("saveSummary").hidden = false;
  const type = node.id === g.current_id ? "当前节点" : "历史节点";
  $("saveSummaryNode").textContent = [type, formatTime(node.time)].filter(Boolean).join(" · ");
  showSaveSummaryMessage("正在读取这版存档…");
  let result;
  try {
    result = await api().node_summary(itemId, node.id);
  } catch {
    result = { ok: false, error: "暂时无法读取这版存档。" };
  }
  if (request !== summaryLoadId) return;
  if (!result?.ok) {
    showSaveSummaryMessage(result?.error || "暂时无法读取这版存档。", true);
    return;
  }
  summarySlots = result.slots || [];
  if (!summarySlots.length) {
    showSaveSummaryMessage("这版备份没有可读取的存档槽。");
    return;
  }
  $("saveSummaryStatus").hidden = true;
  const select = $("saveSummarySlot");
  select.replaceChildren(...summarySlots.map((slot) => new Option(slot.label, slot.index)));
  $("saveSummarySlotLabel").hidden = summarySlots.length === 1;
  const slot = summarySlots.find((entry) => entry.index === summarySlotIndex) || summarySlots[0];
  select.value = slot.index;
  summarySlotIndex = slot.index;
  renderSaveSlot(slot);
}

function layout(g) {
  const nodes = (g.nodes || []).slice().sort((a, b) => b.time - a.time);
  const visible = new Set(nodes.map((n) => n.id));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const kids = new Map();
  nodes.forEach((n) => {
    const pid = (n.parents || []).find((p) => visible.has(p));
    if (!pid) return;
    if (!kids.has(pid)) kids.set(pid, []);
    kids.get(pid).push(n);
  });
  const sortNodes = (arr) => {
    arr.sort((a, b) => a.time - b.time || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  };
  kids.forEach(sortNodes);
  const kidsOrdered = (id) => {
    const cs = kids.get(id) || [];
    return [...cs.filter((c) => !c.fork), ...cs.filter((c) => c.fork)];
  };
  const roots = nodes.filter((n) => !(n.parents || []).some((p) => visible.has(p)));
  sortNodes(roots);

  const widthOf = {};
  const width = (id) => {
    if (widthOf[id] != null) return widthOf[id];
    const cs = kidsOrdered(id);
    if (!cs.length) return (widthOf[id] = 1);
    const forkW = cs.filter((c) => c.fork).reduce((s, c) => s + width(c.id), 0);
    const cont = cs.filter((c) => !c.fork);
    if (!cont.length) return (widthOf[id] = 1 + forkW);
    return (widthOf[id] = cont.reduce((s, c) => s + width(c.id), 0) + forkW);
  };
  roots.forEach((r) => width(r.id));

  const colOf = {};
  const place = (id, left) => {
    const cs = kidsOrdered(id);
    const cont = cs.filter((c) => !c.fork);
    if (!cs.length) {
      colOf[id] = left;
      return;
    }
    if (!cont.length) {
      colOf[id] = left;
      let x = left + 1;
      cs.forEach((c) => {
        place(c.id, x);
        x += width(c.id);
      });
      return;
    }
    let x = left;
    cs.forEach((c) => {
      place(c.id, x);
      x += width(c.id);
    });
    colOf[id] = colOf[cont[0].id];
  };
  let left = 0;
  roots.forEach((r) => {
    place(r.id, left);
    left += width(r.id);
  });

  const genOf = {};
  const gen = (id) => {
    if (genOf[id] != null) return genOf[id];
    const n = byId.get(id);
    const pid = (n?.parents || []).find((p) => visible.has(p));
    if (!pid) return (genOf[id] = 0);
    return (genOf[id] = n.fork ? gen(pid) : gen(pid) + 1);
  };
  nodes.forEach((n) => gen(n.id));
  const maxG = Math.max(0, ...Object.values(genOf), 0);

  const rowOf = {};
  nodes.forEach((n) => {
    rowOf[n.id] = maxG - genOf[n.id];
    if (colOf[n.id] === undefined) colOf[n.id] = 0;
  });
  const colVals = Object.values(colOf);
  const cols = colVals.length ? Math.max(...colVals) + 1 : 1;
  const COL_GAP = 36;
  const FORK_GAP = 200;
  const gapAfter = Array.from({ length: Math.max(cols, 1) }, () => COL_GAP);
  nodes.forEach((n) => {
    nodes.forEach((m) => {
      if (rowOf[n.id] !== rowOf[m.id]) return;
      if (colOf[m.id] === colOf[n.id] + 1) gapAfter[colOf[n.id]] = FORK_GAP;
    });
  });
  const colX = [0];
  for (let i = 1; i < cols; i++) colX[i] = colX[i - 1] + gapAfter[i - 1];
  return { nodes, colOf, rowOf, cols, colX };
}

function layoutKey(g) {
  const nodes = (g.nodes || [])
    .map((n) => `${n.id}:${(n.parents || []).join(",")}`)
    .sort()
    .join("|");
  return nodes;
}

let layoutCache = { key: "", value: null };

function getLayout(g) {
  const k = layoutKey(g);
  const nodes = (g.nodes || []).slice().sort((a, b) => b.time - a.time);
  // 位置可以复用；节点上的备注必须用这一次的数据，否则改备注画面不刷新。
  if (layoutCache.key === k && layoutCache.value) {
    return { ...layoutCache.value, nodes };
  }
  const value = layout(g);
  layoutCache = { key: k, value };
  return value;
}

function edgePath(x1, y1, x2, y2, curve) {
  if (x1 === x2) return `M ${x1} ${y1} L ${x2} ${y2}`;
  if (y1 === y2) return `M ${x1} ${y1} L ${x2} ${y2}`;
  if (!curve) return `M ${x1} ${y1} L ${x1} ${y2} L ${x2} ${y2}`;
  const r = Math.min(12, Math.abs(y2 - y1) / 2, Math.abs(x2 - x1) / 2);
  if (r < 2) return `M ${x1} ${y1} L ${x1} ${y2} L ${x2} ${y2}`;
  const sx = x2 > x1 ? 1 : -1;
  return `M ${x1} ${y1} L ${x1} ${y2 - r} Q ${x1} ${y2} ${x1 + sx * r} ${y2} L ${x2} ${y2}`;
}

function onCurrentLine(g) {
  const set = new Set();
  const byId = new Map((g.nodes || []).map((n) => [n.id, n]));
  let cur = g.current_id;
  while (cur && !set.has(cur)) {
    set.add(cur);
    cur = byId.get(cur)?.parents?.[0];
  }
  return set;
}

function onNodeLine(nodes, nodeId) {
  const set = new Set();
  if (!nodeId) return set;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  let cur = nodeId;
  while (cur && !set.has(cur)) {
    set.add(cur);
    cur = (byId.get(cur)?.parents || []).find((p) => byId.has(p));
  }
  return set;
}

function applyCam() {
  const camEl = $("graphCam");
  const pane = $("graphPane");
  if (pane) {
    pane.style.backgroundSize = `${22 * cam.k}px ${22 * cam.k}px`;
    pane.style.backgroundPosition = `${cam.x}px ${cam.y}px`;
  }
  if (camEl) camEl.setAttribute("transform", `translate(${cam.x} ${cam.y}) scale(${cam.k})`);
}

function fitView() {
  const pane = $("graphPane");
  if (!pane) return;
  const pad = 48;
  const pts = Object.values(nodePos);
  let minX = 0, maxX = graphSize.w, minY = 0, maxY = graphSize.h;
  if (pts.length) {
    minX = Math.min(...pts.map((p) => p.x)) - 20;
    maxX = Math.max(...pts.map((p) => p.x)) + 210;
    minY = Math.min(...pts.map((p) => p.y)) - 40;
    maxY = Math.max(...pts.map((p) => p.y)) + 28;
  }
  const cw = Math.max(maxX - minX, 1);
  const ch = Math.max(maxY - minY, 1);
  const kw = (pane.clientWidth - pad * 2) / cw;
  const kh = (pane.clientHeight - pad * 2) / ch;
  cam.k = Math.min(Math.max(Math.min(kw, kh), 0.2), 1.8);
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  cam.x = pane.clientWidth / 2 - cx * cam.k;
  cam.y = pane.clientHeight / 2 - cy * cam.k;
  applyCam();
}

function panToNode(id) {
  const p = nodePos[id];
  const pane = $("graphPane");
  if (!p || !pane) return;
  cam.x = pane.clientWidth / 2 - p.x * cam.k;
  cam.y = pane.clientHeight / 2 - p.y * cam.k;
  applyCam();
}

function bindCanvas() {
  const pane = $("graphPane");
  pane.title = "按住空格拖动，滚轮缩放";

  window.addEventListener("keydown", (e) => {
    if (e.code !== "Space") return;
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable || t.closest?.("#saveSummary"))) return;
    e.preventDefault();
    spaceDown = true;
    pane.classList.add("pan");
  });
  window.addEventListener("keyup", (e) => {
    if (e.code !== "Space") return;
    spaceDown = false;
    pane.classList.remove("pan");
    if (!panning) pane.classList.remove("panning");
  });

  pane.addEventListener("mousedown", (e) => {
    const wantPan = spaceDown || e.button === 1;
    if (!wantPan) return;
    e.preventDefault();
    panning = true;
    didPan = false;
    panLast = { x: e.clientX, y: e.clientY };
    pane.classList.add("panning");
  });
  window.addEventListener("mousemove", (e) => {
    if (!panning) return;
    const dx = e.clientX - panLast.x;
    const dy = e.clientY - panLast.y;
    if (Math.abs(dx) + Math.abs(dy) > 2) didPan = true;
    cam.x += dx;
    cam.y += dy;
    panLast = { x: e.clientX, y: e.clientY };
    applyCam();
  });
  window.addEventListener("mouseup", () => {
    panning = false;
    pane.classList.remove("panning");
    setTimeout(() => {
      didPan = false;
    }, 0);
  });
  pane.addEventListener("wheel", (e) => {
    if ($("graphWrap").hidden) return;
    e.preventDefault();
    const rect = pane.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const factor = e.deltaY > 0 ? 0.9 : 1.1;
    const nk = Math.min(4, Math.max(0.15, cam.k * factor));
    const wx = (mx - cam.x) / cam.k;
    const wy = (my - cam.y) / cam.k;
    cam.k = nk;
    cam.x = mx - wx * nk;
    cam.y = my - wy * nk;
    applyCam();
  }, { passive: false });
  $("btnFit").onclick = (e) => {
    e.stopPropagation();
    fitView();
  };
  $("btnFit").addEventListener("mousedown", (e) => e.stopPropagation());
  $("btnSide").addEventListener("mousedown", (e) => e.stopPropagation());
  $("btnSide").onclick = (e) => {
    e.stopPropagation();
    showSide = !showSide;
    syncSide();
  };
  pane.addEventListener("click", () => {
    if (didPan || spaceDown || !selectedNode || !graphData) return;
    selectedNode = null;
    renderGraph(graphData);
  });
  let fitMaxTimer = 0;
  let wasMax = false;
  const looksMax = () =>
    screen.availWidth - window.innerWidth <= 24 &&
    screen.availHeight - window.innerHeight <= 96;
  window.addEventListener("resize", () => {
    clearTimeout(fitMaxTimer);
    fitMaxTimer = setTimeout(() => {
      const maxed = looksMax();
      const became = maxed && !wasMax;
      wasMax = maxed;
      if (!became || $("graphWrap").hidden || !graphData) return;
      fitView();
    }, 80);
  });
}

function renderGraph(g) {
  loadSaveSummary(g);
  const { nodes, colOf, rowOf, cols, colX } = getLayout(g);
  const current = onCurrentLine(g);
  const picked = selectedNode ? onNodeLine(nodes, selectedNode.id) : new Set();
  const PAD_TOP = 44;
  const PAD_BOTTOM = 32;
  const PAD_LEFT = 24;
  const COL_W = 36;
  const ROW_H = 56;
  const LABEL_W = 300;
  const rowVals = Object.values(rowOf);
  const rows = rowVals.length ? Math.max(...rowVals) + 1 : 1;
  const lastX = cols ? (colX && colX[cols - 1] != null ? colX[cols - 1] : (cols - 1) * COL_W) : 0;
  const W = Math.max(400, PAD_LEFT + lastX + LABEL_W);
  const H = Math.max(220, PAD_TOP + rows * ROW_H + PAD_BOTTOM);
  const svg = $("graph");
  svg.removeAttribute("viewBox");
  svg.removeAttribute("width");
  svg.removeAttribute("height");
  svg.classList.toggle("hide-remarks", !showRemarks);
  svg.setAttribute("overflow", "visible");
  const x = (id) => PAD_LEFT + ((colX && colX[colOf[id]]) != null ? colX[colOf[id]] : colOf[id] * COL_W);
  const y = (id) => PAD_TOP + rowOf[id] * ROW_H;
  graphSize = { w: W, h: H };
  nodePos = {};
  nodes.forEach((n) => {
    nodePos[n.id] = { x: x(n.id), y: y(n.id) };
  });
  let edges = "";
  nodes.forEach((n) => {
    (n.parents || []).forEach((p) => {
      if (rowOf[p] === undefined) return;
      const onPicked = picked.has(n.id) && picked.has(p);
      const hi = current.has(n.id) && current.has(p);
      const d = edgePath(x(n.id), y(n.id), x(p), y(p), curveEdges);
      const stroke = onPicked ? "#3d8bfd" : hi ? "#e6b325" : "#555";
      const sw = onPicked || hi ? 3 : 1.4;
      edges += `<path d="${d}" fill="none" stroke="${stroke}" stroke-width="${sw}" />`;
    });
  });
  startIds = new Set();
  nodes.forEach((n) => {
    if (!(n.parents || []).some((p) => rowOf[p] !== undefined)) startIds.add(n.id);
  });
  if (!startIds.size && nodes.length) {
    const oldest = nodes.reduce((a, b) => (a.time <= b.time ? a : b));
    startIds.add(oldest.id);
  }
  let dots = "";
  nodes.forEach((n) => {
    const sel = selectedNode && selectedNode.id === n.id;
    const isCur = n.id === g.current_id;
    const isStart = startIds.has(n.id);
    const onPicked = picked.has(n.id);
    const r = n.auto ? 5 : 7;
    const fill = isCur ? "#e6b325" : isStart ? "#6cbe8a" : "#777";
    const remark = isStart ? "起始存档" : nodeRemark(n);
    const badge = isCur ? "正在用" : "";
    const curTxt = badge ? `<text x="${x(n.id) + 14}" y="${y(n.id) - 20}" fill="#e6b325" font-size="12" text-rendering="geometricPrecision">${badge}</text>` : "";
    dots += `<g class="node${n.auto ? " auto" : ""}${sel ? " selected" : ""}${onPicked ? " on-line" : ""}" id="n-${n.id}" data-id="${n.id}">
      <circle cx="${x(n.id)}" cy="${y(n.id)}" r="${r}" fill="${fill}" stroke="${sel ? "#fff" : "none"}" stroke-width="${sel ? 2.5 : 0}" />
      ${curTxt}
      <text class="remark" x="${x(n.id) + 14}" y="${y(n.id) - 4}" fill="${sel ? "#5aa2ff" : "#ddd"}" font-size="13" font-weight="${sel ? 700 : 600}" text-rendering="geometricPrecision">${escapeHtml(remark)}</text>
      <text x="${x(n.id) + 14}" y="${y(n.id) + 14}" fill="#8a8a8a" font-size="12" text-rendering="geometricPrecision">${escapeHtml(formatTime(n.time))}</text>
    </g>`;
  });
  svg.innerHTML = `<g id="graphCam" transform="translate(${cam.x} ${cam.y}) scale(${cam.k})">${edges}${dots}</g>`;
  svg.querySelectorAll("g.node").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      if (didPan || spaceDown) return;
      selectedNode = nodes.find((n) => n.id === el.dataset.id);
      renderGraph(g);
    });
    el.addEventListener("dblclick", () => {
      if (didPan || spaceDown) return;
      restore();
    });
    el.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      selectedNode = nodes.find((n) => n.id === el.dataset.id);
      renderGraph(g);
      const acts = [
        { label: "切换到当前进度", run: restore },
        { label: "新建分支", run: newLine },
      ];
      if (!startIds.has(el.dataset.id)) {
        acts.push({ label: "备注", run: noteNode });
        acts.push({ label: "删除", run: deleteNode });
      }
      showMenu(e.clientX, e.clientY, acts);
    });
  });
}

function renderSteamGames() {
  const list = $("steamGameList");
  list.replaceChildren();
  for (const game of steamGames) {
    const item = items.find((it) => it.steam_app_id === game.app_id);
    const row = document.createElement("li");
    const shortcut = document.createElement("button");
    shortcut.type = "button";
    shortcut.textContent = game.name;
    const action = document.createElement("span");
    action.textContent = item ? "查看存档" : game.save_path ? "跟踪存档" : "手动选存档";
    shortcut.appendChild(action);
    shortcut.title = item ? "打开已有存档跟踪" : game.save_path || "未找到可确认的本地存档目录";
    shortcut.onclick = () => item ? selectItem(item.id) : addFolder(game);
    row.appendChild(shortcut);
    list.appendChild(row);
  }
}

async function scanSteamGames() {
  const button = $("btnScanSteam");
  const status = $("steamScanStatus");
  button.disabled = true;
  status.hidden = false;
  status.textContent = "正在扫描…";
  try {
    steamGames = await api().scan_steam_games();
    renderSteamGames();
    status.hidden = steamGames.length > 0;
    status.textContent = steamGames.length ? "" : "没找到已安装的 Steam 游戏";
  } catch (e) {
    status.textContent = "Steam 扫描失败，可点刷新重试";
  } finally {
    button.disabled = false;
  }
}

async function addFolder(game) {
  if (addingFolder) return;
  addingFolder = true;
  try {
    let path = game?.save_path || await api().pick_folder();
    if (!path) return;
    if (game) {
      path = (await askText(`确认「${game.name}」的存档文件夹`, path))?.trim();
      if (!path) return;
    }
    const base = path.split(/[/\\]/).filter(Boolean).pop() || "存档";
    const name = game?.name || await askText("给这个游戏起个名字，方便以后找", base);
    if (name === null) return;
    setBusy(true, "正在准备首次备份…");
    const r = await api().add_folder(path, name, game?.app_id || "");
    if (!r.ok) return askOk(r.error);
    await selectItem(r.item.id);
  } catch (e) {
    return askOk("无法打开存档跟踪，请重试。");
  } finally {
    setBusy(false);
    addingFolder = false;
  }
}

async function openSettings() {
  try {
    const location = await api().backup_location();
    const change = await ask({
      kind: "confirm",
      message: `当前备份位置\n${location.path}\n\n更改位置时，已有备份和历史会一起迁移。`,
      okLabel: "更改位置",
      cancelLabel: "关闭",
    });
    if (!change) return;
    const destination = await api().pick_folder(location.path);
    if (!destination || destination === location.path) return;
    const confirmed = await ask({
      kind: "confirm",
      message: `将全部备份迁移到以下空文件夹？\n${destination}`,
      okLabel: "迁移备份",
    });
    if (!confirmed) return;

    setBusy(true, "正在迁移并校验备份…");
    let result;
    try {
      result = await api().move_backup_location(destination);
    } finally {
      setBusy(false);
    }
    if (!result.ok) return askOk(result.error);
    await refreshItems();
    if (selectedId) await loadGraph();
    await askOk(result.warning || `备份已迁移到\n${result.path}`);
  } catch {
    await askOk("无法完成备份位置操作，请在设置中查看当前路径。");
  }
}

async function renameItem(id, old) {
  const name = await askText("游戏叫什么名字？", old);
  if (!name) return;
  const r = await api().rename_item(id, name);
  if (!r.ok) return askOk(r.error);
  await refreshItems();
}

async function removeItem(id, name) {
  const need = `我确定删除${name}存档`;
  const typed = await ask({
    kind: "prompt",
    message: `会从本工具里去掉「${name}」，并删掉这里记下的备份。游戏自己的存档文件不会被删。\n\n请输入「${need}」后才能删除。`,
    value: "",
    placeholder: need,
    need,
  });
  if (typed === null || typed.trim() !== need) return;
  const r = await api().remove_item(id);
  if (!r.ok) return askOk(r.error);
  if (selectedId === id) {
    selectedId = null;
    selectedNode = null;
    graphData = null;
    lastFitItem = null;
    hideSaveSummary();
    summarySlotIndex = null;
  }
  await refreshItems();
  if (selectedId) await loadGraph();
}

async function restore() {
  if (!selectedId || !selectedNode) return;
  if (!(await askYes("切换存档前请先退出游戏，否则可能失败或被游戏改回去。\n\n现在已经退出游戏了吗？"))) return;
  if (!(await askYes("会先把你现在的进度另外存一份，再切换到这一刻。如果开了 Steam 云存档，Steam 有可能又把存档改回去。"))) return;
  setBusy(true, "正在切换进度…");
  try {
    const r = await api().restore(selectedId, selectedNode.id, true);
    if (!r.ok) return askOk(r.error);
    await loadGraph();
  } finally {
    setBusy(false);
  }
}

async function newLine() {
  if (!selectedId || !selectedNode) return;
  if (!(await askYes("新建分支会复制这一刻，并切换过去。请先退出游戏。\n\n现在已经退出游戏了吗？"))) return;
  const name = await askText("这条分支叫什么？", "新进度");
  if (!name) return;
  setBusy(true, "正在切换进度…");
  try {
    const r = await api().create_line(selectedId, selectedNode.id, name);
    if (!r.ok) return askOk(r.error);
    await loadGraph();
  } finally {
    setBusy(false);
  }
}

async function noteNode() {
  if (!selectedId || !selectedNode) return;
  if (startIds.has(selectedNode.id)) return;
  const text = await askText("写一句备注，比如刚打完哪个 Boss", selectedNode.note || nodeRemark(selectedNode));
  if (text === null) return;
  const r = await api().set_note(selectedId, selectedNode.id, text);
  if (!r.ok) return askOk(r.error);
  await loadGraph();
}

async function deleteNode() {
  if (!selectedId || !selectedNode) return;
  if (startIds.has(selectedNode.id)) return;
  if (!(await askYes("会删掉这一刻的备份，以及从这里长出来的后续备份。\n\n删了无法恢复。游戏里的存档文件不会被删。\n\n确定删除？"))) return;
  const r = await api().delete_node(selectedId, selectedNode.id);
  if (!r.ok) return askOk(r.error);
  selectedNode = null;
  await loadGraph();
}

function showMenu(x, y, actions) {
  const menu = $("menu");
  menu.innerHTML = "";
  actions.forEach((a) => {
    const li = document.createElement("li");
    li.textContent = a.label;
    li.onclick = () => {
      menu.hidden = true;
      a.run();
    };
    menu.appendChild(li);
  });
  menu.style.left = x + "px";
  menu.style.top = y + "px";
  menu.hidden = false;
}

function formatTime(t) {
  if (!t) return "";
  const d = new Date(t * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function nodeRemark(n) {
  let s = "";
  if (n.note) s = n.note;
  else if (n.tags && n.tags[0]) s = n.tags[0];
  else if (n.auto) s = "存档";
  else s = shortMsg(n.message) || "存档";
  s = String(s)
    .replace(/^(自动存档|手动保存)\s*/, "")
    .replace(/^(自动|手动)\s*[-–—]?\s*/, "")
    .replace(/\s*[（(](自动|手动)[）)]\s*$/, "");
  const mark = n.auto ? "(自动)" : "(手动)";
  return clip(s || "存档", 20 - mark.length) + mark;
}

function clip(s, n) {
  s = String(s || "");
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function shortMsg(s) {
  s = (s || "").replace(/^\[(?:auto|fork)\]\s*/, "");
  return s;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

document.addEventListener("click", () => {
  $("menu").hidden = true;
});
$("btnAdd").onclick = () => addFolder();
$("btnAddBig").onclick = () => addFolder();
$("btnScanSteam").onclick = scanSteamGames;
$("btnSettings").onclick = openSettings;
$("saveSummary").addEventListener("toggle", () => {
  if (graphData && !$("graphWrap").hidden) fitView();
});
$("saveSummaryRetry").onclick = () => {
  if (!graphData) return;
  summaryKey = "";
  loadSaveSummary(graphData);
};
$("saveSummarySlot").onchange = (e) => {
  const slot = summarySlots.find((entry) => String(entry.index) === e.target.value);
  if (!slot) return;
  summarySlotIndex = slot.index;
  renderSaveSlot(slot);
};
$("btnSaveNow").onclick = async () => {
  if (Date.now() < swallowEnterUntil || !$("busy").hidden) return;
  if (!selectedId) return askOk("先选一个游戏");
  $("btnSaveNow").blur();
  setBusy(true, "正在保存…");
  try {
    const r = await api().save_now(selectedId);
    if (!r.ok) return askOk(r.error);
    if (r.skipped) return askOk("现在和上一版一样，没有新进度要存");
    await loadGraph();
    if (graphData && graphData.current_id) {
      selectedNode = (graphData.nodes || []).find((n) => n.id === graphData.current_id) || null;
      if (selectedNode) renderGraph(graphData);
    }
  } finally {
    setBusy(false);
    $("btnSaveNow").blur();
  }
};
$("showAuto").checked = !hideAuto;
$("showAuto").onchange = (e) => {
  hideAuto = !e.target.checked;
  localStorage.setItem("gb-auto-notes", hideAuto ? "0" : "1");
  loadGraph();
};
$("showRemarks").checked = showRemarks;
$("showRemarks").onchange = (e) => {
  showRemarks = e.target.checked;
  localStorage.setItem("gb-remarks", showRemarks ? "1" : "0");
  if (graphData) renderGraph(graphData);
};
function syncEdgeButtons() {
  $("btnCurve").classList.toggle("on", curveEdges);
  $("btnStraight").classList.toggle("on", !curveEdges);
}
function setCurveEdges(on) {
  curveEdges = on;
  localStorage.setItem("gb-curve", on ? "1" : "0");
  syncEdgeButtons();
  if (graphData) renderGraph(graphData);
}
$("btnCurve").onclick = () => setCurveEdges(true);
$("btnStraight").onclick = () => setCurveEdges(false);
syncEdgeButtons();
let allPaused = false;
$("btnPauseAll").onclick = async () => {
  allPaused = !allPaused;
  const r = await api().pause_all(allPaused);
  $("btnPauseAll").textContent = r.paused ? "继续自动备份" : "暂停自动备份";
};
function syncSide() {
  $("side").hidden = !showSide;
  document.querySelector("main").classList.toggle("side-off", !showSide);
  $("btnSide").textContent = showSide ? "‹" : "›";
  $("btnSide").title = showSide ? "隐藏游戏列表" : "显示游戏列表";
  localStorage.setItem("gb-side", showSide ? "1" : "0");
  if (graphData && !$("graphWrap").hidden) fitView();
}
syncSide();

let graphRev = 0;
async function pullGraphIfChanged() {
  if (!$("busy").hidden || !selectedId) return;
  const r = await api().graph_rev();
  if (r.rev === graphRev) return;
  graphRev = r.rev;
  await refreshItems();
  await loadGraph();
}

onReady(async () => {
  bindCanvas();
  scanSteamGames();
  await refreshItems();
  if (selectedId) await loadGraph();
  try {
    graphRev = (await api().graph_rev()).rev;
  } catch (e) {}
  setInterval(() => {
    pullGraphIfChanged();
  }, 2000);
});
