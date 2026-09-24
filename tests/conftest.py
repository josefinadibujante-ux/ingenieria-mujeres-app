"""
Infraestructura compartida de los tests.

IMPORTANTE: estos tests corren contra el Firestore REAL configurado por tus
variables de entorno (el mismo que usa `python app_v2.py`) -- no hay una
base de datos de prueba separada. Por eso:

  - Todo documento que crea un test lleva la marca MARCA_PRUEBA en algún
    campo de texto.
  - Al empezar y al terminar la sesión de tests se borra cualquier
    documento que tenga esa marca, en las 4 colecciones que usa la app --
    así, aunque una corrida anterior se haya cortado a la mitad por un
    error, no queda basura de prueba dando vueltas.
  - Nunca corras esto apuntando a un Firestore con datos reales de
    producción sin revisar antes que el barrido por marca no vaya a tocar
    nada tuyo (no debería, porque solo borra lo que tiene la marca).
"""
import os
import re
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app_v2  # noqa: E402

# Credenciales fijas para que los tests no dependan de lo que tengas en tu
# .env real -- así "pytest" da el mismo resultado sin importar quién lo corra.
app_v2.ADMIN_USER = "admin@pytest.local"
app_v2.ADMIN_PASS = "clave-de-pruebas-1234"
app_v2.app.secret_key = "clave-de-pruebas-no-usar-en-produccion"
app_v2.app.config["TESTING"] = True

# Sin corchetes ni mayúsculas fijas a propósito: así se puede meter tal cual
# adentro de un email de prueba (nombre.testpytest.algo@test.cl) sin romper
# el formato. El barrido busca este texto sin importar mayúsculas/minúsculas.
MARCA_PRUEBA = "testpytest"
COLECCIONES = ("actividades", "inscripciones", "administradoras", "registro_actividad", "equipo")
# "configuracion" queda AFUERA del barrido a propósito: no es una colección
# de documentos descartables como las demás, es un documento único
# (configuracion/equipo) que puede tener contenido real tuyo -- el test que
# lo toca guarda el valor original y lo restaura él mismo (ver test_equipo.py).


def _barrer_datos_de_prueba():
    """Borra por dos criterios independientes, para no depender de que la
    marca haya quedado en el campo justo: (a) cualquier documento con la
    marca en algún campo de texto, y (b) en registro_actividad, cualquier
    entrada hecha por la cuenta de administradora exclusiva de los tests
    (nadie real usa ese correo)."""
    borrados = 0
    for coleccion in COLECCIONES:
        for doc in app_v2.db.collection(coleccion).stream():
            datos = doc.to_dict() or {}
            texto = " ".join(str(v) for v in datos.values()).lower()
            marcado = MARCA_PRUEBA in texto
            es_admin_de_prueba = coleccion == "registro_actividad" and datos.get("admin_email") == app_v2.ADMIN_USER
            if marcado or es_admin_de_prueba:
                doc.reference.delete()
                borrados += 1
    return borrados


@pytest.fixture(scope="session", autouse=True)
def _firestore_limpio_antes_y_despues():
    _barrer_datos_de_prueba()
    yield
    _barrer_datos_de_prueba()


@pytest.fixture(autouse=True)
def _sin_limites_de_intentos_entre_tests():
    """Los contadores de fuerza bruta / spam son en memoria y compartidos
    por todo el proceso -- sin esto, un test de rate-limit dejaría
    bloqueado al siguiente test que use la misma ruta."""
    app_v2._intentos_fallidos.clear()
    app_v2._envios_por_ip.clear()
    yield


@pytest.fixture
def client():
    """Un cliente de prueba SIN sesión iniciada. Cada fixture `client` y
    `admin_client` usa su propio test_client() -- a propósito, no comparten
    cookies, porque varios tests necesitan dos sesiones distintas a la vez
    (ej. una admin haciendo algo, y una cuenta nueva logueándose aparte)."""
    return app_v2.app.test_client()


def _obtener_csrf(client_obj, path):
    html = client_obj.get(path).data.decode()
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert m, f"No se encontró csrf_token en {path}"
    return m.group(1)


@pytest.fixture
def csrf_token():
    """Uso: csrf_token(client, '/login') -> el token para ESE cliente y ESA
    página. Recibe el cliente explícitamente a propósito: un token sacado
    de la sesión de un cliente no sirve para un POST hecho con otro."""
    return _obtener_csrf


@pytest.fixture
def admin_client(csrf_token):
    """Cliente propio, ya logueado con la cuenta de respaldo
    (ADMIN_USER/ADMIN_PASS) -- independiente del fixture `client`."""
    c = app_v2.app.test_client()
    r = c.post("/login", data={
        "email": app_v2.ADMIN_USER,
        "password": app_v2.ADMIN_PASS,
        "csrf_token": csrf_token(c, "/login"),
    })
    assert r.status_code == 302 and r.headers["Location"] == "/panel-admin"
    return c


@pytest.fixture
def crear_actividad(admin_client, csrf_token):
    """Devuelve una función para proponer una actividad de prueba (con la
    cuenta admin_client); borra todas las que se hayan creado con ella al
    terminar el test, sin importar en qué estado hayan quedado."""
    ids_creados = []

    def _crear(**overrides):
        datos = {
            "csrf_token": csrf_token(admin_client, "/proponer"),
            "rol": "alumno",
            "titulo": f"[{MARCA_PRUEBA}] Actividad de prueba {time.time()}",
            "categoria": "Talleres",
            "fecha": "2026-12-01",
            "descripcion": f"[{MARCA_PRUEBA}] Descripción de prueba.",
        }
        datos.update(overrides)
        r = admin_client.post("/proponer", data=datos)
        assert r.status_code == 302, r.data
        pagina = admin_client.get("/panel-admin").data.decode()
        titulo = datos["titulo"]
        # Busca el bloque de esa propuesta puntual por su título, para no
        # agarrar el id de otra tarjeta si hay varias en la página.
        idx = pagina.find(titulo)
        assert idx != -1, f"No se encontró '{titulo}' en el panel tras proponerla"
        m = re.search(r'/aprobar/([^"]+)"', pagina[idx:])
        assert m, "No se encontró el botón Aprobar para la propuesta creada"
        doc_id = m.group(1)
        ids_creados.append(doc_id)
        return doc_id

    yield _crear

    for doc_id in ids_creados:
        app_v2.db.collection("actividades").document(doc_id).delete()
        for insc in app_v2.db.collection("inscripciones").where("actividad_id", "==", doc_id).stream():
            insc.reference.delete()
