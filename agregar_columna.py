import sqlite3

DB_PATH = 'ingenieria_db.sqlite'  # ruta a tu DB

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Agrega la columna 'oficial' (por defecto 0, es decir, no oficial)
cursor.execute("ALTER TABLE actividades ADD COLUMN oficial INTEGER DEFAULT 0")

conn.commit()
conn.close()

print("Columna 'oficial' agregada con éxito.")
