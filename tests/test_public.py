"""Páginas públicas: que carguen, que tengan las cabeceras de seguridad, y
que las rutas viejas que se borraron sigan borradas."""


def test_paginas_publicas_responden_200(client):
    for ruta in ["/", "/info_centro", "/actividades", "/trabajemos-juntas", "/proponer", "/login"]:
        r = client.get(ruta)
        assert r.status_code == 200, f"{ruta} devolvió {r.status_code}"


def test_todas_las_paginas_tienen_csp(client):
    for ruta in ["/", "/info_centro", "/actividades", "/trabajemos-juntas", "/proponer", "/login"]:
        r = client.get(ruta)
        assert r.headers.get("Content-Security-Policy") is not None
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert r.headers.get("X-Content-Type-Options") == "nosniff"


def test_ruta_vieja_club_cine_no_existe(client):
    """Se reemplazó por /trabajemos-juntas; confirma que de verdad no quedó viva."""
    assert client.get("/club_cine").status_code == 404


def test_pagina_404_personalizada(client):
    r = client.get("/esto-no-existe-nunca")
    assert r.status_code == 404
    assert b"404" in r.data


def test_inscribir_a_actividad_inexistente_no_rompe(client):
    r = client.get("/inscribir/id-que-no-existe", follow_redirects=True)
    assert r.status_code == 200
    assert b"ya no est" in r.data and b"disponible" in r.data


def test_panel_admin_sin_sesion_redirige_a_login(client):
    r = client.get("/panel-admin")
    assert r.status_code == 302
    assert r.headers["Location"] == "/login"
