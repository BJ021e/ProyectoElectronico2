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