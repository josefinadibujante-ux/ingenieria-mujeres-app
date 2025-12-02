from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os

# --- Configuración de base de datos ---
# [SOLUCIÓN 1 PARA RENDER]: Usar el directorio /tmp/ si estamos en el servidor de Render,
# que es la única ubicación garantizada como escribible.
if os.environ.get('RENDER'):
    DB_PATH = '/tmp/ingenieria_db.sqlite'
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(BASE_DIR, 'ingenieria_db.sqlite')

app = Flask(__name__, template_folder='templates')
app.secret_key = 'clave_super_secreta' 

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # [SOLUCIÓN 2 PARA RENDER]: Crear las tablas y el admin cada vez
    # que se conecta, ya que la DB se borra en los despliegues gratuitos.
    cursor = conn.cursor()
    
    # 1. Tabla actividades
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS actividades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            fecha DATE NOT NULL,
            categoria TEXT NOT NULL,
            oficial INTEGER NOT NULL,
            cupos INTEGER NOT NULL
        );
    """)
    
    # 2. Tabla admins (necesaria para el login)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        );
    """)

    # 3. Insertar el administrador por defecto si no existe ninguno
    cursor.execute("SELECT COUNT(*) FROM admins")
    if cursor.fetchone()[0] == 0:
        # Credenciales de Admin: admin/1234
        cursor.execute("INSERT INTO admins (username, password) VALUES (?, ?)", ('admin', '1234'))
        
    conn.commit()
    return conn

# --- PÁGINA DE INICIO ---
@app.route('/')
def inicio():
    conn = get_db_connection()
    try:
        actividades_oficiales = conn.execute("SELECT * FROM actividades WHERE oficial=1 ORDER BY fecha DESC").fetchall()
    finally:
        conn.close()
    return render_template('inicio_v2.html', actividades=actividades_oficiales)

# --- LOGIN ADMIN ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        usuario_form = request.form['usuario'] 
        clave_form = request.form['clave']

        conn = get_db_connection()
        try:
            admin = conn.execute("SELECT * FROM admins WHERE username=? AND password=?",
                                 (usuario_form, clave_form)).fetchone()
        finally:
            conn.close()

        if admin:
            session['admin'] = usuario_form
            return redirect(url_for('panel_admin'))
        else:
            flash('Usuario o clave incorrecta', 'error')

    return render_template('login_admin.html')

# --- PANEL ADMIN ---
@app.route('/admin/panel')
def panel_admin():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    try:
        actividades = conn.execute("SELECT * FROM actividades ORDER BY oficial DESC, fecha DESC").fetchall()
    finally:
        conn.close()
    return render_template('panel_admin.html', actividades=actividades)

# --- MARCAR / DESMARCAR ACTIVIDADES COMO OFICIALES ---
@app.route('/admin/marcar_oficial/<int:id>')
def marcar_oficial(id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    try:
        conn.execute("UPDATE actividades SET oficial=1 WHERE id=?", (id,))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('panel_admin'))

@app.route('/admin/desmarcar_oficial/<int:id>')
def desmarcar_oficial(id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    try:
        conn.execute("UPDATE actividades SET oficial=0 WHERE id=?", (id,))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('panel_admin'))

# --- CLUB DE CINE ---
@app.route('/club_cine')
def club_cine():
    conn = get_db_connection()
    try:
        peliculas = conn.execute("SELECT * FROM actividades WHERE categoria='Cine' AND oficial=1 ORDER BY fecha DESC").fetchall()
    finally:
        conn.close()
    return render_template('club_cine.html', peliculas=peliculas)

# --- LISTA DE ACTIVIDADES OFICIALES ---
@app.route('/actividades')
def actividades():
    conn = get_db_connection()
    try:
        actividades_oficiales = conn.execute("SELECT * FROM actividades WHERE oficial=1 ORDER BY fecha DESC").fetchall()
    finally:
        conn.close()
    return render_template('actividades_oficiales.html', actividades=actividades_oficiales)


# --- CREAR / PROPONER ACTIVIDAD ---
@app.route('/proponer_evento', methods=['GET', 'POST'])
def crear_actividad():
    if request.method == 'POST':
        
        titulo = request.form['titulo']
        descripcion = request.form['descripcion']
        fecha = request.form['fecha']
        categoria = request.form['categoria']
        
        conn = get_db_connection()
        try: 
            # Inserción robusta: incluye 'cupos' con valor 0 para evitar IntegrityError
            conn.execute("INSERT INTO actividades (titulo, descripcion, fecha, categoria, oficial, cupos) VALUES (?, ?, ?, ?, 0, 0)",
                         (titulo, descripcion, fecha, categoria))
            conn.commit()
            
            flash('Tu evento ha sido propuesto con éxito y está pendiente de revisión.', 'success')
            return redirect(url_for('inicio'))
        
        except sqlite3.OperationalError:
            # Manejo de error de base de datos bloqueada (común en modo debug local)
            flash('Error: La base de datos está temporalmente bloqueada. Inténtalo de nuevo en unos segundos.', 'error')
            return redirect(url_for('crear_actividad'))
            
        finally:
            conn.close() 

    # Muestra el formulario (GET)
    return render_template('formulario_oficial.html') 

# --- CERRAR SESIÓN ---
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('inicio'))

# --- EJECUTAR APP (COMENTADO PARA PRODUCCIÓN) ---
# if __name__ == '__main__':
#     app.run(debug=True)