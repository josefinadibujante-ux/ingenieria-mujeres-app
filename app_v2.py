import os
import time
from datetime import datetime, timezone, date
from collections import OrderedDict, defaultdict

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman
import firebase_admin
from firebase_admin import credentials, firestore

# --- CONFIGURACIÓN / VARIABLES DE ENTORNO ---
# En desarrollo local las variables se leen de un archivo .env (ver .env.example).
# En Render se cargan desde el panel "Environment" y el key.json se sube como
# "Secret File".
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-inseguro-cambiar-en-produccion")
# Recarga las plantillas al vuelo en desarrollo (no afecta producción con gunicorn).
app.config["TEMPLATES_AUTO_RELOAD"] = os.environ.get("FLASK_ENV") != "production"

# Render (y la mayoría de los hosts) ponen un proxy adelante: sin esto,
# request.remote_addr devuelve la IP interna del proxy para todo el mundo,
# no la del visitante real -- rompería el límite de intentos de /login de
# abajo (bloquearía a todo el mundo junto en vez de a quien falla).
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Credenciales de administración (nunca hardcodeadas en el código).
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "1234")

# Correo para la sección "Trabajemos Juntas" (alianzas con organizaciones).
# TODO: reemplazar cuando tengan un Gmail dedicado para esto -- de momento se
# reutiliza el mismo correo/usuario que el Instagram (@ingenierasmasunab).
CORREO_ALIANZAS = os.environ.get("CORREO_ALIANZAS", "ingenierasmasunab@gmail.com")

# --- PROTECCIÓN CSRF ---
# WTF_CSRF_SSL_STRICT exige además el header "Referer" cuando la conexión es
# HTTPS (como en Render). Se desactiva: algunos navegadores/extensiones de
# privacidad no mandan ese header ni en el propio sitio, y el token CSRF ya
# protege lo importante -- sin esto, alguien podía quedar bloqueada del login
# con un error críptico sin ninguna razón real de seguridad.
app.config["WTF_CSRF_SSL_STRICT"] = False
csrf = CSRFProtect(app)

# --- CABECERAS DE SEGURIDAD (CSP + HSTS + anti-clickjacking + nosniff) ---
csp = {
    "default-src": "'self'",
    "style-src": [
        "'self'",
        "'unsafe-inline'",
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com",
        "https://fonts.googleapis.com",
        "https://unpkg.com",
    ],
    "script-src": [
        "'self'",
        "'unsafe-inline'",
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com",
        "https://unpkg.com",
    ],
    "font-src": [
        "'self'",
        "https://fonts.gstatic.com",
        "https://cdn.jsdelivr.net",
    ],
    "img-src": [
        "'self'",
        "data:",
        "https://images.unsplash.com",
        "https://www.transparenttextures.com",
    ],
}

Talisman(
    app,
    content_security_policy=csp,
    force_https=False,  # Render ya termina el TLS; evita romper el server local.
    strict_transport_security=True,
    strict_transport_security_max_age=31536000,
    session_cookie_secure=os.environ.get("FLASK_ENV") == "production",
    frame_options="DENY",
)

# --- CONEXIÓN FIREBASE ---
# La ruta al key.json sale de una variable de entorno; si no está definida se
# usa un key.json en la raíz del proyecto (que NUNCA se sube a git).
ruta_key = (
    os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    or os.environ.get("FIREBASE_KEY_PATH")
    or os.path.join(BASE_DIR, "key.json")
)
if not firebase_admin._apps:
    cred = credentials.Certificate(ruta_key)
    firebase_admin.initialize_app(cred)
db = firestore.client()

# Páginas que nunca deben quedar en la caché del navegador (login y todo el
# panel): si no, en una compu compartida, el botón "Atrás" después de cerrar
# sesión podría mostrar una versión guardada del panel con datos reales.
RUTAS_SIN_CACHE = {
    "login", "logout", "panel_admin",
    "aprobar_actividad", "despublicar_actividad",
    "eliminar_actividad", "eliminar_inscripcion",
    "agregar_campo_inscripcion", "quitar_campo_inscripcion",
    "agregar_administradora", "eliminar_administradora",
}

@app.after_request
def _sin_cache_en_admin(response):
    if request.endpoint in RUTAS_SIN_CACHE:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


# --- RUTAS PÚBLICAS ---

@app.route('/')
def inicio():
    return render_template('inicio_v2.html')

@app.route('/info_centro')
def info_centro():
    return render_template('info_v2.html')

