"""
Content Agent: banned AI-cliche phrase list.

Purpose of this file
--------------------
A starter list of generic, AI-sounding filler phrases the Content Agent
should avoid producing at all (per Rahul, 2026-08-05). Used in two places
that need to stay in sync:

1. The Writer Agent (.claude/skills/blog-write/SKILL.md) mirrors this
   list directly in its instructions -- prevention, not just detection.
   Skill files are markdown, not Python, so that copy can't literally
   import this one; if this list changes, update both by hand.
2. The QA Checker Agent (content_agent/qa_checks.py) imports
   find_banned_phrases() below to scan a finished draft and catch
   anything that slipped through.

This is a starting list, not a finished one -- expected to grow or shrink
once it's been run against real drafts.
"""

BANNED_PHRASES = [
    "in today's fast-paced world",
    "in today's digital landscape",
    "unlock",
    "dive into",
    "let's dive in",
    "delve into",
    "game-changer",
    "game-changing",
    "seamless",
    "seamlessly",
    "elevate",
    "leverage",
    "revolutionize",
    "revolutionary",
    "empower",
    "empowering",
    "cutting-edge",
    "holistic approach",
    "synergy",
    "synergize",
    "at the end of the day",
    "navigate the complexities of",
    "in the realm of",
    "embark on a journey",
    "whether you're a beginner or an expert",
    "it's important to note that",
    "it is important to note that",
    "it's worth noting that",
    "it is worth noting that",
    "when it comes to",
    "in this article, we will",
    "in this post, we will",
    "in this blog post, we will",
    "testament to",
    "ever-evolving",
    "ever-changing",
    "boasts",
]


def find_banned_phrases(text):
    """
    Case-insensitive scan for every banned phrase in `text`. Returns a
    dict of {phrase: occurrence_count} for only the phrases actually
    found -- empty dict means a clean draft.
    """
    text_lower = text.lower()
    found = {}
    for phrase in BANNED_PHRASES:
        count = text_lower.count(phrase.lower())
        if count:
            found[phrase] = count
    return found
