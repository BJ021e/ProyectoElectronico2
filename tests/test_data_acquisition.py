from InterfazInit import app


def test_data_acquisition_view_is_available():
    app.config["TESTING"] = True

    client = app.test_client()
    response = client.get("/adquisicion_datos")

    assert response.status_code == 200

    html = response.get_data(as_text=True)

    for marker in (
        "Adquisición de datos",
        "Campaña destino",
        "CP-20260907-0006",
        "Importar carpeta RedEdge",
        "Recepción desde cámara",
        "Iniciar recepción",
        "Ver campaña completada",
        "Transferencia completada",
    ):
        assert marker in html


def test_data_acquisition_contains_pe2_navigation():
    app.config["TESTING"] = True

    client = app.test_client()
    response = client.get("/adquisicion_datos")

    assert response.status_code == 200

    html = response.get_data(as_text=True)

    for href in (
        'href="/"',
        'href="/campaigns"',
        'href="/adquisicion_datos"',
        'href="/drone_operation"',
        'href="/mission_routes"',
        'href="/campaigns/6"',
    ):
        assert href in html

    assert 'class="active">Adquisición de datos' in html


def test_data_acquisition_describes_visual_reception_flow():
    app.config["TESTING"] = True

    client = app.test_client()
    response = client.get("/adquisicion_datos")

    assert response.status_code == 200

    html = response.get_data(as_text=True)

    for marker in (
        "Simulación visual",
        "cámara o módulo bridge",
        "Conectando con cámara / bridge",
        "Recibiendo imágenes multiespectrales",
        "Validando bandas RedEdge",
        "Asociando capturas a campaña",
        "Campaña lista para revisión",
        "335 capturas asociadas al flujo multiespectral",
    ):
        assert marker in html