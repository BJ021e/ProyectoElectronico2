from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import SessionLocal
from models import Campaign, CaptureRole, ImageBand, ImageCapture
from services.capture_service import CaptureService, InvalidCaptureError
from services.image_ingestion_service import ImageIngestionService
from services.rededge_import_service import RedEdgeImportService


class CaptureRoleBackfillError(Exception):
    """El análisis de identidad no permite asignar roles de forma segura."""


class CaptureRoleBackfillService:
    """Relaciona grupos RedEdge por contenido, nunca por sus metadatos operativos."""

    EXPECTED_BANDS = tuple(
        band.value
        for band in (
            ImageBand.BLUE,
            ImageBand.GREEN,
            ImageBand.RED,
            ImageBand.NIR,
            ImageBand.RED_EDGE,
        )
    )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _normalize_sources(
        cls,
        sources: dict[CaptureRole | str, str | Path],
    ) -> list[tuple[CaptureRole, Path]]:
        if not isinstance(sources, dict) or not sources:
            raise CaptureRoleBackfillError("Debe declarar al menos un source con rol explícito.")

        normalized = []
        for raw_role, raw_path in sources.items():
            try:
                role = CaptureService.normalize_role(raw_role)
            except InvalidCaptureError as exc:
                raise CaptureRoleBackfillError(str(exc)) from exc
            if role is CaptureRole.UNKNOWN:
                raise CaptureRoleBackfillError("UNKNOWN no puede utilizarse como source role.")
            path = Path(raw_path).expanduser().resolve()
            if not path.is_dir():
                raise CaptureRoleBackfillError(f"El source directory no existe: {path}")
            normalized.append((role, path))

        roles = [role for role, _ in normalized]
        if len(roles) != len(set(roles)):
            raise CaptureRoleBackfillError("Cada role puede declarar un único source directory.")
        return sorted(normalized, key=lambda item: item[0].value)

    @classmethod
    def _group_signature(cls, files: dict[str, str | Path]) -> tuple[tuple[str, str], ...]:
        bands = sorted(files)
        if bands != sorted(cls.EXPECTED_BANDS):
            missing = sorted(set(cls.EXPECTED_BANDS) - set(bands))
            extra = sorted(set(bands) - set(cls.EXPECTED_BANDS))
            raise CaptureRoleBackfillError(
                f"El grupo no contiene exactamente cinco bandas; faltan={missing}, extra={extra}."
            )
        hashes = []
        for band in cls.EXPECTED_BANDS:
            path = Path(files[band])
            if not path.is_file():
                raise CaptureRoleBackfillError(f"No existe el archivo de banda {band}: {path}")
            hashes.append((band, cls._sha256(path)))
        return tuple(hashes)

    @classmethod
    def _source_groups(cls, sources: list[tuple[CaptureRole, Path]]) -> tuple[list[dict], list[dict]]:
        groups = []
        source_reports = []
        for role, directory in sources:
            inspection = RedEdgeImportService.inspect_folder(directory)
            if inspection["group_count"] == 0:
                raise CaptureRoleBackfillError(f"No se detectaron grupos RedEdge en {directory}.")
            incomplete = [group for group in inspection["groups"] if not group["is_complete"]]
            if incomplete:
                keys = ", ".join(group["source_key"] for group in incomplete)
                raise CaptureRoleBackfillError(f"Source contiene grupos incompletos: {keys}")
            source_reports.append({
                "role": role.value,
                "source_directory": str(directory),
                "source_group_count": inspection["group_count"],
                "source_asset_count": sum(len(group["files"]) for group in inspection["groups"]),
            })
            for group in inspection["groups"]:
                signature = cls._group_signature(group["files"])
                groups.append({
                    "role": role.value,
                    "source_directory": str(directory),
                    "source_group": group["source_key"],
                    "signature": signature,
                })
        return groups, source_reports

    @classmethod
    def _database_groups(cls, campaign_id: int, session) -> tuple[list[dict], dict[str, int]]:
        campaign = session.get(Campaign, campaign_id)
        if campaign is None:
            raise CaptureRoleBackfillError(f"La campaña con ID {campaign_id} no existe.")
        captures = session.scalars(
            select(ImageCapture)
            .options(selectinload(ImageCapture.assets))
            .where(ImageCapture.campaign_id == campaign_id)
            .order_by(ImageCapture.id)
        ).all()
        database = {
            "capture_count": len(captures),
            "asset_count": sum(len(capture.assets) for capture in captures),
            "role_counts_before": {
                role.value: sum(capture.role == role for capture in captures)
                for role in CaptureRole
            },
        }
        groups = []
        for capture in captures:
            files = {}
            for asset in capture.assets:
                band = asset.band.value
                if band in files:
                    raise CaptureRoleBackfillError(
                        f"La captura {capture.id} contiene banda duplicada: {band}."
                    )
                files[band] = ImageIngestionService.resolve_managed_path(asset.storage_path)
            signature = cls._group_signature(files)
            groups.append({
                "capture_id": capture.id,
                "capture_code": capture.capture_code,
                "sequence": capture.sequence,
                "persisted_role": capture.role.value,
                "signature": signature,
            })
        return groups, database

    @classmethod
    def analyze(
        cls,
        *,
        campaign_id: int,
        sources: dict[CaptureRole | str, str | Path],
        dry_run: bool = True,
        session=None,
    ) -> dict:
        """Genera un plan verificable. Esta operación no escribe en la base de datos."""
        normalized_sources = cls._normalize_sources(sources)
        source_groups, source_reports = cls._source_groups(normalized_sources)
        owns_session = session is None
        if owns_session:
            session = SessionLocal()
        try:
            db_groups, database = cls._database_groups(campaign_id, session)
        finally:
            if owns_session:
                session.close()

        by_source_signature = defaultdict(list)
        for group in source_groups:
            by_source_signature[group["signature"]].append(group)
        by_db_signature = defaultdict(list)
        for group in db_groups:
            by_db_signature[group["signature"]].append(group)

        ambiguous = []
        ambiguous_signatures = set()
        source_role_conflicts = []
        for signature in sorted(set(by_source_signature) | set(by_db_signature)):
            source_matches = by_source_signature.get(signature, [])
            db_matches = by_db_signature.get(signature, [])
            source_roles = {item["role"] for item in source_matches}
            if len(source_roles) > 1 and db_matches:
                source_role_conflicts.append({
                    "source_groups": [item["source_group"] for item in source_matches],
                    "source_roles": sorted(source_roles),
                    "capture_ids": [item["capture_id"] for item in db_matches],
                    "hashes": dict(signature),
                    "reason": "source_roles_conflict",
                })
                ambiguous_signatures.add(signature)
                continue
            if len(source_matches) > 1 or len(db_matches) > 1:
                ambiguous.append({
                    "source_groups": [item["source_group"] for item in source_matches],
                    "capture_ids": [item["capture_id"] for item in db_matches],
                    "hashes": dict(signature),
                })
                ambiguous_signatures.add(signature)
        matches = []
        conflicts = list(source_role_conflicts)
        already_assigned = []
        unmatched_source = []
        unmatched_db = []
        for signature, source_items in sorted(by_source_signature.items()):
            db_items = by_db_signature.get(signature, [])
            if signature in ambiguous_signatures:
                continue
            if not db_items:
                unmatched_source.extend(source_items)
                continue
            source_item = source_items[0]
            db_item = db_items[0]
            evidence = {
                "capture_id": db_item["capture_id"],
                "capture_code": db_item["capture_code"],
                "sequence": db_item["sequence"],
                "role": source_item["role"],
                "source_group": source_item["source_group"],
                "source_directory": source_item["source_directory"],
                "bands": list(cls.EXPECTED_BANDS),
                "hashes": dict(signature),
            }
            if db_item["persisted_role"] == source_item["role"]:
                already_assigned.append(evidence)
            elif db_item["persisted_role"] != CaptureRole.UNKNOWN.value:
                conflicts.append({
                    **evidence,
                    "persisted_role": db_item["persisted_role"],
                    "reason": "persisted_role_conflict",
                })
            else:
                matches.append(evidence)
        for signature, db_items in sorted(by_db_signature.items()):
            if signature not in by_source_signature:
                unmatched_db.extend(db_items)

        planned_counts = dict(database["role_counts_before"])
        for match in matches:
            planned_counts[CaptureRole.UNKNOWN.value] -= 1
            planned_counts[match["role"]] += 1
        report = {
            "campaign_id": campaign_id,
            "dry_run": dry_run,
            "sources": source_reports,
            "database": database,
            "matching": {
                "matched_capture_groups": len(matches) + len(already_assigned),
                "matched_assets": (len(matches) + len(already_assigned)) * len(cls.EXPECTED_BANDS),
                "unmatched_source_groups": len(unmatched_source),
                "unmatched_db_captures": len(unmatched_db),
                "ambiguous_groups": len(ambiguous),
                "conflicts": len(conflicts),
                "already_assigned": len(already_assigned),
                "matches": matches,
                "already_assigned_matches": already_assigned,
                "unmatched_source_group_details": [
                    {"role": item["role"], "source_group": item["source_group"]}
                    for item in unmatched_source
                ],
                "unmatched_db_capture_details": [
                    {key: item[key] for key in ("capture_id", "capture_code", "sequence", "persisted_role")}
                    for item in unmatched_db
                ],
                "ambiguous_group_details": ambiguous,
                "conflict_details": conflicts,
            },
            "planned_role_counts_after": planned_counts,
        }
        report["safe_to_apply"] = not any((
            report["matching"]["unmatched_source_groups"],
            report["matching"]["ambiguous_groups"],
            report["matching"]["conflicts"],
        ))
        return report

    @classmethod
    def apply(cls, *, campaign_id: int, sources: dict[CaptureRole | str, str | Path]) -> dict:
        """Aplica únicamente el plan completo y verificado, dentro de una transacción."""
        session = SessionLocal()
        try:
            with session.begin():
                report = cls.analyze(
                    campaign_id=campaign_id,
                    sources=sources,
                    dry_run=False,
                    session=session,
                )
                if not report["safe_to_apply"]:
                    raise CaptureRoleBackfillError("El análisis contiene conflictos, ambigüedades o grupos sin match.")
                # Recalcula hashes y estado persistido justo antes de escribir.
                report = cls.analyze(
                    campaign_id=campaign_id,
                    sources=sources,
                    dry_run=False,
                    session=session,
                )
                if not report["safe_to_apply"]:
                    raise CaptureRoleBackfillError("El análisis cambió antes de confirmar el backfill.")
                for match in report["matching"]["matches"]:
                    capture = session.get(ImageCapture, match["capture_id"])
                    if capture is None or capture.role is not CaptureRole.UNKNOWN:
                        raise CaptureRoleBackfillError("El rol persistido cambió antes de confirmar el backfill.")
                    capture.role = CaptureRole(match["role"])
                session.flush()
            return report
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
