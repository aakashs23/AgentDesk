"""PII detection + redaction — the first pipeline stage (TRD §5 stages 2–3).

Regex pass over the ticket text before any content leaves the system for an
external LLM API. Order matters: longer digit patterns (cards) run before
phones so a card number isn't half-eaten as a phone number.
"""

import re

# ponytail: regex/NER-lite. Over-redaction is the safe failure mode here;
# swap in a real NER model if precision ever matters.
_PATTERNS = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[CARD]"),
    (re.compile(r"(?<![\w.])\+?\d[\d\s().-]{6,14}\d(?![\w.])"), "[PHONE]"),
]


def redact(text: str) -> str:
    for pattern, token in _PATTERNS:
        text = pattern.sub(token, text)
    return text
