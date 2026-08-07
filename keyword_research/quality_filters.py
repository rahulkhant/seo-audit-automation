"""
Keyword Research module: keyword-quality filters.

Two mechanical exclusion rules, applied wherever keywords are deduped or
loaded (within-batch save, cross-batch master aggregation, and per-batch
retrieval) so excluded keywords never reach the dashboard, exports, or
reports -- not shown, not stored, per Rahul's call (2026-08-06): drop them
outright, no review queue, no persisted list of what got dropped.

1. Repeated-word keywords (e.g. "hotel hotel management") -- deterministic,
   no reference data needed. Also catches singular/plural near-repeats one
   word apart (e.g. "hotel hotels near me"), via has_near_duplicate_stem --
   deliberately windowed rather than checked anywhere in the keyword, since
   an unwindowed version would wrongly drop legitimate phrases like "hotel
   management software for small hotels" (Rahul flagged the "hotel hotels
   near me" case directly, 2026-08-07).

2. Keywords containing a brand or proper-noun term -- Rahul's 28 tracked
   competitors (an exact, zero-ambiguity list) plus a general heuristic for
   the much bigger source of noise actually observed in the real data:
   specific hotel/resort property names picked up by Google Keyword
   Planner (e.g. "kk royal jaipur", "the byke old anchor goa"). There's no
   dictionary of hotel brand names to check against, so this works by
   elimination instead: a word that isn't in a real English dictionary,
   isn't known industry jargon (pms, gds, crm...), and isn't a real place
   name is almost always a proper noun -- a hotel/resort name, in this
   dataset. That means genuine city/country names have to be allow-listed
   explicitly (LOCATION_ALLOW_WORDS) or they'd be wrongly treated as brand
   noise too. Both allow-lists were built from the actual competitor data
   (frequency-analyzed, not guessed), but neither is exhaustive -- an
   obscure town or an unusual hotel name in some future batch could land
   on the wrong side of this. That's an accepted, disclosed limitation:
   fix individual misses by adding a word to the right list below, don't
   try to rebuild this from scratch.
"""

import re
from functools import lru_cache
from pathlib import Path

_ENGLISH_WORDS_PATH = Path(__file__).resolve().parent / "data" / "english_words.txt"

# (suffix, replacement) pairs tried in order when a word isn't found as-is --
# handles regular plurals/verb forms the dictionary only lists in their base
# form (e.g. "hotels" -> "hotel", "pricing" -> "price", "serviced" -> "service").
_SUFFIX_TRANSFORMS = (
    ("ies", "y"), ("es", ""), ("s", ""),
    ("ing", "e"), ("ing", ""), ("ed", "e"), ("ed", ""), ("est", ""), ("er", ""),
)

# Rahul's 28 tracked competitors, plus the no-space/short spelling variants
# that actually show up in their own keyword exports.
COMPETITOR_BRAND_TERMS = {
    "amenitiz", "apaleo", "axis rooms", "axisrooms", "booking factory",
    "clock", "cloudbeds", "cogwave", "djubo", "ezee absolute", "ezee",
    "guesty", "hmspro", "hotel runner", "hotelrunner", "hotel sync",
    "hotelogix", "ids next", "little hotelier", "mycloud hospitality",
    "myhotelline", "portel", "resnexus", "rmscloud", "roomraccoon",
    "sabee app", "sabeeapp", "staah", "staahmax", "stayflexi", "stayntouch",
    "thinkreservations", "webrezpro", "web rez pro", "webrez",
}

# Modern/technical/industry vocabulary this dataset uses constantly that a
# general-purpose dictionary (or the suffix stripping above) won't recognize.
GENERIC_ALLOW_WORDS = {
    "pos", "pms", "rms", "gds", "api", "crm", "ota", "otas", "erp", "kpi",
    "adr", "revpar", "str", "hms", "crs", "saas", "app", "apps", "website",
    "websites", "webpage", "homepage", "com", "www", "html", "url", "seo",
    "sms", "xml", "php", "ui", "ux", "b2b", "b2c", "sla", "poc", "mgmt",
    "frontdesk", "cms", "iot", "qr", "eco", "wordpress", "plugin",
    "database", "extranet", "chatbot", "overbooking", "upselling", "upsell",
    "internet", "offline", "online", "contactless", "superhost", "download",
    "checklist", "boutique", "promo", "demo", "sustainability", "amenity",
    "amenities", "centre", "mini", "condo", "hostel", "hostels",
    "backpackers", "villas", "cafe", "asi", "hrs", "hr", "rv", "box", "co",
    "ppt", "id", "ids", "opera", "b&b", "f&b", "airbnb", "google", "pdf",
    "email", "automation", "planning", "worldwide", "hsr", "nagar", "midc",
}

