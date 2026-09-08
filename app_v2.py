import os

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

# Credenciales de administración (nunca hardcodeadas en el código).
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "1234")

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
    lista = [doc.to_dict() for doc in docs]
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
            "estado": "pendiente"
        }
        db.collection("actividades").add(datos)
        flash("¡Propuesta enviada con éxito!")
        return redirect(url_for('inicio'))
    return render_template('proponer_v2.html')

@app.route('/club_cine')
def club_cine():
    docs = db.collection("actividades").where("categoria", "==", "Cine").where("estado", "==", "oficial").stream()
    peliculas = [doc.to_dict() for doc in docs]
    return render_template('club_cine_v2.html', peliculas=peliculas)

@app.route('/inscribir', methods=['GET', 'POST'])
def inscribir():
    titulo_act = request.args.get('titulo', 'Actividad')
    if request.method == 'POST':
        registro = {
            "actividad_titulo": titulo_act,
            "nombre_alumna": request.form.get('nombre'),
            "rut": request.form.get('rut'),
            "carrera": request.form.get('carrera'),
            "sede_antonio_varas": request.form.get('sede_av'),
            "contacto": request.form.get('contacto')
        }
        db.collection("inscripciones").add(registro)
        return redirect(url_for('actividades'))
    return render_template('inscripcion_v2.html', titulo_actividad=titulo_act)

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

@app.route('/panel-admin')
def panel_admin():
    if not session.get('admin_logueado'):
        return redirect(url_for('login'))

    # 1. Propuestas pendientes
    prop_docs = db.collection("actividades").where("estado", "==", "pendiente").stream()
    lista_prop = []
    for d in prop_docs:
        p = d.to_dict()
        p['id'] = d.id
        lista_prop.append(p)

    # 2. Actividades oficiales (para poder eliminarlas si hubo error)
    oficial_docs = db.collection("actividades").where("estado", "==", "oficial").stream()
    lista_oficiales = []
    for d in oficial_docs:
        o = d.to_dict()
        o['id'] = d.id
        lista_oficiales.append(o)

    # 3. Inscripciones
    ins_docs = db.collection("inscripciones").stream()
    lista_ins = []
    for d in ins_docs:
        i = d.to_dict()
        i['id'] = d.id
        lista_ins.append(i)

    return render_template('admin_v2.html',
                           propuestas=lista_prop,
                           oficiales=lista_oficiales,
                           inscripciones=lista_ins)

@app.route('/aprobar/<id>')
def aprobar_actividad(id):
    if session.get('admin_logueado'):
        db.collection("actividades").document(id).update({"estado": "oficial"})
    return redirect(url_for('panel_admin'))

@app.route('/eliminar/<id>')
def eliminar_actividad(id):
    if session.get('admin_logueado'):
        try:
            db.collection("actividades").document(id).delete()
            flash("Actividad eliminada correctamente.")
        except Exception as e:
            print(f"Error al eliminar: {e}")
    return redirect(url_for('panel_admin'))

@app.route('/eliminar_inscripcion/<id>')
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
