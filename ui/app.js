const api = () => window.pywebview.api;

let items = [];
let selectedId = null;
let graphData = null;
let selectedNode = null;
let hideAuto = true;

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
    li.innerHTML = `<div>${escapeHtml(it.name)}</div><div class="sub">${escapeHtml(it.available ? it.path_short : "路径不可用")}</div>`;
    li.onclick = () => selectItem(it.id);
    li.oncontextmenu = (e) => {
      e.preventDefault();
      showMenu(e.clientX, e.clientY, [
        { label: "改名", run: () => renameItem(it.id, it.name) },
        { label: it.paused ? "继续备份" : "暂停备份", run: () => api().pause_item(it.id, !it.paused).then(loadGraph) },
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
    return;
  }
  graphData = g;
  $("empty").hidden = true;
  $("graphWrap").hidden = false;
  renderLines(g);
  renderGraph(g);
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
        document.getElementById("n-" + n.id)?.scrollIntoView({ block: "center" });
      }
    };
    li.oncontextmenu = (e) => {
      e.preventDefault();
      showMenu(e.clientX, e.clientY, [
        { label: "改名", run: () => renameLine(ln.name) },
        { label: "删除线", run: () => delLine(ln.name) },
      ]);
    };
    ul.appendChild(li);
  });
}

function layout(g) {
  const nodes = (g.nodes || []).slice().sort((a, b) => b.time - a.time);
  const colOf = {};
  (g.lines || []).forEach((ln, i) => {
    let cur = ln.tip;
    const seen = new Set();
    const byId = new Map(nodes.map((n) => [n.id, n]));
    while (cur && !seen.has(cur)) {
      seen.add(cur);
      if (colOf[cur] === undefined) colOf[cur] = i;
      cur = byId.get(cur)?.parents?.[0];
    }
  });
  const rowOf = {};
  nodes.forEach((n, i) => {
    rowOf[n.id] = i;
    if (colOf[n.id] === undefined) colOf[n.id] = 0;
  });
  return { nodes, colOf, rowOf, cols: Math.max(1, (g.lines || []).length) };
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

function renderGraph(g) {
  const { nodes, colOf, rowOf, cols } = layout(g);
  const current = onCurrentLine(g);
  const W = Math.max(360, cols * 36 + 320);
  const H = Math.max(200, nodes.length * 52 + 48);
  const svg = $("graph");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);
  const x = (id) => 28 + colOf[id] * 36;
  const y = (id) => 28 + rowOf[id] * 52;
  let edges = "";
  nodes.forEach((n) => {
    (n.parents || []).forEach((p) => {
      if (rowOf[p] === undefined) return;
      const hi = current.has(n.id) && current.has(p);
      edges += `<path d="M ${x(n.id)} ${y(n.id)} C ${x(n.id)} ${(y(n.id) + y(p)) / 2}, ${x(p)} ${(y(n.id) + y(p)) / 2}, ${x(p)} ${y(p)}" fill="none" stroke="${hi ? "#e6b325" : "#555"}" stroke-width="${hi ? 3 : 1.4}" />`;
    });
  });
  let dots = "";
  nodes.forEach((n) => {
    const sel = selectedNode && selectedNode.id === n.id;
    const isCur = n.id === g.current_id;
    const r = n.auto ? 5 : 7;
    const fill = isCur ? "#e6b325" : n.auto ? "#777" : "#3d8bfd";
    const remark = nodeRemark(n);
    const curTxt = isCur ? `<text x="${x(n.id) + 14}" y="${y(n.id) - 22}" fill="#e6b325" font-size="11">当前</text>` : "";
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
      selectedNode = nodes.find((n) => n.id === el.dataset.id);
      renderGraph(g);
      renderDetail();
    });
    el.addEventListener("dblclick", () => restore(true));
    el.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      selectedNode = nodes.find((n) => n.id === el.dataset.id);
      renderGraph(g);
      renderDetail();
      showMenu(e.clientX, e.clientY, [
        { label: "恢复（另开一线）", run: () => restore(true) },
        { label: "覆盖恢复", run: () => restore(false) },
        { label: "从这里开新线", run: newLine },
        { label: "打标签", run: tagNode },
        { label: "改备注", run: noteNode },
      ]);
    });
  });
}

