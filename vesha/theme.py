"""The desktop's theme, when varna (github.com/Theyashsawarkar/varna) is
installed: its palette.json, this tool's own pick under `tools.vesha` if it
has one. Without varna, an empty dict and vesha keeps its own colours."""
import json
import os


def colors(tool="vesha"):
    path = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "varna", "palette.json")
    try:
        with open(path) as f:
            data = json.load(f)
        theme = (data.get("tools") or {}).get(tool) or data
        return {k: v for k, v in theme["colors"].items() if isinstance(v, str) and v.startswith("#") and len(v) >= 7}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=True))


def apply(palette, mapping):
    """Overrides palette entries (name -> (r, g, b)) from the theme: mapping is
    {entry: theme colour name, or (name, other name, blend)}."""
    c = colors()
    if not c:
        return palette
    for entry, src in mapping.items():
        try:
            if isinstance(src, tuple):
                palette[entry] = mix(rgb(c[src[0]]), rgb(c[src[1]]), src[2])
            else:
                palette[entry] = rgb(c[src])
        except KeyError:
            pass
    return palette
