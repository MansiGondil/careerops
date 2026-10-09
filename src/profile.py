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


def _split_by_heading(text: str, prefix: str) -> dict[str, str]:
    """
    Split a file into one section per '## ' heading.

    experience.md is ~6,600 characters against a ~2,000-character model
    window, so embedding it whole silently discarded everything after the
    first two roles — including three years of Accenture DevOps and SRE
    work, which is the strongest match for platform and infrastructure
    roles. One vector per role fixes that and makes the breakdown name
    which role matched.
    """
    sections = {}
    current_name = None
    current_lines: list[str] = []

    for line in text.split("\n"):
        if line.startswith("## "):
            if current_name and current_lines:
                sections[f"{prefix}:{current_name}"] = "\n".join(current_lines).strip()
            current_name = line[3:].strip()
            current_lines = [line]
        elif current_name:
            current_lines.append(line)

    if current_name and current_lines:
        sections[f"{prefix}:{current_name}"] = "\n".join(current_lines).strip()

    return sections


def load_sections() -> dict[str, str]:
    """
    Profile as embeddable sections.

    Short files embed whole. Long ones are split per heading so no content
    falls outside the model's input window.
    """
    SPLIT_FILES = {"experience.md", "projects.md"}
    sections: dict[str, str] = {}

    for name in FILES:
        path = PROFILE_DIR / name
        if not path.exists():
            continue

        content = _strip_commentary(path.read_text(encoding="utf-8"))
        if not content:
            continue

        if name in SPLIT_FILES:
            sections.update(_split_by_heading(content, path.stem))
        else:
            sections[path.stem] = content

    if not sections:
        raise FileNotFoundError(f"no profile files found in {PROFILE_DIR}")
    return sections