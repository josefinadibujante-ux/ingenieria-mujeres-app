# Comunidad de Mujeres · Campus Antonio Varas

Sitio web de la Comunidad de Mujeres del Campus Antonio Varas (UNAB). Aplicación
Flask con **Firebase Firestore** como base de datos. Permite publicar talleres y
actividades, recibir propuestas (alumna / tutora), gestionar un club de cine e
inscribir participantes, con un panel de administración protegido.

## Stack

- Python + Flask
- Firebase Admin SDK (Firestore)
- Flask-WTF (protección CSRF)
- Flask-Talisman (CSP y cabeceras de seguridad)
- python-dotenv (variables de entorno en local)
- Bootstrap 5.3 en las plantillas

## Correr el proyecto localmente

### 1. Requisitos

- Python 3.11+
- Una cuenta de servicio de Firebase con acceso a Firestore

### 2. Instalar dependencias

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

### 3. Credenciales de Firebase (`key.json`)

El backend necesita el archivo JSON de la cuenta de servicio de Firebase:

1. Firebase Console → ⚙️ **Configuración del proyecto** → pestaña **Cuentas de
   servicio** → **Generar nueva clave privada**.
2. Guarda el archivo descargado como `key.json` en la raíz del proyecto.

`key.json` (y cualquier `comunidad-mujeres-firebase-adminsdk-*.json`) está en
`.gitignore` y **nunca** debe subirse al repositorio.

Si prefieres tenerlo en otra ruta, define la variable
`GOOGLE_APPLICATION_CREDENTIALS` con la ruta al archivo.

### 4. Variables de entorno

Copia `.env.example` a `.env` y completa los valores:

```bash
cp .env.example .env
```

| Variable                         | Para qué sirve                                                        |
|----------------------------------|---------------------------------------------------------------------|
| `FLASK_SECRET_KEY`               | Firma las cookies de sesión. Usa una cadena larga y aleatoria.       |
| `ADMIN_USER`                     | Correo de la administradora (se compara con el campo `email` del login). |
| `ADMIN_PASS`                     | Contraseña de la administradora.                                     |
| `GOOGLE_APPLICATION_CREDENTIALS` | (Opcional) Ruta al `key.json` si no está en la raíz.                 |
| `FLASK_ENV`                      | `production` en Render para forzar cookies seguras.                  |

Generar una `FLASK_SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Levantar el servidor

```bash
python app_v2.py
```

Queda en `http://localhost:5000`. El puerto se puede cambiar con la variable
`PORT`.

## Rutas

| Ruta                        | Descripción                                    |
|-----------------------------|-----------------------------------------------|
| `/`                         | Inicio                                         |
| `/info_centro`              | Quiénes somos                                  |
| `/actividades`              | Talleres oficiales                             |
| `/proponer`                 | Formulario de propuesta (alumna / tutora)      |
| `/club_cine`                | Cartelera del club de cine                     |
| `/inscribir?titulo=...`     | Inscripción a una actividad                    |
| `/login`                    | Acceso administrativo                          |
| `/panel-admin`              | Panel: propuestas, actividades e inscripciones |
| `/aprobar/<id>`             | Aprueba una propuesta (pasa a `oficial`)       |
| `/eliminar/<id>`            | Elimina una actividad                          |
| `/eliminar_inscripcion/<id>`| Elimina una inscripción                        |
| `/logout`                   | Cierra sesión                                  |

## Base de datos (Firestore)

- **`actividades`**: `titulo`, `descripcion`, `contacto`, `categoria`, `rol`,
  `fecha`, `habilidad`, `materiales`, `estado` (`pendiente` | `oficial`).
- **`inscripciones`**: `actividad_titulo`, `nombre_alumna`, `rut`, `carrera`,
  `sede_antonio_varas`, `contacto`.

## Despliegue en Render

El proyecto está desplegado en Render como
**`comunidad-mujeres-antoniovaras`**.

- **Build command:** `pip install -r requirements.txt`
- **Start command:** el del `Procfile` → `gunicorn app_v2:app`
- **Environment:** define `FLASK_SECRET_KEY`, `ADMIN_USER`, `ADMIN_PASS` y
  `FLASK_ENV=production` en el panel *Environment*.
- **Secret File:** sube el `key.json` como *Secret File*. Render lo deja en
  `/etc/secrets/key.json`, así que define además
  `GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/key.json`.
- Render termina el TLS por su cuenta; Talisman envía HSTS y el resto de
  cabeceras de seguridad detrás de ese proxy.

## Seguridad

- Credenciales de administración fuera del código, en variables de entorno.
- CSRF en todos los formularios POST (`csrf_token` de Flask-WTF). Las acciones
  del panel admin (aprobar, despublicar, eliminar, borrar inscripción) son
  formularios POST, no links GET — así no se pueden disparar sin querer ni sin
  el token CSRF.
- CSP + HSTS + `X-Frame-Options: DENY` + `X-Content-Type-Options: nosniff` vía
  Flask-Talisman. La CSP permite `cdn.jsdelivr.net`, `cdnjs.cloudflare.com`,
  `fonts.googleapis.com`, `fonts.gstatic.com`, `unpkg.com`,
  `images.unsplash.com` y `www.transparenttextures.com`.
