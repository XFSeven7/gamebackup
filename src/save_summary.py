"""Compatibility imports for the original save summary entry points."""

from bundled_support.mortal_shell import summarize as summarize_mortal_shell
from bundled_support.onimusha import (
    annotate_nodes as onimusha_boss_nodes,
    load_index as load_onimusha_boss_index,
    save_index as save_onimusha_boss_index,
    scan_index as scan_onimusha_boss_index,
    summarize as summarize_onimusha,
)
