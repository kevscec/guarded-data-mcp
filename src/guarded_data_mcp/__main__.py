"""Human CLI and stdio entry point. Contract approval never becomes an MCP tool."""

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from guarded_data_mcp.domain import Contract, DomainError, Limits
from guarded_data_mcp.services import DatasetService


def load_contract(path: Path) -> Contract:
    try:
        with path.open("rb") as handle:
            content = handle.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise DomainError("RESOURCE_LIMIT", "Contract exceeds 1 MiB.")
        return Contract.model_validate_json(content)
    except (OSError, ValidationError) as exc:
        raise DomainError(
            "INVALID_CONTRACT", "Contract file cannot be read or is invalid."
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(prog="guarded-data")
    parser.add_argument("--workspace", type=Path, default=Path("workspace"))
    parser.add_argument("--max-rows", type=int, default=100_000)
    parser.add_argument("--max-source-bytes", type=int, default=64 * 1024 * 1024)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser(
        "contract-check", help="Review canonical contract and approval digest"
    )
    check.add_argument("contract", type=Path)
    importer = commands.add_parser("import", help="Human-only import and contract activation")
    importer.add_argument("dataset_id")
    importer.add_argument("source", type=Path)
    importer.add_argument("--format", choices=["csv", "parquet"], required=True)
    importer.add_argument("--contract", type=Path, required=True)
    importer.add_argument("--approve-contract", required=True, metavar="SHA256")
    activate = commands.add_parser("activate-contract", help="Human-only rules/mapping activation")
    activate.add_argument("dataset_id")
    activate.add_argument("--contract", type=Path, required=True)
    activate.add_argument("--approve-contract", required=True, metavar="SHA256")
    activate.add_argument("--expected-revision", required=True, type=int)
    commands.add_parser("list")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("dataset_id")
    commands.add_parser("serve", help="Run the read-only MCP server on stdio")
    args = parser.parse_args()
    try:
        try:
            limits = Limits(max_rows=args.max_rows, max_source_bytes=args.max_source_bytes)
        except ValueError as exc:
            raise DomainError("INVALID_INPUT", str(exc)) from exc
        if args.command == "serve":
            from guarded_data_mcp.server import create_server

            create_server(args.workspace, limits).run(transport="stdio")
            return 0
        service = DatasetService(args.workspace, limits)
        if args.command == "contract-check":
            contract = load_contract(args.contract)
            payload = {"contract_sha256": contract.sha256, "contract": contract.model_dump()}
        elif args.command == "import":
            payload = service.import_file(
                args.dataset_id,
                args.source,
                args.format,
                load_contract(args.contract),
                args.approve_contract,
            ).model_dump(mode="json")
        elif args.command == "list":
            payload = service.list_datasets().model_dump(mode="json")
        elif args.command == "activate-contract":
            payload = service.activate_contract(
                args.dataset_id,
                load_contract(args.contract),
                args.approve_contract,
                args.expected_revision,
            )
        else:
            payload = service.inspect(args.dataset_id).model_dump(mode="json")
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except DomainError as exc:
        print(json.dumps(exc.payload()), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
