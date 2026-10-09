import re
from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parent.parent / "config" / "filters.yml"
RULES = yaml.safe_load(CONFIG.read_text())


def _lower(values: list[str]) -> list[str]:
    return [v.lower() for v in values]


EXCLUDE_COUNTRIES = _lower(RULES["location"]["exclude_countries"])
US_SIGNALS = _lower(RULES["location"]["us_signals"])
EXCLUDE_SENIORITY = _lower(RULES["seniority"]["exclude_patterns"])
INCLUDE_FUNCTION = _lower(RULES["function"]["include_patterns"])
EXCLUDE_FUNCTION = _lower(RULES["function"]["exclude_patterns"])


# Countries that must be excluded even when no city is named:
# "Canada - Remote" and "Remote - Luxembourg" name no city, so the
# city-based exclusion list never fires on them.
FOREIGN_COUNTRY_RE = re.compile(
    r"\b(canada|luxembourg|ireland|united kingdom|uk|germany|france|"
    r"netherlands|india|israel|australia|japan|singapore|brazil|mexico|"
    r"spain|poland|portugal|switzerland|sweden|taiwan|china|korea|"
    r"philippines|indonesia|thailand|vietnam|colombia|argentina|chile|"
    r"emea|apac|latam)\b",
    re.IGNORECASE,
)


def location_verdict(location_raw: str) -> tuple[bool, str]:
    """
    US-eligible unless the location names only foreign places.
    A US signal anywhere wins, because multi-location postings are common.
    """
    text = (location_raw or "").lower()

    if not text:
        return True, "no location given — kept for review"

    # A foreign-only posting is excluded even when a US signal appears
    # nowhere; multi-location roles still pass on their US signal below.
    foreign = FOREIGN_COUNTRY_RE.search(text)

    # Strong US signals: an explicit country or city reference.
    # Checked separately from state suffixes because Canadian province
    # codes collide with US state codes � "(ON, AB, BC, or NS Only)"
    # matched ", NS" and bypassed the Canada exclusion.
    strong_us = any(
        signal in text for signal in US_SIGNALS if not signal.startswith(", ")
    )
    weak_us = any(
        signal in text for signal in US_SIGNALS if signal.startswith(", ")
    )

    # An explicitly named foreign country outweighs a two-letter suffix.
    if foreign and not strong_us:
        return False, f"foreign country: '{foreign.group(0).lower()}'"

    if strong_us or weak_us:
        return True, "us signal present"

    if any(country in text for country in EXCLUDE_COUNTRIES):
        return False, "foreign location, no US signal"

    return True, "unrecognized — kept for review"


# Seniority tokens must match whole words. Plain substring matching
# drops "Account Executive" on "iv" and "Archive" on "iv" � the kind of
# silent over-filtering that is invisible until you read the drop list.
SENIORITY_RE = [
    (p, re.compile(rf"\b{re.escape(p)}\b", re.IGNORECASE))
    for p in EXCLUDE_SENIORITY
]


def seniority_verdict(title: str) -> tuple[bool, str]:
    text = title or ""
    for pattern, regex in SENIORITY_RE:
        if regex.search(text):
            return False, f"seniority: '{pattern}'"
    return True, "within band"


def function_verdict(title: str) -> tuple[bool, str]:
    """
    Excludes run first. An include keyword alone is not sufficient:
    "Account Executive, AI Sales" matched the AI include and passed
    until non-engineering functions were excluded explicitly.
    """
    text = (title or "").lower()

    for pattern in EXCLUDE_FUNCTION:
        if pattern in text:
            return False, f"excluded function: '{pattern}'"

    for pattern in INCLUDE_FUNCTION:
        if pattern in text:
            return True, f"function: '{pattern}'"

    return False, "no matching function"


def evaluate(title: str, location_raw: str,
             description: str | None = None) -> tuple[bool, list[str]]:
    reasons = []
    eligible = True

    for ok, reason in (
        location_verdict(location_raw),
        seniority_verdict(title),
        function_verdict(title),
        description_verdict(description),
    ):
        reasons.append(reason)
        if not ok:
            eligible = False

    return eligible, reasons

EXCLUDE_DESCRIPTION = _lower(RULES["description"]["exclude_patterns"])


def description_verdict(description: str | None) -> tuple[bool, str]:
    """
    Hard blockers in the description body.

    Citizenship, clearance and no-sponsorship statements rarely appear in
    a title or location, so they survive every title-based rule. They are
    absolute: no score makes such a role applyable.
    """
    text = (description or "").lower()
    if not text:
        return True, "no description — kept for review"

    for pattern in EXCLUDE_DESCRIPTION:
        if pattern in text:
            return False, f"blocker: '{pattern}'"

    return True, "no blockers"