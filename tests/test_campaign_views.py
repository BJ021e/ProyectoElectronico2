from InterfazInit import app


def test_campaigns_view_is_available():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns"
    )

    assert response.status_code == 200

    html = response.get_data(
        as_text=True
    )

    assert (
        "Campañas de adquisición"
        in html
    )

    assert (
        "/api/campaigns"
        in html
    )


def test_campaign_detail_view_is_available():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns/123"
    )

    assert response.status_code == 200

    html = response.get_data(
        as_text=True
    )

    assert (
        "Detalle de campaña"
        in html
    )

    assert (
        "123"
        in html
    )
    
def test_campaign_detail_contains_domain_sections():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns/123"
    )

    assert response.status_code == 200

    html = response.get_data(
        as_text=True
    )

    assert (
        "Información general"
        in html
    )

    assert "Capturas" in html

    assert "Procesamiento" in html

    assert (
        "Productos geoespaciales"
        in html
    )

    assert (
        "Procesar campaña"
        in html
    )


def test_campaign_detail_uses_geospatial_apis():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns/7"
    )

    html = response.get_data(
        as_text=True
    )

    assert (
        "/api/campaigns/${CAMPAIGN_ID}/captures"
        in html
    )

    assert (
        "/api/campaigns/${CAMPAIGN_ID}/processing-jobs"
        in html
    )

    assert (
        "/api/campaigns/${CAMPAIGN_ID}/products"
        in html
    )

    assert (
        "/api/campaigns/${CAMPAIGN_ID}/process"
        in html
    )

def test_campaign_detail_contains_rededge_import_controls():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns/123"
    )

    assert response.status_code == 200

    html = response.get_data(
        as_text=True
    )

    assert (
        "Importar carpeta RedEdge"
        in html
    )

    assert (
        'id="redEdgeFolderInput"'
        in html
    )

    assert "webkitdirectory" in html

    assert (
        'id="redEdgeModal"'
        in html
    )


def test_campaign_detail_uses_rededge_import_api():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns/9"
    )

    assert response.status_code == 200

    html = response.get_data(
        as_text=True
    )

    assert (
        "/rededge/import"
        in html
    )

    assert (
        "/rededge/staging/"
        in html
    )
    
def test_campaign_detail_contains_rededge_progress():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns/11"
    )

    html = response.get_data(
        as_text=True
    )

    assert (
        'id="redEdgeUploadProgress"'
        in html
    )

    assert (
        'id="redEdgeProgressBar"'
        in html
    )

    assert (
        "buildRedEdgeBatches"
        in html
    )


def test_campaign_detail_uses_batch_staging_api():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns/11"
    )

    html = response.get_data(
        as_text=True
    )

    assert (
        "/rededge/staging"
        in html
    )

    assert (
        "/files"
        in html
    )

    assert (
        "/inspect"
        in html
    )
    
def test_campaign_detail_contains_gis_viewer():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns/20"
    )

    assert response.status_code == 200

    html = response.get_data(
        as_text=True
    )

    assert (
        'id="campaignMap"'
        in html
    )

    assert "Visor GIS" in html

    assert (
        'id="gisCaptureCount"'
        in html
    )

    assert (
        'id="gisProductCount"'
        in html
    )


def test_campaign_detail_loads_leaflet():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns/20"
    )

    html = response.get_data(
        as_text=True
    )

    assert (
        "leaflet@1.9.4"
        in html
    )

    assert (
        "initializeCampaignMap"
        in html
    )

    assert (
        "renderCampaignMap"
        in html
    )


def test_campaign_detail_renders_geospatial_geometries():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns/20"
    )

    html = response.get_data(
        as_text=True
    )

    assert (
        "getCaptureCoordinate"
        in html
    )

    assert (
        "getProductWgs84Bounds"
        in html
    )

    assert (
        "renderCaptureGeometries"
        in html
    )

    assert (
        "renderProductGeometries"
        in html
    )

def test_campaign_detail_contains_raster_preview_state():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns/25"
    )

    html = response.get_data(
        as_text=True
    )

    assert (
        'id="gisRasterCount"'
        in html
    )

    assert (
        "gisRasterLayer"
        in html
    )

    assert (
        "rasterPreviewPane"
        in html
    )


def test_campaign_detail_uses_geospatial_preview_endpoint():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns/25"
    )

    html = response.get_data(
        as_text=True
    )

    assert (
        "/preview.png"
        in html
    )

    assert (
        "L.imageOverlay"
        in html
    )


def test_campaign_detail_selects_primary_raster_product():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns/25"
    )

    html = response.get_data(
        as_text=True
    )

    assert (
        "selectRasterPreviewProduct"
        in html
    )

    assert (
        "ORTHOMOSAIC_RGB"
        in html
    )

    assert (
        "ORTHOMOSAIC_MULTISPECTRAL"
        in html
    )
    
def test_campaign_detail_does_not_convert_missing_coordinates_to_zero():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns/30"
    )

    assert response.status_code == 200

    html = response.get_data(
        as_text=True
    )

    assert (
        "rawLatitude === null"
        in html
    )

    assert (
        "rawLongitude === null"
        in html
    )

    assert (
        "rawLatitude === undefined"
        in html
    )

    assert (
        "rawLongitude === undefined"
        in html
    )

def test_campaign_detail_contains_multispectral_layer_selector():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns/40"
    )

    html = response.get_data(
        as_text=True
    )

    assert (
        'id="gisRasterMode"'
        in html
    )

    assert (
        'value="natural"'
        in html
    )

    assert (
        'value="blue"'
        in html
    )

    assert (
        'value="nir"'
        in html
    )

    assert (
        'value="red_edge"'
        in html
    )


def test_campaign_detail_preview_uses_raster_mode():

    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get(
        "/campaigns/40"
    )

    html = response.get_data(
        as_text=True
    )

    assert (
        "currentRasterMode"
        in html
    )

    assert (
        "encodeURIComponent"
        in html
    )

    assert (
        "?mode="
        in html
    )

