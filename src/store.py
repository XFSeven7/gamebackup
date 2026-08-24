"""隐藏 git 仓库：提交、存档线、标签、树形图数据。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo
from dulwich.walk import Walker

AUTHOR = b"gamebackup <gamebackup@local>"


def _p(path: Path) -> str:
    return str(Path(path))


def _hex(sha: bytes) -> str:
    if len(sha) == 20:
        return sha.hex()
    return sha.decode("ascii")


def _sha_bytes(commit_id: str) -> bytes:
    # dulwich 的 parse_object 要十六进制字符串，不要 20 字节裸 SHA
    return commit_id.encode("ascii")


def init_repo(path: Path) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    repo = porcelain.init(_p(path))
    repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/main")


def _commit(path: Path, message: str) -> str:
    repo_path = _p(path)
    porcelain.add(repo_path, ["."])
    sha = porcelain.commit(
        repo_path,
        message=message.encode("utf-8"),
        author=AUTHOR,
        committer=AUTHOR,
    )
    _ensure_main(path)
    return _hex(sha)


def _ensure_main(path: Path) -> None:
    repo = Repo(_p(path))
    if b"refs/heads/master" in repo.refs and b"refs/heads/main" not in repo.refs:
        repo.refs[b"refs/heads/main"] = repo.refs[b"refs/heads/master"]
        del repo.refs[b"refs/heads/master"]
    if b"refs/heads/main" in repo.refs:
        repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/main")


def commit_auto(path: Path, message: str | None = None) -> str:
    if not message:
        message = datetime.now().strftime("[auto] %Y-%m-%d %H:%M:%S")
    elif not message.startswith("[auto]"):
        message = "[auto] " + message
    return _commit(path, message)


def commit_manual(path: Path, message: str) -> str:
    return _commit(path, message)


def create_line(path: Path, from_id: str, name: str) -> None:
    porcelain.branch_create(_p(path), name, objectish=from_id)


def checkout_line(path: Path, name: str) -> None:
    repo = Repo(_p(path))
    ref = b"refs/heads/" + name.encode("utf-8")
    if ref not in repo.refs:
        raise KeyError(name)
    sha = repo.refs[ref]
    porcelain.reset(_p(path), "hard", treeish=_hex(sha))
    repo.refs.set_symbolic_ref(b"HEAD", ref)


def reset_to(path: Path, commit_id: str) -> None:
    porcelain.reset(_p(path), "hard", treeish=commit_id)


def rename_line(path: Path, old: str, new: str) -> None:
    repo = Repo(_p(path))
    old_ref = b"refs/heads/" + old.encode("utf-8")
    new_ref = b"refs/heads/" + new.encode("utf-8")
    if old_ref not in repo.refs:
        raise KeyError(old)
    repo.refs[new_ref] = repo.refs[old_ref]
    try:
        head_target = repo.refs.follow(b"HEAD")[0]
        if head_target == old_ref:
            repo.refs.set_symbolic_ref(b"HEAD", new_ref)
    except Exception:
        pass
    del repo.refs[old_ref]


def delete_line(path: Path, name: str) -> None:
    if name == "main":
        raise ValueError("正在用的这条进度不能删")
    repo = Repo(_p(path))
    ref = b"refs/heads/" + name.encode("utf-8")
    if ref not in repo.refs:
        raise KeyError(name)
    del repo.refs[ref]


def put_note(path: Path, commit_id: str, text: str) -> None:
    porcelain.notes_add(_p(path), _sha_bytes(commit_id), text.encode("utf-8"))


def add_tag(path: Path, commit_id: str, name: str) -> None:
    porcelain.tag_create(_p(path), name, objectish=commit_id)


def _display_line(name: str) -> str:
    return "主线" if name == "main" else name


def filter_auto_nodes(g: dict, hide_auto: bool) -> dict:
    """隐藏自动备份节点，但保留线头、标签、备注、手动节点，并接上祖先边。"""
    if not hide_auto:
        return g
    by_id = {n["id"]: n for n in g["nodes"]}
    tips = {ln["tip"] for ln in g["lines"]}
    keep = {
        n["id"]
        for n in g["nodes"]
        if (not n["auto"]) or n["id"] in tips or n["note"] or n["tags"]
    }

    def nearest(start: str) -> str | None:
        cur = start
        seen: set[str] = set()
        while cur and cur not in seen:
            seen.add(cur)
            if cur in keep:
                return cur
            node = by_id.get(cur)
            if not node or not node["parents"]:
                return None
            cur = node["parents"][0]
        return None

    nodes = []
    for n in g["nodes"]:
        if n["id"] not in keep:
            continue
        parents = []
        for p in n["parents"]:
            np = nearest(p)
            if np and np not in parents and np != n["id"]:
                parents.append(np)
        nodes.append({**n, "parents": parents})
    return {**g, "nodes": nodes}


def graph(path: Path, hide_auto: bool, current_line: str) -> dict:
    repo = Repo(_p(path))
    lines = []
    include: list[bytes] = []
    for ref in repo.refs.keys():
        if ref.startswith(b"refs/heads/"):
            name = ref[len(b"refs/heads/") :].decode("utf-8", errors="replace")
            tip = repo.refs[ref]
            lines.append({"name": name, "tip": _hex(tip), "display": _display_line(name)})
            include.append(tip)

    tags_on: dict[str, list[str]] = {}
    for ref in repo.refs.keys():
        if ref.startswith(b"refs/tags/"):
            tname = ref[len(b"refs/tags/") :].decode("utf-8", errors="replace")
            target = repo.refs[ref]
            obj = repo[target]
            # 附注标签指向 tag 对象
            if getattr(obj, "object", None):
                target = obj.object[1]
            cid = _hex(target)
            tags_on.setdefault(cid, []).append(tname)
            include.append(target if len(target) == 20 else bytes.fromhex(cid))

    if not include:
        return {
            "nodes": [],
            "lines": lines,
            "current_line": current_line,
            "current_id": "",
        }

    nodes = []
    seen: set[str] = set()
    for entry in Walker(repo.object_store, include):
        commit = entry.commit
        cid = _hex(commit.id)
        if cid in seen:
            continue
        seen.add(cid)
        msg = commit.message.decode("utf-8", errors="replace").strip()
        note_raw = porcelain.notes_show(_p(path), commit.id)
        note = note_raw.decode("utf-8", errors="replace") if note_raw else ""
        nodes.append(
            {
                "id": cid,
                "parents": [_hex(p) for p in commit.parents],
                "time": int(commit.commit_time),
                "message": msg,
                "auto": msg.startswith("[auto]"),
                "note": note,
                "tags": tags_on.get(cid, []),
            }
        )

    current_id = ""
    for ln in lines:
        if ln["name"] == current_line:
            current_id = ln["tip"]
            break
    if not current_id and lines:
        current_id = lines[0]["tip"]

    raw = {
        "nodes": nodes,
        "lines": lines,
        "current_line": current_line,
        "current_id": current_id,
    }
    return filter_auto_nodes(raw, hide_auto)
