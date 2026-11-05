"""
Request intent classification module.

Determines whether a user's request text actually authorises personal data
deletion or is instead an access request, export request, correction request,
marketing opt-out, or informational inquiry.

Owned by: Member 4 (Hrushikesh)
Module: code/policy/intent.py
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional, Tuple


def _normalize_text(text: str) -> str:
    """Normalize unicode text by lowercasing and stripping diacritics/accents."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    # Strip combining diacritical marks for robust matching across accent variations
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# Deletion intent patterns (matching on normalized text without accents)
DELETION_PATTERNS = [
    # English
    r"\bdelet(?:e|ing|ion|ed|es)?\b",
    r"\beras(?:e|ing|ure|ed|es)?\b",
    r"\bremov(?:e|al|ing|ed|es)?\b",
    r"\bclos(?:e|ing|ed|es)?\b(?:\s+(?:my|this|the|an))?\s+(?:account|profile)\b",
    r"\bpurg(?:e|ing|ed)?\b",
    r"\bright\s+to\s+be\s+forgotten\b",
    r"\bforget\s+me\b",
    r"\bwip(?:e|ing|ed)?\b",
    r"\bclean\s+(?:out\s+)?my\s+personal\s+details\b",
    r"\bwithout\s+a\s+trace\b",
    r"\b(?:profile|account)\s+is\s+gone\b",
    # Spanish (elimin*, borr*, cerr* cuenta, suprim*)
    r"\belimin(?:ar|acion|ado|o|e|en|es)?\b",
    r"\bborr(?:ar|ado|o|e|en|es)?\b",
    r"\bcerr(?:ar|ada|ado|o|e)?\b(?:\s+(?:mi|esta|la))?\s+cuenta\b",
    r"\bcierr(?:e|en|o)?\b(?:\s+(?:mi|esta|la))?\s+cuenta\b",
    r"\bsuprim(?:ir|ido|an|e)?\b",
    # French (suppress*, effac*, clotur*)
    r"\bsuppress(?:ion|er|e|ez|ent)?\b",
    r"\beffac(?:er|ement|e|ez)?\b",
    r"\bclotur(?:er|e|ez)?\b(?:\s+(?:mon|ce))?\s+compte\b",
    # German (losch*, entfern*, konto schliess*)
    r"\blosch(?:en|ung|t|te)?\b",
    r"\bentfern(?:en|ung|t|te)?\b",
    r"\bkonto\s+schliess(?:en)?\b",
    # Portuguese (exclu*, apag*, encerr* conta)
    r"\bexclu(?:ir|r|cao|sao|do|a|am|o)?\b",
    r"\bapag(?:ar|ado|e|em)?\b",
    r"\bencerr(?:ar|amento|e)?\b(?:\s+(?:minha|esta))?\s+conta\b",
    # Italian (cancell*, elimin*)
    r"\bcancell(?:are|azione|ato|i)?\b",
]

# Non-normalized patterns for CJK (Japanese, Korean)
CJK_DELETION_PATTERNS = [
    r"削除",
    r"消去",
    r"アカウント.*解約",
    r"삭제",
    r"탈퇴",
]

# Informational query patterns
INQUIRY_PATTERNS = [
    r"^(?:how\s+do\s+i|how\s+can\s+i)\s+(?:delete|close|erase)\b",
    r"^(?:what\s+is\s+your)\s+(?:deletion|retention)\s+policy\b",
    r"^(?:can\s+you\s+explain)\s+(?:how\s+deletion\s+works)\b",
]

# Access request patterns
ACCESS_PATTERNS = [
    r"\bsubject\s+access\s+request\b",
    r"\bsar\b",
    r"\baccess\s+(?:to\s+)?my\s+data\b",
    r"\bwhat\s+data\s+do\s+you\s+(?:have|hold|keep)\b",
    r"\bshow\s+me\s+my\s+data\b",
    r"\bview\s+my\s+(?:data|records|profile|information)\b",
    r"\bacces(?:o|s)\s+(?:a|to)\s+mis\s+datos\b",
    r"\bacces\s+a\s+mes\s+donnees\b",
    r"\bauskunft\s+uber\s+daten\b",
]

# Export request patterns
EXPORT_PATTERNS = [
    r"\bexport\b",
    r"\bdownload\b",
    r"\bportability\b",
    r"\bsend\s+me\s+a\s+copy\b",
    r"\bdescargar\b",
    r"\bdescarga\b",
    r"\bexporter\b",
    r"\btelecharger\b",
    r"\bherunterladen\b",
]

# Correction request patterns
CORRECTION_PATTERNS = [
    r"\bcorrect\b",
    r"\brectif",
    r"\bupdate\b",
    r"\bfix\b",
    r"\bchange\b",
    r"\bcorregir\b",
    r"\bactuali[zc]",
    r"\bmodif",
    r"\btypo\b",
    r"\bspelling\b",
]

# Marketing opt-out patterns
MARKETING_OPT_OUT_PATTERNS = [
    r"\bunsubscribe\b",
    r"\bopt[\s-]out\b",
    r"\bmarketing\b",
    r"\bnewsletter\b",
    r"\bpromotional\b",
    r"\bmailing\s+list\b",
    r"\bpublicidad\b",
    r"\bpublicite\b",
    r"\bwerbung\b",
]


def classify_request_intent(request_text: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Classify whether a request text authorizes personal data deletion.

    Returns:
        (is_deletion, reason_if_not)
        - If True: request authorizes deletion (proceed to audit).
        - If False: request is NOT_APPLICABLE with specific reason.
    """
    if not request_text or not request_text.strip():
        return False, "Empty or missing request text"

    raw_text = request_text.strip()
    norm_text = _normalize_text(raw_text)

    # 1. Check for pure informational inquiry first
    for pattern in INQUIRY_PATTERNS:
        if re.search(pattern, norm_text):
            return False, "Informational inquiry only; does not authorize deletion"

    # 2. Check for deletion intent in normalized text and raw CJK text
    has_deletion = any(re.search(pat, norm_text) for pat in DELETION_PATTERNS)
    if not has_deletion:
        has_deletion = any(re.search(pat, raw_text) for pat in CJK_DELETION_PATTERNS)

    if has_deletion:
        return True, None

    # 3. No deletion intent: classify the specific non-deletion request type
    for pattern in ACCESS_PATTERNS:
        if re.search(pattern, norm_text):
            return False, "Subject access request (SAR); does not authorize deletion"

    for pattern in EXPORT_PATTERNS:
        if re.search(pattern, norm_text):
            return False, "Data export / portability request; does not authorize deletion"

    for pattern in CORRECTION_PATTERNS:
        if re.search(pattern, norm_text):
            return False, "Data rectification / correction request; does not authorize deletion"

    for pattern in MARKETING_OPT_OUT_PATTERNS:
        if re.search(pattern, norm_text):
            return False, "Marketing opt-out; does not authorize deletion"

    # Fallback
    return False, "Request does not authorize deletion"
