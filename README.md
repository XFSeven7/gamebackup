# gamebackup

给普通玩家用的游戏存档备份工具。

手动选择存档文件夹，可同时管理多份；后台按分钟备份（没改动就跳过）。用隐藏 git 仓库保存历史，主界面用树形图查看存档线、回档、开新线。

## 目标

- 打开就能用：选文件夹即进入管理，可起显示名
- 托盘常驻，不要求安装 Git / .NET / Node
- 回档默认另开一条线，当前进度不会丢
- 自动备份节点可隐藏，当前线高亮

Windows 桌面应用（Python + 系统 WebView2）。开发时：

```text
python -m pip install -r requirements.txt
python run.py
```

备份数据默认在 `%LOCALAPPDATA%\gamebackup`。

设计文档：`docs/superpowers/specs/2026-08-24-gamebackup-design.md`
