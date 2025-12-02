# crear_base_datos.py - SIMPLIFICADO

import sqlite3
import os

# Define la ruta absoluta al directorio del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Usamos la misma DB, pero limpiaremos la estructura
DB_PATH = os.path.join(BASE_DIR, 'ingenieria_db.sqlite')

# Conexión a la base de datos
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
print(f"Base de datos conectada en: {DB_PATH}")

cursor = conn.cursor()

# 1. CREAR TABLA DE ACTIVIDADES (¡NUEVA ESTRUCTURA!)
# NOTA: Agregamos el campo 'categoria'
cursor.execute("""
    CREATE TABLE IF NOT EXISTS actividades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        descripcion TEXT,
        fecha TEXT NOT NULL,
        cupos INTEGER NOT NULL,
        categoria TEXT NOT NULL -- Nuevo campo para Cine, Taller, o Actividad
    )
""")

# --- DATOS DE EJEMPLO ---

# Insertar datos de ejemplo con su categoría
cursor.execute("INSERT INTO actividades (titulo, descripcion, fecha, cupos, categoria) VALUES (?, ?, ?, ?, ?)",
               ('Taller: Python Básico', 'Primeros pasos en programación y estructuras de datos', '2025-12-05', 40, 'Taller'))

cursor.execute("INSERT INTO actividades (titulo, descripcion, fecha, cupos, categoria) VALUES (?, ?, ?, ?, ?)",
               ('Charla: IA para Mujeres', 'Conferencia sobre el futuro de la Inteligencia Artificial.', '2025-12-10', 60, 'Actividad'))

cursor.execute("INSERT INTO actividades (titulo, descripcion, fecha, cupos, categoria) VALUES (?, ?, ?, ?, ?)",
               ('Cine: Figuras Ocultas', 'Proyección de película inspiradora sobre mujeres en la NASA.', '2025-12-17', 50, 'Cine'))

# Guardar los cambios y cerrar
conn.commit()
conn.close()

print("Tabla 'actividades' recreada con el campo 'categoria'.")