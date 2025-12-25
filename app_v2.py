from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
import firebase_admin
from firebase_admin import credentials, firestore

# --- CONFIGURACIÓN DE FIREBASE (GOOGLE CLOUD) ---
# Esto reemplaza a SQLite. Los datos ahora viven en la nube.
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase-key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

app = Flask(__name__, template_folder='templates')
app.secret_key = 'clave_super_secreta' 

# --- PÁGINA DE INICIO ---
@app.route('/')
def inicio():
    # Buscamos actividades oficiales (oficial == 1)
    docs = db.collection("actividades").where("oficial", "==", 1).order_by("fecha", direction=firestore.Query.DESCENDING).stream()
    actividades_lista = [doc.to_dict() | {"id": doc.id} for doc in docs]
    return render_template('inicio_v2.html', actividades=actividades_lista)

# --- LOGIN ADMIN ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        usuario_form = request.form['usuario'] 
        clave_form = request.form['clave']

        # En Firebase, puedes manejar los admins en una colección llamada 'admins'
        # O para algo simple, dejarlo fijo aquí:
        if usuario_form == 'admin' and clave_form == '1234':
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

    docs = db.collection("actividades").order_by("oficial", direction=firestore.Query.DESCENDING).stream()
    actividades_lista = [doc.to_dict() | {"id": doc.id} for doc in docs]
    return render_template('panel_admin.html', actividades=actividades_lista)

# --- MARCAR / DESMARCAR OFICIALES ---
@app.route('/admin/marcar_oficial/<id>')
def marcar_oficial(id):
    if 'admin' not in session: return redirect(url_for('admin_login'))
    db.collection("actividades").document(id).update({"oficial": 1})
    return redirect(url_for('panel_admin'))

@app.route('/admin/desmarcar_oficial/<id>')
def desmarcar_oficial(id):
    if 'admin' not in session: return redirect(url_for('admin_login'))
    db.collection("actividades").document(id).update({"oficial": 0})
    return redirect(url_for('panel_admin'))

# --- CLUB DE CINE ---
@app.route('/club_cine')
def club_cine():
    docs = db.collection("actividades").where("categoria", "==", "Cine").where("oficial", "==", 1).stream()
    peliculas = [doc.to_dict() | {"id": doc.id} for doc in docs]
    return render_template('club_cine.html', peliculas=peliculas)

# --- LISTA DE ACTIVIDADES ---
@app.route('/actividades')
def actividades():
    docs = db.collection("actividades").where("oficial", "==", 1).order_by("fecha", direction=firestore.Query.DESCENDING).stream()
    actividades_lista = [doc.to_dict() | {"id": doc.id} for doc in docs]
    return render_template('actividades_oficiales.html', actividades=actividades_lista)

# --- CREAR / PROPONER ACTIVIDAD ---
@app.route('/proponer_evento', methods=['GET', 'POST'])
def crear_actividad():
    if request.method == 'POST':
        nueva_actividad = {
            "titulo": request.form['titulo'],
            "descripcion": request.form['descripcion'],
            "fecha": request.form['fecha'],
            "categoria": request.form['categoria'],
            "oficial": 0,
            "cupos": 0
        }
        
        try: 
            db.collection("actividades").add(nueva_actividad)
            flash('Tu evento ha sido propuesto con éxito y está en la nube de Google.', 'success')
            return redirect(url_for('inicio'))
        except Exception as e:
            flash(f'Error al conectar con la nube: {e}', 'error')
            return redirect(url_for('crear_actividad'))

    return render_template('formulario_oficial.html') 

# --- CERRAR SESIÓN ---
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('inicio'))

if __name__ == '__main__':
    app.run(debug=True)