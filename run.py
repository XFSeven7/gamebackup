import sys
from pathlib import Path


def _unblock_package() -> None:
    """浏览器下载的 zip 会带 Zone.Identifier，pythonnet 加载 DLL 会直接炸掉。"""
    if not getattr(sys, "frozen", False):
        return
    import ctypes

    roots = [Path(sys.executable).resolve().parent]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))

    # ponytail: 只清关键 DLL，全量扫太慢还容易被杀软拖住。
    interesting = (
        "python.runtime.dll",
        "clrloader.dll",
        "webview2loader.dll",
        "microsoft.web.webview2",
        "webbrowserinterop",
        ".pyd",
        "python314.dll",
        "python3.dll",
        "gamebackup.exe",
    )
    delete = ctypes.windll.kernel32.DeleteFileW
    for root in roots:
        try:
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                name = path.name.lower()
                if any(token in name for token in interesting):
                    delete(str(path) + ":Zone.Identifier")
        except OSError:
            continue


def _die(msg: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, msg, "存档助手", 0x10)
    except Exception:
        print(msg, file=sys.stderr)
    raise SystemExit(1)


_unblock_package()

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
try:
    from app import main
except Exception as e:
    _die(
        "启动失败。若文件是从浏览器下载的，请先双击同目录 start.bat，"
        f"或右键文件夹 → 属性 → 解除锁定。\n\n{e}"
    )

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _die(f"运行出错：\n{e}")
