"""Built-in Onimusha: Way of the Sword support."""

from pathlib import Path

from .events import major_events, read_event_state
from .summary import (
    load_onimusha_boss_index as load_index,
    onimusha_boss_nodes as annotate_nodes,
    save_onimusha_boss_index as save_index,
    scan_onimusha_boss_index as scan_index,
    summarize_onimusha as summarize,
)


def available(tools_dir: Path) -> bool:
    return (tools_dir / "UniversalSaveEditor.exe").is_file()
