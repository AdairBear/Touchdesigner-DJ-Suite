# archive/toe/ — non-canonical TouchDesigner `.toe` variants

This directory holds every `.toe` file that is **not** the canonical project file.
The canonical file is **`dj_visuals.toe` at the repo root** (311,010 bytes) and
stays there — it is the file TouchDesigner opens for the live DJ visual suite.

## Why these were archived

During the 2026-06-15 TD-DJ-Suite prep session, an audit flagged an apparent
"311 → 25 → 21 KB regression" in the project file and raised the worry that the
canonical network had been clobbered down to a near-empty shell.

The prep session **disproved** that: the size regression lived entirely in the
separate `dj_visuals.live_*.toe` working/checkpoint files (TouchDesigner's
per-save incrementing variants), which were never the file the project opens.
`dj_visuals.toe` at root was confirmed intact at its full 311,010 bytes and is
canonical. The smaller `live_*` files are mid-edit checkpoints from sessions
where only a sub-network was open, not regressions of the canonical file.

To keep the repo root unambiguous — one `.toe`, and it is the right one — every
other variant is moved here rather than deleted. Nothing is lost; the lineage is
preserved for reference.

## What's here

| Group | Files | What they are |
|-------|-------|---------------|
| `dj_visuals.N.toe` | `.6`, `.12`, `.14` | TouchDesigner incrementing save twins of the canonical network |
| `dj_visuals.live_*.toe` | `2026-04-18[.1]`, `2026-04-19[.6/.11]`, bare | "live" session checkpoints — the size-regression lineage from the audit |
| `CrashAutoSave.dj_visuals.*.toe` | `.7`, `.8`, `.9`, `.12`, `live_2026-04-18.1` | TouchDesigner crash-recovery auto-saves (`live_2026-04-18.1` is a 0-byte crash artifact) |
| `Backup/` | 18 files | TouchDesigner's own `Backup/` directory of timestamped incremental saves, moved here intact (not unwrapped) |

## Rules

- **Do not edit `.toe` contents.** They are opaque binary; `.gitattributes`
  marks `*.toe binary` so git never line-ending-normalizes them.
- **`dj_visuals.toe` at root is the only canonical file.** If you need an old
  network, copy a variant out of here — don't move it back to root and rename.

_Archived as part of the 2026-06-15 TD-DJ-Suite Project Ambassador prep pass._
