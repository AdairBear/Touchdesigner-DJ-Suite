"""Tests for the per-profile .toe test files (python/dj_profile_toes.py).

The thing that actually matters here is a NEGATIVE property: the canonical live
show file must be unaffected. Five copies of one .toe boot into five different
looks by filename alone, and the mechanism that reads that filename must return
"no profile" for the show file, so the startup hook leaves it exactly as it was.

These tests assert that directly instead of trusting the reasoning, and they
never write to the real canonical .toe -- generation is exercised against a
synthetic source in a tmp directory.
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "touchdesigner" / "scripts"))
sys.path.insert(0, str(REPO / "python"))

import dj_graphics_profiles as gp  # noqa: E402
import dj_profile_toes as toes  # noqa: E402


# ---------------------------------------------------------------------------
# THE NO-OP GUARANTEE for the live show file
# ---------------------------------------------------------------------------
class TestCanonicalIsNeverClaimed:
    """The startup hook must apply nothing when the show file is running."""

    @pytest.mark.parametrize("name", [
        "DJ_Graphics_LIVE.toe",
        "DJ_Graphics_LIVE.7.toe",
        "/Users/thomasadair/Desktop/DJ_Graphics_LIVE.toe",
        "DJ_Graphics.toe",
        "dj_visuals.toe",
        "newproject.toe",
        "",
    ])
    def test_non_profile_toe_names_yield_no_profile(self, name):
        assert gp.profile_from_toe_name(name) is None

    def test_the_real_canonical_filename_yields_no_profile(self):
        """Pinned to the actual path the rig loads, not a paraphrase of it."""
        assert toes.CANONICAL_TOE.endswith("DJ_Graphics_LIVE.toe")
        assert gp.profile_from_toe_name(Path(toes.CANONICAL_TOE).name) is None

    def test_prefix_is_required_not_merely_conventional(self):
        """A profile name alone must not be enough to claim a file."""
        assert gp.profile_from_toe_name("UV_RAVE.toe") is None
        assert gp.profile_from_toe_name("my_UV_RAVE.toe") is None

    def test_unknown_profile_in_a_prefixed_name_is_rejected(self):
        assert gp.profile_from_toe_name("dj_launcher_NOT_A_PROFILE.toe") is None


# ---------------------------------------------------------------------------
# Filename -> profile resolution
# ---------------------------------------------------------------------------
class TestFilenameResolution:
    @pytest.mark.parametrize("profile", list(gp.PROFILES), ids=list(gp.PROFILES))
    def test_generated_filename_round_trips(self, profile):
        assert gp.profile_from_toe_name(gp.toe_filename(profile)) == profile

    @pytest.mark.parametrize("profile", list(gp.PROFILES), ids=list(gp.PROFILES))
    def test_td_save_increment_still_resolves(self, profile):
        """TD writes dj_launcher_X.3.toe after a save; that must still boot X."""
        name = "%s%s.3.toe" % (gp.TOE_PREFIX, profile)
        assert gp.profile_from_toe_name(name) == profile

    def test_full_path_resolves(self):
        path = "/Users/thomasadair/projects/x/dj_launcher_STROBE_ACID.toe"
        assert gp.profile_from_toe_name(path) == "STROBE_ACID"

    def test_case_of_extension_is_tolerated(self):
        assert gp.profile_from_toe_name("dj_launcher_UV_RAVE.TOE") == "UV_RAVE"


# ---------------------------------------------------------------------------
# The startup hook wiring
# ---------------------------------------------------------------------------
class TestStartupHookWiring:
    HOOKS = (REPO / "touchdesigner" / "scripts" / "td_startup_hooks.py").read_text()

    def test_profile_step_runs_after_the_rave_look(self):
        """Order matters: a profile must override the base look, not precede it.

        Scoped to the runner tuple. Searching the whole file matches the
        _log("graphics_profile", ...) call inside the step itself, which sits
        ABOVE _run() and made this assertion compare the wrong two positions.
        """
        start = self.HOOKS.index("for name, fn in (")
        tuple_body = self.HOOKS[start: self.HOOKS.index("):", start)]
        assert '("rave_look"' in tuple_body
        assert '("graphics_profile"' in tuple_body
        assert tuple_body.index('("rave_look"') < tuple_body.index('("graphics_profile"')

    def test_hook_imports_the_modules_it_uses(self):
        """os/sys are not pre-imported in TD's exec namespace."""
        assert "\nimport os\n" in self.HOOKS
        assert "\nimport sys\n" in self.HOOKS

    def test_hook_delegates_resolution_rather_than_reimplementing_it(self):
        """One parser, tested here -- not a second copy that can drift."""
        assert "profile_from_toe_name" in self.HOOKS

    def test_hook_adds_no_audio_tap(self):
        """The freeze guarantee still holds for the new step."""
        new_block = self.HOOKS[self.HOOKS.index("Per-profile .toe boot"):]
        new_block = new_block[: new_block.index("def _run(")]
        code = "\n".join(
            line for line in new_block.splitlines() if not line.lstrip().startswith("#")
        )
        assert "onValueChange" not in code
        assert "audio_spectrum" not in code


