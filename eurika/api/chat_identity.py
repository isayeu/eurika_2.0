"""Shared identity / authorship question patterns for chat intents.

Only persona + authorship of *this* assistant/project — not «кто написал тетрис?».
"""

from __future__ import annotations

# Whole-message patterns (match_direct_intent / defaults). Message may have spaces.
IDENTITY_REGEX_PATTERNS: tuple[str, ...] = (
    r"^\s*ты\s+кто\??\s*$",
    r"^\s*кто\s+ты(\s+такой)?\??\s*$",
    r"^\s*кто\s+(твой|ваш)\s+создател\w*\??\s*$",
    r"^\s*кто\s+автор(\s+(этого\s+)?(проекта|программы|кода|eurika))?\??\s*$",
    # Object = self / this project (not arbitrary «кто написал игру…»)
    r"^\s*кто\s+тебя\s+(создал|сделал|написал|разработал)\??\s*$",
    r"^\s*кто\s+(создал|сделал|написал|разработал)\s+тебя\??\s*$",
    r"^\s*кто\s+(создал|сделал|написал|разработал)\s+(твой|ваш)\s+\w+\??\s*$",
    r"^\s*кто\s+(создал|сделал|написал|разработал)\s+(эту|этот)\s+"
    r"(программ\w*|проект\w*|код\w*|ассистент\w*)\??\s*$",
    r"^\s*кто\s+(создал|сделал|написал|разработал)\s+eurika\??\s*$",
    r"^\s*who\s+are\s+you\??\s*$",
    r"^\s*what\s+are\s+you\??\s*$",
    r"^\s*who\s+is\s+your\s+(creator|author)\??\s*$",
    r"^\s*who\s+(created|made|built|wrote|coded|developed)\s+you\??\s*$",
    r"^\s*who\s+(created|made|built|wrote|coded|developed)\s+your\s+\w+\??\s*$",
    r"^\s*who\s+(created|made|built|wrote|coded|developed)\s+this\s+"
    r"(program|project|code|assistant)\??\s*$",
)

# Normalized message (no leading ^\s*).
IDENTITY_REGEX_NORM: tuple[str, ...] = (
    r"^ты\s+кто\??$",
    r"^кто\s+ты(\s+такой)?\??$",
    r"^кто\s+(твой|ваш)\s+создател\w*\??$",
    r"^кто\s+автор(\s+(этого\s+)?(проекта|программы|кода|eurika))?\??$",
    r"^кто\s+тебя\s+(создал|сделал|написал|разработал)\??$",
    r"^кто\s+(создал|сделал|написал|разработал)\s+тебя\??$",
    r"^кто\s+(создал|сделал|написал|разработал)\s+(твой|ваш)\s+\w+\??$",
    r"^кто\s+(создал|сделал|написал|разработал)\s+(эту|этот)\s+"
    r"(программ\w*|проект\w*|код\w*|ассистент\w*)\??$",
    r"^кто\s+(создал|сделал|написал|разработал)\s+eurika\??$",
    r"^who\s+are\s+you\??$",
    r"^what\s+are\s+you\??$",
    r"^who\s+is\s+your\s+(creator|author)\??$",
    r"^who\s+(created|made|built|wrote|coded|developed)\s+you\??$",
    r"^who\s+(created|made|built|wrote|coded|developed)\s+your\s+\w+\??$",
    r"^who\s+(created|made|built|wrote|coded|developed)\s+this\s+"
    r"(program|project|code|assistant)\??$",
)

IDENTITY_VECTOR_EXEMPLARS: tuple[str, ...] = (
    "ты кто",
    "кто ты такой",
    "кто тебя создал",
    "кто твой создатель",
    "кто написал твой код",
    "кто написал эту программу",
    "кто автор проекта",
    "who are you",
    "who created you",
    "who wrote your code",
    "who wrote this program",
)
