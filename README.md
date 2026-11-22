# 存档助手

<img src="docs/images/logo.svg" width="96" alt="存档助手图标" />

给普通玩家用的游戏存档备份工具。选好存档文件夹之后，它会在后台悄悄记住每一版；主界面用树形图看进度、回档、开新线。

## 下载

**[点击下载 Windows 版（最新）](https://github.com/XFSeven7/gamebackup/releases/latest/download/gamebackup-win64.zip)**

解压后双击 `start.bat`（推荐），或直接运行 `gamebackup.exe`。  
若提示被拦截：右键 zip / 文件夹 → 属性 → 勾选「解除锁定」。需要 Windows 10/11，并已安装 [WebView2](https://developer.microsoft.com/microsoft-edge/webview2/)（一般自带）。

历史版本见 [Releases](https://github.com/XFSeven7/gamebackup/releases)。

从 v1.1.2 起，Windows 版启动后会在后台检查最新正式版本。发现更新时，可查看「本次更新」，点击「立即更新」后会显示下载进度。下载校验完成后，应用会自动安装并重启，存档和设置保留。

![主界面：多游戏 + 存档树](docs/images/main.png)

## 能做什么

- **多游戏管理**：左边列出你在管的存档，各自占用空间一目了然
- **自动备份**：默认每两分钟检查一次，存档有变化才生成备份
- **树形进度**：分叉、标签、备注都能看见；当前进度高亮
- **安全回档**：默认另开一条线，当前进度不会被盖掉
- **托盘常驻**：关闭窗口后继续备份。可从托盘打开窗口、暂停备份或退出程序

![首次使用：选择存档文件夹](docs/images/empty.png)

## 怎么用

1. 打开应用，左侧会自动列出各个 Steam 库中已安装的游戏；安装或卸载后可点 **刷新**
2. 点 Steam 游戏下的 **跟踪存档**。扫描找到存档时可直接确认预填的路径，否则手动选择存档文件夹。确认后即进入存档树，之后可点 **查看存档** 直接打开
3. 之后正常玩游戏即可；重要节点可点 **立即保存**，或右键节点打标签 / 写备注
4. 想试另一条路线：从某个节点 **开新线**；想回去：双击或右键恢复（默认保留当前线）

备份数据默认在 `%LOCALAPPDATA%\gamebackup`。可在 **设置 → 更改位置** 选择空文件夹，迁移全部备份、分支、备注和摘要工具。迁移校验通过后会自动切换位置，下次启动继续使用新目录。

## 《鬼武者：剑之道》存档摘要

Steam 版《鬼武者：剑之道》可以在存档树中查看当前目标、游玩时长、红魂、背包和 Boss 再战进度，以及相对上一份备份的变化。展开树图内的「Boss 再战解锁记录」可查看各分支自动存档中首次观察到解锁的时间段。同一备份新增的条目会合并显示。摘要从备份副本读取。

摘要需要单独安装 [Universal Save Editor](https://github.com/Lucasifium/universal-save-editor)。在项目源码目录运行：

```powershell
powershell -File scripts/install-summary-tools.ps1
```

脚本校验下载文件的 SHA-256 后，将解析器和物品名称表放到当前备份目录下的 `tools`。Windows 压缩包里的存档助手会使用同一目录。

## 《致命躯壳 2》存档摘要

添加 `%LOCALAPPDATA%\MortalShell2\Saved\SaveGames` 后，选择存档树中的节点可查看正式版槽位和试玩档的游玩时长、战斗进度、装备、货币和背包，以及与上一备份同一槽位的变化。摘要直接读取备份，无需安装工具。未对照游戏内名称的物品和重生点显示内部 ID。

## 运行（开发）

需要 Windows 10/11，并已安装 [WebView2](https://developer.microsoft.com/microsoft-edge/webview2/)。

```powershell
python -m pip install -r requirements.txt
python run.py
```

可选：用独立数据目录跑演示，不碰你自己的备份：

```powershell
$env:GAMEBACKUP_ROOT = "$PWD\docs\_demo_root"
python run.py
```

## 打包

```powershell
powershell -File scripts/build.ps1
```

产物：`dist/gamebackup-win64.zip`。

## 重新生成 README 截图

```powershell
python scripts/seed_readme_demo.py
python docs/readme-demo/serve.py
# 浏览器打开 http://127.0.0.1:8765/ 与 ?empty=1 截图
```

## 说明

- 设计文档：`docs/superpowers/specs/2026-08-24-gamebackup-design.md`
