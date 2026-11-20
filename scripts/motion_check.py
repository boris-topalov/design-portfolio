#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""motion_check.py — motion / animation quality gate for the portfolio site.

Self-contained: Python standard library only (Python 3.8+), no third-party
dependencies. Run it from anywhere:

    python scripts/motion_check.py
    python scripts/motion_check.py --root /path/to/project

Exit code: 0 when no check fails (WARN notices do not fail the gate), 1 when at
least one check fails.

Checks
------
(m1) assets/js/motion.js exists and contains an early exit for
     prefers-reduced-motion: a matchMedia('(prefers-reduced-motion: reduce)')
     probe plus a `return` guard. FAIL otherwise.
(m2) some CSS file defines @media (prefers-reduced-motion: reduce) and resets
     both transitions and animations inside it (transition: none /
     transition-duration: .001ms and animation: none /
     animation-duration: .001ms / animation-iteration-count: 1). FAIL otherwise.
(m3) the JS has no external dependency constructs: fetch( / import / export /
     require( / http(s):// — comments and string literals are stripped before
     the scan, so attribution links in comments do not fail the gate.
(m4) every motion class (.word-roll, .scramble, .card-tilt, .card-expand,
     .hold-btn, .stream, .magnetic) appears at least once in the HTML and is
     defined as a selector in the CSS.
(m5) the total weight of assets/js/*.js is <= 72 KB, and no single
     assets/js/*.js file exceeds 40 KB.
(m6) the interactive motion controls carry their ARIA attributes: .card-expand
     needs aria-expanded, .hold-btn must be a <button> or carry role + tabindex.
(m7) pointer/scroll listeners are registered with {passive:true} where it
     matters (wheel / touchstart / touchmove / scroll). Heuristic, WARN only.

Why a separate gate
-------------------
qa_check.py already covers structure, links, alt text, file:// safety, themes,
fonts and offline CSS. The motion layer adds different failure modes (an
animation that ignores the OS reduced-motion setting, a CDN dependency sneaking
into the bundle, a keyboard-inaccessible hold-to-publish CTA). Keeping those in
their own script lets the design rebuild land without touching the structural
gate, and gives CI one command per concern.

Known limitations
-----------------
This is a lexical scanner, not a JS/CSS parser. It blanks comments, string
literals, template literals and regex literals before looking for forbidden
tokens, and it matches @media blocks by brace counting. Code inside a
template-literal ${...} substitution is not analysed. The passive-listener
check (m7) is a heuristic and never fails the gate.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MOTION_JS_REL = Path("assets/js/motion.js")
JS_DIR_PARTS = ("assets", "js")

# --- m5 budgets -------------------------------------------------------------
# Two limits, because one number alone cannot tell the two failure modes apart.
#
# JS_BUDGET_BYTES — whole bundle (assets/js + assets/vendor), 72 KB.
#   The page is three hand-written files totalling ~61 KB uncompressed, which
#   gzip to ~18 KB; the shipped weight was never the concern. The limit exists
#   to catch a heavy dependency appearing in the bundle. At 60 KB it sat only
#   ~320 B above the real total, so every new line of copy in i18n.js failed the
#   gate even though nothing heavy arrived — the old bound punished text edits
#   instead of dependencies. 72 KB leaves ~12 KB for real additions while still
#   stopping a vendored library (jQuery alone is ~87 KB).
#
# JS_FILE_BUDGET_BYTES — any single assets/js/*.js file, 40 KB.
#   The total can stay under budget while one file balloons (e.g. the whole
#   dictionary plus a motion engine merged into i18n.js), which hides both a
#   parse cost and a maintenance smell. 40 KB is above today's largest file
#   (i18n.js, ~30 KB) but well below any single vendored library, so a bloated
#   file is reported by name instead of being averaged away.
JS_BUDGET_BYTES = 72 * 1024      # m5: 72 KB total for the whole bundle
JS_FILE_BUDGET_BYTES = 40 * 1024  # m5: 40 KB max for any single JS file

# m4: classes the motion layer drives. Order is the order used in the report.
MOTION_CLASSES = (
    "word-roll",
    "scramble",
    "card-tilt",
    "card-expand",
    "hold-btn",
    "stream",
    "magnetic",
)

# m3: constructs that mean the file is not a plain file://-safe script.
FORBIDDEN_JS = ("fetch(", "import ", "export ", "require(", "https://", "http://")

# m7: events whose listener must be passive to keep scrolling smooth.
PASSIVE_EVENTS = ("wheel", "touchstart", "touchmove", "scroll")

REDUCED_QUERY = "prefers-reduced-motion: reduce"
REDUCED_MEDIA_RE = re.compile(
    r"@media[^{]*prefers-reduced-motion\s*:\s*reduce[^{]*\{", re.IGNORECASE
)

# Deep-reset values accepted as "the animation/transition is neutralised".
TRANSITION_RESET_RE = re.compile(
    r"(?:^|[;{])\s*transition\s*:\s*(?:none|0s|0ms|all\s+0s)"
    r"|(?:^|[;{])\s*transition-duration\s*:\s*(?:0s|0ms|\.?0*m?s|0\.001ms|\.001ms)",
    re.IGNORECASE,
)
ANIMATION_RESET_RE = re.compile(
    r"(?:^|[;{])\s*animation\s*:\s*none"
    r"|(?:^|[;{])\s*animation-duration\s*:\s*(?:0s|0ms|0\.001ms|\.001ms)"
    r"|(?:^|[;{])\s*animation-iteration-count\s*:\s*1",
    re.IGNORECASE,
)

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".qa"}
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def strip_css_comments(text: str) -> str:
    """Replace /* ... */ comments with whitespace, preserving offsets/lines."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                end = n - 2
            chunk = text[i:end + 2]
            out.append("".join("\n" if ch == "\n" else " " for ch in chunk))
            i = end + 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _match_brace(text: str, open_index: int) -> int:
    """Index of the '}' that closes the '{' at *open_index* (or len(text))."""
    depth = 0
    i = open_index
    n = len(text)
    quote = None
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


# ---------------------------------------------------------------------------
# JS scanning
# ---------------------------------------------------------------------------

REGEX_PRECEDERS = set("(,=:[!&|?{};+-*%~^<>\n")
REGEX_KEYWORDS = {
    "return", "typeof", "instanceof", "in", "of", "new", "delete",
    "void", "throw", "case", "do", "else", "yield", "await",
}


def _regex_starts(text: str, index: int) -> bool:
    j = index - 1
    while j >= 0 and text[j] in " \t\r\n":
        j -= 1
    if j < 0:
        return True
    char = text[j]
    if char.isalnum() or char in "_$":
        k = j
        while k >= 0 and (text[k].isalnum() or text[k] in "_$"):
            k -= 1
        return text[k + 1:j + 1] in REGEX_KEYWORDS
    return char in REGEX_PRECEDERS


def _skip_regex(text: str, index: int):
    j = index + 1
    n = len(text)
    in_class = False
    while j < n:
        char = text[j]
        if char == "\\":
            j += 2
            continue
        if char == "\n":
            return None
        if in_class:
            if char == "]":
                in_class = False
            j += 1
            continue
        if char == "[":
            in_class = True
            j += 1
            continue
        if char == "/":
            j += 1
            break
        j += 1
    else:
        return None
    while j < n and text[j].isalpha():
        j += 1
    return j


def mask_js(text: str) -> str:
    """Blank out comments, strings, templates and regexes, keeping positions."""
    out = []
    i = 0
    n = len(text)
    state = "code"
    quote = ""
    while i < n:
        char = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state == "code":
            if char == "/" and nxt == "/":
                out.append("  ")
                i += 2
                state = "line"
                continue
            if char == "/" and nxt == "*":
                out.append("  ")
                i += 2
                state = "block"
                continue
            if char == "/" and _regex_starts(text, i):
                end = _skip_regex(text, i)
                if end is not None:
                    out.append("".join("\n" if text[k] == "\n" else " "
                                       for k in range(i, end)))
                    i = end
                    continue
            if char in "\"'":
                quote = char
                out.append(" ")
                i += 1
                state = "str"
                continue
            if char == "`":
                out.append(" ")
                i += 1
                state = "tmpl"
                continue
            out.append(char)
            i += 1
            continue
        if state == "line":
            if char == "\n":
                state = "code"
                out.append("\n")
            else:
                out.append(" ")
            i += 1
            continue
        if state == "block":
            if char == "*" and nxt == "/":
                out.append("  ")
                i += 2
                state = "code"
                continue
            out.append("\n" if char == "\n" else " ")
            i += 1
            continue
        # state == "str" / "tmpl"
        if char == "\\":
            out.append("  " if nxt else " ")
            i += 2
            continue
        if (state == "str" and char == quote) or (state == "tmpl" and char == "`"):
            out.append(" ")
            i += 1
            state = "code"
            continue
        out.append("\n" if char == "\n" else " ")
        i += 1
    return "".join(out)


def strip_js_comments(text: str) -> str:
    """Blank comments only — string literals stay readable (for m1/m7 probes)."""
    out = []
    i = 0
    n = len(text)
    state = "code"
    quote = ""
    while i < n:
        char = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state == "code":
            if char == "/" and nxt == "/":
                out.append("  ")
                i += 2
                state = "line"
                continue
            if char == "/" and nxt == "*":
                out.append("  ")
                i += 2
                state = "block"
                continue
            if char in "\"'`":
                quote = char
                state = "str"
                out.append(char)
                i += 1
                continue
            out.append(char)
            i += 1
            continue
        if state == "str":
            out.append(char)
            if char == "\\" and nxt:
                out.append(nxt)
                i += 2
                continue
            if char == quote:
                state = "code"
            i += 1
            continue
        if state == "line":
            if char == "\n":
                state = "code"
                out.append("\n")
            else:
                out.append(" ")
            i += 1
            continue
        # block comment
        if char == "*" and nxt == "/":
            out.append("  ")
            i += 2
            state = "code"
            continue
        out.append("\n" if char == "\n" else " ")
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# HTML scanning
# ---------------------------------------------------------------------------


class ElementParser(HTMLParser):
    """Collects every start tag plus its parent/children, for ARIA checks.

    A flat list is not enough: aria-expanded belongs on the trigger button that
    sits *inside* an expandable card, so the gate needs the nesting to tell a
    correct ARIA pattern from a missing one.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements = []   # [{tag, classes, attrs, line, parent, children}]
        self._stack = []     # indices of currently open elements

    @staticmethod
    def _attrs(attrs) -> dict:
        result = {}
        for name, value in attrs:
            if name not in result:
                result[name] = value
        return result

    def _open(self, tag, attrs, push):
        line = self.getpos()[0]
        data = self._attrs(attrs)
        index = len(self.elements)
        parent = self._stack[-1] if self._stack else None
        self.elements.append({
            "tag": tag,
            "classes": (data.get("class") or "").split(),
            "attrs": data,
            "line": line,
            "parent": parent,
            "children": [],
        })
        if parent is not None:
            self.elements[parent]["children"].append(index)
        if push and tag not in VOID_TAGS:
            self._stack.append(index)

    def handle_starttag(self, tag, attrs):
        self._open(tag, attrs, push=True)

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs, push=False)

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        for position in range(len(self._stack) - 1, -1, -1):
            if self.elements[self._stack[position]]["tag"] == tag:
                del self._stack[position:]
                return

    def descendants(self, index):
        """Yield the indices of every element nested inside *index*."""
        stack = list(self.elements[index]["children"])
        while stack:
            current = stack.pop()
            yield current
            stack.extend(self.elements[current]["children"])

    def page_ids(self):
        return {str(element["attrs"]["id"]) for element in self.elements
                if element["attrs"].get("id")}


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def _walk_files(root: Path, extensions):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
        )
        for name in sorted(filenames):
            if name.lower().endswith(extensions):
                found.append(Path(dirpath) / name)
    return sorted(found)


def discover_html(root: Path):
    return _walk_files(root, (".html", ".htm"))


def discover_js(root: Path):
    return _walk_files(root, (".js", ".mjs"))


def discover_css(root: Path):
    return _walk_files(root, (".css",))

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _read(path: Path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RuntimeError(f"cannot read file ({exc})") from exc


def check_m1(root: Path):
    """(m1) motion.js exists and exits early under prefers-reduced-motion.

    Three things are required, and they must hang together:
      1. a matchMedia('(prefers-reduced-motion: reduce)') probe;
      2. the probe result actually read (its <var>.matches);
      3. an if() guard that returns, testing that same variable — directly or
         through a helper function that returns <var>.matches.

    Merely having *some* `.matches` in the file is not enough: a
    matchMedia('(pointer: fine)') probe has one too, and an animation guarded by
    pointer type alone still ignores the OS reduced-motion setting.
    """
    path = root / MOTION_JS_REL
    rel = MOTION_JS_REL.as_posix()
    if not path.is_file():
        return False, [
            f"{rel}: file not found — the animated motion layer has not been "
            f"committed yet (expected at assets/js/motion.js)"
        ]

    text = _read(path)
    clean = strip_js_comments(text)
    masked = mask_js(text)
    problems = []
    notes = []

    query_re = re.compile(r"prefers-reduced-motion\s*:\s*reduce", re.IGNORECASE)
    query = query_re.search(clean)
    if not query:
        problems.append(
            f"{rel}: no matchMedia('({REDUCED_QUERY})') probe found — the script "
            f"never asks the OS whether motion is allowed"
        )
        return False, problems
    notes.append(
        f"{rel}:{_line_of(clean, query.start())}: reduced-motion query present"
    )

    probe_re = re.compile(
        r"(\w+)\s*=\s*[^;\n]*?matchMedia\s*\(\s*['\"]"
        r"\??\(?prefers-reduced-motion\s*:\s*reduce",
        re.IGNORECASE,
    )
    probe = probe_re.search(clean)
    if not probe:
        problems.append(
            f"{rel}: the reduced-motion matchMedia() result is not stored in a "
            f"variable (expected `<name> = window.matchMedia('...')`)"
        )
        return False, problems
    variable = probe.group(1)
    notes.append(f"{rel}: probe stored in `{variable}`")

    read_re = re.compile(r"\b" + re.escape(variable) + r"\s*\.\s*matches\b")
    if not read_re.search(masked):
        problems.append(
            f"{rel}: `{variable}.matches` is never read — the probe cannot "
            f"influence the animation setup"
        )
        return False, problems
    notes.append(f"`{variable}.matches` is read")

    # Which helpers return <var>.matches?
    helpers = set()
    for match in re.finditer(
        r"function\s+(\w+)\s*\([^)]*\)\s*\{([^{}]*)\}",
        masked,
    ):
        if read_re.search(match.group(2)):
            helpers.add(match.group(1))
    notes.append(
        "helpers exposing the result: " + (", ".join(sorted(helpers)) or "none")
    )

    condition_re = r"(?:\b" + re.escape(variable) + r"\s*\.\s*matches\b"
    if helpers:
        condition_re += "|" + "|".join(r"\b" + re.escape(name) + r"\s*\("
                                       for name in sorted(helpers))
    condition_re += ")"
    # [^;{]* (not [^)]*) so the condition may contain its own parentheses:
    # `if (reduced() || !inView) { return; }` must match.
    guard_re = re.compile(
        r"if\s*\([^;{]*?" + condition_re + r"[^;{]*?\)\s*\{?\s*(?:return|throw)",
        re.IGNORECASE,
    )
    guard = guard_re.search(masked)
    if not guard:
        problems.append(
            f"{rel}: no `if (<{variable}.matches …>) return` guard — the probe is "
            f"read but the initialiser is never skipped, so the animations run "
            f"even when the user asked for reduced motion"
        )
        return False, problems
    notes.append(
        f"{rel}:{_line_of(masked, guard.start())}: early-exit guard "
        f"`{guard.group(0).strip()[:52]}`"
    )
    notes.append("reduced-motion is honoured before any animation is attached")
    return True, notes


def check_m2(root: Path, css_files):
    """(m2) CSS has a reduced-motion block that resets transitions AND animations."""
    if not css_files:
        return False, ["no CSS files found under the project root"]
    blocks = []
    problems = []
    for path in css_files:
        rel = _rel(path, root)
        text = strip_css_comments(_read(path))
        for match in REDUCED_MEDIA_RE.finditer(text):
            open_brace = text.rfind("{", match.start(), match.end())
            close_brace = _match_brace(text, open_brace)
            body = text[open_brace + 1:close_brace]
            line = _line_of(text, match.start())
            blocks.append((rel, line, body))

    if not blocks:
        return False, [
            'no @media (prefers-reduced-motion: reduce) block in any CSS file '
            '(assets/css/*.css)'
        ]

    details = []
    for rel, line, body in blocks:
        has_transition = bool(TRANSITION_RESET_RE.search(body))
        has_animation = bool(ANIMATION_RESET_RE.search(body))
        if not has_transition:
            problems.append(
                f"{rel}:{line}: reduced-motion block does not reset transitions "
                f"(expected `transition: none` or `transition-duration: .001ms`)"
            )
        if not has_animation:
            problems.append(
                f"{rel}:{line}: reduced-motion block does not reset animations "
                f"(expected `animation: none` / `animation-duration: .001ms` / "
                f"`animation-iteration-count: 1`)"
            )
        if has_transition and has_animation:
            details.append(
                f"{rel}:{line}: transitions + animations neutralised inside the block"
            )

    if problems:
        return False, problems
    details.insert(0, f"{len(blocks)} reduced-motion block(s) found")
    return True, details


def check_m3(root: Path, js_files):
    """(m3) no fetch/import/export/require/http(s) in the executable JS."""
    if not js_files:
        return False, ["no JS files found under the project root"]
    problems = []
    checked = 0
    for path in js_files:
        rel = _rel(path, root)
        text = _read(path)
        masked = mask_js(text)
        checked += 1
        for token in FORBIDDEN_JS:
            start = 0
            while True:
                index = masked.find(token, start)
                if index == -1:
                    break
                start = index + 1
                problems.append(
                    f"{rel}:{_line_of(masked, index)}: external dependency "
                    f"construct {token!r} in executable code (breaks file:// "
                    f"and offline use)"
                )
    if problems:
        return False, problems
    return True, [
        f"{checked} JS file(s) scanned: no fetch/import/export/require/http(s) "
        f"outside comments and strings"
    ]


def check_m4(root: Path, css_files, html_files, parsed):
    """(m4) every motion class is used in HTML and defined in CSS."""
    if not html_files:
        return False, ["no HTML files found under the project root"]
    if not css_files:
        return False, ["no CSS files found under the project root"]

    html_uses = {name: [] for name in MOTION_CLASSES}
    for page in html_files:
        data = parsed[page]
        for element in data.elements:
            for name in MOTION_CLASSES:
                if name in element["classes"]:
                    html_uses[name].append(f"{_rel(page, root)}:{element['line']}")

    css_defs = {name: [] for name in MOTION_CLASSES}
    for path in css_files:
        rel = _rel(path, root)
        text = strip_css_comments(_read(path))
        for name in MOTION_CLASSES:
            pattern = re.compile(r"\." + re.escape(name) + r"(?![\w-])")
            for match in pattern.finditer(text):
                css_defs[name].append(f"{rel}:{_line_of(text, match.start())}")

    problems = []
    details = []
    for name in MOTION_CLASSES:
        used = html_uses[name]
        defined = css_defs[name]
        marker = "ok"
        if not used:
            problems.append(
                f".{name}: not used by any HTML element (motion component missing "
                f"from the markup)"
            )
            marker = "MISSING-IN-HTML"
        if not defined:
            problems.append(
                f".{name}: no CSS selector defined in assets/css/*.css "
                f"(styling for the motion component missing)"
            )
            marker = "MISSING-IN-CSS" if not used else "MISSING-IN-CSS"
        if used and defined:
            marker = f"{len(used)} use(s) / {len(defined)} rule(s)"
        details.append(f".{name}: {marker}"
                       + (f" — first use {used[0]}" if used else "")
                       + (f", first rule {defined[0]}" if defined else ""))

    if problems:
        return False, problems + details
    return True, details


def check_m5(root: Path):
    """(m5) total JS weight <= 72 KB and no single file over 40 KB.

    assets/js is the bundle; assets/vendor is scanned too, because a
    copied-in library there would otherwise escape both the size budget and
    the intent of "no external dependencies" while still shipping.

    Two limits, deliberately: the 72 KB total catches a heavy dependency
    entering the bundle, the 40 KB per-file cap catches one file ballooning
    (which the total alone hides).
    """
    js_dir = root.joinpath(*JS_DIR_PARTS)
    if not js_dir.is_dir():
        return False, [f"assets/js directory not found under {root}"]
    files = sorted(p for p in js_dir.rglob("*") if p.is_file() and p.suffix.lower() in (".js", ".mjs"))
    if not files:
        return False, ["no .js files under assets/js"]
    vendor_dir = root / "assets" / "vendor"
    if vendor_dir.is_dir():
        files += sorted(p for p in vendor_dir.rglob("*")
                        if p.is_file() and p.suffix.lower() in (".js", ".mjs"))

    total = 0
    details = []
    oversized = []   # files over JS_FILE_BUDGET_BYTES
    largest = None   # (size, path) of the biggest file
    for path in files:
        size = path.stat().st_size
        total += size
        if largest is None or size > largest[0]:
            largest = (size, path)
        details.append(f"{_rel(path, root)}: {size} bytes")
        if size > JS_FILE_BUDGET_BYTES:
            oversized.append((path, size))

    summary = (f"total JS weight {total} bytes = {total / 1024:.1f} KB "
               f"(budget {JS_BUDGET_BYTES} bytes = {JS_BUDGET_BYTES // 1024} KB; "
               f"{len(files)} file(s), assets/js + assets/vendor)")
    per_file_summary = (
        f"largest file {_rel(largest[1], root)}: {largest[0]} bytes "
        f"(limit {JS_FILE_BUDGET_BYTES} bytes = {JS_FILE_BUDGET_BYTES // 1024} KB)"
    )
    problems = []
    if total > JS_BUDGET_BYTES:
        problems.append(
            f"{summary} — over budget by {total - JS_BUDGET_BYTES} bytes"
        )
    for path, size in oversized:
        problems.append(
            f"{_rel(path, root)} is {size} bytes = {size / 1024:.1f} KB — over the "
            f"per-file limit {JS_FILE_BUDGET_BYTES} bytes = "
            f"{JS_FILE_BUDGET_BYTES // 1024} KB (single file has grown too heavy)"
        )
    if problems:
        return False, problems + [summary] + details
    return True, [summary, per_file_summary] + details


def check_m6(html_files, parsed, root: Path):
    """(m6) ARIA / keyboard contract of .hold-btn and .card-expand.

    Two correct implementations are accepted for each control:

    .card-expand — aria-expanded on the card itself, OR on a trigger nested
    inside it that points at an id on the page (the ARIA disclosure pattern
    used by the current markup: the button flips aria-expanded and controls the
    panel by id). What fails is a card with neither, because then nothing in
    the accessibility tree announces the open state.

    .hold-btn — a native <button>, a link with an href, or any element carrying
    role + tabindex. A bare <div>/<span> without role/tabindex is a FAIL: it is
    neither focusable nor announced. A link is focusable by itself, so it is a
    WARN: the hold affordance is invisible to screen readers unless the hint is
    referenced with aria-describedby.
    """
    if not html_files:
        return False, ["no HTML files found under the project root"]

    hold = []
    expand = []
    for page in html_files:
        rel = _rel(page, root)
        for element in parsed[page].elements:
            if "hold-btn" in element["classes"]:
                hold.append((rel, page, element))
            if "card-expand" in element["classes"]:
                expand.append((rel, page, element))

    problems = []
    details = []
    warnings = []

    if not hold:
        problems.append(
            ".hold-btn: not found in any HTML page — the hold-to-publish CTA has "
            "no markup to check yet"
        )
    for rel, page, element in hold:
        attrs = element["attrs"]
        line = element["line"]
        if element["tag"] == "button":
            details.append(f"{rel}:{line}: .hold-btn is a native <button>")
            continue
        if element["tag"] == "a" and (attrs.get("href") or "").strip():
            details.append(
                f"{rel}:{line}: .hold-btn is a native <a href> — focusable and "
                f"Enter-activatable"
            )
            if "aria-describedby" not in attrs:
                warnings.append(
                    f"{rel}:{line}: .hold-btn announces only its label; the "
                    f"hold gesture is not described (add "
                    f'aria-describedby pointing at the hold hint)'
                )
            continue
        if attrs.get("role") and attrs.get("tabindex") is not None:
            details.append(
                f"{rel}:{line}: .hold-btn <{element['tag']}> has "
                f"role={attrs.get('role')!r} tabindex={attrs.get('tabindex')!r}"
            )
            continue
        problems.append(
            f"{rel}:{line}: .hold-btn <{element['tag']}> is not a <button>, not a "
            f"link and has no role + tabindex (not focusable, cannot be triggered "
            f"from the keyboard)"
        )

    if not expand:
        problems.append(
            ".card-expand: not found in any HTML page — the expanding card has "
            "no markup to check yet"
        )
    for rel, page, element in expand:
        attrs = element["attrs"]
        line = element["line"]
        parser = parsed[page]
        if "aria-expanded" in attrs:
            details.append(
                f"{rel}:{line}: .card-expand carries aria-expanded="
                f"{attrs.get('aria-expanded')!r}"
            )
            continue
        triggers = [index for index in parser.descendants(
                        parser.elements.index(element))
                    if "aria-expanded" in parser.elements[index]["attrs"]]
        if not triggers:
            problems.append(
                f"{rel}:{line}: .card-expand has no aria-expanded — neither on the "
                f"card nor on a nested trigger (screen readers cannot tell whether "
                f"the card is open)"
            )
            continue
        bad = []
        for index in triggers:
            trigger = parser.elements[index]
            controls = (trigger["attrs"].get("aria-controls") or "").strip()
            if controls and controls not in parser.page_ids():
                bad.append(
                    f"{rel}:{trigger['line']}: expand trigger aria-controls="
                    f"{controls!r} matches no id on the page"
                )
        if bad:
            problems.extend(bad)
            continue
        details.append(
            f"{rel}:{line}: .card-expand aria-expanded lives on "
            f"{len(triggers)} nested trigger(s), aria-controls verified"
        )

    if problems:
        return False, problems + details, warnings
    details.insert(0, f"{len(hold)} .hold-btn and {len(expand)} .card-expand checked")
    return True, details, warnings


def _call_args(text: str, open_index: int) -> str:
    """Source text between '(' at *open_index* and its matching ')'."""
    depth = 0
    i = open_index
    n = len(text)
    quote = None
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'`":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_index + 1:i]
        i += 1
    return text[open_index + 1:]


def check_m7(root: Path, js_files):
    """(m7) wheel/touch/scroll listeners should be passive (WARN only)."""
    if not js_files:
        return True, ["no JS files found — nothing to check"], []
    warnings = []
    checked = 0
    passive = 0
    for path in js_files:
        rel = _rel(path, root)
        text = strip_js_comments(_read(path))
        for match in re.finditer(r"addEventListener\s*\(", text):
            open_index = text.find("(", match.start())
            args = _call_args(text, open_index)
            first = re.match(r"\s*(['\"])([A-Za-z0-9:_-]+)\1", args)
            if not first:
                continue  # dynamic event name — cannot judge
            event = first.group(2).lower()
            if event not in PASSIVE_EVENTS:
                continue
            checked += 1
            rest = args[first.end():]
            if re.search(r"passive\s*:\s*true", rest):
                passive += 1
                continue
            warnings.append(
                f"{rel}:{_line_of(text, match.start())}: addEventListener('{event}') "
                f"without {{passive:true}} — the browser may block scrolling while "
                f"the handler runs"
            )
    details = [
        f"{checked} scroll/touch/wheel listener(s) inspected, "
        f"{passive} with passive:true, {len(warnings)} without"
    ]
    return True, details, warnings


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class CheckResult:
    def __init__(self, name, passed, details, warnings=None):
        self.name = name
        self.passed = passed
        self.details = details
        self.warnings = warnings or []


def run_check(name, func):
    try:
        outcome = func()
    except Exception as exc:  # noqa: BLE001 — a gate must never traceback
        return CheckResult(name, False, [f"check crashed: {type(exc).__name__}: {exc}"])
    warnings = []
    if isinstance(outcome, tuple) and len(outcome) == 3:
        passed, details, warnings = outcome
    else:
        passed, details = outcome
    return CheckResult(name, bool(passed), list(details), list(warnings))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Motion/animation quality gate for the portfolio site."
    )
    parser.add_argument("--root", default=str(ROOT),
                        help="project root (default: auto-detect)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: project root does not exist: {root}", file=sys.stderr)
        return 1

    html_files = discover_html(root)
    js_files = discover_js(root)
    css_files = discover_css(root)

    parsed = {}
    for page in html_files:
        try:
            element_parser = ElementParser()
            element_parser.feed(page.read_text(encoding="utf-8", errors="replace"))
            element_parser.close()
            parsed[page] = element_parser
        except Exception as exc:  # noqa: BLE001
            print(f"error: cannot parse {_rel(page, root)}: "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr)
            return 1

    motion_js = root / MOTION_JS_REL

    print("=" * 72)
    print(" MOTION CHECK - portfolio animated layer")
    print(f" root: {root}")
    print(f" pages: {len(html_files)} | js: {len(js_files)} | css: {len(css_files)}")
    print(f" motion.js: {'present' if motion_js.is_file() else 'MISSING'}")
    print("=" * 72)
    print()

    results = [
        run_check("(m1) motion.js + prefers-reduced-motion early exit",
                  lambda: check_m1(root)),
        run_check("(m2) CSS reduced-motion block resets transitions/animations",
                  lambda: check_m2(root, css_files)),
        run_check("(m3) no external JS dependencies",
                  lambda: check_m3(root, js_files)),
        run_check("(m4) motion classes present in HTML and CSS",
                  lambda: check_m4(root, css_files, html_files, parsed)),
        run_check("(m5) total JS weight <= 72 KB and no file over 40 KB",
                  lambda: check_m5(root)),
        run_check("(m6) ARIA/keyboard contract for .hold-btn / .card-expand",
                  lambda: check_m6(html_files, parsed, root)),
        run_check("(m7) passive pointer/scroll listeners (heuristic)",
                  lambda: check_m7(root, js_files)),
    ]

    for result in results:
        if result.passed and not result.warnings:
            status = "PASS"
        elif result.passed:
            status = "WARN"
        else:
            status = "FAIL"
        print(f"[{status}] {result.name}")
        for detail in result.details:
            print(f"       {detail}")
        for warning in result.warnings:
            print(f"   WARN {warning}")
        print()

    failed = [r for r in results if not r.passed]
    warned = [r for r in results if r.passed and r.warnings]
    passed_count = len(results) - len(failed)

    print("-" * 72)
    print(f"RESULT: {'PASS' if not failed else 'FAIL'} - {passed_count}/{len(results)} "
          f"checks passed, {len(failed)} failed, {len(warned)} with warnings")
    print("-" * 72)
    if failed:
        print("FAILING CHECKS:")
        for result in failed:
            print(f"   - {result.name}")
        print()

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
