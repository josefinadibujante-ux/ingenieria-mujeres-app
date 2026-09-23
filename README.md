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

Existe un servicio en Render llamado **`comunidad-mujeres-antoniovaras`**,
pero quedó configurado para el código y el proyecto de Firebase **viejos**
(el de antes de esta reconstrucción). Antes de volver a desplegar ahí, hay
que actualizar su configuración — no alcanza con hacer `git push`.

**Checklist para cuando decidas publicar:**

1. **Build command:** `pip install -r requirements.txt`
2. **Start command:** el del `Procfile` → `gunicorn app_v2:app`
3. **Variables de entorno** (panel *Environment*), todas nuevas o a
   revisar:
   - `FLASK_SECRET_KEY` — generá una con
     `python -c "import secrets; print(secrets.token_hex(32))"`
   - `ADMIN_USER` / `ADMIN_PASS` — las credenciales reales del panel de
     administración (nunca `admin`/`1234`, que son solo el valor por
     defecto en desarrollo).
   - `FLASK_ENV=production` — activa cookies seguras y desactiva la
     recarga automática de desarrollo.
   - `GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/key.json`
   - `CORREO_ALIANZAS` — opcional; si no se define, usa
     `ingenierasmasunab@gmail.com` (ver [CREDENCIALES.md](CREDENCIALES.md)).
4. **Secret File:** subí el `key.json` del proyecto de Firebase **nuevo**
   (`web-ingenieras-oficial`, no el viejo `comunidad-mujeres` — ver
   [CREDENCIALES.md](CREDENCIALES.md)) como *Secret File* con el nombre
   `key.json`. Render lo deja en `/etc/secrets/key.json`, que es justo la
   ruta que apunta la variable de arriba.
5. Render termina el TLS por su cuenta; Talisman envía HSTS y el resto de
   cabeceras de seguridad detrás de ese proxy — no hace falta configurar
   nada extra para HTTPS.
6. Una vez desplegado, probá el login real (con `ADMIN_USER`/`ADMIN_PASS`,
   no con las credenciales de desarrollo) y que `/actividades` cargue —
   confirma que Render puede llegar a Firestore con la clave subida.

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
- Límite de intentos en `/login`: 5 intentos fallidos por IP bloquean esa IP
  15 minutos (429). En memoria del proceso, pensado para el único worker de
  gunicorn que usa el `Procfile` — si algún día se agregan más workers o
  autoescalado, hay que pasar esto a un almacén compartido (Redis, Firestore).
  `ProxyFix` está activado para que la IP se lea del proxy de Render y no
  bloquee a todo el mundo junto.
- Validación del lado del servidor en `/proponer` e `/inscribir` (campos
  obligatorios y largo máximo) — el `required` del HTML no alcanza porque
  cualquiera puede mandar el POST directo sin pasar por el formulario.
