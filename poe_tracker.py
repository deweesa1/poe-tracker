"""Entry point for the packaged app (PoE Tracker.exe). Same as: python -m poetracker"""
import multiprocessing

if __name__ in {"__main__", "__mp_main__"}:
    multiprocessing.freeze_support()
    if __name__ == "__main__":
        from poetracker.__main__ import main
        raise SystemExit(main())
