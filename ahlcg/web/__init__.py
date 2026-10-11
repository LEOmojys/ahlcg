"""Web layer: FastAPI backend plus a single page front end.

See SPEC.md section 3 for the HTTP contract.  Nothing in here implements game
rules: it turns engine state into JSON and turns clicks into ChoiceAnswer
submissions.

Start it with:

    python -m ahlcg.web.app
"""

from __future__ import annotations

__all__ = ["app", "create_app", "main"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def __getattr__(name: str):
    """Lazily expose create_app / main so importing the package stays cheap."""
    if name in ("create_app", "main", "build_app"):
        from . import app as app_module

        return getattr(app_module, "create_app" if name == "build_app" else name)
    if name == "app":
        raise AttributeError("the FastAPI application is created by ahlcg.web.app.main()")
    raise AttributeError(name)
