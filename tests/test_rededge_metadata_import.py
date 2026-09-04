import numpy as np
import pytest
import rasterio

from config import Config

from services.campaign_service import (
    CampaignService,
)

from services.capture_service import (
    CaptureService,
)

from services.rededge_import_service import (
    RedEdgeImportExecutionError,
    RedEdgeImportService,
)


BANDS = [
    (
        1,
        "Blue",
        475,
    ),
    (
        2,
        "Green",
        560,
    ),
    (
        3,
        "Red",
        668,
    ),
    (
        4,
        "NIR",
        840,
    ),
    (
        5,
        "Rededge",
        717,
    ),
]


def build_xmp(
    *,
    band_name,
    wavelength,
    capture_id="CAPTURE-REAL-001",
    flight_id="FLIGHT-REAL-001",
):

    return f"""
<x:xmpmeta
    xmlns:x="adobe:ns:meta/"
    xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    xmlns:MicaSense="http://micasense.com/MicaSense/1.0/"
    xmlns:Camera="http://pix4d.com/1.0"
>
    <rdf:RDF>
        <rdf:Description>

            <MicaSense:FlightId>
                {flight_id}
            </MicaSense:FlightId>

            <MicaSense:CaptureId>
                {capture_id}
            </MicaSense:CaptureId>

            <Camera:BandName>
                {band_name}
            </Camera:BandName>

            <Camera:CentralWavelength>
                {wavelength}
            </Camera:CentralWavelength>

        </rdf:Description>
    </rdf:RDF>
</x:xmpmeta>
""".strip()


def write_rededge_tiff(
    path,
    *,
    band_name,
    wavelength,
    capture_id="CAPTURE-REAL-001",
    with_metadata=True,
):

    data = np.full(
        (
            8,
            8,
        ),
        wavelength,
        dtype=np.uint16,
    )

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=8,
        height=8,
        count=1,
        dtype="uint16",
    ) as dataset:

        dataset.write(
            data,
            1,
        )

        if not with_metadata:
            return

        dataset.update_tags(
            ns="EXIF",

            EXIF_GPSLatitude=(
                "(12) (5) (1.71996)"
            ),

            EXIF_GPSLatitudeRef="S",

            EXIF_GPSLongitude=(
                "(76) (56) (35.8962)"
            ),

            EXIF_GPSLongitudeRef="W",

            EXIF_GPSAltitude=(
                "(261.244)"
            ),

            EXIF_GPSAltitudeRef="0x00",

            EXIF_DateTimeOriginal=(
                "2025:10:07 15:32:12"
            ),
        )

        dataset.update_tags(
            ns="xml:XMP",
            **{
                "xml:XMP": build_xmp(
                    band_name=band_name,
                    wavelength=wavelength,
                    capture_id=capture_id,
                )
            },
        )


def create_source_group(
    source_dir,
    *,
    with_metadata=True,
    inconsistent_capture_id=False,
):

    source_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    for (
        band_index,
        band_name,
        wavelength,
    ) in BANDS:

        capture_id = (
            "CAPTURE-DIFFERENT"
            if (
                inconsistent_capture_id
                and band_index == 5
            )
            else "CAPTURE-REAL-001"
        )

        write_rededge_tiff(
            (
                source_dir
                / (
                    f"IMG_0100_"
                    f"{band_index}.tif"
                )
            ),
            band_name=band_name,
            wavelength=wavelength,
            capture_id=capture_id,
            with_metadata=with_metadata,
        )


def create_campaign():

    return (
        CampaignService
        .create_campaign(
            name=(
                "Campaña metadata "
                "MicaSense"
            ),
            sensor_type=(
                "MULTISPECTRAL"
            ),
            sensor_model=(
                "MicaSense RedEdge-3"
            ),
        )
    )


def test_rededge_import_persists_micasense_gps(
    tmp_path,
    monkeypatch,
):

    source_dir = (
        tmp_path
        / "source"
    )

    create_source_group(
        source_dir
    )

    monkeypatch.setattr(
        Config,
        "CAMPAIGN_STORAGE_ROOT",
        str(
            tmp_path
            / "managed"
        ),
    )

    campaign = create_campaign()

    result = (
        RedEdgeImportService
        .import_folder(
            campaign_id=campaign["id"],
            source_dir=source_dir,
        )
    )

    assert (
        result["imported_count"]
        == 1
    )

    captures = (
        CaptureService
        .list_captures(
            campaign["id"]
        )
    )

    assert len(captures) == 1

    capture = captures[0]

    assert (
        capture["status"]
        == "READY"
    )

    assert capture[
        "latitude"
    ] == pytest.approx(
        -12.0838111,
        abs=1e-6,
    )

    assert capture[
        "longitude"
    ] == pytest.approx(
        -76.9433045,
        abs=1e-6,
    )

    assert capture[
        "altitude"
    ] == pytest.approx(
        261.244,
        abs=1e-3,
    )

    assert (
        capture["captured_at"]
        is not None
    )


def test_rededge_import_without_metadata_remains_supported(
    tmp_path,
    monkeypatch,
):

    source_dir = (
        tmp_path
        / "source"
    )

    create_source_group(
        source_dir,
        with_metadata=False,
    )

    monkeypatch.setattr(
        Config,
        "CAMPAIGN_STORAGE_ROOT",
        str(
            tmp_path
            / "managed"
        ),
    )

    campaign = create_campaign()

    result = (
        RedEdgeImportService
        .import_folder(
            campaign_id=campaign["id"],
            source_dir=source_dir,
        )
    )

    assert (
        result["imported_count"]
        == 1
    )

    captures = (
        CaptureService
        .list_captures(
            campaign["id"]
        )
    )

    capture = captures[0]

    assert (
        capture["latitude"]
        is None
    )

    assert (
        capture["longitude"]
        is None
    )

    assert (
        capture["altitude"]
        is None
    )


def test_rededge_import_rejects_inconsistent_capture_metadata(
    tmp_path,
    monkeypatch,
):

    source_dir = (
        tmp_path
        / "source"
    )

    create_source_group(
        source_dir,
        inconsistent_capture_id=True,
    )

    monkeypatch.setattr(
        Config,
        "CAMPAIGN_STORAGE_ROOT",
        str(
            tmp_path
            / "managed"
        ),
    )

    campaign = create_campaign()

    with pytest.raises(
        RedEdgeImportExecutionError
    ):
        (
            RedEdgeImportService
            .import_folder(
                campaign_id=campaign[
                    "id"
                ],
                source_dir=source_dir,
            )
        )

    captures = (
        CaptureService
        .list_captures(
            campaign["id"]
        )
    )

    assert captures == []