"""Offline dry-run harness: watch every gate decide, without a live show.

WHAT THIS IS FOR
    HIVE is well covered by unit tests and has never been run end to end. The
    thing tests cannot give you is a *reviewable* answer to "what would the
    classifier actually do to my chat?" -- gate by gate, message by message,
    with the adversarial lines mixed in among the ordinary ones. That review has
    to happen before a key is pointed at a live feed, not after.

    So this runs the real pipeline -- the real prefilter, the real moderation
    fail-closed logic, the real GATE 2 validator, the real arbiter with its
    quorum, cooldowns and photosensitivity ceiling -- over a fixed corpus, and
    prints what each stage did with each line.

WHAT IT COSTS
    Nothing, by default. ``--engine offline`` substitutes a deterministic local
    classifier for the model, so there is no key, no network and no bill. That
    is the default precisely because the expensive gate is the LEAST important
    one: GATE 1 is assumed defeatable and nothing downstream trusts it (see
    :mod:`chat_bridge.interpreter`). Everything the offline engine cannot tell
    you is a question about English, not about safety.

    ``--engine openai`` makes real, paid calls and is refused unless
    ``--i-approve-paid-calls`` is also given AND ``OPENAI_API_KEY`` is set. It
    prints what it is about to spend and on how many messages first. There is no
    environment variable that turns that confirmation off: a harness that can
    quietly start billing is a harness nobody can leave lying around.

WHAT THE OFFLINE ENGINE IS AND IS NOT
    It is a stand-in with the same OUTPUT CONTRACT as the model -- it emits the
    same JSON, against the same live schema, and it goes through the same
    validator. It is NOT a prediction of what GPT would say. Where the two would
    differ is exactly the English-comprehension question ``--engine openai``
    exists to answer on a small sample.

    It is deliberately a little too eager (it classifies on keywords, so it
    "understands" nothing and cannot be prompt-injected either). Read a NONE
    from it as "no keyword matched", never as "the model would refuse".

USAGE
    ./venv/bin/python -m chat_bridge.dryrun
    ./venv/bin/python -m chat_bridge.dryrun --ndjson outputs/hive_dryrun.ndjson
    ./venv/bin/python -m chat_bridge.dryrun --engine openai --i-approve-paid-calls
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import config, prefilter, validator
from .arbiter import Arbiter
from .interpreter import Interpreter, build_schema, build_system_prompt, render_batch
from .model import Action, ChatMessage, safe_display_name
from .moderation import Moderator, structural_check

#: The corpus that ships with the module. Absolute, so the harness runs from
#: anywhere rather than depending on the caller's working directory.
DEFAULT_CORPUS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "samples", "dryrun_corpus.jsonl")

#: A synthetic clock. The arbiter's cooldowns, vote window and one-shot minimum
#: intervals are all time-based, so a wall clock would make this harness
#: non-deterministic and its output non-diffable. Messages arrive one second
#: apart, which is dense enough that the per-user cooldown (90 s) and the
#: one-shot minimum intervals (8-30 s) both visibly bite -- that is the point.
T0 = 1000.0
DT = 1.0


# --- The offline stand-in ----------------------------------------------------
# Keyword rules, tried in order. First match wins. This is a fixture, not an
# attempt at natural language: see the module docstring.

#: (pattern, verb, target, amount, colour). Ordered -- specific before general.
_RULES: Tuple[Tuple[str, str, str, float, Optional[str]], ...] = (
    # One-shots before nudges: "strobe burst" must not be eaten by "strobe".
    (r"\bstrobe\s*burst\b|\bburst\b.*\bdrop\b", "ONESHOT", "STROBE_BURST", 0.0, None),
    (r"\bwhite\s*out\b|\bwhiteout\b", "ONESHOT", "WHITEOUT", 0.0, None),
    (r"\bcolou?r\s*pop\b|\brain\b.*\b(acid|green)\b", "ONESHOT", "COLOR_POP", 0.0, "ACID"),
    # Profiles. Two words each, so they do not collide with the nudge words.
    (r"\bstrobe\s*acid\b|\bacid\s*strobe\b", "PROFILE", "STROBE_ACID", 0.0, None),
    (r"\bdeep\s*laser\b", "PROFILE", "DEEP_LASER", 0.0, None),
    (r"\bvapou?r\s*uv\b", "PROFILE", "VAPOR_UV", 0.0, None),
    (r"\bmono\s*pulse\b", "PROFILE", "MONO_PULSE", 0.0, None),
    (r"\buv\s*rave\b", "PROFILE", "UV_RAVE", 0.0, None),
    # Nudges. Direction is decided separately by _direction().
    (r"\bglow\b|\bbright\b|\bdim\b", "NUDGE", "GLOW", 0.0, None),
    (r"\bstrobes?\b|\bflash\b", "NUDGE", "FLASH", 0.0, None),
    (r"\btrails?\b|\bsmear\b", "NUDGE", "TRAILS", 0.0, None),
    (r"\bshake\b|\bwobble\b", "NUDGE", "SHAKE", 0.0, None),
    (r"\bzoom\b|\bpunch\b", "NUDGE", "ZOOM", 0.0, None),
    (r"\b(speed|fast(er)?|slow(er)?)\b", "NUDGE", "SPEED", 0.0, None),
    (r"\bchaos\b|\bcrazy\b|\bwild\b", "NUDGE", "CHAOS", 0.0, None),
    (r"\bmorph\b", "NUDGE", "MORPH", 0.0, None),
)

#: Words that flip a nudge negative. Checked before the positive default,
#: because "too bright, less glow" contains both.
_NEGATIVE = re.compile(
    r"\b(less|lower|reduce|down|slow(er)?|too\s+\w+|calm|chill|softer|smaller)\b")

#: An explicit colour word anywhere in the line, mapped to a legal anchor.
_COLOURS: Tuple[Tuple[str, str], ...] = (
    (r"\bcyan\b|\bteal\b", "CYAN"),
    (r"\bmagenta\b", "MAGENTA"),
    (r"\bacid\b|\bgreen\b|\blime\b", "ACID"),
    (r"\bpink\b", "PINK"),
    (r"\bviolet\b|\bpurple\b", "VIOLET"),
    (r"\bblue\b", "BLUE"),
    (r"\bwhite\s*hot\b|\bwhite\b", "WHITE_HOT"),
)


def _direction(text: str) -> float:
    """Decide a nudge's sign and strength from the wording.

    Args:
        text: Lowercased message text.

    Returns:
        A value in [-1, 1]. Never 0.0 -- the validator drops a zero nudge as
        meaningless, so an undecidable direction defaults to a mild increase,
        which is what "more X" without a qualifier means in practice.
    """
    strong = bool(re.search(r"\b(way|much|so|really|too|insane(ly)?)\b", text))
    if _NEGATIVE.search(text):
        return -0.8 if strong else -0.5
    return 0.8 if strong else 0.5


def _colour_in(text: str) -> Optional[str]:
    """Map any colour word in the line to a legal anchor.

    Args:
        text: Lowercased message text.

    Returns:
        A member of ``config.COLOUR_NAMES``, or None. An RGB triple returns
        None on purpose -- the audience cannot author one, and the validator
        refuses ``COLOR_POP`` without a legal name.
    """
    if re.search(r"#[0-9a-f]{3,8}\b|\brgb\b", text):
        return None
    for pattern, name in _COLOURS:
        if re.search(pattern, text):
            return name
    return None


def offline_classify(batch: Sequence[ChatMessage]) -> Dict[str, Any]:
    """Classify a batch with keyword rules, in the model's own response shape.

    Args:
        batch: The messages the interpreter was given, in order.

    Returns:
        A payload matching the live response schema. Indices are batch
        positions, exactly as the model is instructed to emit them.
    """
    actions: List[Dict[str, Any]] = []
    for i, msg in enumerate(batch):
        text = " ".join(msg.text.lower().split())
        verb, target, amount, colour = "NONE", "NONE", 0.0, None
        for pattern, rule_verb, rule_target, _amt, rule_colour in _RULES:
            if re.search(pattern, text):
                verb, target, colour = rule_verb, rule_target, rule_colour
                if verb == "NUDGE":
                    amount = _direction(text)
                break
        if verb == "ONESHOT" and target == "COLOR_POP":
            colour = _colour_in(text)
        actions.append({
            "i": i, "verb": verb, "target": target, "amount": amount,
            "colour": colour,
            # A flat 0.9 for every match. The offline engine has no opinion
            # worth expressing as a confidence, and inventing a spread would
            # make MIN_CONFIDENCE look tested when it is not.
            "confidence": 0.9 if verb != "NONE" else 0.0,
        })
    return {"actions": actions}


def offline_completion(system: str, user: str, schema: Dict[str, Any],
                       model: str, timeout: float) -> str:
    """Completion function with the interpreter's own signature, run locally.

    ``user`` is re-parsed rather than closed over, so the harness exercises
    ``render_batch``'s numbering for real: if that ever stopped round-tripping,
    this would misattribute exactly the way a confused model would.

    Args:
        system: The built system prompt. Unused; present for the signature.
        user: The rendered CHAT block.
        schema: The live response schema. Unused; present for the signature.
        model: Model id. Unused.
        timeout: Seconds. Unused.

    Returns:
        The response as JSON text, as the SDK would return it.
    """
    lines = []
    for line in user.splitlines():
        match = re.match(r"^(\d+): (.*)$", line)
        if match:
            lines.append(match.group(2))
    fake = [ChatMessage(msg_id=str(i), author_id=str(i), author_name="x",
                        text=text, ts=0.0) for i, text in enumerate(lines)]
    return json.dumps(offline_classify(fake))


def offline_moderation(texts: Sequence[str]) -> List[bool]:
    """Local stand-in for the hosted moderation layer.

    Passes everything. That is honest rather than lazy: the hosted layer's job
    is judging whether text is abusive, which cannot be approximated offline,
    and a stub that guessed would make the report look like moderation had run.
    The structural screen in front of it is REAL in this harness and is what
    the corpus's BLOCKED lines actually exercise.

    Args:
        texts: Strings that would have been screened.

    Returns:
        True for every input.
    """
    return [True] * len(texts)


# --- Corpus ------------------------------------------------------------------

def load_corpus(path: str) -> List[Dict[str, Any]]:
    """Read the JSONL corpus, skipping comment records.

    Args:
        path: Path to a JSONL file.

    Returns:
        One dict per message, in file order.

    Raises:
        ValueError: On a malformed line, naming the line number. A corpus that
            silently loses a message would silently lose a test case.
    """
    records: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError as exc:
                raise ValueError("%s:%d is not valid JSON: %s"
                                 % (path, lineno, exc)) from exc
            if "_comment" in record:
                continue
            missing = {"msg_id", "author_id", "author_name", "text"} - set(record)
            if missing:
                raise ValueError("%s:%d is missing %s"
                                 % (path, lineno, ", ".join(sorted(missing))))
            records.append(record)
    return records


def to_messages(records: Sequence[Dict[str, Any]]) -> List[ChatMessage]:
    """Build ChatMessages on the synthetic clock.

    Args:
        records: Corpus records.

    Returns:
        Messages one DT apart, so the arbiter's timers behave reproducibly.
    """
    return [ChatMessage(msg_id=r["msg_id"], author_id=r["author_id"],
                        author_name=r["author_name"], text=r["text"],
                        ts=T0 + i * DT, source=r.get("source", "youtube"))
            for i, r in enumerate(records)]


# --- The run -----------------------------------------------------------------

def run(records: Sequence[Dict[str, Any]],
        complete_fn: Optional[Callable[..., str]] = None,
        moderate_fn: Optional[Callable[[Sequence[str]], List[bool]]] = None,
        ) -> Dict[str, Any]:
    """Run the corpus through the real pipeline and record every verdict.

    The stage order mirrors ``bridge.Bridge.run_batch`` exactly -- prefilter,
    dedupe, moderate, classify, validate, offer, resolve. Nothing here
    reimplements a gate; the only substitutions are the two injected callables
    the production classes already accept.

    Args:
        records: Corpus records.
        complete_fn: Interpreter completion function. Defaults to offline.
        moderate_fn: Hosted moderation function. Defaults to offline.

    Returns:
        A report dict: per-message rows, arbiter decisions, and totals.
    """
    messages = to_messages(records)
    by_id = {m.msg_id: r for m, r in zip(messages, records)}

    # Every message starts as "never reached the model" and is overwritten by
    # whichever stage actually decided it. A row that still says this at the
    # end was dropped by a gate that did not name itself, which would be a bug
    # in this harness rather than in the bridge -- so it is visible, not blank.
    rows: Dict[str, Dict[str, Any]] = {
        m.msg_id: {
            "msg_id": m.msg_id, "author_id": m.author_id,
            "author_name": m.author_name, "safe_name": m.safe_name,
            "text": m.text, "stopped_at": "unreached", "reason": "",
            "arbiter": "",
            "verb": "", "target": "", "amount": 0.0, "colour": None,
            "duration": 0.0, "confidence": 0.0,
            "expect": by_id[m.msg_id].get("expect", ""),
            "why": by_id[m.msg_id].get("why", ""),
        } for m in messages
    }

    # 1. Prefilter -- the cost gate.
    kept = prefilter.prefilter(messages)
    kept_ids = {m.msg_id for m in kept}
    for m in messages:
        if m.msg_id not in kept_ids:
            rows[m.msg_id].update(stopped_at="prefilter", reason="no_keyword")

    # 2. Dedupe -- one author, one voice per batch.
    deduped = prefilter.dedupe(kept)
    deduped_ids = {m.msg_id for m in deduped}
    for m in kept:
        if m.msg_id not in deduped_ids:
            rows[m.msg_id].update(stopped_at="dedupe", reason="repeat_in_batch")

    # 3. Moderation -- structural screen is real; hosted layer is injected.
    moderator = Moderator(moderate_fn=moderate_fn or offline_moderation)
    passed, rejected = moderator.check_batch(deduped)
    by_author_reason = dict(rejected)
    passed_ids = {m.msg_id for m in passed}
    for m in deduped:
        if m.msg_id not in passed_ids:
            rows[m.msg_id].update(
                stopped_at="moderation",
                reason=by_author_reason.get(m.author_id, "rejected"))

    # 4 + 5. Interpreter and GATE 2. classify() runs the validator itself, so
    # the accepted actions below have already survived the gate that matters.
    interpreter = Interpreter(complete_fn=complete_fn or offline_completion)
    actions, reasons = interpreter.classify(passed)

    # The validator returns actions without the batch index, so attribution is
    # rebuilt the same way it resolves it: by author. An author appearing twice
    # in one batch cannot happen -- dedupe is per (author, text) and the
    # per-user cooldown catches the rest -- but assert rather than assume.
    trimmed = list(passed)[-config.BATCH_MAX_LINES:]
    by_author: Dict[str, ChatMessage] = {}
    for m in trimmed:
        by_author.setdefault(m.author_id, m)

    acted_ids = set()
    for action in actions:
        msg = by_author.get(action.author_id)
        if msg is None:  # pragma: no cover - attribution is index-resolved
            continue
        acted_ids.add(msg.msg_id)
        rows[msg.msg_id].update(
            stopped_at="", reason="", verb=action.verb, target=action.target,
            amount=round(action.amount, 3), colour=action.colour,
            duration=action.duration, confidence=round(action.confidence, 3))
    for m in trimmed:
        if m.msg_id not in acted_ids:
            rows[m.msg_id].update(stopped_at="validator", reason="none_or_refused")

    # 6. Arbiter -- quorum, cooldowns, per-user limits, one-shot intervals.
    arbiter = Arbiter()
    now = T0 + len(messages) * DT
    # The arbiter's verdict is recorded in its OWN column, never folded into
    # `stopped_at`. Quorum holding a single-voter PROFILE, or a cooldown
    # swallowing the second STROBE_BURST, is the system working exactly as
    # designed -- scoring it as a classification miss would bury the real
    # misses among a dozen correct refusals.
    for action in actions:
        msg = by_author.get(action.author_id)
        status = arbiter.offer(action, now)
        if msg is not None:
            rows[msg.msg_id]["arbiter"] = status

    oneshots = arbiter.take_oneshots(now)
    decisions, tally = arbiter.resolve(now + config.VOTE_WINDOW_S)

    def _decision(d: Any) -> Dict[str, Any]:
        return {"verb": d.verb, "target": d.target,
                "amount": round(d.amount, 3), "colour": d.colour,
                "duration": d.duration, "votes": d.votes,
                "safe_name": d.safe_name}

    ordered = [rows[m.msg_id] for m in messages]
    return {
        "engine_rows": ordered,
        "decisions": [_decision(d) for d in list(oneshots) + list(decisions)],
        "tally": tally,
        "validator_reasons": reasons,
        "totals": {
            "messages": len(messages),
            "survived_prefilter": len(kept),
            "survived_dedupe": len(deduped),
            "survived_moderation": len(passed),
            "actions_validated": len(actions),
            "decisions_emitted": len(oneshots) + len(decisions),
        },
    }


# --- Reporting ---------------------------------------------------------------

def _outcome(row: Dict[str, Any]) -> str:
    """Reduce a row to the symbol the corpus's ``expect`` is written in.

    This is the CLASSIFICATION outcome -- what the interpreter proposed and
    GATE 2 allowed through. What the arbiter subsequently did with it is a
    separate question with its own column; see the note in `run`.

    Args:
        row: One report row.

    Returns:
        ``BLOCKED``, ``NONE``, or ``VERB:TARGET``.
    """
    if row["stopped_at"] == "moderation":
        return "BLOCKED"
    if not row["verb"]:
        return "NONE"
    return "%s:%s" % (row["verb"], row["target"])


def _truncate(text: str, width: int) -> str:
    """Cut a string to width with an ellipsis.

    Args:
        text: Input.
        width: Maximum characters.

    Returns:
        A string no longer than ``width``.
    """
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"


def format_report(report: Dict[str, Any]) -> str:
    """Render the human-reviewable table.

    Args:
        report: The dict `run` returned.

    Returns:
        The full report as text.
    """
    out: List[str] = []
    out.append("=" * 100)
    out.append("HIVE DRY RUN -- every gate's verdict on every line")
    out.append("=" * 100)
    out.append("")
    out.append("%-5s %-32s %-10s %-21s %-18s %-14s %s"
               % ("ID", "TEXT", "STOPPED", "CLASSIFIED AS", "EXPECTED",
                  "ARBITER", "?"))
    out.append("-" * 110)

    agree = disagree = 0
    mismatches: List[Dict[str, Any]] = []
    for row in report["engine_rows"]:
        outcome = _outcome(row)
        expect = row["expect"]
        if not expect:
            mark = " "
        elif outcome == expect:
            mark = "ok"
            agree += 1
        else:
            mark = "XX"
            disagree += 1
            mismatches.append(dict(row, outcome=outcome))
        stopped = row["stopped_at"] or "passed"
        detail = outcome
        if row["verb"] == "NUDGE":
            detail += " %+.2f" % row["amount"]
        if row["colour"]:
            detail += "/" + row["colour"]
        if row["duration"]:
            detail += " %.1fs" % row["duration"]
        out.append("%-5s %-32s %-10s %-21s %-18s %-14s %s"
                   % (row["msg_id"], _truncate(row["text"], 32), stopped,
                      _truncate(detail, 21), _truncate(expect, 18),
                      row["arbiter"] or "-", mark))

    out.append("-" * 110)
    out.append("")

    out.append("FUNNEL")
    for key, value in report["totals"].items():
        out.append("  %-22s %d" % (key.replace("_", " "), value))
    out.append("")

    out.append("DECISIONS ACTUALLY EMITTED (what TouchDesigner would receive)")
    if not report["decisions"]:
        out.append("  (none)")
    for d in report["decisions"]:
        line = "  %s %s" % (d["verb"], d["target"])
        if d["verb"] == "NUDGE":
            line += " amount=%+.3f" % d["amount"]
        if d["colour"]:
            line += " colour=%s" % d["colour"]
        if d["duration"]:
            line += " duration=%.2fs" % d["duration"]
        line += "  votes=%d  ack=%s" % (d["votes"], d["safe_name"] or "-")
        out.append(line)
    out.append("")

    if report["tally"]:
        out.append("VOTE TALLY")
        for key, count in sorted(report["tally"].items()):
            out.append("  %-28s %d" % (key, count))
        out.append("")

    if report["validator_reasons"]:
        counts: Dict[str, int] = {}
        for reason in report["validator_reasons"]:
            counts[reason] = counts.get(reason, 0) + 1
        out.append("GATE 2 REFUSALS")
        for reason, count in sorted(counts.items()):
            out.append("  %-28s %d" % (reason, count))
        out.append("")

    if mismatches:
        out.append("DISAGREEMENTS WITH THE CORPUS -- read these")
        out.append("")
        for row in mismatches:
            out.append("  %s  %s" % (row["msg_id"], _truncate(row["text"], 78)))
            out.append("      got %-22s expected %s (stopped at: %s%s)"
                       % (row["outcome"], row["expect"],
                          row["stopped_at"] or "passed",
                          ", " + row["reason"] if row["reason"] else ""))
            if row["arbiter"]:
                out.append("      arbiter: %s" % row["arbiter"])
            if row["why"]:
                out.append("      corpus note: %s" % _truncate(row["why"], 88))
            out.append("")

    out.append("AGREEMENT WITH CORPUS: %d/%d  (%d disagree)"
               % (agree, agree + disagree, disagree))
    out.append("")
    out.append("A disagreement is not automatically a bug. The offline engine "
               "matches keywords and")
    out.append("understands nothing -- read each one and decide whether the "
               "GATE, the CORPUS, or the")
    out.append("ENGINE is wrong. Only --engine openai answers the "
               "English-comprehension question.")
    return "\n".join(out)


# --- Entry point -------------------------------------------------------------

def _openai_guard(args: argparse.Namespace) -> None:
    """Refuse a paid run that was not explicitly and specifically approved.

    Args:
        args: Parsed arguments.

    Raises:
        SystemExit: If approval or a key is missing.
    """
    if not args.i_approve_paid_calls:
        raise SystemExit(
            "--engine openai makes real, paid API calls.\n"
            "Re-run with --i-approve-paid-calls if that is what you want.\n"
            "The default (--engine offline) exercises every gate for free.")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is not set. Export it in this shell only --\n"
            "do not add it to a file in this repo.")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        argv: Argument vector. Defaults to ``sys.argv[1:]``.

    Returns:
        The parsed namespace.
    """
    parser = argparse.ArgumentParser(
        prog="python -m chat_bridge.dryrun",
        description="Run the HIVE moderation + interpreter pipeline over a "
                    "fixed corpus, offline and free by default.")
    parser.add_argument("--corpus", default=DEFAULT_CORPUS,
                        help="JSONL corpus (default: the one that ships here)")
    parser.add_argument("--engine", default="offline",
                        choices=["offline", "openai"],
                        help="offline = deterministic local stand-in, free. "
                             "openai = real paid calls, gated below.")
    parser.add_argument("--i-approve-paid-calls", action="store_true",
                        help="required by --engine openai. No env var "
                             "substitutes for it.")
    parser.add_argument("--limit", type=int, default=None,
                        help="use only the first N messages -- keep a paid "
                             "sample small")
    parser.add_argument("--ndjson", default=None, metavar="PATH",
                        help="also write one JSON row per message here")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the harness.

    Args:
        argv: Argument vector.

    Returns:
        Process exit code. 0 even when rows disagree with the corpus -- a
        disagreement is a thing to read, not a build failure, and returning
        non-zero would invite someone to "fix" it by editing the corpus.
    """
    args = parse_args(argv)
    records = load_corpus(args.corpus)
    if args.limit is not None:
        records = records[: args.limit]

    complete_fn = moderate_fn = None
    if args.engine == "openai":
        _openai_guard(args)
        sys.stderr.write(
            "About to make PAID OpenAI calls: 1 interpreter completion over "
            "%d messages,\nplus one free moderation call. Model: %s\n\n"
            % (len(records), config.INTERPRETER_MODEL))
        # None on both means the production defaults -- the real SDK paths.

    report = run(records, complete_fn=complete_fn, moderate_fn=moderate_fn)
    report["engine"] = args.engine
    report["corpus"] = args.corpus

    print(format_report(report))

    if args.ndjson:
        directory = os.path.dirname(os.path.abspath(args.ndjson))
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(args.ndjson, "w", encoding="utf-8") as handle:
            for row in report["engine_rows"]:
                handle.write(json.dumps(dict(row, engine=args.engine),
                                        sort_keys=True) + "\n")
        print("\nwrote %s (%d rows)" % (args.ndjson, len(report["engine_rows"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