# ---------------------------------------------------------------------------
# Generation -- never against the real canonical file
# ---------------------------------------------------------------------------
class TestGeneration:
    @staticmethod
    def _fake_source(tmp_path):
        src = tmp_path / "DJ_Graphics_LIVE.toe"
        src.write_bytes(b"TOE-BINARY-PAYLOAD" * 100)
        return src

    def test_generate_leaves_the_source_byte_identical(self, tmp_path):
        """The one outcome this feature must never produce."""
        src = self._fake_source(tmp_path)
        before = toes.sha256(str(src))
        before_bytes = src.read_bytes()

        toes.generate(source=str(src), dest_dir=str(tmp_path / "out"))

        assert toes.sha256(str(src)) == before
        assert src.read_bytes() == before_bytes

    def test_generate_writes_one_toe_per_profile(self, tmp_path):
        src = self._fake_source(tmp_path)
        out = tmp_path / "out"
        manifest = toes.generate(source=str(src), dest_dir=str(out))

        assert len(manifest["profiles"]) == len(gp.PROFILES)
        for entry in manifest["profiles"]:
            assert (out / entry["file"]).exists()

    def test_every_copy_is_byte_identical_to_the_source(self, tmp_path):
        """Copies must differ only in filename -- no divergence to maintain."""
        src = self._fake_source(tmp_path)
        out = tmp_path / "out"
        manifest = toes.generate(source=str(src), dest_dir=str(out))
        for entry in manifest["profiles"]:
            assert (out / entry["file"]).read_bytes() == src.read_bytes()

    def test_every_generated_name_resolves_back_to_its_profile(self, tmp_path):
        src = self._fake_source(tmp_path)
        manifest = toes.generate(source=str(src), dest_dir=str(tmp_path / "out"))
        for entry in manifest["profiles"]:
            assert gp.profile_from_toe_name(entry["file"]) == entry["profile"]

    def test_missing_source_raises_rather_than_writing_junk(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            toes.generate(source=str(tmp_path / "nope.toe"), dest_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# The on-disk artefacts an agent will actually enumerate
# ---------------------------------------------------------------------------
class TestGeneratedArtefacts:
    def test_manifest_exists_and_lists_every_profile(self):
        manifest = toes.load_manifest()
        assert manifest is not None, "run: dj_profile_toes.py generate"
        assert {e["profile"] for e in manifest["profiles"]} == set(gp.PROFILES)

    def test_all_five_toe_files_are_present(self):
        rows = toes.list_profiles()
        missing = [r["profile"] for r in rows if not r["exists"]]
        assert not missing, "missing generated .toe for: %s" % missing

    def test_listing_is_machine_readable(self, capsys):
        toes.list_profiles(as_json=True)
        parsed = json.loads(capsys.readouterr().out)
        assert {r["profile"] for r in parsed} == set(gp.PROFILES)
        assert all("path" in r and "exists" in r for r in parsed)

    def test_profile_dir_is_not_the_desktop(self):
        """A copy must never sit next to the live file and be grabbed by mistake."""
        assert "Desktop" not in toes.PROFILE_DIR

    def test_open_rejects_an_unknown_profile(self):
        assert toes.open_profile("NOT_REAL") == 1

    def test_verify_reports_the_canonical_as_unchanged(self):
        """Read-only check against the checksum recorded at generation time."""
        if not Path(toes.CANONICAL_TOE).exists():
            pytest.skip("canonical .toe not present on this machine")
        assert toes.verify() == 0
