const api = () => window.pywebview.api;

let items = [];
let selectedId = null;
let graphData = null;
let selectedNode = null;
let hideAuto = true;
let curveEdges = localStorage.getItem("gb-curve") !== "0";
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

function onReady(fn) {
  if (window.pywebview) fn();
  else window.addEventListener("pywebviewready", fn);
}

async function refreshItems() {
  items = await api().list_items();
  const ul = $("itemList");
  ul.innerHTML = "";
  items.forEach((it) => {
    const li = document.createElement("li");
    li.className = "item" + (it.id === selectedId ? " active" : "") + (it.available ? "" : " missing");
    li.innerHTML = `<div>${escapeHtml(it.name)}</div><div class="sub">${escapeHtml(it.available ? it.path_short : "找不到这个文件夹了")}</div>`;
    li.onclick = () => selectItem(it.id);
    li.oncontextmenu = (e) => {
      e.preventDefault();
      showMenu(e.clientX, e.clientY, [
        { label: "改名字", run: () => renameItem(it.id, it.name) },
        { label: it.paused ? "继续自动备份" : "暂停自动备份", run: () => api().pause_item(it.id, !it.paused).then(loadGraph) },
      ]);
    };
    ul.appendChild(li);
  });
  $("empty").hidden = items.length > 0 && !!selectedId;
  if (!selectedId && items[0]) selectItem(items[0].id);
  else if (items.length === 0) {
    selectedId = null;
    $("empty").hidden = false;
    $("graphWrap").hidden = true;
    $("btnFit").hidden = true;
    $("lineList").innerHTML = "";
  }
}

async function selectItem(id) {
  selectedId = id;
  selectedNode = null;
  await refreshItems();
  await loadGraph();
}

async function loadGraph() {
  if (!selectedId) return;
  const g = await api().graph(selectedId, hideAuto);
  if (!g.ok) {
    $("empty").hidden = false;
    $("graphWrap").hidden = true;
    $("btnFit").hidden = true;
    return;
  }
  graphData = g;
  $("empty").hidden = true;
  $("graphWrap").hidden = false;
  $("btnFit").hidden = false;
  renderLines(g);
  renderGraph(g);
  if (lastFitItem !== selectedId) {
    lastFitItem = selectedId;
    fitView();
  }
  renderDetail();
}

function renderLines(g) {
  const ul = $("lineList");
  ul.innerHTML = "";
  (g.lines || []).forEach((ln) => {
    const li = document.createElement("li");
    li.className = "line" + (ln.name === g.current_line ? " current active" : "");
    li.textContent = ln.display || ln.name;
    li.onclick = () => {
      const n = (g.nodes || []).find((x) => x.id === ln.tip);
      if (n) {
        selectedNode = n;
        renderGraph(g);
        renderDetail();
        panToNode(n.id);
      }
    };
    li.oncontextmenu = (e) => {
      e.preventDefault();
      showMenu(e.clientX, e.clientY, [
        { label: "改名字", run: () => renameLine(ln.name) },
        { label: "删掉这条进度", run: () => delLine(ln.name) },
      ]);
    };
    ul.appendChild(li);
  });
}

