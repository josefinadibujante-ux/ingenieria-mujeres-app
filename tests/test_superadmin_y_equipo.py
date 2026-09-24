"""Cuenta de superadmin (solo ve el registro de actividad de todas las
cuentas, no gestiona nada) y el equipo (integrantes + descripción que se
muestran en /info_centro)."""
import re

import app_v2
from conftest import MARCA_PRUEBA


def _crear_superadmin(admin_client, csrf_token):
    """Crea una cuenta de superadmin de prueba y devuelve (email, id)."""
    email = f"{MARCA_PRUEBA}-super-{id(admin_client)}@test.cl".lower()
    admin_client.post("/panel-admin/administradoras/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
        "email": email, "password": "claveSuperSegura123", "es_superadmin": "on",
    })
    doc_id = None
    for d in app_v2.db.collection("administradoras").where("email", "==", email).stream():
        doc_id = d.id
    assert doc_id, "no se encontró la cuenta de superadmin recién creada"
    return email, doc_id


def test_login_de_superadmin_redirige_a_su_propio_panel(admin_client, client, csrf_token):
    email, doc_id = _crear_superadmin(admin_client, csrf_token)
    r = client.post("/login", data={
        "email": email, "password": "claveSuperSegura123",
        "csrf_token": csrf_token(client, "/login"),
    })
    assert r.status_code == 302 and r.headers["Location"] == "/panel-superadmin"

    admin_client.post(f"/panel-admin/administradoras/eliminar/{doc_id}", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
    })


def test_superadmin_ve_el_registro_de_otra_cuenta(admin_client, crear_actividad, client, csrf_token):
    doc_actividad = crear_actividad()
    admin_client.post(f"/aprobar/{doc_actividad}", data={"csrf_token": csrf_token(admin_client, "/panel-admin")})

    email, doc_id = _crear_superadmin(admin_client, csrf_token)
    client.post("/login", data={
        "email": email, "password": "claveSuperSegura123",
        "csrf_token": csrf_token(client, "/login"),
    })
    pagina = client.get("/panel-superadmin").data.decode()
    assert app_v2.ADMIN_USER in pagina  # ve la acción hecha por la OTRA cuenta
    assert "Aprobó actividad" in pagina

    admin_client.post(f"/panel-admin/administradoras/eliminar/{doc_id}", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
    })


def test_superadmin_no_puede_entrar_al_panel_normal(admin_client, client, csrf_token):
    email, doc_id = _crear_superadmin(admin_client, csrf_token)
    client.post("/login", data={
        "email": email, "password": "claveSuperSegura123",
        "csrf_token": csrf_token(client, "/login"),
    })
    r = client.get("/panel-admin")
    assert r.status_code == 302 and r.headers["Location"] == "/panel-superadmin"

    admin_client.post(f"/panel-admin/administradoras/eliminar/{doc_id}", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
    })


def test_administradora_normal_no_puede_entrar_al_panel_de_superadmin(admin_client):
    r = admin_client.get("/panel-superadmin")
    assert r.status_code == 302 and r.headers["Location"] == "/panel-admin"


# --- Equipo ---

def test_agregar_y_quitar_integrante_del_equipo(admin_client, csrf_token):
    nombre = f"[{MARCA_PRUEBA}] Integrante de prueba"
    r = admin_client.post("/panel-admin/equipo/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
        "nombre": nombre, "rol": "Rol de prueba",
    })
    assert r.status_code == 302

    pagina = admin_client.get("/panel-admin").data.decode()
    assert nombre in pagina and "Rol de prueba" in pagina

    publica = admin_client.get("/info_centro").data.decode()
    assert nombre in publica and "Rol de prueba" in publica

    m = re.search(r'/panel-admin/equipo/eliminar/([^"]+)"', pagina)
    assert m
    admin_client.post(f"/panel-admin/equipo/eliminar/{m.group(1)}", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
    })
    # tras eliminar, el nombre solo debería quedar en el mensaje flash de
    # confirmación ("se sacó del equipo") -- no en la lista/tab-equipo.
    pagina2 = admin_client.get("/panel-admin").data.decode()
    assert "Todavía no cargaste ninguna integrante" in pagina2


def test_integrante_sin_nombre_rechazada(admin_client, csrf_token):
    r = admin_client.post("/panel-admin/equipo/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
        "nombre": "", "rol": "Algo",
    })
    assert r.status_code == 302
    pagina = admin_client.get("/panel-admin").data.decode()
    assert "Escribe el nombre".encode() in pagina.encode()


def test_actualizar_descripcion_del_equipo_y_restaurar(admin_client, csrf_token):
    """configuracion/equipo es un documento único (no algo descartable como
    las demás pruebas) -- este test guarda el valor real que hubiera antes
    de tocarlo, y lo deja EXACTAMENTE como estaba al terminar."""
    doc_ref = app_v2.db.collection("configuracion").document("equipo")
    original = doc_ref.get().to_dict() or {}

    try:
        texto_prueba = f"[{MARCA_PRUEBA}] Descripción de prueba."
        r = admin_client.post("/panel-admin/equipo/descripcion", data={
            "csrf_token": csrf_token(admin_client, "/panel-admin"),
            "descripcion": texto_prueba,
        })
        assert r.status_code == 302
        publica = admin_client.get("/info_centro").data.decode()
        # sin integrantes cargadas la sección no se muestra -- se agrega una
        # temporal solo para poder ver el texto en la página pública
        admin_client.post("/panel-admin/equipo/agregar", data={
            "csrf_token": csrf_token(admin_client, "/panel-admin"),
            "nombre": f"[{MARCA_PRUEBA}] Temporal", "rol": "",
        })
        publica2 = admin_client.get("/info_centro").data.decode()
        assert texto_prueba in publica2

        # limpieza de la integrante temporal
        pagina = admin_client.get("/panel-admin").data.decode()
        idx = pagina.find(f"[{MARCA_PRUEBA}] Temporal")
        m = re.search(r'/panel-admin/equipo/eliminar/([^"]+)"', pagina[idx:])
        admin_client.post(f"/panel-admin/equipo/eliminar/{m.group(1)}", data={
            "csrf_token": csrf_token(admin_client, "/panel-admin"),
        })
    finally:
        if original:
            doc_ref.set(original)
        else:
            doc_ref.delete()
