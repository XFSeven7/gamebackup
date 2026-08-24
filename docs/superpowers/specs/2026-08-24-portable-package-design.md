# 绿色包设计

日期：2026-08-24  
状态：已确认，可实现

## 一句话

把 gamebackup 打成 Windows 绿色 zip：解压后双击 `gamebackup.exe` 就能用，对方不用装 Python、Git 或本仓库。

## 目标用户

把 zip 发给朋友或放到网盘。他们会解压、双击，不会跑命令行。

## 交付物

- 文件名：`gamebackup-win64.zip`
- 解压后是一个文件夹，内含 `gamebackup.exe` 和 PyInstaller 的依赖目录（`_internal`）
- 无安装向导、不写注册表、不进开始菜单、没有卸载程序
- 备份数据仍在 `%LOCALAPPDATA%\gamebackup`，和 `python run.py` 开发版共用同一处；换解压位置或覆盖 exe 不会丢掉已有备份
- 仅 Windows 10/11 **64 位**

## 非目标

- 安装程序（Inno / NSIS）
- 代码签名（SmartScreen 可能提示「未知发布者」，第一次点「仍要运行」）
- 32 位 Windows
- 开机启动、自动更新
- 把备份数据放进绿色包文件夹（便携盘带走历史）

## 运行时

- 界面：系统 WebView2。Win11 自带；Win10 若缺失，启动时用系统 MessageBox 说明「需要先安装 Microsoft Edge WebView2」，并写出下载地址 `https://go.microsoft.com/fwlink/p/?LinkId=2124703`，然后退出，不要只抛英文堆栈。
- 托盘 + 主窗口行为和开发版相同。
- `ui/` 网页文件打进包内。frozen 时从打包资源目录读 `index.html`，开发时仍从仓库 `ui/index.html` 读。
- 控制台窗口不出现（windowed）。

## 怎么打

- 工具：PyInstaller，`onedir`（不是单文件 exe）。
- 仓库增加打包配置和一条命令（PowerShell 脚本即可），在项目根执行后产出 zip。
- `dist/`、`build/`、生成的 zip 不进 git。
- 开发仍用 `python run.py`，打包命令不改变日常调试。
- `requirements.txt` 不强制开发者安装 PyInstaller；打包脚本里再装，或单独 `requirements-build.txt`。

## 体积与预期

大约 30–50MB 量级（Python 运行时 + dulwich + pywebview + 托盘）。不追求压到 10MB。

## 测试

- 有一个小检查：开发模式和模拟 frozen 模式下，UI 入口文件路径都指向真实存在的 `index.html`。
- 手工：本机打出 zip → 解压到另一个目录 → 双击 `gamebackup.exe` → 窗口和托盘出现 → 能添加文件夹、看树图。不要求在本仓库自动化点 GUI。