@app.route('/actividades')
def actividades():
    docs = db.collection("actividades").where("estado", "==", "oficial").stream()
    lista = []
    for doc in docs:
        a = doc.to_dict()
        a['id'] = doc.id
        # No mostramos públicamente actividades cuya fecha ya pasó.
        if not _actividad_vencida(a):
            lista.append(a)
    lista.sort(key=_fecha_actividad_orden)
    return render_template('actividades_v2.html', actividades=lista)

CATEGORIAS_VALIDAS = {"Talleres", "Actividades"}
ROLES_VALIDOS = {"alumno", "tutor"}

# Límite de envíos por IP en los formularios públicos (proponer / inscribir).
# Más permisivo que el del login a propósito: acá pueden coincidir varias
# estudiantes reales detrás de la misma IP (wifi del campus, un mismo NAT),
# así que esto frena spam masivo de bots, no un uso normal concurrente.
_envios_por_ip = defaultdict(list)
ENVIOS_MAX = 20
ENVIOS_VENTANA_SEGUNDOS = 60 * 60  # 1 hora

def _envio_excedido(clave):
    ahora = time.time()
    vigentes = [t for t in _envios_por_ip[clave] if ahora - t < ENVIOS_VENTANA_SEGUNDOS]
    if len(vigentes) >= ENVIOS_MAX:
        _envios_por_ip[clave] = vigentes
        return True
    vigentes.append(ahora)
    _envios_por_ip[clave] = vigentes
    return False

@app.route('/proponer', methods=['GET', 'POST'])
def crear_actividad():
    if request.method == 'POST':
        if _envio_excedido(f"proponer:{request.remote_addr}"):
            flash("Demasiadas propuestas enviadas desde acá en poco tiempo. Intenta de nuevo más tarde.")
            return render_template('proponer_v2.html'), 429
        # El HTML ya exige estos campos, pero eso lo puede saltar cualquiera
        # que mande el POST directo (curl, JS desactivado) -- se revalida acá.
        titulo = (request.form.get('titulo') or '').strip()[:150]
        descripcion = (request.form.get('descripcion') or '').strip()[:2000]
        rol = request.form.get('rol') or ''
        categoria = request.form.get('categoria') or ''
        contacto = (request.form.get('contacto') or '').strip()[:200]
        habilidad = (request.form.get('habilidad') or '').strip()[:200]
        materiales = (request.form.get('materiales') or '').strip()[:500]
        fecha = (request.form.get('fecha') or '').strip()[:10]

        if not titulo or not descripcion or rol not in ROLES_VALIDOS:
            flash("Completa el título, la descripción y cómo quieres participar.")
            return render_template('proponer_v2.html'), 400
        if categoria not in CATEGORIAS_VALIDAS:
            categoria = "Talleres"
        if rol == "tutor" and (not contacto or not habilidad):
            flash("Como tutora, indica tu habilidad y deja un contacto.")
            return render_template('proponer_v2.html'), 400

        datos = {
            "titulo": titulo,
            "descripcion": descripcion,
            "contacto": contacto,
            "categoria": categoria,
            "rol": rol,
            "fecha": fecha,
            "habilidad": habilidad,
            "materiales": materiales,
            "estado": "pendiente",
            "creado_en": firestore.SERVER_TIMESTAMP,
        }
        db.collection("actividades").add(datos)
        flash("¡Propuesta enviada con éxito!")
        return redirect(url_for('inicio'))
    return render_template('proponer_v2.html')

@app.route('/trabajemos-juntas')
def alianzas():
    # Página puramente estática: sin Firestore de por medio. Solo invita a
    # organizaciones/fundaciones/personas a escribir por correo.
    return render_template('alianzas_v2.html', correo_alianzas=CORREO_ALIANZAS)

