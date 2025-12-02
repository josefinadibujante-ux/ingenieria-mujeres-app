import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'ingenieria_db.sqlite')

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Crear tabla de administradores
cursor.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
""")

# Insertar un admin de prueba (usuario: admin, contraseña: 1234)
try:
    cursor.execute("INSERT INTO admins (username, password) VALUES (?, ?)", ("admin", "1234"))
except sqlite3.IntegrityError:
    # Si ya existe, no hace nada
    pass

conn.commit()
conn.close()
print("Tabla de administradores creada y admin de prueba agregado.")
