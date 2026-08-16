"""Mascaramento de telefones em textos exibidos no chat publico."""

from __future__ import annotations

import re

# Sequencias com 10+ digitos (com ou sem formatacao leve).
_PHONE_IN_TEXT_RE = re.compile(r"(?:\+?\d[\d\s().-]{8,}\d|\d{10,13})")


def mask_phone_digits(phone: str) -> str:
    """Mascara MSISDN: primeiros 4 + *** + ultimos 4 digitos."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 8:
        return phone
    if len(digits) <= 8:
        return f"{digits[:2]}***{digits[-2:]}"
    return f"{digits[:4]}***{digits[-4:]}"


def mask_phones_in_text(text: str) -> str:
    """Substitui numeros de telefone detectados por versao mascarada."""

    def _replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 10:
            return raw
        masked = mask_phone_digits(digits)
        return f"+{masked}" if raw.strip().startswith("+") else masked

    return _PHONE_IN_TEXT_RE.sub(_replace, text)
