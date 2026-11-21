# 存档助手

给普通玩家用的游戏存档备份工具。选好存档文件夹之后，它会在后台悄悄记住每一版；主界面用树形图看进度、回档、开新线。

## 下载

**[点击下载 Windows 版（最新）](https://github.com/XFSeven7/gamebackup/releases/latest/download/gamebackup-win64.zip)**

解压后双击 `start.bat`（推荐），或直接运行 `gamebackup.exe`。  
若提示被拦截：右键 zip / 文件夹 → 属性 → 勾选「解除锁定」。需要 Windows 10/11，并已安装 [WebView2](https://developer.microsoft.com/microsoft-edge/webview2/)（一般自带）。

历史版本见 [Releases](https://github.com/XFSeven7/gamebackup/releases)。

![主界面：多游戏 + 存档树](docs/images/main.png)

## 能做什么

- **多游戏管理**：左边列出你在管的存档，各自占用空间一目了然
- **自动备份**：按固定间隔检测改动，没改就跳过
- **树形进度**：分叉、标签、备注都能看见；当前进度高亮
- **安全回档**：默认另开一条线，当前进度不会被盖掉
- **托盘常驻**：关掉窗口也还在备份；可一键暂停

![首次使用：选择存档文件夹](docs/images/empty.png)

## 怎么用

1. 打开应用，左侧会自动列出各个 Steam 库中已安装的游戏；安装或卸载后可点 **刷新**
2. 点 Steam 游戏下的 **跟踪存档**，选中实际的存档文件夹后即进入存档树。之后点 **查看存档** 可直接打开。也可以点左侧 `+` 手动添加
3. 之后正常玩游戏即可；重要节点可点 **立即保存**，或右键节点打标签 / 写备注
4. 想试另一条路线：从某个节点 **开新线**；想回去：双击或右键恢复（默认保留当前线）

备份数据默认在 `%LOCALAPPDATA%\gamebackup`，和游戏原目录分开存放。

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
