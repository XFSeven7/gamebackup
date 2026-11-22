/* Fictional snapshots for the README. The interface is the normal application UI. */
(() => {
  if (new URLSearchParams(location.search).get("game") !== "onimusha") return;

  const demo = window.README_DEMO;
  const id = "onimusha-demo";
  const name = "鬼武者：剑之道";
  demo.selectedId = id;
  demo.items.unshift({
    id, name, path_short: "Steam 存档", current_line: "main", paused: false, available: true,
    size_bytes: 3869245, size_text: "3.7 MB", summary_supported: true, steam_app_id: "2638890",
  });

  const snapshot = (id, parent, time, note, milestones = {}) => ({
    id, parents: parent ? [parent] : [], time: new Date(`2026-11-15T${time}`).getTime() / 1000,
    message: note || "[auto]", note, auto: !note, fork: false, tags: [], ...milestones,
  });
  const nodes = [
    snapshot("benkei-win", "benkei-before", "21:44:00", "", {
      event_phase: "after", event_label: "击败：弁庆",
      progress_milestones: [{kind: "exploration", text: "到访区域 +1（累计 32）"}],
    }),
    snapshot("side-finish", "side-start", "21:39:00", "完成京都奇谭", {
      progress_milestones: [{kind: "mystery", text: "异闻已汇报 +1（累计 8）"}],
    }),
    snapshot("benkei-before", "mirror", "21:34:00", "", {event_phase: "before", event_label: ""}),
    snapshot("side-start", "mirror", "21:26:00", "去探索京都", {fork: true}),
    snapshot("mirror", "nue", "21:19:00", "", {
      progress_milestones: [{kind: "exploration", text: "传送镜 +1（累计 19）"}],
    }),
    snapshot("nue", "start", "20:52:00", "", {event_phase: "after", event_label: "击败：大鵺"}),
    snapshot("start", null, "20:18:00", "旅程开始"),
  ];
  const layout = {tabs: {overview: "节点摘要", boss: "Boss 进度", achievements: "成就"}};
  const graph = {
    ok: true, item_name: name, summary_supported: true, boss_progress_supported: true,
    support_layout: layout, support_version: "1.0.0", current_line: "main", current_id: "benkei-win",
    lines: [
      {name: "main", tip: "benkei-win", display: "主线"},
      {name: "探索京都", tip: "side-finish", display: "探索京都"},
    ],
    nodes,
  };
  demo.graphs[`${id}:0`] = demo.graphs[`${id}:1`] = graph;

  const bossNames = [
    "佐佐木巌流", "大唾拉", "罗掌愿", "百秽", "畏风", "鵺（青＆赤）", "大鵺", "百秽（强化）",
    "怒伐天", "怒伐天（强化）", "弁庆", "抚雷", "酒吞童子", "畏风＆抚雷",
    "佐佐木巌流（变异）", "道狂", "弁庆（完全武装）", "源义经",
  ];
  const completed = new Set([2, 3, 4, 5, 6, 7, 15, 17, 19, 21, 22, 26, 30, 33, 35, 46, 48, 50]);
  const counts = {16: 4, 18: 7, 20: 14, 23: 16, 24: 10, 38: 17, 41: 24, 44: 40, 49: 67};
  demo.summaries = {
    [id]: {
      ok: true, support_layout: layout,
      slots: [{
        index: 20, label: "自动存档", goal: "前往六道珍皇寺", previous_goal: "击败弁庆",
        location: "五条大桥", play_time: "010:36:20", difficulty: "剑戟",
        saved_at: "11/15/2026 21:43:26", souls: 28460, souls_delta: 2500, has_previous: true,
        boss_progress: bossNames.map((name, index) => ({name, unlocked: index < 11})),
        boss_unlocked: ["弁庆"],
        items: [
          {name: "丸药", quantity: 5, delta: -1},
          {name: "砥石", quantity: 3, delta: 0},
        ],
      }],
      achievements: Object.entries(window.DEMO_ACHIEVEMENTS).map(([id, [name, description, target]]) => ({
        id: Number(id), name, description, target, unlocked: completed.has(Number(id)),
        value: completed.has(Number(id)) ? target : (counts[id] || 0),
      })),
    },
  };
})();
