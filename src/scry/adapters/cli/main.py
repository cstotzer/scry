import argparse
import sys
from collections.abc import Callable
from contextlib import AbstractContextManager

from scry.app import Services
from scry.domain import DocumentId, LinkRef, ScryError
from scry.ports import IndexUnavailable

OpenServices = Callable[[], AbstractContextManager[Services]]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scry", description="Knowledge base maintenance")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync", help="reconcile the Markdown files with the search index")
    search = sub.add_parser("search", help="run a search and print raw hits (debugging)")
    search.add_argument("query")
    search.add_argument("-k", "--top-k", type=int, default=8)
    search.add_argument("-t", "--tag", action="append", dest="tags")
    links = sub.add_parser("links", help="show the links and backlinks of a note (debugging)")
    links.add_argument("doc_id")
    links.add_argument("-q", "--query")
    links.add_argument("-n", "--limit", type=int, default=10)
    return parser


def _print_refs(label: str, refs: list[LinkRef], total: int) -> None:
    print(f"{label} ({len(refs)} of {total})")
    for r in refs:
        hub = "  [hub]" if r.hub else ""
        print(f"  {r.mentions:3}x  {r.doc_id}  ({r.degree} neighbours){hub}")


def run(argv: list[str], open_services: OpenServices) -> int:
    args = _parser().parse_args(argv)
    try:
        with open_services() as services:
            if args.command == "sync":
                report = services.sync()
                for label, ids in (
                    ("added", report.added),
                    ("updated", report.updated),
                    ("removed", report.removed),
                ):
                    print(f"{label:8} {len(ids):4}  {', '.join(map(str, ids))}")
                for w in report.warnings:
                    print(f"warning  {w.doc_id}: {'; '.join(w.messages)}")
            elif args.command == "links":
                services.sync()  # builds the link graph
                links = services.links(DocumentId(args.doc_id), args.query, args.limit)
                _print_refs("outgoing", links.outgoing, links.total_outgoing)
                _print_refs("backlinks", links.backlinks, links.total_backlinks)
                if links.unresolved:
                    print(f"unresolved: {', '.join(links.unresolved)}")
            else:
                for hit in services.search(args.query, args.top_k, args.tags):
                    path = " > ".join(hit.heading_path)
                    print(f"{hit.score:.4f}  {hit.doc_id}  [{path}]")
                    print("        " + hit.text[:200].replace("\n", " "))
    except IndexUnavailable:
        print(
            "scry: the index is in use by the running server, which keeps it in sync on its own. "
            "Use /status or the MCP tools instead.",
            file=sys.stderr,
        )
        return 2
    except ScryError as exc:
        print(f"scry: {exc}", file=sys.stderr)
        return 1
    return 0
