import re
from typing import Iterable, List, Tuple

def get_regex_matches(pattern: str, text: str) -> list[str]:
    try:
        return re.findall(pattern, text)
    except re.error as e:
        return [f"Regex Error: {e}"]

def _esc(s: str) -> str:
    return re.escape(s)

def _heuristic_pattern(expected: str) -> str:
    """Used only when expected isn't present in input_str."""
    if re.fullmatch(r"\d+", expected or ""):
        return r"(\d+)"
    if re.fullmatch(r"[A-Fa-f0-9]+", expected or ""):
        return r"([A-Fa-f0-9]+)"
    # UUID v4-ish
    if re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", expected or ""):
        return r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    # Email-ish
    if "@" in (expected or ""):
        return r"([^@\s]+@[^@\s]+\.[^@\s]+)"
    # Base64-ish
    if re.fullmatch(r"[A-Za-z0-9+/=]+", expected or ""):
        return r"([A-Za-z0-9+/=]+)"
    # Default token
    return r"([\w\.-]+)"

def build_regex_from_example(input_str: str, expected: str, *, multiline: bool=False, dotall: bool=False, embed_flags: bool=False) -> str:
    """
    Produces ONE capturing group so group(1) is the value.
    Uses ^ anchor when prefix is empty, and $ anchor when suffix is empty.
    """
    def _flags():
        mods = ""
        if dotall: mods += "s"
        if multiline: mods += "m"
        return f"(?{mods})" if mods else ""

    if input_str and expected and expected in input_str:
        i = input_str.index(expected)
        pre = input_str[:i]
        suf = input_str[i + len(expected):]

        prefix = re.escape(pre)
        suffix = re.escape(suf)

        # Anchoring logic
        if pre and suf:
            core = f"{prefix}(.*?){suffix}"
        elif pre and not suf:
            core = f"{prefix}(.*?)$"
        elif not pre and suf:
            core = f"^(.*?){suffix}"
        else:
            # expected == whole string
            core = r"^(.*?)$"

        return (_flags() + core) if embed_flags else core

    # Fallback heuristics when expected not found in input
    if re.fullmatch(r"\d+", expected or ""):
        token = r"(\d+)"
    elif re.fullmatch(r"[0-9A-Fa-f-]{36}", expected or ""):
        token = r"([0-9A-Fa-f-]{36})"
    elif "@" in (expected or ""):
        token = r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})"
    elif re.fullmatch(r"[A-Za-z0-9+/=]+", expected or ""):
        token = r"([A-Za-z0-9+/=]+)"
    else:
        token = r"([\w\.-]+)"

    core = token if not input_str else f".*?{token}.*?"
    return (_flags() + core) if embed_flags else core