from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.capture_role_backfill_service import (  # noqa: E402
    CaptureRoleBackfillError,
    CaptureRoleBackfillService,
)


def parse_source(value: str) -> tuple[str, str]:
    role, separator, directory = value.partition("=")
    if not separator or not role or not directory:
        raise argparse.ArgumentTypeError("Cada --source debe tener formato ROLE=SOURCE_DIRECTORY.")
    return role, directory


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill verificable de roles de capturas RedEdge.")
    parser.add_argument("--campaign-id", type=int, required=True)
    parser.add_argument("--source", type=parse_source, action="append", required=True)
    parser.add_argument("--apply", action="store_true", help="Aplica el plan validado; por defecto solo dry-run.")
    parser.add_argument("--report", type=Path, help="Ruta opcional para guardar el reporte JSON.")
    args = parser.parse_args()
    sources = dict(args.source)
    if len(sources) != len(args.source):
        parser.error("Cada role solo puede declarar un source directory.")
    try:
        if args.apply:
            report = CaptureRoleBackfillService.apply(campaign_id=args.campaign_id, sources=sources)
        else:
            report = CaptureRoleBackfillService.analyze(
                campaign_id=args.campaign_id, sources=sources, dry_run=True,
            )
    except CaptureRoleBackfillError as exc:
        parser.error(str(exc))
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
