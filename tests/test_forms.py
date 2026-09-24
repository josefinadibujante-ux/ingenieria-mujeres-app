"""/proponer e /inscribir: validación del lado del servidor y límite de
envíos por IP. El flujo "feliz" completo (proponer -> aprobar -> aparece
público -> inscribirse) está en test_admin_workflow.py."""
import re

from conftest import MARCA_PRUEBA


def test_proponer_sin_titulo_rechazado(client, csrf_token):
    r = client.post("/proponer", data={
        "csrf_token": csrf_token(client, "/proponer"),
        "rol": "alumno", "titulo": "", "categoria": "Talleres",
        "fecha": "2026-12-01", "descripcion": "algo",
    })
    assert r.status_code == 400


def test_proponer_tutora_sin_habilidad_ni_contacto_rechazado(client, csrf_token):
    r = client.post("/proponer", data={
        "csrf_token": csrf_token(client, "/proponer"),
        "rol": "tutor", "titulo": f"[{MARCA_PRUEBA}] Taller X", "categoria": "Talleres",
        "fecha": "2026-12-01", "descripcion": "algo", "habilidad": "", "contacto": "",
    })
    assert r.status_code == 400


def test_proponer_categoria_invalida_cae_a_talleres(admin_client, csrf_token):
    """Manda una categoría que no existe (bypaseando el <select> del HTML);
    el servidor no debe guardarla tal cual, sino usar un valor válido."""
    r = admin_client.post("/proponer", data={
        "csrf_token": csrf_token(admin_client, "/proponer"),
        "rol": "alumno", "titulo": f"[{MARCA_PRUEBA}] Categoria rara", "categoria": "<script>",
        "fecha": "2026-12-01", "descripcion": "algo",
    })
    assert r.status_code == 302
    pagina = admin_client.get("/panel-admin").data.decode()
    assert "<script>" not in pagina.split(f"[{MARCA_PRUEBA}] Categoria rara")[1][:200]

    # limpieza
    idx = pagina.find(f"[{MARCA_PRUEBA}] Categoria rara")
    m = re.search(r'/eliminar/([^"]+)"', pagina[idx:])
    admin_client.post(f"/eliminar/{m.group(1)}", data={"csrf_token": csrf_token(admin_client, "/panel-admin")})


def test_proponer_rate_limit_veinte_por_hora(client, csrf_token):
    for i in range(20):
        r = client.post("/proponer", data={
            "csrf_token": csrf_token(client, "/proponer"),
            "rol": "alumno", "titulo": f"[{MARCA_PRUEBA}] Spam {i}", "categoria": "Talleres",
            "fecha": "2026-12-01", "descripcion": "x",
        })
        assert r.status_code == 302
    r = client.post("/proponer", data={
        "csrf_token": csrf_token(client, "/proponer"),
        "rol": "alumno", "titulo": f"[{MARCA_PRUEBA}] Spam 21", "categoria": "Talleres",
        "fecha": "2026-12-01", "descripcion": "x",
    })
    assert r.status_code == 429

    # limpieza: las 20 quedaron creadas de verdad, hay que borrarlas
    import app_v2
    for doc in app_v2.db.collection("actividades").stream():
        if MARCA_PRUEBA in (doc.to_dict().get("titulo") or "").lower():
            doc.reference.delete()


def test_inscribir_sin_nombre_ni_contacto_rechazado(crear_actividad, client, csrf_token):
    doc_id = crear_actividad()
    r = client.post(f"/inscribir/{doc_id}", data={
        "csrf_token": csrf_token(client, f"/inscribir/{doc_id}"),
        "nombre": "", "contacto": "",
    })
    assert r.status_code == 400


def test_inscribir_pregunta_obligatoria_faltante_rechazada(admin_client, crear_actividad, csrf_token):
    doc_id = crear_actividad()
    admin_client.post(f"/panel-admin/actividad/{doc_id}/campo/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
        "etiqueta": "RUT", "tipo": "texto", "requerido": "on",
    })
    r = admin_client.post(f"/inscribir/{doc_id}", data={
        "csrf_token": csrf_token(admin_client, f"/inscribir/{doc_id}"),
        "nombre": "Alguien", "contacto": "a@a.cl", "extra_0": "",
    })
    assert r.status_code == 400
    assert "RUT".encode() in r.data


def test_inscribir_guarda_las_respuestas_dinamicas(admin_client, crear_actividad, csrf_token):
    doc_id = crear_actividad()
    admin_client.post(f"/panel-admin/actividad/{doc_id}/campo/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
        "etiqueta": "Nivel", "tipo": "texto", "requerido": "on",
    })
    r = admin_client.post(f"/inscribir/{doc_id}", data={
        "csrf_token": csrf_token(admin_client, f"/inscribir/{doc_id}"),
        "nombre": "Valentina Paz", "contacto": "v@a.cl", "extra_0": "Intermedio",
    })
    assert r.status_code == 302
    pagina = admin_client.get("/panel-admin").data.decode()
    assert "Valentina Paz" in pagina and "Intermedio" in pagina
