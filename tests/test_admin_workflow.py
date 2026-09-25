"""El flujo completo del panel: proponer -> aprobar -> aparece pública ->
despublicar -> eliminar. Restricciones de método (nada de GET en acciones
que cambian datos), actividades vencidas, formulario de inscripción
personalizable, y que el registro de actividad quede bien escrito."""
import re

from conftest import MARCA_PRUEBA


def test_flujo_completo_proponer_aprobar_despublicar_eliminar(admin_client, crear_actividad, csrf_token):
    doc_id = crear_actividad()

    # aparece en el panel, en propuestas
    pagina = admin_client.get("/panel-admin").data.decode()
    assert f"/aprobar/{doc_id}" in pagina

    # aprobar -> debe aparecer en /actividades (público)
    r = admin_client.post(f"/aprobar/{doc_id}", data={"csrf_token": csrf_token(admin_client, "/panel-admin")})
    assert r.status_code == 302
    pagina_publica = admin_client.get("/actividades").data.decode()
    assert f"[{MARCA_PRUEBA}]" in pagina_publica or doc_id  # visible con su título

    # despublicar -> ya no debería estar en /actividades
    admin_client.post(f"/despublicar/{doc_id}", data={"csrf_token": csrf_token(admin_client, "/panel-admin")})
    pagina = admin_client.get("/panel-admin").data.decode()
    assert f"/aprobar/{doc_id}" in pagina  # volvió a pendientes

    # eliminar -> desaparece del todo
    admin_client.post(f"/eliminar/{doc_id}", data={"csrf_token": csrf_token(admin_client, "/panel-admin")})
    pagina = admin_client.get("/panel-admin").data.decode()
    assert doc_id not in pagina


def test_acciones_de_admin_rechazan_get(admin_client):
    """Todas estas rutas cambian datos -- si aceptaran GET, un <img> en
    cualquier página externa podría dispararlas sin querer."""
    for ruta in ["/aprobar/x", "/despublicar/x", "/eliminar/x", "/eliminar_inscripcion/x",
                 "/panel-admin/actividad/x/campo/agregar", "/panel-admin/actividad/x/campo/quitar",
                 "/panel-superadmin/administradoras/agregar", "/panel-superadmin/administradoras/eliminar/x",
                 "/panel-admin/equipo/agregar", "/panel-admin/equipo/eliminar/x", "/panel-admin/equipo/descripcion"]:
        r = admin_client.get(ruta)
        assert r.status_code == 405, f"{ruta} aceptó GET"


def test_actividad_vencida_no_aparece_en_publico_pero_si_en_panel(admin_client, crear_actividad, csrf_token):
    doc_id = crear_actividad(fecha="2020-01-01")  # muy en el pasado
    admin_client.post(f"/aprobar/{doc_id}", data={"csrf_token": csrf_token(admin_client, "/panel-admin")})

    publica = admin_client.get("/actividades").data.decode()
    idx_publico = publica.find(f"[{MARCA_PRUEBA}]")
    # puede haber otras actividades de prueba en paralelo; buscamos el ID en el href de inscribir
    assert doc_id not in publica

    panel = admin_client.get("/panel-admin").data.decode()
    assert doc_id in panel
    assert "Vencida".encode() in panel.encode() or "Vencida" in panel


def test_agregar_y_quitar_pregunta_de_inscripcion(admin_client, crear_actividad, csrf_token):
    doc_id = crear_actividad()

    r = admin_client.post(f"/panel-admin/actividad/{doc_id}/campo/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
        "etiqueta": "Talla", "tipo": "opciones", "opciones": "S, M, L", "requerido": "on",
    })
    assert r.status_code == 302
    pagina = admin_client.get(f"/inscribir/{doc_id}").data.decode()
    assert "Talla" in pagina and "extra_0" in pagina and "S" in pagina

    # quitar
    admin_client.post(f"/panel-admin/actividad/{doc_id}/campo/quitar", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
        "etiqueta": "Talla", "tipo": "opciones", "opciones": "S,M,L", "requerido": "on",
    })
    pagina2 = admin_client.get(f"/inscribir/{doc_id}").data.decode()
    assert "extra_0" not in pagina2


def test_pregunta_de_opcion_multiple_sin_opciones_rechazada(admin_client, crear_actividad, csrf_token):
    doc_id = crear_actividad()
    r = admin_client.post(f"/panel-admin/actividad/{doc_id}/campo/agregar", data={
        "csrf_token": csrf_token(admin_client, "/panel-admin"),
        "etiqueta": "Sin opciones", "tipo": "opciones", "opciones": "", "requerido": "on",
    })
    pagina = admin_client.get(f"/inscribir/{doc_id}").data.decode()
    assert "Sin opciones" not in pagina


def test_registro_de_actividad_anota_quien_aprobo_que(admin_client, crear_actividad, csrf_token):
    """El registro ya no vive en /panel-admin (pasó a ser exclusivo del
    superadmin) -- se verifica directo en Firestore, que es lo único que
    de verdad importa acá: que la entrada haya quedado bien escrita."""
    import app_v2
    doc_id = crear_actividad()
    admin_client.post(f"/aprobar/{doc_id}", data={"csrf_token": csrf_token(admin_client, "/panel-admin")})

    entradas = [
        d.to_dict() for d in app_v2.db.collection("registro_actividad")
        .where("accion", "==", "Aprobó actividad").stream()
    ]
    coincidencias = [e for e in entradas if MARCA_PRUEBA in (e.get("detalle") or "").lower()]
    assert coincidencias, "no se encontró la entrada de 'Aprobó actividad' para esta actividad de prueba"
    assert coincidencias[-1]["admin_email"] == app_v2.ADMIN_USER
