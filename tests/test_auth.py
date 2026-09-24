"""Login: credenciales, CSRF, límite de intentos, cookies, y el sistema de
varias administradoras (crear/eliminar cuentas, autoeliminación bloqueada)."""
import re

import app_v2
from conftest import MARCA_PRUEBA


def test_login_credenciales_incorrectas(client, csrf_token):
    r = client.post("/login", data={
        "email": "quien-sea@test.cl", "password": "mal",
        "csrf_token": csrf_token(client, "/login"),
    })
    assert r.status_code == 200
    assert "Credenciales incorrectas".encode() in r.data


def test_login_credenciales_correctas(client, csrf_token):
    r = client.post("/login", data={
        "email": app_v2.ADMIN_USER, "password": app_v2.ADMIN_PASS,
        "csrf_token": csrf_token(client, "/login"),
    })
    assert r.status_code == 302
    assert r.headers["Location"] == "/panel-admin"


def test_login_sin_csrf_token_rechazado(client):
    r = client.post("/login", data={"email": app_v2.ADMIN_USER, "password": app_v2.ADMIN_PASS})
    assert r.status_code == 400


def test_logout_bloquea_el_panel(admin_client):
    assert admin_client.get("/panel-admin").status_code == 200
    admin_client.get("/logout")
    r = admin_client.get("/panel-admin")
    assert r.status_code == 302 and r.headers["Location"] == "/login"


def test_limite_de_intentos_bloquea_tras_cinco_fallidos(client, csrf_token):
    for _ in range(5):
        r = client.post("/login", data={
            "email": "x@x.cl", "password": "mal",
            "csrf_token": csrf_token(client, "/login"),
        })
        assert r.status_code == 200
    # el sexto, aunque use la clave CORRECTA, debe quedar bloqueado
    r = client.post("/login", data={
        "email": app_v2.ADMIN_USER, "password": app_v2.ADMIN_PASS,
        "csrf_token": csrf_token(client, "/login"),
    })
    assert r.status_code == 429
    assert "Demasiados intentos".encode() in r.data


def test_cookie_de_sesion_tiene_httponly_y_samesite(client, csrf_token):
    r = client.post("/login", data={
        "email": app_v2.ADMIN_USER, "password": app_v2.ADMIN_PASS,
        "csrf_token": csrf_token(client, "/login"),
    })
    cookie = r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_panel_admin_manda_cache_control_no_store(admin_client):
    r = admin_client.get("/panel-admin")
    assert r.headers.get("Cache-Control") == "no-store, no-cache, must-revalidate, max-age=0"


def test_paginas_publicas_no_fuerzan_cache_control(client):
    assert client.get("/").headers.get("Cache-Control") is None


# --- Administradoras (varias cuentas, cada una con su login) ---

def test_crear_administradora_y_loguearse_con_ella(admin_client, csrf_token, client):
    email = f"{MARCA_PRUEBA}-nueva-{id(client)}@test.cl".lower()
    r = admin_client.post("/panel-admin/administradoras/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
        "email": email, "password": "unaClaveSegura123",
    })
    assert r.status_code == 302
    pagina = admin_client.get("/panel-admin").data.decode()
    assert email in pagina

    # un cliente nuevo, sin sesión, se loguea con la cuenta recién creada
    r2 = client.post("/login", data={
        "email": email, "password": "unaClaveSegura123",
        "csrf_token": csrf_token(client, "/login"),
    })
    assert r2.status_code == 302 and r2.headers["Location"] == "/panel-admin"

    # limpieza
    m = re.search(r'/panel-admin/administradoras/eliminar/([^"]+)"', pagina)
    admin_client.post(f"/panel-admin/administradoras/eliminar/{m.group(1)}", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
    })


def test_contrasena_corta_rechazada(admin_client, csrf_token):
    email = f"{MARCA_PRUEBA}-corta-{id(admin_client)}@test.cl".lower()
    admin_client.post("/panel-admin/administradoras/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
        "email": email, "password": "1234567",  # 7 caracteres, menos del mínimo
    })
    pagina = admin_client.get("/panel-admin").data.decode()
    assert email not in pagina


def test_correo_duplicado_rechazado(admin_client, csrf_token):
    email = f"{MARCA_PRUEBA}-dup-{id(admin_client)}@test.cl".lower()
    admin_client.post("/panel-admin/administradoras/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"), "email": email, "password": "claveValida123",
    })
    r = admin_client.post("/panel-admin/administradoras/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"), "email": email, "password": "otraClave456",
    })
    pagina = admin_client.get("/panel-admin").data.decode()
    assert "Ya existe una cuenta".encode() in r.data or "Ya existe una cuenta" in pagina

    m = re.search(r'/panel-admin/administradoras/eliminar/([^"]+)"', pagina)
    admin_client.post(f"/panel-admin/administradoras/eliminar/{m.group(1)}", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
    })


def test_no_se_puede_autoeliminar(admin_client, csrf_token, client):
    email = f"{MARCA_PRUEBA}-self-{id(client)}@test.cl".lower()
    admin_client.post("/panel-admin/administradoras/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"), "email": email, "password": "claveValida123",
    })
    pagina = admin_client.get("/panel-admin").data.decode()
    m = re.search(r'/panel-admin/administradoras/eliminar/([^"]+)"', pagina)
    doc_id = m.group(1)

    # entra CON esa cuenta (cliente propio) y prueba borrarse a si misma
    client.post("/login", data={
        "email": email, "password": "claveValida123",
        "csrf_token": csrf_token(client, "/login"),
    })
    client.post(f"/panel-admin/administradoras/eliminar/{doc_id}", data={
        "csrf_token": csrf_token(client, "/panel-admin"),
    })
    pagina2 = client.get("/panel-admin").data.decode()
    assert email in pagina2  # sigue estando, no se pudo autoeliminar

    # limpieza con la cuenta de respaldo
    admin_client.post(f"/panel-admin/administradoras/eliminar/{doc_id}", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
    })
