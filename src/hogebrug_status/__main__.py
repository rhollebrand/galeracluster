"""Module entry-point to run the CLI via ``python -m hogebrug_status``."""

from .cli import main

if __name__ == "__main__":  # pragma: no cover - delegated to cli
    raise SystemExit(main())
