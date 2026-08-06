#!/usr/bin/env python3
"""Generate, list and open the per-profile TouchDesigner test files.

WHAT THIS IS
    Five copies of the live .toe, one per graphics profile, each booting
    straight into that look. They exist so a look can be tested by OPENING A
    FILE ("open this, see this") instead of pasting into the Textport.

HOW A COPY KNOWS WHICH LOOK TO BOOT
    Every .toe -- canonical and copies alike -- execs the same external
    ``td_startup_hooks.py`` on load. That hook asks
    ``dj_graphics_profiles.profile_from_toe_name(project.name)`` which profile
    the running file encodes, and applies it. The answer comes purely from the
    FILENAME, so the copies are byte-identical to the original and need no
    in-TD edits, no per-file saves, and no divergence to maintain.

THE LIVE SHOW FILE IS NEVER TOUCHED
    The canonical file is /Users/thomasadair/Desktop/DJ_Graphics_LIVE.toe. It
    does not start with the ``dj_launcher_`` prefix, so the hook's lookup
    returns None for it and applies nothing -- it boots to UV_RAVE via the
    existing rave look pass, exactly as before. This tool only ever READS that
    file (as a copy source) and verifies its checksum afterwards; it has no code
    path that writes to it.

USAGE
    ./venv/bin/python python/dj_profile_toes.py generate   # make the 5 copies
    ./venv/bin/python python/dj_profile_toes.py list       # human-readable
    ./venv/bin/python python/dj_profile_toes.py list --json # for an agent
    ./venv/bin/python python/dj_profile_toes.py open STROBE_ACID
    ./venv/bin/python python/dj_profile_toes.py verify     # canonical unchanged?
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "touchdesigner", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import dj_graphics_profiles as gp  # noqa: E402

#: The file TouchDesigner actually loads for a show. READ-ONLY here, always.
CANONICAL_TOE = os.path.expanduser("~/Desktop/DJ_Graphics_LIVE.toe")

#: Where the generated per-profile test files live. Kept OUT of ~/Desktop so a
#: profile copy can never be mistaken for the live show file at a glance.
PROFILE_DIR = os.path.join(REPO_ROOT, "touchdesigner", "profiles")

#: Machine-readable index an agent can read instead of guessing filenames.
MANIFEST = os.path.join(PROFILE_DIR, "manifest.json")


def sha256(path: str) -> str:
    """Hash a file.

    Args:
        path: File to hash.

    Returns:
        Lowercase hex digest.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate(source: str = CANONICAL_TOE, dest_dir: str = PROFILE_DIR) -> Dict[str, Any]:
    """Copy the canonical .toe once per profile and write the manifest.

    The source is opened read-only and never written. Its checksum is recorded
    before and after the copies are made, and a mismatch is reported as a hard
    failure -- the live show file being modified is the one outcome this whole
    feature must not produce.

    Args:
        source: Canonical .toe to copy from.
        dest_dir: Directory to write the per-profile copies into.

    Returns:
        The manifest dict that was written.

    Raises:
        FileNotFoundError: If the canonical .toe is absent.
        RuntimeError: If the canonical file's checksum changes during the run.
    """
    if not os.path.exists(source):
        raise FileNotFoundError("canonical .toe not found: %s" % source)

    before = sha256(source)
    os.makedirs(dest_dir, exist_ok=True)

    entries: List[Dict[str, Any]] = []
    for name, profile in gp.PROFILES.items():
        filename = gp.toe_filename(name)
        target = os.path.join(dest_dir, filename)
        shutil.copy2(source, target)
        entries.append({
            "profile": name,
            "description": profile.description,
            "file": filename,
            "path": target,
            "sha256": sha256(target),
        })

    after = sha256(source)
    if before != after:
        raise RuntimeError(
            "canonical .toe changed during generation (%s -> %s) -- aborting"
            % (before[:12], after[:12])
        )

    # The manifest belongs BESIDE the copies it describes. Writing it to the
    # module-level MANIFEST path instead would mean a generate() into any other
    # directory (a test tmpdir, say) silently overwrites the real one with a
    # different source's checksum -- which is exactly what happened the first
    # time this ran under pytest.
    manifest_path = os.path.join(dest_dir, "manifest.json")
    manifest = {
        "generated_from": source,
        "canonical_sha256": before,
        "note": (
            "Each copy boots into its profile via the filename, read by "
            "td_startup_hooks -> dj_graphics_profiles.profile_from_toe_name(). "
            "The canonical file has no dj_launcher_ prefix, so the hook is a "
            "no-op for it."
        ),
        "profiles": entries,
    }
    with open(manifest_path, "w") as handle:
        json.dump(manifest, handle, indent=2)
    return manifest