function renderDetail() {
  const empty = $("detailEmpty");
  const body = $("detailBody");
  if (!selectedNode) {
    empty.hidden = false;
    body.hidden = true;
    return;
  }
  empty.hidden = true;
  body.hidden = false;
  $("dTime").textContent = formatTime(selectedNode.time);
  $("dMsg").textContent = selectedNode.auto ? "自动备份" : selectedNode.message;
  $("dNote").textContent = selectedNode.note ? "备注：" + selectedNode.note : "";
  $("dTags").textContent = (selectedNode.tags || []).length ? "标签：" + selectedNode.tags.join("、") : "";
}

async function addFolder() {
  const path = await api().pick_folder();
  if (!path) return;
  const base = path.split(/[/\\]/).filter(Boolean).pop() || "存档";
  const name = prompt("给这份存档起个名字", base);
  if (name === null) return;
  const r = await api().add_folder(path, name);
  if (!r.ok) return alert(r.error);
  selectedId = r.item.id;
  await refreshItems();
  await loadGraph();
}

async function renameItem(id, old) {
  const name = prompt("名字", old);
  if (!name) return;
  const r = await api().rename_item(id, name);
  if (!r.ok) return alert(r.error);
  await refreshItems();
}

async function restore(fork) {
  if (!selectedId || !selectedNode) return;
  const extra = "若开启了 Steam 云存档，恢复后云端可能再次覆盖。";
  if (fork) {
    if (!confirm("把当前进度另存成一条线，再恢复到这一版。\n" + extra)) return;
  } else if (!confirm("覆盖当前存档，不另开一线。此操作更危险。\n" + extra)) return;
  const r = await api().restore(selectedId, selectedNode.id, fork);
  if (!r.ok) return alert(r.error);
  await loadGraph();
}

async function newLine() {
  if (!selectedId || !selectedNode) return;
  const name = prompt("新线名称", "线");
  if (!name) return;
  const r = await api().create_line(selectedId, selectedNode.id, name);
  if (!r.ok) return alert(r.error);
  await loadGraph();
}

async function tagNode() {
  if (!selectedId || !selectedNode) return;
  const name = prompt("标签", "打 Boss 前");
  if (!name) return;
  const r = await api().tag(selectedId, selectedNode.id, name);
  if (!r.ok) return alert(r.error);
  await loadGraph();
}

async function noteNode() {
  if (!selectedId || !selectedNode) return;
  const text = prompt("备注", selectedNode.note || "");
  if (text === null) return;
  const r = await api().set_note(selectedId, selectedNode.id, text);
  if (!r.ok) return alert(r.error);
  await loadGraph();
}

async function renameLine(old) {
  const name = prompt("存档线名称", old);
  if (!name) return;
  const r = await api().rename_line(selectedId, old, name);
  if (!r.ok) return alert(r.error);
  await loadGraph();
}

async function delLine(name) {
  if (!confirm("删除这条存档线？游戏文件夹不会动。")) return;
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
let allPaused = false;
$("btnPauseAll").onclick = async () => {
  allPaused = !allPaused;
  const r = await api().pause_all(allPaused);
  $("btnPauseAll").textContent = r.paused ? "继续备份" : "暂停全部";
};
$("btnRestore").onclick = () => restore(true);
$("btnOverwrite").onclick = () => restore(false);
$("btnNewLine").onclick = newLine;
$("btnTag").onclick = tagNode;
$("btnNote").onclick = noteNode;

onReady(async () => {
  await refreshItems();
  if (selectedId) await loadGraph();
});
