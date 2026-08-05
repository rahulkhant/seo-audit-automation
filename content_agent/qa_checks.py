"""
Content Agent, QA Checker step: deterministic checks + scoring.

Purpose of this file
--------------------
Everything in this file is plain Python -- no LLM call, no judgment,
fully reproducible for the same draft. This is deliberately the bulk of
the QA Checker's report: word count, keyword coverage, keyword density,
readability, sentence complexity, passive voice, and banned-phrase hits
are all things a script can measure directly from the text.

The one piece this file does NOT produce is the judgment half -- "does
this actually read naturally / match our voice" isn't something a formula
can answer, so that comes from the Writer... no, the QA Checker skill
conversation itself (see .claude/skills/blog-qa/SKILL.md), which adds a
small score adjustment and a short qualitative note on top of everything
computed here.

A note on the scoring math
---------------------------
The point deductions below are a reasonable starting point, explicitly
NOT final -- Rahul said (2026-08-05) he wants to research scoring
approaches properly and update this later. Every deduction is itemized
and explained in the report rather than folded into an opaque number, so
it stays easy to see exactly why a draft scored what it scored, and easy
to adjust any one number without touching the others.

Readability/complexity/passive-voice detection here are heuristics, not
a real grammatical parse (no NLP library dependency) -- good enough to
flag real problems, not precise enough to treat as ground truth on their
own. Worth keeping in mind when reading a report that leans heavily on
one of these three.
"""

import re

from content_agent.banned_phrases import find_banned_phrases

_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+(?:\s|$)")
_VOWEL_GROUPS_RE = re.compile(r"[aeiouy]+")

# Common irregular past participles, since not every passive construction
# ends in "-ed" ("the account was suspended" vs "the item was sold").
# Not exhaustive -- a heuristic, see module docstring.
_IRREGULAR_PARTICIPLES = (
    "born|built|bought|brought|caught|chosen|done|drawn|driven|eaten|"
    "fallen|felt|found|given|gone|held|kept|known|left|lost|made|meant|"
    "met|paid|put|read|said|seen|sent|shown|shut|sold|spoken|spent|"
    "taken|taught|told|thought|understood|written"
)
_PASSIVE_RE = re.compile(
    rf"\b(is|are|was|were|be|been|being)\s+(\w+ed|{_IRREGULAR_PARTICIPLES})\b",
    re.IGNORECASE,
)


def _full_text(draft):
    return " ".join(section["content"] for section in draft["sections"])


def _split_sentences(text):
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def _count_syllables(word):
    """Vowel-group counting -- the standard cheap approximation, not a
    dictionary lookup. Good enough for an aggregate readability score
    across hundreds of words; not meant to be exact for any one word."""
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0
    count = len(_VOWEL_GROUPS_RE.findall(word))
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


# --- Individual checks ---

def check_word_count(brief, draft):
    target = brief["target_word_count"]
    actual = sum(section["word_count"] for section in draft["sections"])
    deviation_pct = round(abs(actual - target) / target * 100, 1) if target else 0.0

    # Section-level deviations are reported for visibility but don't
    # individually affect the score -- only the total does. Flagging
    # every section that's a little off would just be noise.
    notable_section_deviations = []
    for brief_section, draft_section in zip(brief["sections"], draft["sections"]):
        budget = brief_section["word_budget"]
        if not budget:
            continue
        section_actual = draft_section["word_count"]
        section_deviation = round(abs(section_actual - budget) / budget * 100, 1)
        if section_deviation > 40:
            notable_section_deviations.append({
                "section": brief_section["heading"] or brief_section["level"],
                "budget": budget,
                "actual": section_actual,
                "deviation_pct": section_deviation,
            })

    return {
        "target": target,
        "actual": actual,
        "deviation_pct": deviation_pct,
        "notable_section_deviations": notable_section_deviations,
    }


def check_keyword_coverage(brief, draft):
    """
    Intro/conclusion detection uses POSITION (first section / last section
    in the list), not the section's "level" field -- a brief with an
    explicit Rahul-authored heading like "Conclusion" stores that section
    with level "H2" (its real heading level), not the synthetic "conclusion"
    sentinel the word-budget allocator uses for unheaded slots. Matching on
    level alone silently missed every brief that has a real, named
    conclusion/intro heading, which is a real and fairly common case (found
    via testing against the actual Google Merchant Center brief -- its
    "Conclusion" H2 wasn't being detected as the conclusion at all).
    """
    primary = brief["primary_keyword"].lower()
    section_keyword_misses = []
    primary_in_intro = False
    primary_in_conclusion = False
    primary_in_body = False

    paired_sections = list(zip(brief["sections"], draft["sections"]))
    last_index = len(paired_sections) - 1

    for index, (brief_section, draft_section) in enumerate(paired_sections):
        content_lower = draft_section["content"].lower()

        for keyword in brief_section.get("keywords") or []:
            if keyword.lower() not in content_lower:
                section_keyword_misses.append({
                    "section": brief_section["heading"] or brief_section["level"],
                    "keyword": keyword,
                })

        if primary in content_lower:
            if index == 0:
                primary_in_intro = True
            elif index == last_index:
                primary_in_conclusion = True
            else:
                primary_in_body = True

    return {
        "section_keyword_misses": section_keyword_misses,
        "primary_keyword_in_intro": primary_in_intro,
        "primary_keyword_in_conclusion": primary_in_conclusion,
        "primary_keyword_in_body_heading": primary_in_body,
    }


