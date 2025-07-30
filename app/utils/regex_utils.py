import re

def build_regex_from_example(input_str: str, expected: str, *, multiline: bool=False, dotall: bool=False, embed_flags: bool=False) -> str:
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

        if pre and suf:
            core = f"{prefix}(.*?){suffix}"
        elif pre and not suf:
            core = f"{prefix}(.*?)$"
        elif not pre and suf:
            core = f"^(.*?){suffix}"
        else:
            core = r"^(.*?)$"

        return (_flags() + core) if embed_flags else core

    # Heuristic fallback
    token = r"([\w\.-]+)"
    if re.fullmatch(r"\d+", expected or ""):
        token = r"(\d+)"
    elif re.fullmatch(r"[0-9A-Fa-f-]{36}", expected or ""):
        token = r"([0-9A-Fa-f-]{36})"
    elif "@" in (expected or ""):
        token = r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})"
    elif re.fullmatch(r"[A-Za-z0-9+/=]+", expected or ""):
        token = r"([A-Za-z0-9+/=]+)"

    return (_flags() + token) if embed_flags else token