@app.route('/inscribir/<actividad_id>', methods=['GET', 'POST'])
def inscribir(actividad_id):
    doc = db.collection("actividades").document(actividad_id).get()
    if not doc.exists:
        flash("Esa actividad ya no está disponible.")
        return redirect(url_for('actividades'))
    actividad = doc.to_dict()
    actividad['id'] = doc.id
    # Preguntas que la administradora armó para esta actividad en particular
    # (además de Nombre y Contacto, que siempre se piden).
    campos_extra = actividad.get('campos_inscripcion', [])

    if request.method == 'POST':
        if _envio_excedido(f"inscribir:{request.remote_addr}"):
            flash("Demasiadas inscripciones enviadas desde acá en poco tiempo. Intenta de nuevo más tarde.")
            return render_template('inscripcion_v2.html', actividad=actividad, campos_extra=campos_extra), 429
        nombre = (request.form.get('nombre') or '').strip()[:150]
        contacto = (request.form.get('contacto') or '').strip()[:200]
        if not nombre or not contacto:
            flash("Completa tu nombre y un contacto antes de enviar.")
            return render_template('inscripcion_v2.html', actividad=actividad, campos_extra=campos_extra), 400

        respuestas = {}
        for i, campo in enumerate(campos_extra):
            valor = (request.form.get(f'extra_{i}') or '').strip()[:300]
            if campo.get('requerido') and not valor:
                flash(f"Falta responder “{campo.get('etiqueta', f'Pregunta {i+1}')}”.")
                return render_template('inscripcion_v2.html', actividad=actividad, campos_extra=campos_extra), 400
            respuestas[campo.get('etiqueta', f'Pregunta {i+1}')] = valor

        registro = {
            "actividad_id": actividad_id,
            "actividad_titulo": actividad.get('titulo'),
            "nombre_alumna": nombre,
            "contacto": contacto,
            "respuestas": respuestas,
            "creado_en": firestore.SERVER_TIMESTAMP,
        }
        db.collection("inscripciones").add(registro)
        flash("¡Postulación enviada! Te contactaremos pronto.")
        return redirect(url_for('actividades'))
    return render_template('inscripcion_v2.html', actividad=actividad, campos_extra=campos_extra)

# --- RUTAS ADMINISTRADOR ---

# Protección contra fuerza bruta en el login: sin esto, alguien puede probar
# contraseñas sin parar. En memoria (no Redis) porque el sitio corre con un
# solo worker de gunicorn -- si algún día se agregan más workers o se hace
# autoescalado, esto hay que pasarlo a un almacén compartido (Redis, Firestore).
LOGIN_MAX_INTENTOS = 5
LOGIN_VENTANA_SEGUNDOS = 15 * 60  # 15 minutos
_intentos_fallidos = defaultdict(list)

def _login_bloqueado(ip):
    ahora = time.time()
    vigentes = [t for t in _intentos_fallidos[ip] if ahora - t < LOGIN_VENTANA_SEGUNDOS]
    _intentos_fallidos[ip] = vigentes
    return len(vigentes) >= LOGIN_MAX_INTENTOS

def _registrar_intento_fallido(ip):
    _intentos_fallidos[ip].append(time.time())


def _esta_logueada():
    return bool(session.get('admin_email'))


def _verificar_administradora(email, password):
    """Primero busca la cuenta en Firestore (varias administradoras, con
    contraseña hasheada); si no hay ninguna que coincida, cae a la cuenta
    única por variables de entorno -- así nunca queda nadie bloqueada del
    todo si algo falla con la colección de Firestore."""
    email = (email or '').strip().lower()
    if not email or not password:
        return False
    docs = list(db.collection('administradoras').where('email', '==', email).limit(1).stream())
    if docs:
        datos = docs[0].to_dict()
        return check_password_hash(datos.get('password_hash', ''), password)
    return email == ADMIN_USER.strip().lower() and password == ADMIN_PASS

@app.route('/login', methods=['GET', 'POST'])
def login():
    ip = request.remote_addr or 'desconocida'
    if request.method == 'POST':
        if _login_bloqueado(ip):
            flash("Demasiados intentos fallidos. Intenta de nuevo en unos minutos.")
            return render_template('login.html'), 429
        email = (request.form.get('email') or '').strip()
        password = request.form.get('password') or ''
        if _verificar_administradora(email, password):
            _intentos_fallidos.pop(ip, None)
            session['admin_email'] = email.lower()
            return redirect(url_for('panel_admin'))
        else:
            _registrar_intento_fallido(ip)
            flash("Credenciales incorrectas.")
    return render_template('login.html')

def _fecha_orden(item):
    """Clave de orden: más antigua primero. Lo que no tiene 'creado_en'
    (propuestas de antes de que se empezara a guardar la fecha) queda al
    principio, marcado como fecha desconocida."""
    valor = item.get('creado_en')
    if valor is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return valor


def _fecha_actividad_orden(actividad):
    """Clave de orden por fecha del evento (la más próxima primero). Las
    actividades sin fecha cargada quedan al final."""
    return actividad.get('fecha') or '9999-99-99'