def check_keyword_density(brief, draft):
    full_text = _full_text(draft)
    total_words = len(full_text.split()) or 1
    primary_count = full_text.lower().count(brief["primary_keyword"].lower())
    return {
        "primary_keyword_count": primary_count,
        "total_words": total_words,
        "primary_density_pct": round(primary_count / total_words * 100, 2),
    }


def check_readability(draft):
    full_text = _full_text(draft)
    sentences = _split_sentences(full_text)
    words = full_text.split()
    total_sentences = len(sentences) or 1
    total_words = len(words) or 1
    total_syllables = sum(_count_syllables(word) for word in words)

    # Standard Flesch Reading Ease formula. Roughly: 90-100 very easy,
    # 60-70 plain English, 30-50 fairly difficult, below 30 very difficult.
    flesch_reading_ease = (
        206.835 - 1.015 * (total_words / total_sentences) - 84.6 * (total_syllables / total_words)
    )
    return {
        "flesch_reading_ease": round(flesch_reading_ease, 1),
        "total_sentences": total_sentences,
        "total_words": total_words,
    }


def check_sentence_complexity(draft):
    sentences = _split_sentences(_full_text(draft))
    lengths = [len(s.split()) for s in sentences]
    if not lengths:
        return {"avg_sentence_length": 0.0, "sentence_length_stdev": 0.0, "sentence_count": 0}

    avg = sum(lengths) / len(lengths)
    variance = sum((length - avg) ** 2 for length in lengths) / len(lengths)
    return {
        "avg_sentence_length": round(avg, 1),
        "sentence_length_stdev": round(variance ** 0.5, 1),
        "sentence_count": len(lengths),
    }


def check_passive_voice(draft):
    sentences = _split_sentences(_full_text(draft))
    total = len(sentences) or 1
    passive_count = sum(1 for sentence in sentences if _PASSIVE_RE.search(sentence))
    return {
        "passive_sentence_count": passive_count,
        "total_sentences": total,
        "percentage": round(passive_count / total * 100, 1),
    }


def check_banned_phrases(draft):
    return find_banned_phrases(_full_text(draft))


def run_deterministic_checks(brief, draft):
    """Everything computable without a model, bundled into one report."""
    return {
        "word_count": check_word_count(brief, draft),
        "keyword_coverage": check_keyword_coverage(brief, draft),
        "keyword_density": check_keyword_density(brief, draft),
        "readability": check_readability(draft),
        "sentence_complexity": check_sentence_complexity(draft),
        "passive_voice": check_passive_voice(draft),
        "banned_phrases": check_banned_phrases(draft),
    }


# --- Scoring: deterministic report + the skill's own judgment adjustment ---

def compute_score(deterministic, judgment_adjustment=0.0, judgment_notes=""):
    """
    Starts at 10, deducts a fixed amount per deterministic issue found
    (see module docstring re: this being a v1, not final, formula), then
    applies the QA Checker skill's own judgment_adjustment (a small
    positive or negative number reflecting tone/flow/naturalness -- not
    computable, the one genuinely judgment-based input here).
    """
    score = 10.0
    deductions = []

    word_count = deterministic["word_count"]
    if word_count["deviation_pct"] > 15:
        score -= 1.0
        deductions.append(
            f"Word count {word_count['actual']} vs. target {word_count['target']} "
            f"({word_count['deviation_pct']}% off) (-1.0)"
        )

    keyword_coverage = deterministic["keyword_coverage"]
    missing = keyword_coverage["section_keyword_misses"]
    if missing:
        penalty = min(0.5 * len(missing), 2.0)
        score -= penalty
        deductions.append(
            f"{len(missing)} section keyword(s) not found in their assigned section (-{penalty})"
        )
    if not (keyword_coverage["primary_keyword_in_intro"] and keyword_coverage["primary_keyword_in_conclusion"]):
        score -= 0.5
        deductions.append("Primary keyword missing from the intro or conclusion (-0.5)")

    density = deterministic["keyword_density"]
    if density["primary_density_pct"] > 2.5:
        score -= 1.0
        deductions.append(
            f"Primary keyword density {density['primary_density_pct']}% -- risk of reading as stuffed (-1.0)"
        )

    readability = deterministic["readability"]
    if readability["flesch_reading_ease"] < 20:
        score -= 1.0
        deductions.append(
            f"Flesch Reading Ease {readability['flesch_reading_ease']} -- very difficult to read (-1.0)"
        )

    passive = deterministic["passive_voice"]
    if passive["percentage"] > 25:
        score -= 1.0
        deductions.append(f"Passive voice in {passive['percentage']}% of sentences (-1.0)")

    banned = deterministic["banned_phrases"]
    if banned:
        total_hits = sum(banned.values())
        penalty = min(0.5 * total_hits, 2.0)
        score -= penalty
        phrase_list = ", ".join(f'"{phrase}" x{count}' for phrase, count in banned.items())
        deductions.append(f"Banned phrase(s) found: {phrase_list} (-{penalty})")

    score += judgment_adjustment
    score = max(0.0, min(10.0, score))

    return {
        "score": round(score, 1),
        "deductions": deductions,
        "judgment_adjustment": judgment_adjustment,
        "judgment_notes": judgment_notes,
    }
