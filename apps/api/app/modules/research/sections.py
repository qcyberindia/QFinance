"""Canonical Research workspace section registry — the backend mirror of
`apps/web/lib/research-progress.ts`'s `SECTIONS` array, which is the one
place section numbers/keys/fields are actually defined for the UI. This file
does not duplicate that list arbitrarily: it exists because `ai_context.py`
needs the SAME ordering server-side (for `current_stage`/`next_stage`), and
`research/service.py`'s add-to-research path needs the SAME key->field
mapping to validate an incoming `stage` string against a real, addressable
column — there is nowhere in the existing Python code that already has this;
`research/models.py`'s `QRES_STAGE_FIELDS` is NOT it (confirmed by
inspection: it includes `business_quality`, a column the frontend never
binds to any section at all, and it omits the Section 01 field entirely).

Keep this in sync with research-progress.ts by hand — there is no shared
codegen between the two apps in this repository. `key`/`n`/`field` here match
that file's `key`/`n`/`field` exactly, for every section in this list.

Section 01 (Research Question), 11 (Investment Thesis, derived), and 13
(Review, derived) are deliberately NOT included as an addable AI target:
Section 01 is the researcher's own starting question, not a research
finding; 11/13 have no field of their own (`field: null` in
research-progress.ts) — they are computed summaries, so nothing could be
"added to" them.

Section 09 (Bull / Base / Bear) is included for progress/stage-ordering
purposes but is NOT an ADD_TO_RESEARCH_STAGES target in this pass: it maps
to three separate columns (bull_case/base_case/bear_case) and there is no
reliable way to infer which scenario an AI answer belongs to. Reported as an
explicit limitation, not silently guessed at.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SectionDef:
    n: str
    key: str
    label: str
    field: str | None  # None for derived sections (thesis, review)


# Mirrors research-progress.ts's SECTIONS, in the same order.
SECTIONS: tuple[SectionDef, ...] = (
    SectionDef("01", "question", "Research Question", "summary"),
    SectionDef("02", "business", "Business", "business_model"),
    SectionDef("03", "industry", "Industry & Competition", "competitive_position"),
    SectionDef("04", "financials", "Financial Health", "financial_snapshot"),
    SectionDef("05", "growth", "Growth", "catalysts"),
    SectionDef("06", "management", "Management", "management_notes"),
    SectionDef("07", "forecast", "Assumptions & Outlook", "assumptions_outlook"),
    SectionDef("08", "valuation", "Valuation", "valuation_range"),
    SectionDef("09", "scenarios", "Bull / Base / Bear", "bull_case"),  # see module docstring: not an add-to-research target
    SectionDef("10", "risks", "Risks", "risk_register"),
    SectionDef("11", "thesis", "Investment Thesis", None),  # derived
    SectionDef("12", "invalidation", "Prove Me Wrong", "invalidation_conditions"),
    SectionDef("13", "review", "Review", None),  # derived
)

# Stages an AI answer can actually be saved into this pass (excludes
# question/thesis/review/scenarios — see module docstring for each).
ADD_TO_RESEARCH_STAGES: dict[str, str] = {
    s.key: s.field for s in SECTIONS if s.field is not None and s.key not in ("question", "scenarios")
}

_PROGRESS_ORDER: tuple[SectionDef, ...] = tuple(s for s in SECTIONS if s.key != "question")


def is_section_filled(research, section: SectionDef) -> bool:
    if section.key == "scenarios":
        return all(bool(getattr(research, f) and getattr(research, f).strip())
                   for f in ("bull_case", "base_case", "bear_case"))
    if section.field is None:
        return False  # derived sections never count on their own — matches research-progress.ts
    value = getattr(research, section.field)
    return bool(value) and value.strip() != ""


def current_stage_key(research) -> str:
    """First not-yet-filled section (Section 02 onward), or 'review' once
    every addressable section is filled. Matches isSectionFilled's ordering
    exactly, so this can never disagree with the progress bar the user sees."""
    for section in _PROGRESS_ORDER:
        if section.key in ("thesis", "review"):
            continue
        if not is_section_filled(research, section):
            return section.key
    return "review"


def next_stage_key(current_key: str) -> str | None:
    keys = [s.key for s in _PROGRESS_ORDER if s.key not in ("thesis",)]
    try:
        idx = keys.index(current_key)
    except ValueError:
        return None
    return keys[idx + 1] if idx + 1 < len(keys) else None


def section_by_key(key: str) -> SectionDef | None:
    return next((s for s in SECTIONS if s.key == key), None)