# Real place names (cities, states, countries, tourist/pilgrimage sites)
# that show up constantly in this data -- without this, "hotels in
# chennai" would get wrongly treated as brand noise the same way a
# specific hotel's name would.
LOCATION_ALLOW_WORDS = {
    "chennai", "bangalore", "mumbai", "srinagar", "ahmedabad", "pondicherry",
    "nashik", "katra", "noida", "udaipur", "pune", "indore", "gandhinagar",
    "kashmir", "jaisalmer", "morjim", "kolkata", "mangalore", "kasol",
    "matheran", "shimla", "vadapalani", "jabalpur", "jaipur", "gulmarg",
    "dalhousie", "hyderabad", "bhubaneswar", "alibaug", "panjim", "panaji",
    "digha", "mahabaleshwar", "colombo", "guwahati", "ujjain", "pahalgam",
    "dwarka", "coonoor", "gir", "igatpuri", "wakad", "pimpri", "chittorgarh",
    "bhavnagar", "shirdi", "chail", "ajmer", "kuchesar", "karjat", "andheri",
    "nathdwara", "sajjangarh", "kandla", "tirupati", "ooty", "narkanda",
    "gokarna", "gandhidham", "jammu", "varanasi", "mussoorie", "arambol",
    "khajuraho", "namakkal", "madhavaram", "sriperumbudur", "vaitarna",
    "saputara", "shikohabad", "himachal", "pradesh", "rajasthan", "gujarat",
    "goa", "kerala", "punjab", "maharashtra", "karnataka", "sisli", "koh",
    "lipe", "samui", "uk", "usa", "uae", "nz", "europe", "asia", "africa",
    "spain", "dubai", "istanbul", "london", "singapore", "antalya",
    "budapest", "thailand", "malaysia", "indonesia", "melbourne", "sydney",
    "edinburgh", "toronto", "sharjah", "lanka", "vaishno", "devi", "manali",
    "navi", "zirakpur", "arumbakkam", "pudukkottai", "ranikhet",
}


@lru_cache(maxsize=1)
def _english_words():
    with open(_ENGLISH_WORDS_PATH, encoding="utf-8") as words_file:
        return frozenset(line.strip().lower() for line in words_file if line.strip())


def _is_known_word(word):
    english = _english_words()
    if word in english or word in GENERIC_ALLOW_WORDS or word in LOCATION_ALLOW_WORDS:
        return True
    for suffix, replacement in _SUFFIX_TRANSFORMS:
        if word.endswith(suffix):
            candidate = word[: -len(suffix)] + replacement
            if candidate in english:
                return True
    return False


def _tokenize(keyword_text):
    # "b & b", "b&b", and "b and b" should all tokenize identically to the
    # single unit "b&b" (bed and breakfast) -- otherwise splitting on "&"
    # (or spelling it out as "and") turns it into two adjacent/duplicate
    # "b" tokens and wrongly trips the repeated-word check.
    fused = keyword_text.lower()
    fused = re.sub(r"\b([a-z0-9]) and ([a-z0-9])\b", r"\1&\2", fused)
    fused = re.sub(r"\b([a-z0-9])\s*&\s*([a-z0-9])\b", r"\1&\2", fused)
    return re.findall(r"[a-z0-9&]+", fused)


def has_repeated_word(keyword_text):
    words = _tokenize(keyword_text)
    return len(words) != len(set(words))


def _stem(word):
    # Light singular/plural normalization -- just enough to recognize
    # "hotel"/"hotels" as the same word without a real stemmer. Guarded by
    # a minimum length so short words like "as" or "gas" don't get mangled
    # into something that accidentally matches a neighbor.
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("es") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def has_near_duplicate_stem(keyword_text):
    """Catches singular/plural repeats close together ("hotel hotels near
    me") that has_repeated_word misses because "hotel" and "hotels" are
    different tokens. Deliberately windowed to at most one word apart --
    unlike has_repeated_word, an unconstrained version of this would wrongly
    catch legitimate phrases like "hotel management software for small
    hotels", where the same stem repeats much later for a real reason."""
    stems = [_stem(word) for word in _tokenize(keyword_text) if len(word) > 1 and not word.isdigit()]
    for i, stem in enumerate(stems):
        for gap in (1, 2):
            if i + gap < len(stems) and stems[i + gap] == stem:
                return True
    return False


def contains_brand_term(keyword_text):
    lowered = keyword_text.lower()
    if any(brand in lowered for brand in COMPETITOR_BRAND_TERMS):
        return True
    return any(
        len(word) > 1 and not word.isdigit() and not _is_known_word(word)
        for word in _tokenize(keyword_text)
    )


def is_valid_keyword(keyword_text):
    return (
        not has_repeated_word(keyword_text)
        and not has_near_duplicate_stem(keyword_text)
        and not contains_brand_term(keyword_text)
    )
