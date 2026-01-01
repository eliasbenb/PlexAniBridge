#!/usr/bin/env python3

"""Export the FastAPI OpenAPI schema to a JSON file."""

import argparse
import json
import sys
from pathlib import Path

from scripts import __file__ as scripts_file

if scripts_file is None:
    raise RuntimeError("Cannot determine scripts file path.")

ROOT_DIR = Path(scripts_file).parent.parent.resolve()
DEFAULT_OUTPUT = ROOT_DIR / "docs" / "web" / "openapi.json"


def build_openapi_json() -> str:
    """Return the OpenAPI specification as a JSON string.

    Returns:
        The OpenAPI specification in JSON format.
    """
    from src.web.app import create_app

    app = create_app()
    spec = app.openapi()

    return json.dumps(
        spec,
        ensure_ascii=True,
        sort_keys=True,
        indent=4,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for exporting the OpenAPI schema."""
    parser = argparse.ArgumentParser(
        description="Export the FastAPI OpenAPI schema to docs/web/openapi.json."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Path to write the schema (default: {DEFAULT_OUTPUT}).",
    )

    args = parser.parse_args(argv)
    output_path = args.output.resolve()

    try:
        rendered = build_openapi_json()
    except Exception as exc:
        print(f"Failed to generate OpenAPI schema: {exc}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered + "\n", encoding="utf-8")
    print(f"Wrote OpenAPI schema to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