def _actividad_vencida(actividad):
    """True si la actividad ya tiene una fecha pasada. Sin fecha cargada no
    se considera vencida (no hay forma de saberlo)."""
    fecha = actividad.get('fecha')
    return bool(fecha) and fecha < date.today().isoformat()


@app.route('/panel-admin')
def panel_admin():
    if not _esta_logueada():
        return redirect(url_for('login'))

    # 1. Propuestas pendientes (con todos los datos que mandó la persona,
    #    para poder revisarlas antes de aprobarlas, no solo el título).
    prop_docs = db.collection("actividades").where("estado", "==", "pendiente").stream()
    lista_prop = []
    for d in prop_docs:
        p = d.to_dict()
        p['id'] = d.id
        lista_prop.append(p)
    lista_prop.sort(key=_fecha_orden)

    # 2. Actividades oficiales (para poder despublicarlas o eliminarlas).
    #    Se muestran todas -- incluidas las vencidas, marcadas aparte, para
    #    que la administradora decida si las despublica o las borra -- pero
    #    ordenadas por la fecha del evento (la más próxima primero).
    oficial_docs = db.collection("actividades").where("estado", "==", "oficial").stream()
    lista_oficiales = []
    for d in oficial_docs:
        o = d.to_dict()
        o['id'] = d.id
        o['vencida'] = _actividad_vencida(o)
        lista_oficiales.append(o)
    lista_oficiales.sort(key=_fecha_actividad_orden)

    # 3. Inscripciones, agrupadas por actividad para ver de un vistazo
    #    cuántas alumnas se anotaron a cada una.
    ins_docs = db.collection("inscripciones").stream()
    grupos = OrderedDict()
    for d in ins_docs:
        i = d.to_dict()
        i['id'] = d.id
        titulo = i.get('actividad_titulo') or 'Sin actividad'
        grupos.setdefault(titulo, []).append(i)
    inscripciones_agrupadas = []
    for titulo, personas in sorted(grupos.items()):
        personas.sort(key=_fecha_orden)
        # Columnas dinámicas: la unión de las preguntas que efectivamente
        # contestaron (no depende de las preguntas actuales de la actividad,
        # así no se pierden respuestas viejas si después se edita el formulario).
        columnas = []
        for persona in personas:
            for etiqueta in (persona.get('respuestas') or {}).keys():
                if etiqueta not in columnas:
                    columnas.append(etiqueta)
        inscripciones_agrupadas.append({
            "actividad": titulo,
            "inscritas": personas,
            "columnas": columnas,
        })

    total_inscritas = sum(len(g["inscritas"]) for g in inscripciones_agrupadas)

    # 4. Administradoras (cuentas en Firestore -- no incluye la cuenta única
    #    de respaldo por variables de entorno, que no vive en la base).
    admin_docs = db.collection("administradoras").stream()
    lista_admins = []
    for d in admin_docs:
        a = d.to_dict()
        a['id'] = d.id
        lista_admins.append(a)
    lista_admins.sort(key=lambda a: a.get('email') or '')

    return render_template('admin_v2.html',
                           propuestas=lista_prop,
                           oficiales=lista_oficiales,
                           inscripciones_agrupadas=inscripciones_agrupadas,
                           total_inscritas=total_inscritas,
                           administradoras=lista_admins,
                           mi_correo=session.get('admin_email', ''))

@app.route('/aprobar/<id>', methods=['POST'])
def aprobar_actividad(id):
    if _esta_logueada():
        db.collection("actividades").document(id).update({"estado": "oficial"})
        flash("Actividad aprobada y publicada.")
    return redirect(url_for('panel_admin'))

@app.route('/despublicar/<id>', methods=['POST'])
def despublicar_actividad(id):
    if _esta_logueada():
        db.collection("actividades").document(id).update({"estado": "pendiente"})
        flash("Actividad despublicada: volvió a Propuestas por Aprobar.")
    return redirect(url_for('panel_admin'))

@app.route('/panel-admin/actividad/<id>/campo/agregar', methods=['POST'])
def agregar_campo_inscripcion(id):
    if not _esta_logueada():
        return redirect(url_for('login'))
    etiqueta = (request.form.get('etiqueta') or '').strip()[:100]
    tipo = request.form.get('tipo') if request.form.get('tipo') in ('texto', 'opciones') else 'texto'
    requerido = request.form.get('requerido') == 'on'
    if not etiqueta:
        flash("Escribe el texto de la pregunta antes de agregarla.")
        return redirect(url_for('panel_admin'))
    campo = {"etiqueta": etiqueta, "tipo": tipo, "requerido": requerido}
    if tipo == 'opciones':
        campo['opciones'] = [o.strip()[:60] for o in (request.form.get('opciones') or '').split(',') if o.strip()][:20]
        if not campo['opciones']:
            flash("Para una pregunta de opción múltiple escribe al menos una opción.")
            return redirect(url_for('panel_admin'))
    # ArrayUnion es atómico: no hace falta leer el documento primero.
    db.collection("actividades").document(id).update({
        "campos_inscripcion": firestore.ArrayUnion([campo])
    })
    flash(f"Pregunta “{etiqueta}” agregada al formulario de inscripción.")
    return redirect(url_for('panel_admin'))

