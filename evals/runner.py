"""Deterministic M1 evaluation: human CLI import, real stdio transport, full-state oracle."""

import argparse
import asyncio
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

import pyarrow as pa
from jsonschema import validate
from mcp import Client, StdioServerParameters

from guarded_data_mcp.domain import Contract

CASES = Path(__file__).parent / "cases" / "m1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def full_state_oracle(workspace: Path) -> None:
    """Read physical state independently of the application's snapshot decoder."""
    expected = json.loads((CASES / "expected.json").read_text())
    with closing(sqlite3.connect(workspace / "guarded-data.sqlite3")) as connection:
        source = connection.execute("SELECT content,sha256 FROM sources").fetchone()
        require(source[0] == (CASES / "source.csv").read_bytes(), "Source bytes changed")
        require(hashlib.sha256(source[0]).hexdigest() == source[1], "Source hash mismatch")
        blob, quarantine, digest = connection.execute(
            "SELECT snapshot,quarantine,snapshot_sha256 FROM versions"
        ).fetchone()
        require(hashlib.sha256(blob).hexdigest() == digest, "Snapshot hash mismatch")
        table = pa.ipc.open_file(pa.BufferReader(blob)).read_all()
        require(table["_gdm_row_id"].to_pylist() == [1, 2, 3, 4], "Occurrence IDs changed")
        actual = table.drop(["_gdm_row_id"]).to_pylist()
        for row in actual:
            row["amount"] = str(row["amount"])
        require(
            actual == expected["rows"], "Full output differs from expected records/multiplicity"
        )
        require(
            pa.ipc.open_file(pa.BufferReader(quarantine)).read_all().num_rows == 0,
            "Import unexpectedly quarantined data",
        )


async def protocol_cases(workspace: Path, *, mode: str = "auto") -> tuple[list[str], str]:
    passed = []
    expected = json.loads((CASES / "expected.json").read_text())
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "guarded_data_mcp", "--workspace", str(workspace), "serve"],
    )
    async with Client(parameters, mode=mode, read_timeout_seconds=20) as client:
        protocol_version = str(client.protocol_version)
        tools = (await client.list_tools()).tools
        require(
            {tool.name for tool in tools} == {"list_datasets", "inspect_dataset"},
            "Unexpected privilege/tool exposed",
        )
        schemas = {tool.name: tool.output_schema for tool in tools}
        require(all(schemas.values()), "Missing output schemas")
        require(all(tool.annotations.read_only_hint for tool in tools), "Missing read-only hints")
        passed.append("tool_surface")

        listing = await client.call_tool("list_datasets", {})
        require(not listing.is_error, "Dataset listing failed")
        validate(listing.structured_content, schemas["list_datasets"])
        require(
            [d["dataset_id"] for d in listing.structured_content["datasets"]] == ["fixture"],
            "Registered scope mismatch",
        )
        passed.append("registered_scope")

        result = await client.call_tool("inspect_dataset", {"dataset_id": "fixture"})
        require(not result.is_error, "Inspection failed")
        payload = result.structured_content
        validate(payload, schemas["inspect_dataset"])
        require(payload["row_count"] == expected["row_count"], "Row count mismatch")
        require(
            {c["name"]: c["null_count"] for c in payload["columns"]} == expected["null_counts"],
            "Null profile mismatch",
        )
        require(
            payload["quality_status"] == "not_evaluated" and not payload["findings_evaluated"],
            "Inspection falsely claimed quality validation",
        )
        require(
            "rows" not in payload and "source_path" not in payload, "Unexpected raw data disclosure"
        )
        passed.append("honest_complete_profile")

        for tool, arguments, code in [
            ("inspect_dataset", {"dataset_id": "missing"}, "UNKNOWN_DATASET"),
            ("inspect_dataset", {"dataset_id": "../../private"}, "INVALID_INPUT"),
            (
                "inspect_dataset",
                {"dataset_id": "fixture", "version": 99},
                "UNKNOWN_DATASET_VERSION",
            ),
            ("list_datasets", {"limit": 101}, "INVALID_INPUT"),
        ]:
            failure = await client.call_tool(tool, arguments)
            require(failure.is_error, f"Expected refusal: {arguments}")
            require(failure.structured_content["code"] == code, f"Wrong refusal code: {arguments}")
            passed.append(f"refusal:{code}:{arguments}")
        invalid_type = await client.call_tool("list_datasets", {"limit": True})
        require(invalid_type.is_error, "Boolean was silently accepted as an integer limit")
        passed.append("refusal:argument_type")
    return passed, protocol_version


def run(mode: str = "auto") -> dict:
    with tempfile.TemporaryDirectory(prefix="guarded-m1-") as directory:
        workspace = Path(directory) / "workspace"
        contract = Contract.model_validate_json((CASES / "contract.json").read_bytes())
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "guarded_data_mcp",
                "--workspace",
                str(workspace),
                "import",
                "fixture",
                str(CASES / "source.csv"),
                "--format",
                "csv",
                "--contract",
                str(CASES / "contract.json"),
                "--approve-contract",
                contract.sha256,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        require(completed.returncode == 0, f"CLI import failed: {completed.stderr}")
        full_state_oracle(workspace)
        cases, protocol_version = asyncio.run(protocol_cases(workspace, mode=mode))
        passed = ["full_state_and_source_oracle", *cases]
        full_state_oracle(workspace)
        return {
            "suite": "m1-deterministic",
            "mode": mode,
            "protocol_version": protocol_version,
            "status": "passed",
            "passed": len(passed),
            "cases": passed,
            "real_agent": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["auto", "legacy"], default="auto")
    args = parser.parse_args()
    print(json.dumps(run(args.mode), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