function layout(g) {
  const nodes = (g.nodes || []).slice().sort((a, b) => b.time - a.time);
  const visible = new Set(nodes.map((n) => n.id));
  const kids = new Map();
  nodes.forEach((n) => {
    const pid = (n.parents || []).find((p) => visible.has(p));
    if (!pid) return;
    if (!kids.has(pid)) kids.set(pid, []);
    kids.get(pid).push(n);
  });
  const sortNodes = (arr) => {
    arr.sort((a, b) => b.time - a.time || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  };
  kids.forEach(sortNodes);
  const roots = nodes.filter((n) => !(n.parents || []).some((p) => visible.has(p)));
  sortNodes(roots);

  const widthOf = {};
  const width = (id) => {
    if (widthOf[id] != null) return widthOf[id];
    const cs = kids.get(id) || [];
    if (!cs.length) return (widthOf[id] = 1);
    return (widthOf[id] = cs.reduce((s, c) => s + width(c.id), 0));
  };
  roots.forEach((r) => width(r.id));

  const colOf = {};
  const place = (id, left) => {
    const cs = kids.get(id) || [];
    if (!cs.length) {
      colOf[id] = left;
      return;
    }
    let x = left;
    cs.forEach((c) => {
      place(c.id, x);
      x += width(c.id);
    });
    colOf[id] = colOf[cs[0].id];
  };
  let left = 0;
  roots.forEach((r) => {
    place(r.id, left);
    left += width(r.id);
  });

  const rowOf = {};
  nodes.forEach((n, i) => {
    rowOf[n.id] = i;
    if (colOf[n.id] === undefined) colOf[n.id] = 0;
  });
  const colVals = Object.values(colOf);
  const cols = colVals.length ? Math.max(...colVals) + 1 : 1;
  return { nodes, colOf, rowOf, cols };
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
  if (layoutCache.key === k && layoutCache.value) return layoutCache.value;
  const value = layout(g);
  layoutCache = { key: k, value };
  return value;
}

function edgePath(x1, y1, x2, y2, curve) {
  if (x1 === x2) return `M ${x1} ${y1} L ${x2} ${y2}`;
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

function applyCam() {
  const world = $("graphWorld");
  const pane = $("graphPane");
  if (!world || !pane) return;
  world.style.transform = `translate(${cam.x}px, ${cam.y}px) scale(${cam.k})`;
  pane.style.backgroundSize = `${22 * cam.k}px ${22 * cam.k}px`;
  pane.style.backgroundPosition = `${cam.x}px ${cam.y}px`;
}

function fitView() {
  const pane = $("graphPane");
  if (!pane) return;
  const pad = 48;
  const kw = (pane.clientWidth - pad * 2) / Math.max(graphSize.w, 1);
  const kh = (pane.clientHeight - pad * 2) / Math.max(graphSize.h, 1);
  cam.k = Math.min(Math.max(Math.min(kw, kh), 0.2), 1.8);
  cam.x = (pane.clientWidth - graphSize.w * cam.k) / 2;
  cam.y = (pane.clientHeight - graphSize.h * cam.k) / 2;
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
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
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
}

function renderGraph(g) {
  const { nodes, colOf, rowOf, cols } = getLayout(g);
  const current = onCurrentLine(g);
  const PAD_TOP = 44;
  const PAD_BOTTOM = 32;
  const PAD_LEFT = 24;
  const COL_W = 36;
  const ROW_H = 56;
  const LABEL_W = 300;
  const W = Math.max(400, PAD_LEFT + cols * COL_W + LABEL_W);
  const H = Math.max(220, PAD_TOP + nodes.length * ROW_H + PAD_BOTTOM);
  const svg = $("graph");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);
  svg.setAttribute("overflow", "visible");
  const x = (id) => PAD_LEFT + colOf[id] * COL_W;
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
      const hi = current.has(n.id) && current.has(p);
      const d = edgePath(x(n.id), y(n.id), x(p), y(p), curveEdges);
      edges += `<path d="${d}" fill="none" stroke="${hi ? "#e6b325" : "#555"}" stroke-width="${hi ? 3 : 1.4}" />`;
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
    const r = n.auto ? 5 : 7;
    const fill = isCur ? "#e6b325" : isStart ? "#6cbe8a" : n.auto ? "#777" : "#3d8bfd";
    const remark = isStart ? "起始存档" : nodeRemark(n);
    const badge = isCur ? "正在用" : "";
    const curTxt = badge ? `<text x="${x(n.id) + 14}" y="${y(n.id) - 20}" fill="#e6b325" font-size="11">${badge}</text>` : "";
    dots += `<g class="node${n.auto ? " auto" : ""}${sel ? " selected" : ""}" id="n-${n.id}" data-id="${n.id}">
      <circle cx="${x(n.id)}" cy="${y(n.id)}" r="${r}" fill="${fill}" stroke="${sel ? "#fff" : "none"}" />
      ${curTxt}
      <text x="${x(n.id) + 14}" y="${y(n.id) - 4}" fill="#ddd" font-size="12">${escapeHtml(remark)}</text>
      <text x="${x(n.id) + 14}" y="${y(n.id) + 14}" fill="#8a8a8a" font-size="11">${escapeHtml(formatTime(n.time))}</text>
    </g>`;
  });
  svg.innerHTML = edges + dots;
  svg.querySelectorAll("g.node").forEach((el) => {
    el.addEventListener("click", () => {
      if (didPan || spaceDown) return;
      selectedNode = nodes.find((n) => n.id === el.dataset.id);
      renderGraph(g);
      renderDetail();
    });
    el.addEventListener("dblclick", () => {
      if (didPan || spaceDown) return;
      restore(true);
    });
    el.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      selectedNode = nodes.find((n) => n.id === el.dataset.id);
      renderGraph(g);
      renderDetail();
      const acts = [
        { label: "切换到这一刻（保留当前进度）", run: () => restore(true) },
        { label: "不保留当前进度，直接切换", run: () => restore(false) },
        { label: "从这一刻另存一条进度", run: newLine },
        { label: "给这一刻起名", run: tagNode },
      ];
      if (!startIds.has(el.dataset.id)) acts.push({ label: "写备注", run: noteNode });
      showMenu(e.clientX, e.clientY, acts);
    });
  });
}

