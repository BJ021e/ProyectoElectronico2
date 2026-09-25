from InterfazInit import app, Config

def test_pe2_home_in_demo_mode(monkeypatch):
    monkeypatch.setattr(Config, "PE2_DEMO_MODE", True)

    response = app.test_client().get("/")

    assert response.status_code == 200

    html = response.get_data(as_text=True)

    assert "Plataforma UAV multiespectral" in html
    assert 'href="/campaigns"' in html
    assert 'href="/drone_operation"' in html
    assert 'href="/mission_routes"' in html

    assert "drone_agricultura_referencial.jpg" in html

    # Ocultar los accesos legacy en la demostración.
    assert 'href="/flight_history"' not in html
    assert 'href="/ground_login"' not in html


def test_pe2_home_outside_demo_mode(monkeypatch):
    monkeypatch.setattr(Config, "PE2_DEMO_MODE", False)

    response = app.test_client().get("/")

    assert response.status_code == 200

    html = response.get_data(as_text=True)

    assert 'href="/flight_history"' not in html
    assert 'href="/ground_login"' not in html


def test_pe2_home_highlights_data_acquisition_module():
    app.config["TESTING"] = True

    response = app.test_client().get("/")
    assert response.status_code == 200

    html = response.get_data(as_text=True)

    assert "Accesos rápidos" in html

    for href in (
        "/campaigns",
        "/campaigns/6",
        "/adquisicion_datos",
        "/drone_operation",
        "/mission_routes",
    ):
        assert f'href="{href}"' in html

    assert "Adquisición de datos" in html
    assert "Módulos principales" not in html
    assert "Accesos complementarios" not in html