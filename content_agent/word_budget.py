"""
Content Agent, Outliner step: word-budget allocation.

Purpose of this file
--------------------
Given a target total word count and a list of headings, works out how many
words each section should get -- the one piece of "what goes in the brief"
that doesn't need AI judgment at all, just arithmetic. Keeping it here as
plain, testable Python (rather than leaving it to the model's judgment
every time) means the same inputs always produce the same budget, and it's
easy to see exactly why a section got the number it got.

The rule (deliberately simple, not a content-structure heuristic)
-------------------------------------------------------------------
Every blog gets a fixed intro and conclusion allowance (10% of the total
each, by default) since those exist even when they're not their own
heading. Whatever's left is split evenly across every heading you provide,
regardless of whether it's an H2 or H3 -- no attempt is made to guess that
"H2s with H3 children need less direct prose" or similar; that's exactly
the kind of assumption worth adjusting once you've seen real output, not
guessing upfront. Any leftover words from rounding go to the first few
sections so the numbers always add up to the exact target.
"""

INTRO_FRACTION = 0.10
CONCLUSION_FRACTION = 0.10


def allocate_word_budget(headings, target_word_count):
    """
    headings: list of {"heading": str, "level": "H2"|"H3"} -- the content
    sections, i.e. NOT including the H1 (the title itself doesn't get a
    word budget).

    Returns a new list of dicts, one per heading, each with a "word_budget"
    key added, plus two extra entries at the start/end for the intro and
    conclusion (heading=None, so the brief renderer knows these aren't
    real headings).
    """
    if not headings:
        raise ValueError("allocate_word_budget requires at least one heading")

    intro_budget = round(target_word_count * INTRO_FRACTION)
    conclusion_budget = round(target_word_count * CONCLUSION_FRACTION)
    remaining = target_word_count - intro_budget - conclusion_budget

    section_count = len(headings)
    base_share = remaining // section_count
    leftover = remaining - (base_share * section_count)

    body_sections = []
    for index, heading in enumerate(headings):
        # Distribute the rounding leftover one extra word at a time to the
        # first `leftover` sections, so the total always equals the target
        # exactly instead of being a few words short.
        word_budget = base_share + (1 if index < leftover else 0)
        body_sections.append({**heading, "word_budget": word_budget})

    return (
        [{"heading": None, "level": "intro", "word_budget": intro_budget}]
        + body_sections
        + [{"heading": None, "level": "conclusion", "word_budget": conclusion_budget}]
    )


# Manual test: a quick sanity check that budgets add up to the target.
if __name__ == "__main__":
    test_headings = [
        {"heading": "What is Multichannel Inventory Sync?", "level": "H2"},
        {"heading": "Why It Matters for Shopify Sellers", "level": "H2"},
        {"heading": "Common Sync Errors", "level": "H3"},
        {"heading": "How Simprosys Solves This", "level": "H2"},
    ]
    result = allocate_word_budget(test_headings, 1200)
    for section in result:
        label = section["heading"] or section["level"]
        print(f"  [{section['level']}] {label}: {section['word_budget']} words")
    print("Total:", sum(s["word_budget"] for s in result), "(target: 1200)")