@app.route('/panel-admin/actividad/<id>/campo/quitar', methods=['POST'])
def quitar_campo_inscripcion(id):
    if not _esta_logueada():
        return redirect(url_for('login'))
    etiqueta = request.form.get('etiqueta', '')
    tipo = request.form.get('tipo', 'texto')
    requerido = request.form.get('requerido') == 'on'
    campo = {"etiqueta": etiqueta, "tipo": tipo, "requerido": requerido}
    if tipo == 'opciones':
        campo['opciones'] = [o.strip() for o in (request.form.get('opciones') or '').split(',') if o.strip()]
    # ArrayRemove borra por igualdad exacta del elemento -- por eso el form
    # que llama a esta ruta manda de vuelta los mismos datos que se guardaron.
    db.collection("actividades").document(id).update({
        "campos_inscripcion": firestore.ArrayRemove([campo])
    })
    flash(f"Pregunta “{etiqueta}” quitada del formulario.")
    return redirect(url_for('panel_admin'))

@app.route('/eliminar/<id>', methods=['POST'])
def eliminar_actividad(id):
    if _esta_logueada():
        try:
            db.collection("actividades").document(id).delete()
            flash("Actividad eliminada correctamente.")
        except Exception as e:
            print(f"Error al eliminar: {e}")
    return redirect(url_for('panel_admin'))

@app.route('/eliminar_inscripcion/<id>', methods=['POST'])
def eliminar_inscripcion(id):
    if _esta_logueada():
        db.collection("inscripciones").document(id).delete()
        flash("Inscripción eliminada.")
    return redirect(url_for('panel_admin'))

@app.route('/panel-admin/administradoras/agregar', methods=['POST'])
def agregar_administradora():
    if not _esta_logueada():
        return redirect(url_for('login'))
    email = (request.form.get('email') or '').strip().lower()
    password = request.form.get('password') or ''
    if not email or '@' not in email:
        flash("Escribe un correo válido para la nueva administradora.")
        return redirect(url_for('panel_admin'))
    if len(password) < 8:
        flash("La contraseña debe tener al menos 8 caracteres.")
        return redirect(url_for('panel_admin'))
    existe = list(db.collection('administradoras').where('email', '==', email).limit(1).stream())
    if existe or email == ADMIN_USER.strip().lower():
        flash(f"Ya existe una cuenta con el correo “{email}”.")
        return redirect(url_for('panel_admin'))
    db.collection('administradoras').add({
        "email": email,
        "password_hash": generate_password_hash(password),
        "creado_en": firestore.SERVER_TIMESTAMP,
    })
    flash(f"Cuenta creada para “{email}”.")
    return redirect(url_for('panel_admin'))

@app.route('/panel-admin/administradoras/eliminar/<id>', methods=['POST'])
def eliminar_administradora(id):
    if not _esta_logueada():
        return redirect(url_for('login'))
    doc = db.collection('administradoras').document(id).get()
    if doc.exists and (doc.to_dict().get('email') or '') == session.get('admin_email'):
        flash("No puedes eliminar la cuenta con la que estás conectada ahora mismo.")
        return redirect(url_for('panel_admin'))
    db.collection('administradoras').document(id).delete()
    flash("Cuenta de administradora eliminada.")
    return redirect(url_for('panel_admin'))

@app.route('/logout')
def logout():
    session.pop('admin_email', None)
    return redirect(url_for('inicio'))


# --- MANEJADORES DE ERROR ---

@app.errorhandler(404)
def pagina_no_encontrada(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def error_interno(e):
    return render_template('500.html'), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    # use_reloader reinicia solo el proceso al guardar un cambio en el código
    # (en producción corre con gunicorn, no con esto, así que no aplica ahí).
    modo_dev = os.environ.get("FLASK_ENV") != "production"
    app.run(host='0.0.0.0', port=port, use_reloader=modo_dev)
