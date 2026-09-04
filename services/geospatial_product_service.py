from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from config import Config
from database import SessionLocal
from models import (
    Campaign,
    GeospatialProduct,
    GeospatialProductType,
    ProcessingJob,
)
from services.raster_service import (
    InvalidRasterError,
    RasterService,
)


class GeospatialProductPersistenceError(Exception):
    """
    Error producido durante la persistencia
    de productos geoespaciales.
    """
    pass


class InvalidGeospatialProductError(Exception):
    """
    El producto solicitado no cumple las reglas
    necesarias para ser registrado.
    """
    pass


class GeospatialProductService:

    ALLOWED_EXTENSIONS = {
        ".tif",
        ".tiff",
    }

    @staticmethod
    def _storage_root() -> Path:

        configured = Path(
            Config.CAMPAIGN_STORAGE_ROOT
        )

        if configured.is_absolute():
            return configured

        project_root = Path(
            __file__
        ).resolve().parents[1]

        return (
            project_root
            / configured
        ).resolve()

    @staticmethod
    def _normalize_product_type(
        product_type: (
            GeospatialProductType
            | str
        ),
    ) -> GeospatialProductType:

        if isinstance(
            product_type,
            GeospatialProductType,
        ):
            return product_type

        if not isinstance(
            product_type,
            str,
        ):
            raise InvalidGeospatialProductError(
                "El tipo de producto "
                "geoespacial no es válido."
            )

        normalized = (
            product_type
            .strip()
            .upper()
            .replace("-", "_")
            .replace(" ", "_")
        )

        try:
            return GeospatialProductType(
                normalized
            )

        except ValueError as exc:
            raise InvalidGeospatialProductError(
                "Tipo de producto "
                f"no válido: {product_type}."
            ) from exc

    @staticmethod
    def _optional_bounds(
        values: tuple[
            float | None,
            float | None,
            float | None,
            float | None,
        ],
    ) -> dict | None:

        if not all(
            value is not None
            for value in values
        ):
            return None

        left, bottom, right, top = values

        return {
            "left": left,
            "bottom": bottom,
            "right": right,
            "top": top,
        }

    @classmethod
    def _serialize(
        cls,
        product: GeospatialProduct,
    ) -> dict:

        return {
            "id": product.id,
            "product_code": (
                product.product_code
            ),
            "campaign_id": (
                product.campaign_id
            ),
            "processing_job_id": (
                product.processing_job_id
            ),
            "product_type": (
                product.product_type.value
            ),
            "name": product.name,
            "storage_path": (
                product.storage_path
            ),
            "crs": product.crs,
            "epsg": product.epsg,
            "width": product.width,
            "height": product.height,
            "band_count": (
                product.band_count
            ),
            "resolution": {
                "x": product.resolution_x,
                "y": product.resolution_y,
            },
            "bounds": cls._optional_bounds(
                (
                    product.bounds_left,
                    product.bounds_bottom,
                    product.bounds_right,
                    product.bounds_top,
                )
            ),
            "bounds_wgs84": (
                cls._optional_bounds(
                    (
                        product.wgs84_left,
                        product.wgs84_bottom,
                        product.wgs84_right,
                        product.wgs84_top,
                    )
                )
            ),
            "created_at": (
                product.created_at.isoformat()
                if product.created_at
                else None
            ),
        }

    @staticmethod
    def _get_product_entity(
        session,
        product_id: int,
    ) -> GeospatialProduct | None:

        statement = select(
            GeospatialProduct
        ).where(
            GeospatialProduct.id
            == product_id
        )

        return session.scalar(
            statement
        )

    @classmethod
    def register_raster_product(
        cls,
        *,
        campaign_id: int,
        product_type: (
            GeospatialProductType
            | str
        ),
        name: str,
        source_path: str | os.PathLike,
        processing_job_id: int | None = None,
    ) -> dict:

        if (
            not isinstance(name, str)
            or not name.strip()
        ):
            raise InvalidGeospatialProductError(
                "El nombre del producto "
                "es obligatorio."
            )

        normalized_type = (
            cls._normalize_product_type(
                product_type
            )
        )

        source = Path(
            source_path
        ).expanduser().resolve()

        suffix = (
            source.suffix.lower()
        )

        if suffix not in cls.ALLOWED_EXTENSIONS:
            raise InvalidGeospatialProductError(
                "Los productos raster "
                "deben utilizar formato "
                "GeoTIFF (.tif o .tiff)."
            )

        try:
            raster_info = (
                RasterService.inspect_raster(
                    source
                )
            )

        except InvalidRasterError as exc:
            raise InvalidGeospatialProductError(
                str(exc)
            ) from exc

        if (
            raster_info["driver"]
            != "GTiff"
        ):
            raise InvalidGeospatialProductError(
                "El producto debe ser "
                "un GeoTIFF válido."
            )

        if not raster_info[
            "is_georeferenced"
        ]:
            raise InvalidGeospatialProductError(
                "El raster no posee "
                "georreferenciación suficiente."
            )

        session = SessionLocal()

        destination = None
        temporary = None

        try:
            campaign = session.get(
                Campaign,
                campaign_id,
            )

            if campaign is None:
                raise InvalidGeospatialProductError(
                    f"La campaña con ID "
                    f"{campaign_id} no existe."
                )

            if processing_job_id is not None:

                processing_job = session.get(
                    ProcessingJob,
                    processing_job_id,
                )

                if processing_job is None:
                    raise InvalidGeospatialProductError(
                        "El trabajo de procesamiento "
                        f"con ID {processing_job_id} "
                        "no existe."
                    )

                if (
                    processing_job.campaign_id
                    != campaign_id
                ):
                    raise InvalidGeospatialProductError(
                        "El trabajo de procesamiento "
                        "pertenece a otra campaña."
                    )

            provisional_code = (
                f"TEMP-{uuid4().hex}"
            )

            product = GeospatialProduct(
                product_code=(
                    provisional_code
                ),
                campaign_id=campaign_id,
                processing_job_id=(
                    processing_job_id
                ),
                product_type=(
                    normalized_type
                ),
                name=name.strip(),
                storage_path="PENDING",
                crs=raster_info["crs"],
                epsg=raster_info["epsg"],
                width=raster_info["width"],
                height=raster_info["height"],
                band_count=(
                    raster_info[
                        "band_count"
                    ]
                ),
                resolution_x=(
                    raster_info[
                        "resolution"
                    ]["x"]
                ),
                resolution_y=(
                    raster_info[
                        "resolution"
                    ]["y"]
                ),
                bounds_left=(
                    raster_info[
                        "bounds"
                    ]["left"]
                ),
                bounds_bottom=(
                    raster_info[
                        "bounds"
                    ]["bottom"]
                ),
                bounds_right=(
                    raster_info[
                        "bounds"
                    ]["right"]
                ),
                bounds_top=(
                    raster_info[
                        "bounds"
                    ]["top"]
                ),
            )

            wgs84 = raster_info[
                "bounds_wgs84"
            ]

            if wgs84 is not None:
                product.wgs84_left = (
                    wgs84["left"]
                )
                product.wgs84_bottom = (
                    wgs84["bottom"]
                )
                product.wgs84_right = (
                    wgs84["right"]
                )
                product.wgs84_top = (
                    wgs84["top"]
                )

            session.add(
                product
            )

            session.flush()

            today = datetime.now(
                timezone.utc
            ).strftime(
                "%Y%m%d"
            )

            product.product_code = (
                f"GP-{today}-"
                f"{product.id:04d}"
            )

            relative_path = (
                Path(
                    campaign.campaign_code
                )
                / "products"
                / (
                    f"{product.product_code}_"
                    f"{normalized_type.value}"
                    f"{suffix}"
                )
            )

            destination = (
                cls._storage_root()
                / relative_path
            )

            if destination.exists():
                raise (
                    InvalidGeospatialProductError(
                        "Ya existe un archivo "
                        "administrado para este "
                        "producto."
                    )
                )

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            temporary = (
                destination.with_name(
                    destination.name
                    + ".tmp"
                )
            )

            shutil.copy2(
                source,
                temporary,
            )

            os.replace(
                temporary,
                destination,
            )

            product.storage_path = (
                relative_path.as_posix()
            )

            session.commit()

            session.refresh(
                product
            )

            return cls._serialize(
                product
            )

        except InvalidGeospatialProductError:
            session.rollback()

            if (
                temporary is not None
                and temporary.exists()
            ):
                temporary.unlink()

            if (
                destination is not None
                and destination.exists()
            ):
                destination.unlink()

            raise

        except SQLAlchemyError as exc:
            session.rollback()

            if (
                temporary is not None
                and temporary.exists()
            ):
                temporary.unlink()

            if (
                destination is not None
                and destination.exists()
            ):
                destination.unlink()

            raise GeospatialProductPersistenceError(
                "No fue posible registrar "
                f"el producto geoespacial: {exc}"
            ) from exc

        except Exception as exc:
            session.rollback()

            if (
                temporary is not None
                and temporary.exists()
            ):
                temporary.unlink()

            if (
                destination is not None
                and destination.exists()
            ):
                destination.unlink()

            raise GeospatialProductPersistenceError(
                "No fue posible incorporar "
                f"el raster: {exc}"
            ) from exc

        finally:
            session.close()

    @classmethod
    def get_product(
        cls,
        product_id: int,
    ) -> dict | None:

        session = SessionLocal()

        try:
            product = (
                cls._get_product_entity(
                    session,
                    product_id,
                )
            )

            if product is None:
                return None

            return cls._serialize(
                product
            )

        except SQLAlchemyError as exc:
            raise GeospatialProductPersistenceError(
                "No fue posible consultar "
                f"el producto: {exc}"
            ) from exc

        finally:
            session.close()

    @classmethod
    def list_products(
        cls,
        campaign_id: int,
        *,
        product_type: (
            GeospatialProductType
            | str
            | None
        ) = None,
    ) -> list[dict]:

        session = SessionLocal()

        try:
            campaign = session.get(
                Campaign,
                campaign_id,
            )

            if campaign is None:
                raise InvalidGeospatialProductError(
                    f"La campaña con ID "
                    f"{campaign_id} no existe."
                )

            statement = select(
                GeospatialProduct
            ).where(
                GeospatialProduct.campaign_id
                == campaign_id
            )

            if product_type is not None:

                normalized_type = (
                    cls._normalize_product_type(
                        product_type
                    )
                )

                statement = statement.where(
                    GeospatialProduct.product_type
                    == normalized_type
                )

            statement = statement.order_by(
                GeospatialProduct.id.desc()
            )

            products = session.scalars(
                statement
            ).all()

            return [
                cls._serialize(product)
                for product in products
            ]

        except InvalidGeospatialProductError:
            raise

        except SQLAlchemyError as exc:
            raise GeospatialProductPersistenceError(
                "No fue posible listar "
                f"los productos: {exc}"
            ) from exc

        finally:
            session.close()
            
    @classmethod
    def delete_products_for_job(
        cls,
        processing_job_id: int,
    ) -> int:
        """
        Elimina todos los productos asociados a un
        trabajo de procesamiento y sus archivos físicos
        administrados.
        """

        session = SessionLocal()

        managed_paths = []

        try:
            statement = (
                select(GeospatialProduct)
                .where(
                    GeospatialProduct.processing_job_id
                    == processing_job_id
                )
                .order_by(
                    GeospatialProduct.id.desc()
                )
            )

            products = session.scalars(
                statement
            ).all()

            storage_root = (
                cls._storage_root().resolve()
            )

            for product in products:

                candidate = (
                    storage_root
                    / Path(
                        product.storage_path
                    )
                ).resolve()

                try:
                    candidate.relative_to(
                        storage_root
                    )

                except ValueError as exc:
                    raise (
                        InvalidGeospatialProductError(
                            "La ruta del producto "
                            "no pertenece al "
                            "almacenamiento administrado."
                        )
                    ) from exc

                managed_paths.append(
                    candidate
                )

                session.delete(
                    product
                )

            deleted_count = len(
                products
            )

            session.commit()

        except InvalidGeospatialProductError:
            session.rollback()
            raise

        except SQLAlchemyError as exc:
            session.rollback()

            raise GeospatialProductPersistenceError(
                "No fue posible revertir "
                "los productos del trabajo "
                f"{processing_job_id}: {exc}"
            ) from exc

        finally:
            session.close()

        cleanup_errors = []

        for managed_path in managed_paths:

            if not managed_path.exists():
                continue

            try:
                managed_path.unlink()

            except OSError as exc:
                cleanup_errors.append(
                    f"{managed_path}: {exc}"
                )

        if cleanup_errors:
            raise GeospatialProductPersistenceError(
                "Los productos fueron eliminados "
                "de la base de datos, pero algunos "
                "archivos físicos no pudieron "
                "eliminarse: "
                + " | ".join(
                    cleanup_errors
                )
            )

        return deleted_count