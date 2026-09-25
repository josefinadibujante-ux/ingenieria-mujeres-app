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
#
# Solo el superadmin -- y, para poder crear a la primerísima, también la
# cuenta de respaldo por variables de entorno -- puede crear o eliminar
# cuentas. Por eso estos tests usan admin_client (que ES esa cuenta de
# respaldo) contra las rutas de /panel-superadmin.

def test_crear_administradora_y_loguearse_con_ella(admin_client, csrf_token, client):
    email = f"{MARCA_PRUEBA}-nueva-{id(client)}@test.cl".lower()
    r = admin_client.post("/panel-superadmin/administradoras/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-superadmin"),
        "email": email, "password": "unaClaveSegura123",
    })
    assert r.status_code == 302
    pagina = admin_client.get("/panel-superadmin").data.decode()
    assert email in pagina

    # un cliente nuevo, sin sesión, se loguea con la cuenta recién creada
    r2 = client.post("/login", data={
        "email": email, "password": "unaClaveSegura123",
        "csrf_token": csrf_token(client, "/login"),
    })
    assert r2.status_code == 302 and r2.headers["Location"] == "/panel-admin"

    # limpieza
    m = re.search(r'/panel-superadmin/administradoras/eliminar/([^"]+)"', pagina)
    admin_client.post(f"/panel-superadmin/administradoras/eliminar/{m.group(1)}", data={
        "csrf_token": csrf_token(admin_client, "/panel-superadmin"),
    })


def test_contrasena_corta_rechazada(admin_client, csrf_token):
    email = f"{MARCA_PRUEBA}-corta-{id(admin_client)}@test.cl".lower()
    admin_client.post("/panel-superadmin/administradoras/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-superadmin"),
        "email": email, "password": "1234567",  # 7 caracteres, menos del mínimo
    })
    pagina = admin_client.get("/panel-superadmin").data.decode()
    assert email not in pagina


def test_correo_duplicado_rechazado(admin_client, csrf_token):
    email = f"{MARCA_PRUEBA}-dup-{id(admin_client)}@test.cl".lower()
    admin_client.post("/panel-superadmin/administradoras/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-superadmin"), "email": email, "password": "claveValida123",
    })
    r = admin_client.post("/panel-superadmin/administradoras/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-superadmin"), "email": email, "password": "otraClave456",
    })
    pagina = admin_client.get("/panel-superadmin").data.decode()
    assert "Ya existe una cuenta".encode() in r.data or "Ya existe una cuenta" in pagina

    m = re.search(r'/panel-superadmin/administradoras/eliminar/([^"]+)"', pagina)
    admin_client.post(f"/panel-superadmin/administradoras/eliminar/{m.group(1)}", data={
        "csrf_token": csrf_token(admin_client, "/panel-superadmin"),
    })


def test_no_se_puede_autoeliminar(admin_client, csrf_token, client):
    email = f"{MARCA_PRUEBA}-self-{id(client)}@test.cl".lower()
    admin_client.post("/panel-superadmin/administradoras/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-superadmin"),
        "email": email, "password": "claveValida123", "es_superadmin": "on",
    })
    pagina = admin_client.get("/panel-superadmin").data.decode()
    m = re.search(r'/panel-superadmin/administradoras/eliminar/([^"]+)"', pagina)
    doc_id = m.group(1)

    # entra CON esa cuenta (cliente propio, que es superadmin) y prueba
    # borrarse a si misma
    client.post("/login", data={
        "email": email, "password": "claveValida123",
        "csrf_token": csrf_token(client, "/login"),
    })
    client.post(f"/panel-superadmin/administradoras/eliminar/{doc_id}", data={
        "csrf_token": csrf_token(client, "/panel-superadmin"),
    })
    pagina2 = client.get("/panel-superadmin").data.decode()
    assert email in pagina2  # sigue estando, no se pudo autoeliminar

    # limpieza con la cuenta de respaldo
    admin_client.post(f"/panel-superadmin/administradoras/eliminar/{doc_id}", data={
        "csrf_token": csrf_token(admin_client, "/panel-superadmin"),
    })


def test_administradora_normal_no_puede_crear_ni_eliminar_cuentas(admin_client, csrf_token, client):
    """El pedido concreto de esta funcionalidad: solo el superadmin (y la
    cuenta de respaldo, que la necesita para crear a la primera) gestiona
    cuentas -- una administradora normal no puede, ni siquiera mandando el
    POST directo."""
    email = f"{MARCA_PRUEBA}-normal-{id(client)}@test.cl".lower()
    admin_client.post("/panel-superadmin/administradoras/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-superadmin"),
        "email": email, "password": "claveValida123",  # sin es_superadmin: administradora normal
    })

    client.post("/login", data={
        "email": email, "password": "claveValida123",
        "csrf_token": csrf_token(client, "/login"),
    })
    # no puede ver el panel de gestión de cuentas
    r = client.get("/panel-superadmin")
    assert r.status_code == 302 and r.headers["Location"] == "/panel-admin"

    # ni crear otra cuenta mandando el POST directo
    otro_email = f"{MARCA_PRUEBA}-intento-{id(client)}@test.cl".lower()
    client.post("/panel-superadmin/administradoras/agregar", data={
        "csrf_token": csrf_token(client, "/panel-admin"),
        "email": otro_email, "password": "claveValida123",
    })
    pagina = admin_client.get("/panel-superadmin").data.decode()
    assert otro_email not in pagina

    # limpieza
    m = re.search(r'/panel-superadmin/administradoras/eliminar/([^"]+)"', pagina[pagina.find(email):])
    admin_client.post(f"/panel-superadmin/administradoras/eliminar/{m.group(1)}", data={
        "csrf_token": csrf_token(admin_client, "/panel-superadmin"),
    })
