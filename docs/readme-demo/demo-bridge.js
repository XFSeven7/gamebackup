/* README 截图用：用预生成数据冒充 pywebview.api */
(function () {
  const D = window.README_DEMO;
  if (!D) return;
  const empty = new URLSearchParams(location.search).get("empty") === "1";
  const selected = empty ? null : D.selectedId;

  const api = {
    list_items: async () => (empty ? [] : D.items),
    scan_steam_games: async () => [],
    graph: async (id, hideAuto) => {
      const key = id + ":" + (hideAuto ? "1" : "0");
      return D.graphs[key] || { ok: false, error: "没有找到这份存档" };
    },
    graph_rev: async () => ({ rev: 0 }),
    pause_all: async (paused) => ({ ok: true, paused: !!paused }),
    pause_item: async () => ({ ok: true }),
    pick_folder: async () => "",
    add_folder: async () => ({ ok: false, error: "演示模式" }),
    rename_item: async () => ({ ok: true }),
    remove_item: async () => ({ ok: true }),
    restore: async () => ({ ok: true }),
    create_line: async () => ({ ok: true }),
    tag: async () => ({ ok: true }),
    set_note: async () => ({ ok: true }),
    rename_line: async () => ({ ok: true }),
    delete_line: async () => ({ ok: true }),
    delete_node: async () => ({ ok: true }),
    backup_now: async () => ({ ok: true }),
    save_now: async () => ({ ok: true, skipped: true }),
  };

  window.pywebview = { api };
  // 让 app.js 选中演示主游戏
  if (selected) {
    const orig = api.list_items;
    api.list_items = async () => {
      const items = await orig();
      // app.js 会在 refreshItems 里自动选第一项；我们把选中项排到最前
      const i = items.findIndex((x) => x.id === selected);
      if (i > 0) {
        const [it] = items.splice(i, 1);
        items.unshift(it);
      }
      return items;
    };
  }
})();