function renderDetail() {
  const empty = $("detailEmpty");
  const body = $("detailBody");
  if (!selectedNode) {
    empty.hidden = false;
    body.hidden = true;
    $("btnNote").hidden = false;
    return;
  }
  empty.hidden = true;
  body.hidden = false;
  $("dTime").textContent = formatTime(selectedNode.time);
  $("dMsg").textContent = startIds.has(selectedNode.id) ? "起始存档" : selectedNode.auto ? "自动存档" : selectedNode.message;
  $("dNote").textContent = startIds.has(selectedNode.id) ? "" : selectedNode.note ? "备注：" + selectedNode.note : "";
  $("dTags").textContent = (selectedNode.tags || []).length ? "名称：" + selectedNode.tags.join("、") : "";
  $("btnNote").hidden = startIds.has(selectedNode.id);
}

async function addFolder() {
  const path = await api().pick_folder();
  if (!path) return;
  const base = path.split(/[/\\]/).filter(Boolean).pop() || "存档";
  const name = prompt("给这个游戏起个名字，方便以后找", base);
  if (name === null) return;
  const r = await api().add_folder(path, name);
  if (!r.ok) return alert(r.error);
  selectedId = r.item.id;
  await refreshItems();
  await loadGraph();
}

async function renameItem(id, old) {
  const name = prompt("游戏叫什么名字？", old);
  if (!name) return;
  const r = await api().rename_item(id, name);
  if (!r.ok) return alert(r.error);
  await refreshItems();
}

async function restore(fork) {
  if (!selectedId || !selectedNode) return;
  if (!confirm("切换存档前请先退出游戏，否则可能失败或被游戏改回去。\n\n现在已经退出游戏了吗？")) return;
  const extra = "如果开了 Steam 云存档，Steam 有可能又把存档改回去。";
  if (fork) {
    if (!confirm("会先把你现在的进度另外存一份，再切换到这一刻。\n" + extra)) return;
  } else if (!confirm("不保留当前进度，游戏会直接切换到这一刻。\n" + extra)) return;
  const r = await api().restore(selectedId, selectedNode.id, fork);
  if (!r.ok) return alert(r.error);
  await loadGraph();
}

async function newLine() {
  if (!selectedId || !selectedNode) return;
  const name = prompt("这条进度叫什么？", "新进度");
  if (!name) return;
  const r = await api().create_line(selectedId, selectedNode.id, name);
  if (!r.ok) return alert(r.error);
  await loadGraph();
}

async function tagNode() {
  if (!selectedId || !selectedNode) return;
  const name = prompt("给这一刻起个名字，方便以后找", "打 Boss 前");
  if (!name) return;
  const r = await api().tag(selectedId, selectedNode.id, name);
  if (!r.ok) return alert(r.error);
  await loadGraph();
}

async function noteNode() {
  if (!selectedId || !selectedNode) return;
  if (startIds.has(selectedNode.id)) return;
  const text = prompt("写一句备注，比如刚打完哪个 Boss", selectedNode.note || "");
  if (text === null) return;
  const r = await api().set_note(selectedId, selectedNode.id, text);
  if (!r.ok) return alert(r.error);
  await loadGraph();
}

async function renameLine(old) {
  const name = prompt("这条进度叫什么？", old);
  if (!name) return;
  const r = await api().rename_line(selectedId, old, name);
  if (!r.ok) return alert(r.error);
  await loadGraph();
}

async function delLine(name) {
  if (!confirm("从图上删掉这条进度？游戏里的存档文件不会被删。")) return;
  const r = await api().delete_line(selectedId, name);
  if (!r.ok) return alert(r.error);
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
  if (n.note) return clip(n.note, 20);
  if (n.tags && n.tags[0]) return clip(n.tags[0], 20);
  if (n.auto) return "自动存档";
  return clip(shortMsg(n.message) || "存档", 20);
}

function clip(s, n) {
  s = String(s || "");
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function shortMsg(s) {
  s = (s || "").replace(/^\[auto\]\s*/, "");
  return s;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

document.addEventListener("click", () => {
  $("menu").hidden = true;
});
$("btnAdd").onclick = addFolder;
$("btnAddBig").onclick = addFolder;
$("showAuto").onchange = (e) => {
  hideAuto = !e.target.checked;
  loadGraph();
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
$("btnRestore").onclick = () => restore(true);
$("btnOverwrite").onclick = () => restore(false);
$("btnNewLine").onclick = newLine;
$("btnTag").onclick = tagNode;
$("btnNote").onclick = noteNode;

onReady(async () => {
  bindCanvas();
  await refreshItems();
  if (selectedId) await loadGraph();
});
