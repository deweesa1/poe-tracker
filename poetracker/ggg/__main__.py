"""python -m poetracker.ggg characters   (needs api settings; see __init__.py)"""
import json
import sys

from .. import config
from . import Client


def main() -> int:
    cfg = config.load_config()
    api = cfg.settings.get("api") or {}
    if not api.get("enabled"):
        print("The GGG API is switched off (settings.yaml -> api: enabled: false).")
        print("GGG isn't accepting new developer applications right now.")
        return 1
    c = Client(api.get("client_id", ""), api.get("contact_email", ""))
    c.login()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "characters"
    if cmd == "characters":
        print(json.dumps(c.characters(), indent=2))
    elif cmd == "stash":
        print(json.dumps(c.stashes(sys.argv[2]), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
