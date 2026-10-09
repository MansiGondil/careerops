"""
Load and embed the candidate profile.

The profile lives in profile/ as plain markdown: hand-edited, user-versioned,
and small enough to re-read per run.

Each file is embedded separately rather than concatenated. The model reads
only ~2,000 characters, and the full profile is ~13,000 — one vector would
discard most of it. Separate vectors also keep distinct questions distinct:
"can I do this job" and "do I want it" are not the same similarity.
"""

from pathlib import Path

PROFILE_DIR = Path(__file__).resolve().parent.parent / "profile"

FILES = ["preferences.md", "skills.md", "experience.md", "projects.md"]


def _strip_commentary(text: str) -> str:
    """
    Drop the explanatory preamble above the first section heading.

    Those notes are instructions to the reader about how to maintain the
    file. Embedding them adds words about editing files to a vector that
    should describe a candidate.
    """
    marker = "\n## "
    index = text.find(marker)
    return text[index:].strip() if index != -1 else text.strip()


def load_sections() -> dict[str, str]:
    """Each profile file as its own section, keyed by name without extension."""
    sections = {}
    for name in FILES:
        path = PROFILE_DIR / name
        if path.exists():
            content = _strip_commentary(path.read_text(encoding="utf-8"))
            if content:
                sections[path.stem] = content
    if not sections:
        raise FileNotFoundError(f"no profile files found in {PROFILE_DIR}")
    return sections