"""Request-local messages via Python's GNU gettext implementation."""
from contextvars import ContextVar
import gettext as _gettext
from pathlib import Path

language = ContextVar("alter_language", default="ko")
_english = _gettext.translation("alter", Path(__file__).parent / "locales", ["en"], fallback=True)


def request_language(request):
    selected = request.cookies.get("alter_language", "")
    if selected in {"ko", "en"}:
        return selected
    for item in request.headers.get("accept-language", "ko").split(","):
        code = item.split(";", 1)[0].strip().lower().split("-", 1)[0]
        if code in {"ko", "en"}:
            return code
    return "en"


def gettext(message):
    return _english.gettext(message) if language.get() == "en" else message
