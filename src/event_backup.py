"""Keep a rolling sample and publish the two snapshots around a major event."""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

from dulwich import porcelain
from dulwich.index import commit_tree
from dulwich.objects import Blob, Commit
from dulwich.repo import Repo

from fingerprint import fingerprint
from game_support import GameSupport
from store import AUTHOR
from sync import mirror


def _pending_sample(repo: Path, head: bytes, live: Path, support: GameSupport) -> dict:
    try:
        metadata = json.loads((repo / ".git" / "event-sample.json").read_text(encoding="utf-8"))
        if (
            metadata["head"] == head.decode("ascii") and metadata["source"] == str(live)
            and metadata["kind"] == support.id and metadata.get("support_version", "1.0.0") == support.version
            and type(metadata["time"]) is int
            and isinstance(metadata["fingerprint"], str) and isinstance(metadata["state"], dict)
            and (repo / ".git" / "event-sample").is_dir()
        ):
            return metadata
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return {}


def _remember_sample(repo: Path, sample: Path, metadata: dict) -> None:
    # Invalidate metadata before replacing the working copy of the pending sample.
    manifest = repo / ".git" / "event-sample.json"
    manifest.unlink(missing_ok=True)
    mirror(sample, repo / ".git" / "event-sample")
    staged = sample.parent / "event-sample.json"
    staged.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    staged.replace(manifest)


def _snapshot_tree(history: Repo, folder: Path) -> bytes:
    entries = []
    for file in sorted(folder.rglob("*")):
        if not file.is_file():
            continue
        path = os.fsencode(file.relative_to(folder).as_posix())
        blob = Blob.from_string(file.read_bytes())
        history.object_store.add_object(blob)
        mode = 0o100755 if file.stat().st_mode & 0o100 else 0o100644
        entries.append((path, blob.id, mode))
    return commit_tree(history.object_store, entries)


def _event_commit(history: Repo, parent: bytes, tree: bytes, timestamp: int, message: str) -> bytes:
    commit = Commit()
    commit.parents = [parent]
    commit.tree = tree
    commit.author = commit.committer = AUTHOR
    commit.author_time = commit.commit_time = timestamp
    offset = datetime.fromtimestamp(timestamp).astimezone().utcoffset()
    commit.author_timezone = commit.commit_timezone = int(offset.total_seconds()) if offset else 0
    commit.encoding = b"UTF-8"
    commit.message = message.encode("utf-8")
    history.object_store.add_object(commit)
    return commit.id


def _publish_pair(history: Repo, repo: Path, head: bytes, sample: Path, before: dict, timestamp: int, labels: list[str]) -> bytes:
    previous_tree = _snapshot_tree(history, repo / ".git" / "event-sample")
    # Make both commits reachable in a single reference update. Until then, the
    # previous sample remains available for a retry after a failed write.
    parent = head
    if previous_tree != history[head].tree:
        parent = _event_commit(history, head, previous_tree, before["time"], "[auto] [event-before]")
    mirror(sample, repo)
    porcelain.add(str(repo), ["."])
    tree = history.open_index().commit(history.object_store)
    commit = _event_commit(history, parent, tree, timestamp, "[auto] [event-after] " + "；".join(labels))
    if not history.refs.set_if_equals(b"HEAD", head, commit):
        raise OSError("存档分支已切换，下次重新读取。")
    return commit


def poll_event_backup(
    root: Path, repo: Path, live: Path, support: GameSupport, current_fingerprint: str, saved_fingerprint: str,
) -> dict | None:
    """Yield a visible backup only when consecutive samples show a major event."""
    with Repo(str(repo)) as history:
        try:
            head = history.head()
        except KeyError:
            return None
        before = _pending_sample(repo, head, live, support)
        if current_fingerprint == before.get("fingerprint"):
            return {"skipped": True, "reason": "unchanged"}
        with tempfile.TemporaryDirectory(prefix="event-poll-", dir=repo / ".git") as scratch:
            sample = Path(scratch) / "save"
            mirror(live, sample)
            if fingerprint(sample) != current_fingerprint:
                return {"skipped": True, "reason": "save-changing"}
            timestamp = int(time.time())
            state = support.module.read_event_state(sample, root / "tools")
            if state is None:
                return {"skipped": True, "reason": "unreadable"}
            binding = {"source": str(live), "kind": support.id, "support_version": support.version}
            if not before and saved_fingerprint and saved_fingerprint != current_fingerprint:
                saved = Path(scratch) / "saved"
                mirror(repo, saved)
                if fingerprint(saved) == saved_fingerprint:
                    saved_state = support.module.read_event_state(saved, root / "tools")
                    if saved_state is not None:
                        before = {
                            **binding, "head": head.decode("ascii"), "time": history[head].commit_time,
                            "fingerprint": saved_fingerprint, "state": saved_state,
                        }
                        _remember_sample(repo, saved, before)
            labels = support.module.major_events(before["state"], state) if before else []
            if labels:
                head = _publish_pair(history, repo, head, sample, before, timestamp, labels)
            try:
                _remember_sample(repo, sample, {
                    **binding, "head": head.decode("ascii"), "time": timestamp,
                    "fingerprint": current_fingerprint, "state": state,
                })
            except OSError:
                if not labels:
                    raise
            return {"skipped": not labels, "reason": "ok" if labels else "event-sample"}
