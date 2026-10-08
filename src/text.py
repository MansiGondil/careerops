"""Text normalization helpers for job descriptions."""

import html as html_module
from bs4 import BeautifulSoup


def strip_html(html: str | None) -> str:
    """
    Convert HTML job-description markup into clean plain text.

    Job feeds return descriptions as HTML fragments — nested divs, <li>
    bullets, <p> wrappers. Embedding models want plain text, and the tags
    are pure noise, so they are discarded here rather than downstream.

    A newline separator matters: without it, get_text() runs adjacent
    list items together ("Build Kotlin codeCollaborate with teams").
    """
    if not html:
        return ""

    # Greenhouse returns content HTML-escaped (&lt;div&gt; rather than
    # <div>), so unescaping must happen before parsing — otherwise
    # BeautifulSoup sees no tags and returns the markup as plain text.
    soup = BeautifulSoup(html_module.unescape(html), "html.parser")
    text = soup.get_text(separator="\n")

    # get_text leaves long runs of blank lines where the markup was
    # indented. Collapse them so the stored text stays compact.
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def join_sections(*parts: str | None) -> str:
    """
    Combine description fragments into one block, skipping empties.

    Lever splits a posting across descriptionPlain (team/mission prose)
    and a `lists` field holding the actual requirements as HTML. Scoring
    needs both: the mission text alone carries little signal about what
    the role requires.
    """
    cleaned = [p.strip() for p in parts if p and p.strip()]
    return "\n\n".join(cleaned)
