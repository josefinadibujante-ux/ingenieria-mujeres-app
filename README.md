# Comunidad de Mujeres · Campus Antonio Varas

[![Tests](https://github.com/josefinadibujante-ux/ingenieria-mujeres-app/actions/workflows/tests.yml/badge.svg)](https://github.com/josefinadibujante-ux/ingenieria-mujeres-app/actions/workflows/tests.yml)

Sitio web de la Comunidad de Mujeres del Campus Antonio Varas (UNAB). Aplicación
Flask con **Firebase Firestore** como base de datos. Permite publicar talleres y
actividades, recibir propuestas (alumna / tutora), gestionar alianzas con
organizaciones externas e inscribir participantes, con un panel de
administración protegido (varias administradoras, registro de actividad).

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

**Públicas:**

| Ruta                          | Descripción                                      |
|-------------------------------|--------------------------------------------------|
| `/`                            | Inicio                                            |
| `/info_centro`                 | Quiénes somos                                     |
| `/actividades`                 | Talleres/actividades oficiales, sin las vencidas  |
| `/proponer`                    | Formulario de propuesta (alumna / tutora)         |
| `/trabajemos-juntas`           | Alianzas con organizaciones externas (estática)   |
| `/inscribir/<actividad_id>`    | Inscripción a una actividad, con sus preguntas propias |

**Administración** (requieren sesión, si no redirige a `/login`):

| Ruta                                              | Descripción                              |
|----------------------------------------------------|-------------------------------------------|
| `/login`                                           | Acceso administrativo                     |
| `/logout`                                          | Cierra sesión                             |
| `/panel-admin`                                     | Panel con pestañas (propuestas, publicadas, inscritas, equipo) |
| `/aprobar/<id>`                                    | Aprueba una propuesta (pasa a `oficial`)  |
| `/despublicar/<id>`                                | Vuelve una actividad oficial a pendiente  |
| `/eliminar/<id>`                                   | Elimina una actividad                     |
| `/eliminar_inscripcion/<id>`                       | Elimina una inscripción                   |
| `/panel-admin/actividad/<id>/campo/agregar`        | Agrega una pregunta al formulario de una actividad |
| `/panel-admin/actividad/<id>/campo/quitar`         | Quita una pregunta                        |
| `/panel-admin/equipo/agregar`                      | Agrega una integrante al equipo           |
| `/panel-admin/equipo/eliminar/<id>`                | Saca una integrante del equipo            |
| `/panel-admin/equipo/descripcion`                  | Actualiza el texto de presentación del equipo |
| `/panel-superadmin`                                | Panel exclusivo de superadmin (y de la cuenta de respaldo): registro de actividad de todas las cuentas + gestión de cuentas de administradora |
| `/panel-superadmin/administradoras/agregar`        | Crea una cuenta de administradora nueva (solo superadmin o cuenta de respaldo) |
| `/panel-superadmin/administradoras/eliminar/<id>`  | Elimina el acceso de una administradora (solo superadmin o cuenta de respaldo) |

## Base de datos (Firestore)

- **`actividades`**: `titulo`, `descripcion`, `contacto`, `categoria`
  (`Talleres`|`Actividades`), `rol` (`alumno`|`tutor`), `fecha`, `habilidad`,
  `materiales`, `estado` (`pendiente`|`oficial`), `creado_en`,
  `campos_inscripcion` (lista de `{etiqueta, tipo, requerido, opciones?}` —
  las preguntas que arma la administradora para inscribirse a esa actividad).
- **`inscripciones`**: `actividad_id`, `actividad_titulo`, `nombre_alumna`,
  `contacto`, `respuestas` (mapa `etiqueta -> valor`, según las
  `campos_inscripcion` de la actividad), `creado_en`.
- **`administradoras`**: `email`, `password_hash` (nunca en texto plano —
  `werkzeug.security.generate_password_hash`), `es_superadmin` (booleano),
  `creado_en`. Se gestionan desde `/panel-superadmin` (solo superadmin o la
  cuenta de respaldo — ver abajo); además de las cuentas acá, la cuenta
  única por `ADMIN_USER`/`ADMIN_PASS` sigue funcionando siempre como
  respaldo, aunque no aparezca en esta colección — esa cuenta de respaldo
  nunca es superadmin, para no quedar bloqueada afuera del panel normal.
- **`registro_actividad`**: `accion`, `detalle`, `admin_email`, `creado_en`.
  Se escribe automáticamente en cada acción del panel que cambia datos
  (aprobar, despublicar, eliminar, agregar/quitar pregunta, crear/eliminar
  administradora, agregar/quitar integrante del equipo, actualizar
  descripción del equipo) — solo lo ve la cuenta de superadmin (y la de
  respaldo), en `/panel-superadmin`, que muestra las últimas 300 entradas
  de **todas** las cuentas, más reciente primero.
- **`equipo`**: `nombre`, `rol`, `creado_en`. Las integrantes que se
  muestran en "Nuestro Equipo" dentro de `/info_centro`. Se gestionan desde
  la pestaña "Equipo" del panel normal.
- **`configuracion/equipo`** (documento único, no colección de varios
  documentos): campo `descripcion`, el texto de presentación que aparece
  arriba de la lista de integrantes en `/info_centro`.

### Cuentas de superadmin

Una administradora con `es_superadmin: true` entra por el mismo `/login`,
pero en vez de ir a `/panel-admin` la manda a `/panel-superadmin`: un panel
que muestra el registro de actividad de **todas** las cuentas y gestiona
las cuentas de administradora (crear/eliminar, incluidas otras cuentas de
superadmin), sin gestionar propuestas, actividades, inscripciones ni
equipo — si intenta entrar a `/panel-admin` directamente, se la redirige
de vuelta a su panel.

**Solo puede crear o eliminar cuentas** quien ya es superadmin, o la
cuenta única de respaldo (`ADMIN_USER`/`ADMIN_PASS`) — una administradora
normal no tiene esa opción en ningún lado, ni mandando el formulario
directo. Esto es a propósito: la cuenta de respaldo es la única forma de
crear la primerísima cuenta de superadmin (antes de que exista alguna, no
hay ningún superadmin todavía que pueda crearla); desde el panel normal,
a esa cuenta de respaldo le aparece un botón "Gestión de Cuentas" que la
lleva a `/panel-superadmin`.

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

## Tests

Suite de `pytest` en `tests/` que cubre páginas públicas, cabeceras de
seguridad, login (credenciales, CSRF, límite de intentos), administradoras
(crear/eliminar cuentas, autoeliminación bloqueada), formularios (proponer,
inscribir, validación, límite de envíos) y el flujo completo del panel
(proponer → aprobar → publicada → despublicar → eliminar, formulario de
inscripción personalizable, registro de actividad).

```bash
pip install -r requirements-dev.txt
pytest
```

**Importante: los tests corren contra tu Firestore real** (el mismo que
`python app_v2.py`, según tus variables de entorno) — no hay una base de
datos de prueba separada. Por eso:

- Usan una cuenta de administradora fija (`admin@pytest.local`) en vez de
  tu `ADMIN_USER`/`ADMIN_PASS` real, para no depender de tu `.env`.
- Todo lo que crean lleva una marca interna y se borra solo al terminar —
  incluso si una corrida se corta a la mitad por un error, la siguiente
  corrida barre cualquier resto antes de empezar.
- No hace falta (ni conviene) correrlos apuntando a una base con datos
  reales de estudiantes sin haber revisado antes `tests/conftest.py`.

### Corren solos en GitHub (CI)

`.github/workflows/tests.yml` corre toda la suite automáticamente en cada
`push` a `main` — mismas advertencias que arriba (Firestore real, se limpia
solo). Se dispara **solo con push, nunca con pull request** a propósito: el
repo es público, y así ningún pull request externo puede llegar a tocar los
secretos.

**Para activarlo hace falta cargar la clave de Firebase como secreto del
repo** (una sola vez):

1. En GitHub: `Settings` → `Secrets and variables` → `Actions` →
   `New repository secret`.
2. Nombre: `FIREBASE_KEY_JSON`.
3. Valor: el contenido completo de tu `key.json` (abrilo con un editor de
   texto y pegá todo, tal cual).

Sin ese secreto cargado, el workflow va a fallar en el paso de "Escribir la
clave de Firebase" — no rompe nada más, pero no va a poder conectarse a la
base para correr los tests.

## Seguridad

- Credenciales de administración fuera del código, en variables de entorno
  (cuenta de respaldo) o hasheadas en Firestore (cuentas de la colección
  `administradoras`) — nunca en texto plano en ningún lado.
- Varias administradoras posibles, cada una con su propio correo/contraseña
  (colección `administradoras`, gestionada desde `/panel-superadmin`). Dos
  niveles: administradora normal (gestiona propuestas, actividades,
  inscripciones y equipo) y superadmin (solo ve el registro de actividad de
  todas las cuentas y gestiona las cuentas mismas). Crear o eliminar
  cuentas es exclusivo del superadmin (y de la cuenta de respaldo, para
  poder crear a la primera) — una administradora normal no tiene esa
  opción ni siquiera mandando el formulario directo. Ninguna cuenta puede
  eliminar su propia cuenta desde la interfaz (para no quedar bloqueada sin
  querer).
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
- Límite de envíos en `/proponer` e `/inscribir`: 20 por IP por hora (429) —
  más permisivo que el del login a propósito, porque varias estudiantes
  reales pueden compartir la misma IP (wifi del campus).
- El panel de administración y `/login` mandan `Cache-Control: no-store` —
  para que en una computadora compartida, el botón "Atrás" después de cerrar
  sesión no muestre una versión guardada en caché del panel.
- Cookie de sesión con `Secure` (en producción) + `HttpOnly` + `SameSite=Lax`.
- `/login` siempre redirige a una ruta fija (`/panel-admin`); no acepta
  ningún parámetro tipo `?next=`, así que no hay riesgo de open redirect ahí.
