"""Command line: python -m poetracker [command]

    run       (default) start the tracker and open the dashboard window
    mini      open the small always-on-top tracker window
    restart   (used by updates) wait for the tracker to close, then start it again
              --browser  open it in your web browser instead
    ingest    read new lines from Client.txt once and exit
    rebuild   rebuild all derived tables (add --from-log to re-read Client.txt)
    status    print where things are and how much has been read
    capture   save a copied map from a text file:  capture path\\to\\map.txt
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import captures, config as config_mod, db, ingest, paths, service


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="poetracker", description="Path of Exile play tracker")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("--browser", action="store_true", help="open in the web browser instead of its own window")
    r.add_argument("--headless", action="store_true", help="don't open anything (for testing)")
    r.add_argument("--port", type=int)
    sub.add_parser("mini", help="open the always-on-top mini tracker (the tracker must be running)")
    sub.add_parser("restart", help="(used by updates) wait for the tracker to close, then start it again")
    sub.add_parser("ingest")
    rb = sub.add_parser("rebuild")
    rb.add_argument("--from-log", action="store_true", help="re-read Client.txt from the start")
    sub.add_parser("status")
    cp = sub.add_parser("capture")
    cp.add_argument("file")
    args = ap.parse_args(argv)

    if args.cmd == "mini":
        from .mini import run_mini
        return run_mini()

    if args.cmd == "restart":
        from .updater import run_restart
        return run_restart()

    if args.cmd in (None, "run"):
        from .ui.app import run
        window = "headless" if getattr(args, "headless", False) else ("browser" if getattr(args, "browser", False) else None)
        run(window=window, port=getattr(args, "port", None))
        return 0

    service.setup_logging()
    cfg = config_mod.load_config()
    con = db.open_db()
    log_path = service.find_log(cfg)

    if args.cmd == "ingest":
        if not log_path:
            print("Client.txt not found; set log_path in", paths.config_dir() / "settings.yaml")
            return 1
        t = time.time()
        n = ingest.Ingestor(con, cfg, log_path).run_once(_bar)
        captures.link_pending(con, cfg)
        print(f"\n{n} events in {time.time() - t:.1f}s")
    elif args.cmd == "rebuild":
        t = time.time()
        n = ingest.rebuild(con, cfg, log_path, from_log=args.from_log, progress=_bar)
        print(f"\nRebuilt from {n} events in {time.time() - t:.1f}s")
    elif args.cmd == "status":
        print("Data folder :", paths.data_dir())
        print("Config      :", paths.config_dir())
        print("Client.txt  :", log_path or "not found")
        print("Read up to  :", db.get_state(con, "log_offset", 0), "bytes")
        for t in ("game_session", "area_visit", "run", "level_up", "death", "map_capture", "currency_snapshot"):
            print(f"  {t:18}", con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    elif args.cmd == "capture":
        cid = captures.save_capture(con, Path(args.file).read_text(encoding="utf-8"))
        print("saved capture", cid if cid else "(not a map)")
        captures.link_pending(con, cfg)
    return 0


def _bar(done: int, total: int) -> None:
    if total:
        pct = done / total
        sys.stdout.write(f"\r  [{'#' * int(pct * 30):30}] {pct:5.1%}")
        sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
