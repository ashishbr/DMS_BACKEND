"""
Shared MSA number normalization utility.
Used by UploadService and DocumentService to ensure consistent formatting.
"""
import re
from typing import Optional

MSA_PATTERN = re.compile(r"(MSA[\s#:\-]*\d{3,}(?:[-/]\d{2,})?)", re.IGNORECASE)


def normalize_msa_number(value: Optional[str]) -> Optional[str]:
    """
    Normalize an MSA number string to a canonical form like MSA-2025-001.
    Returns None if the value cannot be parsed as an MSA reference.
    """
    if not value:
        return None
    cleaned = value.strip().upper().replace(" ", "").replace("_", "-")
    match = MSA_PATTERN.search(cleaned)
    if not match:
        generic = re.search(r"(\d{4}[-/]\d{3,})", cleaned)
        if generic:
            cleaned = generic.group(1)
        else:
            return None
    else:
        cleaned = match.group(1)
    if not cleaned.startswith("MSA"):
        cleaned = f"MSA-{cleaned}"
    return cleaned
