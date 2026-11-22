"""Built-in Mortal Shell 2 support."""

from pathlib import Path

from .events import major_events, read_event_state
from .summary import summarize_mortal_shell as summarize


def available(tools_dir: Path) -> bool:
    return True
