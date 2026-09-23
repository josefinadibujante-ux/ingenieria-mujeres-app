import os
from datetime import datetime, timezone
from collections import OrderedDict

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
)
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

# Credenciales de administración (nunca hardcodeadas en el código).
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "1234")

# Correo para la sección "Trabajemos Juntas" (alianzas con organizaciones).
# TODO: reemplazar cuando tengan un Gmail dedicado para esto -- de momento se
# reutiliza el mismo correo/usuario que el Instagram (@ingenierasmasunab).
CORREO_ALIANZAS = os.environ.get("CORREO_ALIANZAS", "ingenierasmasunab@gmail.com")

# --- PROTECCIÓN CSRF ---
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
        lista.append(a)
    return render_template('actividades_v2.html', actividades=lista)

@app.route('/proponer', methods=['GET', 'POST'])
def crear_actividad():
    if request.method == 'POST':
        datos = {
            "titulo": request.form.get('titulo'),
            "descripcion": request.form.get('descripcion'),
            "contacto": request.form.get('contacto'),
            "categoria": request.form.get('categoria'),
            "rol": request.form.get('rol'),
            "fecha": request.form.get('fecha'),
            "habilidad": request.form.get('habilidad'),
            "materiales": request.form.get('materiales'),
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
        respuestas = {}
        for i, campo in enumerate(campos_extra):
            respuestas[campo.get('etiqueta', f'Pregunta {i+1}')] = request.form.get(f'extra_{i}', '')
        registro = {
            "actividad_id": actividad_id,
            "actividad_titulo": actividad.get('titulo'),
            "nombre_alumna": request.form.get('nombre'),
            "contacto": request.form.get('contacto'),
            "respuestas": respuestas,
            "creado_en": firestore.SERVER_TIMESTAMP,
        }
        db.collection("inscripciones").add(registro)
        flash("¡Postulación enviada! Te contactaremos pronto.")
        return redirect(url_for('actividades'))
    return render_template('inscripcion_v2.html', actividad=actividad, campos_extra=campos_extra)

# --- RUTAS ADMINISTRADOR ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        if email == ADMIN_USER and password == ADMIN_PASS:
            session['admin_logueado'] = True
            return redirect(url_for('panel_admin'))
        else:
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


@app.route('/panel-admin')
def panel_admin():
    if not session.get('admin_logueado'):
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

    # 2. Actividades oficiales (para poder despublicarlas o eliminarlas)
    oficial_docs = db.collection("actividades").where("estado", "==", "oficial").stream()
    lista_oficiales = []
    for d in oficial_docs:
        o = d.to_dict()
        o['id'] = d.id
        lista_oficiales.append(o)
    lista_oficiales.sort(key=_fecha_orden)

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

    return render_template('admin_v2.html',
                           propuestas=lista_prop,
                           oficiales=lista_oficiales,
                           inscripciones_agrupadas=inscripciones_agrupadas,
                           total_inscritas=total_inscritas)

@app.route('/aprobar/<id>', methods=['POST'])
def aprobar_actividad(id):
    if session.get('admin_logueado'):
        db.collection("actividades").document(id).update({"estado": "oficial"})
        flash("Actividad aprobada y publicada.")
    return redirect(url_for('panel_admin'))

@app.route('/despublicar/<id>', methods=['POST'])
def despublicar_actividad(id):
    if session.get('admin_logueado'):
        db.collection("actividades").document(id).update({"estado": "pendiente"})
        flash("Actividad despublicada: volvió a Propuestas por Aprobar.")
    return redirect(url_for('panel_admin'))

@app.route('/panel-admin/actividad/<id>/campo/agregar', methods=['POST'])
def agregar_campo_inscripcion(id):
    if not session.get('admin_logueado'):
        return redirect(url_for('login'))
    etiqueta = (request.form.get('etiqueta') or '').strip()
    tipo = request.form.get('tipo') or 'texto'
    requerido = request.form.get('requerido') == 'on'
    if not etiqueta:
        flash("Escribí el texto de la pregunta antes de agregarla.")
        return redirect(url_for('panel_admin'))
    campo = {"etiqueta": etiqueta, "tipo": tipo, "requerido": requerido}
    if tipo == 'opciones':
        campo['opciones'] = [o.strip() for o in (request.form.get('opciones') or '').split(',') if o.strip()]
        if not campo['opciones']:
            flash("Para una pregunta de opción múltiple escribí al menos una opción.")
            return redirect(url_for('panel_admin'))
    # ArrayUnion es atómico: no hace falta leer el documento primero.
    db.collection("actividades").document(id).update({
        "campos_inscripcion": firestore.ArrayUnion([campo])
    })
    flash(f"Pregunta “{etiqueta}” agregada al formulario de inscripción.")
    return redirect(url_for('panel_admin'))

@app.route('/panel-admin/actividad/<id>/campo/quitar', methods=['POST'])
def quitar_campo_inscripcion(id):
    if not session.get('admin_logueado'):
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
    if session.get('admin_logueado'):
        try:
            db.collection("actividades").document(id).delete()
            flash("Actividad eliminada correctamente.")
        except Exception as e:
            print(f"Error al eliminar: {e}")
    return redirect(url_for('panel_admin'))

@app.route('/eliminar_inscripcion/<id>', methods=['POST'])
def eliminar_inscripcion(id):
    if session.get('admin_logueado'):
        db.collection("inscripciones").document(id).delete()
        flash("Inscripción eliminada.")
    return redirect(url_for('panel_admin'))

@app.route('/logout')
def logout():
    session.pop('admin_logueado', None)
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
    app.run(host='0.0.0.0', port=port)
