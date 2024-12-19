import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

sys.path.append(str(Path(__file__).parent.parent))

import colorama

from src import log
from src.core.anilist import AniListClient
from src.models.anilist import MediaListCollection


@dataclass
class ExportAnilistArgs:
    token: str
    file: Path
    dry_run: bool
    restore: bool


def export_anilist(output_file: Path) -> None:
    if output_file.exists():
        should_overwrite = input(
            f"{colorama.Fore.YELLOW}File '{output_file}' already exists. Do you want to overwrite it? [y/N]: {colorama.Style.RESET_ALL}"
        ).lower()
        if should_overwrite != "y":
            log.info("ExportAnilist: Exiting...")
            sys.exit(1)

    query = dedent(f"""
    query MediaListCollection($userId: Int, $type: MediaType, $chunk: Int) {{
        MediaListCollection(userId: $userId, type: $type, chunk: $chunk) {{
{MediaListCollection.model_dump_graphql(indent_level=3)}
        }}
    }}
    """).strip()

    data = MediaListCollection(user=client.anilist_user, has_next_chunk=True)
    variables = {"userId": client.anilist_user.id, "type": "ANIME", "chunk": 0}

    while data.has_next_chunk:
        response = client._make_request(query, variables)["data"]["MediaListCollection"]
        new_data = MediaListCollection(**response)

        data.has_next_chunk = new_data.has_next_chunk
        data.lists.extend(new_data.lists)

        variables["chunk"] += 1

    output_file.write_text(data.model_dump_json(indent=2))
    log.info(f"ExportAnilist: Exported AniList data to '{output_file}'")


def import_anilist(input_file: Path) -> None:
    if not input_file.exists():
        log.info(f"ExportAnilist: File '{input_file}' does not exist")
        sys.exit(1)

    data = MediaListCollection.model_validate_json(input_file.read_text())

    for media_list in (mle for lg in data.lists for mle in lg.entries):
        client.update_anime_entry(media_list)
        log.info(
            f"ExportAnilist: (anilist_id={media_list.media_id}, {str(media_list)[1:]}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export AniList data to a JSON file")
    parser.add_argument("--token", "-t", required=True, help="AniList API access token")
    parser.add_argument(
        "--file",
        "-f",
        required=True,
        help="Input or output JSON file path for export/import",
        type=Path,
    )
    parser.add_argument(
        "--dry-run",
        "-d",
        action="store_true",
        help="Dry run, don't make any API requests and only log the changes",
    )
    parser.add_argument(
        "--restore",
        "-r",
        action="store_true",
        help="Import AniList data from a JSON file instead of exporting it",
    )
    args = ExportAnilistArgs(**vars(parser.parse_args()))
    client = AniListClient(args.token, dry_run=args.dry_run)

    if args.restore:
        import_anilist(args.file)
    else:
        export_anilist(args.file)