def load_manifest() -> Optional[Dict[str, Any]]:
    """Read the manifest if it exists.

    Returns:
        The manifest dict, or None if the copies have not been generated.
    """
    try:
        with open(MANIFEST) as handle:
            return json.load(handle)
    except Exception:
        return None


def list_profiles(as_json: bool = False) -> List[Dict[str, Any]]:
    """List the available profile .toe files.

    Reports each profile's file, whether it is present on disk, and its
    description, so an agent can pick one without guessing at names.

    Args:
        as_json: Print machine-readable JSON instead of a table.

    Returns:
        One entry per registered profile.
    """
    manifest = load_manifest()
    by_name = {e["profile"]: e for e in (manifest or {}).get("profiles", [])}

    rows: List[Dict[str, Any]] = []
    for name, profile in gp.PROFILES.items():
        entry = by_name.get(name, {})
        path = entry.get("path", os.path.join(PROFILE_DIR, gp.toe_filename(name)))
        rows.append({
            "profile": name,
            "description": profile.description,
            "path": path,
            "exists": os.path.exists(path),
            "is_default": name == gp.DEFAULT_PROFILE,
        })

    if as_json:
        print(json.dumps(rows, indent=2))
    else:
        if not manifest:
            print("no manifest yet -- run: dj_profile_toes.py generate")
        for row in rows:
            print("%s %-12s %s" % (
                "OK " if row["exists"] else "MISSING",
                row["profile"],
                row["description"],
            ))
            print("       %s" % row["path"])
    return rows


def open_profile(name: str) -> int:
    """Open one profile's .toe in TouchDesigner.

    Args:
        name: Registry key, e.g. ``STROBE_ACID``.

    Returns:
        A process exit code: 0 on success, 1 on a bad name or missing file.
    """
    if name not in gp.PROFILES:
        print("unknown profile %r. available: %s" % (name, ", ".join(gp.PROFILES)))
        return 1
    path = os.path.join(PROFILE_DIR, gp.toe_filename(name))
    if not os.path.exists(path):
        print("not generated yet: %s\nrun: dj_profile_toes.py generate" % path)
        return 1
    print("opening %s -> %s" % (name, path))
    return subprocess.call(["open", "-a", "TouchDesigner", path])


def verify(source: str = CANONICAL_TOE, expected: Optional[str] = None) -> int:
    """Report the canonical .toe's checksum, optionally comparing to a baseline.

    Args:
        source: Canonical .toe path.
        expected: A known-good sha256 to compare against.

    Returns:
        0 if the file matches (or no baseline was supplied), 1 otherwise.
    """
    if not os.path.exists(source):
        print("MISSING canonical .toe: %s" % source)
        return 1
    actual = sha256(source)
    manifest = load_manifest()
    baseline = expected or (manifest or {}).get("canonical_sha256")
    print("canonical: %s" % source)
    print("sha256:    %s" % actual)
    if baseline:
        ok = actual == baseline
        print("baseline:  %s" % baseline)
        print("UNCHANGED" if ok else "CHANGED -- the live show file differs!")
        return 0 if ok else 1
    print("(no baseline recorded to compare against)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point.

    Args:
        argv: Argument list, defaulting to sys.argv[1:].

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate", help="copy the canonical .toe once per profile")
    p_list = sub.add_parser("list", help="list available profile .toe files")
    p_list.add_argument("--json", action="store_true", help="machine-readable output")
    p_open = sub.add_parser("open", help="open a profile .toe in TouchDesigner")
    p_open.add_argument("profile", help="profile name, e.g. STROBE_ACID")
    p_verify = sub.add_parser("verify", help="check the canonical .toe is unchanged")
    p_verify.add_argument("--expect", help="baseline sha256 to compare against")

    args = parser.parse_args(argv)
    if args.cmd == "generate":
        manifest = generate()
        print("generated %d profile .toe files in %s"
              % (len(manifest["profiles"]), PROFILE_DIR))
        for entry in manifest["profiles"]:
            print("  %-12s %s" % (entry["profile"], entry["file"]))
        print("canonical unchanged: %s" % manifest["canonical_sha256"][:16])
        return 0
    if args.cmd == "list":
        list_profiles(as_json=args.json)
        return 0
    if args.cmd == "open":
        return open_profile(args.profile)
    if args.cmd == "verify":
        return verify(expected=args.expect)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
