"""Check project decision-record structure and repository-local Markdown links."""

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
ADR_DIRECTORY = ROOT / "docs" / "adr"
REQUIRED_SECTIONS = (
    "## Status",
    "## Date",
    "## Context",
    "## Options Considered",
    "## Decision",
    "## Consequences",
    "## Related Decisions",
)
MARKDOWN_LINK = re.compile(r"\]\(([^)]+)\)")


def main() -> int:
    errors: list[str] = []
    records = sorted(ADR_DIRECTORY.glob("[0-9][0-9][0-9][0-9]-*.md"))
    index = (ADR_DIRECTORY / "README.md").read_text(encoding="utf-8-sig")
    if not records:
        errors.append("No numbered architecture decision records found.")
    for record in records:
        content = record.read_text(encoding="utf-8-sig")
        for section in REQUIRED_SECTIONS:
            if section not in content.splitlines():
                errors.append(f"{record.name}: missing {section}")
        if not re.search(r"^\d{4}-\d{2}-\d{2}$", content, re.MULTILINE):
            errors.append(f"{record.name}: missing ISO decision date")
        if record.name not in index:
            errors.append(f"{record.name}: missing from ADR index")

    documents = sorted(ROOT.glob("*.md")) + sorted((ROOT / "docs").rglob("*.md"))
    for document in documents:
        content = document.read_text(encoding="utf-8-sig")
        for match in MARKDOWN_LINK.finditer(content):
            target = match.group(1).strip()
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            resolved = (document.parent / unquote(parsed.path)).resolve()
            if not resolved.is_relative_to(ROOT):
                errors.append(f"{document.name}: link escapes repository: {target}")
            elif not resolved.exists():
                errors.append(f"{document.name}: broken link: {target}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Checked {len(records)} ADRs and local links in {len(documents)} documents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
