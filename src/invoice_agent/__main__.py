"""CLI entry: uvicorn invoice_agent.app:app --reload."""

from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run(
        "invoice_agent.app:app",
        host="127.0.0.1",
        port=int(__import__("os").environ.get("PORT", "8000")),
        reload=True,
    )


if __name__ == "__main__":
    main()
