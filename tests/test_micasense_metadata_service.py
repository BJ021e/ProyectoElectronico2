import numpy as np
import pytest
import rasterio

from services.micasense_metadata_service import (
    InconsistentMicaSenseMetadataError,
    MicaSenseMetadataService,
)


def build_xmp(
    *,
    band_name,
    capture_id="CAPTURE-001",
    flight_id="FLIGHT-001",
    wavelength=475,
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


def write_micasense_tiff(
    path,
    *,
    band_name="Blue",
    capture_id="CAPTURE-001",
    flight_id="FLIGHT-001",
    latitude="(12) (5) (1.67604)",
    latitude_ref="S",
    longitude="(76) (56) (35.8764)",
    longitude_ref="W",
    altitude="(291.38)",
    captured_at="2025:10:07 15:35:18",
):

    data = np.ones(
        (
            8,
            8,
        ),
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

        dataset.update_tags(
            ns="EXIF",
            EXIF_GPSLatitude=(
                latitude
            ),
            EXIF_GPSLatitudeRef=(
                latitude_ref
            ),
            EXIF_GPSLongitude=(
                longitude
            ),
            EXIF_GPSLongitudeRef=(
                longitude_ref
            ),
            EXIF_GPSAltitude=(
                altitude
            ),
            EXIF_GPSAltitudeRef=(
                "0x00"
            ),
            EXIF_DateTimeOriginal=(
                captured_at
            ),
        )

        dataset.update_tags(
            ns="xml:XMP",
            **{
                "xml:XMP": build_xmp(
                    band_name=band_name,
                    capture_id=capture_id,
                    flight_id=flight_id,
                )
            },
        )


def test_extracts_real_micasense_shaped_gps(
    tmp_path,
):

    source = (
        tmp_path
        / "IMG_0004_1.tif"
    )

    write_micasense_tiff(
        source
    )

    metadata = (
        MicaSenseMetadataService
        .extract_image_metadata(
            source
        )
    )

    assert metadata.latitude == pytest.approx(
        -12.0837989,
        abs=1e-7,
    )

    assert metadata.longitude == pytest.approx(
        -76.9432990,
        abs=1e-7,
    )

    assert metadata.altitude == pytest.approx(
        291.38
    )

    assert (
        metadata.captured_at.year
        == 2025
    )

    assert (
        metadata.capture_id
        == "CAPTURE-001"
    )

    assert (
        metadata.flight_id
        == "FLIGHT-001"
    )

    assert (
        metadata.band_name
        == "BLUE"
    )

    assert (
        metadata.central_wavelength
        == pytest.approx(
            475.0
        )
    )


def test_rededge_band_name_is_normalized(
    tmp_path,
):

    source = (
        tmp_path
        / "IMG_0004_5.tif"
    )

    write_micasense_tiff(
        source,
        band_name="Rededge",
    )

    metadata = (
        MicaSenseMetadataService
        .extract_image_metadata(
            source
        )
    )

    assert (
        metadata.band_name
        == "RED_EDGE"
    )


def test_consistent_five_band_capture_is_accepted(
    tmp_path,
):

    files = {}

    bands = [
        (
            "BLUE",
            "Blue",
        ),
        (
            "GREEN",
            "Green",
        ),
        (
            "RED",
            "Red",
        ),
        (
            "NIR",
            "NIR",
        ),
        (
            "RED_EDGE",
            "Rededge",
        ),
    ]

    for (
        index,
        (
            expected_band,
            xmp_band,
        ),
    ) in enumerate(
        bands,
        start=1,
    ):

        source = (
            tmp_path
            / f"IMG_0004_{index}.tif"
        )

        write_micasense_tiff(
            source,
            band_name=xmp_band,
        )

        files[
            expected_band
        ] = source

    metadata = (
        MicaSenseMetadataService
        .extract_capture_metadata(
            files
        )
    )

    assert metadata.latitude == pytest.approx(
        -12.0837989,
        abs=1e-7,
    )

    assert metadata.longitude == pytest.approx(
        -76.9432990,
        abs=1e-7,
    )

    assert (
        metadata.capture_id
        == "CAPTURE-001"
    )


def test_capture_rejects_different_capture_ids(
    tmp_path,
):

    first = (
        tmp_path
        / "IMG_0004_1.tif"
    )

    second = (
        tmp_path
        / "IMG_0004_2.tif"
    )

    write_micasense_tiff(
        first,
        band_name="Blue",
        capture_id="CAPTURE-A",
    )

    write_micasense_tiff(
        second,
        band_name="Green",
        capture_id="CAPTURE-B",
    )

    with pytest.raises(
        InconsistentMicaSenseMetadataError
    ):
        (
            MicaSenseMetadataService
            .extract_capture_metadata({
                "BLUE": first,
                "GREEN": second,
            })
        )


def test_capture_rejects_wrong_xmp_band(
    tmp_path,
):

    source = (
        tmp_path
        / "IMG_0004_1.tif"
    )

    write_micasense_tiff(
        source,
        band_name="Green",
    )

    with pytest.raises(
        InconsistentMicaSenseMetadataError
    ):
        (
            MicaSenseMetadataService
            .extract_capture_metadata({
                "BLUE": source,
            })
        )


def test_tiff_without_metadata_remains_supported(
    tmp_path,
):

    source = (
        tmp_path
        / "synthetic.tif"
    )

    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        width=8,
        height=8,
        count=1,
        dtype="uint16",
    ) as dataset:

        dataset.write(
            np.ones(
                (
                    8,
                    8,
                ),
                dtype=np.uint16,
            ),
            1,
        )

    metadata = (
        MicaSenseMetadataService
        .extract_image_metadata(
            source
        )
    )

    assert metadata.latitude is None
    assert metadata.longitude is None
    assert metadata.altitude is None
    assert metadata.capture_id is None
    assert metadata.band_name is None