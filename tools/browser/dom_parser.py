"""
tools/browser/dom_parser.py — Converts raw HTML into a compact, token-efficient
interaction map that the LLM can reason about without hallucinating CSS cruft.

Output format (plain text):
  [INTERACTIVE ELEMENTS]
  #login-btn    BUTTON   "Sign In"
  #username     INPUT    type=text placeholder="admin"
  ...
  [PAGE TEXT]
  (clean visible text content)
"""
from __future__ import annotations

import re
from typing import Optional

try:
    from bs4 import BeautifulSoup, Tag
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False


_INTERACTIVE_TAGS = {"a", "button", "input", "select", "textarea", "form", "label"}
_SKIP_TAGS = {"script", "style", "meta", "link", "head", "noscript", "svg", "path"}


def parse_dom(html: str, max_interactive: int = 60, max_text_chars: int = 1500) -> str:
    """
    Parses raw HTML and returns a compact, structured text representation.

    Args:
        html:              Raw HTML string from the browser.
        max_interactive:   Maximum number of interactive elements to include.
        max_text_chars:    Maximum characters of visible page text to include.

    Returns:
        A multi-line string with [INTERACTIVE ELEMENTS] and [PAGE TEXT] sections.
    """
    if not _BS4_AVAILABLE:
        # Graceful degradation: strip tags and return raw text
        clean = re.sub(r"<[^>]+>", " ", html)
        return f"[PAGE TEXT]\n{' '.join(clean.split())[:max_text_chars]}"

    soup = BeautifulSoup(html, "lxml")

    # ── Remove noise ─────────────────────────────────────────────────────────
    for tag in soup.find_all(_SKIP_TAGS):
        tag.decompose()

    # ── Extract interactive elements ──────────────────────────────────────────
    interactive_lines: list[str] = []
    seen_ids: set[str] = set()

    for el in soup.find_all(_INTERACTIVE_TAGS):
        if not isinstance(el, Tag):
            continue

        el_id = el.get("id", "")
        el_name = el.get("name", "")
        el_type = el.name.upper()

        # Build a selector
        if el_id:
            selector = f"#{el_id}"
        elif el_name:
            selector = f"[name={el_name!r}]"
        else:
            selector = el_type.lower()

        if selector in seen_ids:
            continue
        seen_ids.add(selector)

        # Build attributes summary
        attrs: list[str] = []
        if el.name == "input":
            inp_type = el.get("type", "text")
            attrs.append(f"type={inp_type}")
            if ph := el.get("placeholder"):
                attrs.append(f'placeholder="{ph}"')
            if el.get("required"):
                attrs.append("required")
        elif el.name == "select":
            options = [o.get_text(strip=True) for o in el.find_all("option")][:5]
            attrs.append(f"options=[{', '.join(options)}]")
        elif el.name == "a":
            if href := el.get("href"):
                attrs.append(f'href="{href}"')
        elif el.name == "button":
            if btn_type := el.get("type"):
                attrs.append(f"type={btn_type}")

        label_text = el.get_text(strip=True)[:60] or el.get("value", "")[:60]
        attr_str = "  " + "  ".join(attrs) if attrs else ""
        line = f"{selector:<30} {el_type:<10} \"{label_text}\"{attr_str}"
        interactive_lines.append(line)

        if len(interactive_lines) >= max_interactive:
            break

    # ── Extract visible text ──────────────────────────────────────────────────
    raw_text = soup.get_text(separator=" ", strip=True)
    # Collapse whitespace
    clean_text = " ".join(raw_text.split())[:max_text_chars]

    # ── Assemble output ───────────────────────────────────────────────────────
    sections: list[str] = []
    if interactive_lines:
        sections.append("[INTERACTIVE ELEMENTS]")
        sections.extend(interactive_lines)
    if clean_text:
        sections.append("[PAGE TEXT]")
        sections.append(clean_text)

    return "\n".join(sections) if sections else "(empty page)"
