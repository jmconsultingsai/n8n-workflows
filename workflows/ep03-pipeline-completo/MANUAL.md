# Manual de configuración — EP3: Pipeline Completo (Cold Email + Reporte + LinkedIn)

> Este manual acompaña a los tres archivos `.json` de esta carpeta.
> Seguí los pasos en orden: primero las credenciales, después las planillas,
> luego importás los workflows, y al final los probás uno por uno.
>
> **Tiempo estimado: 25-40 minutos** (más si es la primera vez que configurás Google OAuth2).

---

## Qué hace este pipeline

Este EP tiene **tres workflows que trabajan juntos**:

| Workflow | Archivo | Qué hace | Cuándo corre |
|---|---|---|---|
| **WF7 — CVR Cold Email** | `wf7-cvr-cold-email.json` | Lee leads con `Fuente=cvr` y `Estado=nuevo`, genera un email HTML personalizado por sector, lo envía vía Gmail, y actualiza el estado a `emailed` | Todos los días a las 9AM — hasta 25 emails/día |
| **WF4 — Reporte Diario** | `wf4-daily-report-telegram.json` | Lee toda la hoja `RAW_LEADS`, calcula métricas del pipeline CVR (totales, emails enviados, por sector), y manda un reporte a Telegram | Todos los días a las 9PM |
| **WF8 — LinkedIn Reminder** | `wf8-linkedin-outreach.json` | Lee tu hoja de LinkedIn leads, selecciona 10 al azar que todavía no fueron contactados, te los manda por Telegram con los datos y el mensaje de conexión, y los marca como `contactado` | Lunes, miércoles y viernes a las 9AM |

El pipeline no usa IA. Es automatización pura: leer datos, procesar, actuar, reportar.

---

## Diferencias clave respecto a EP1 y EP2

Si ya configuraste EP1 o EP2, prestá atención a estos cambios:

**Google Sheets: OAuth2, no Service Account**
EP1 usaba una Service Account (solo lectura). EP3 necesita **OAuth2** porque WF7 y WF8 tienen que *escribir* en la planilla (actualizar el campo `Estado`). Son credenciales distintas en n8n — no reutilizables entre sí.

**Telegram: nodo nativo, no HTTP Request**
EP1 mandaba mensajes de Telegram via nodo HTTP Request con el token en la URL. EP3 usa el **nodo nativo de Telegram** de n8n, que tiene su propio tipo de credencial (`Telegram API`). El setup es más simple.

**Gmail: necesita su propia credencial OAuth2**
WF7 envía emails via Gmail. Necesitás habilitar la Gmail API en Google Cloud Console y crear una credencial OAuth2 separada para Gmail en n8n.

**Sin OpenAI**
Este pipeline no llama a ninguna IA. Todo el procesamiento es JavaScript en nodos Code.

---

## Qué necesitás antes de empezar

| Servicio | Para qué | ¿Gratis? |
|---|---|---|
| Google Cloud Console | Habilitar Sheets API + Gmail API, crear credenciales OAuth2 | Sí |
| Google Sheets | La planilla con tus leads (RAW_LEADS y hoja de LinkedIn) | Sí |
| Gmail | Enviar los cold emails (WF7) | Sí — con cuenta de Google |
| Telegram | Recibir el reporte diario (WF4) y el reminder de LinkedIn (WF8) | Sí |
| n8n | Ejecutar los workflows | Sí (self-hosted) o plan gratuito en n8n Cloud |

---

## Paso 1 — Preparar las planillas de Google Sheets

### 1.1 La hoja RAW_LEADS (usada por WF7 y WF4)

Necesitás una planilla con una hoja llamada exactamente `RAW_LEADS` con estas columnas:

| Columna | Descripción |
|---|---|
| `Empresa` | Nombre de la empresa |
| `Email` | Email de contacto |
| `Industry` | Texto de la industria/branche (viene del CVR) |
| `Estado` | Estado del lead: `nuevo` (sin contactar), `emailed` (email enviado) |
| `Fuente` | Fuente del lead: debe ser `cvr` para que WF7 lo procese |
| Otras columnas | URL, Teléfono, LinkedIn, etc. — el workflow las ignora |

WF7 filtra por `Fuente = cvr` y `Estado = nuevo`. Cuando manda el email, actualiza `Estado` a `emailed`.

> Si no tenés leads todavía, podés crear filas de prueba manualmente con datos ficticios para testear el workflow.

### 1.2 La hoja de LinkedIn (usada por WF8)

Creá otra hoja en la misma planilla (o en otra). El nombre lo define vos — lo vas a poner como placeholder en el Paso 5. Las columnas necesarias:

| Columna | Descripción |
|---|---|
| `Nombre completo` | Nombre y apellido del lead |
| `Empresa actual` | Empresa donde trabaja |
| `Título actual` | Cargo/título |
| `LinkedIn URL` | URL del perfil de LinkedIn |
| `Connect Request Message` | El mensaje personalizado para la invitación de conexión |
| `Estado` | Vacío = pendiente, `contactado` = ya procesado |

WF8 lee los que tienen `Estado` vacío, te los manda por Telegram, y los marca como `contactado`.

### 1.3 Copiar el ID de la planilla

La URL de tu planilla tiene este formato:

```
https://docs.google.com/spreadsheets/d/AQUI_ESTA_EL_ID/edit
```

Copiá la parte entre `/d/` y `/edit`. Ese es tu `YOUR_GOOGLE_SHEETS_ID`. Guardalo — lo necesitás en el Paso 5.

---

## Paso 2 — Credencial de Google Sheets (OAuth2)

A diferencia de EP1 (que usaba Service Account), acá necesitás OAuth2 porque los workflows escriben en la planilla.

### 2.1 Crear el proyecto en Google Cloud Console (si no lo tenés)

1. Abrí [https://console.cloud.google.com](https://console.cloud.google.com).
2. Seleccioná o creá un proyecto. Podés reusar el proyecto `n8n-workflows` de EP1.

### 2.2 Habilitar las APIs necesarias

Necesitás habilitar **dos APIs** en el mismo proyecto:

**Google Sheets API:**
1. Andá a [https://console.cloud.google.com/apis/library](https://console.cloud.google.com/apis/library).
2. Buscá `Google Sheets API` → hacé clic → **Habilitar**.

**Gmail API:**
1. En el mismo buscador, buscá `Gmail API` → hacé clic → **Habilitar**.

### 2.3 Crear las credenciales OAuth2

1. En el menú de la izquierda, hacé clic en **Credenciales**.
2. Hacé clic en **"+ Crear credenciales"** → **"ID de cliente de OAuth"**.
3. Si nunca configuraste la pantalla de consentimiento, Google te va a pedir hacerlo primero:
   - Tipo de usuario: **Externo** → Crear.
   - Nombre de la app: `n8n-workflows` — completá los campos obligatorios y guardá.
   - En "Alcances", no necesitás agregar nada ahora — n8n los pide automáticamente.
   - En "Usuarios de prueba", agregá tu propio email de Gmail.
4. De vuelta en "Crear ID de cliente de OAuth":
   - Tipo de aplicación: **Aplicación web**.
   - Nombre: `n8n OAuth2`.
   - En **"URIs de redireccionamiento autorizados"**, agregá la URL de callback de n8n. El formato es:
     ```
     https://TU_INSTANCIA_N8N/rest/oauth2-credential/callback
     ```
     Si usás n8n Cloud: `https://app.n8n.cloud/rest/oauth2-credential/callback`.
     Si es self-hosted local: `http://localhost:5678/rest/oauth2-credential/callback`.
5. Hacé clic en **Crear**. Google te muestra el **Client ID** y el **Client Secret**. Copialos.

### 2.4 Crear la credencial de Google Sheets en n8n

1. En n8n, andá a **Settings → Credentials → Add credential**.
2. Buscá y seleccioná **"Google Sheets OAuth2 API"**.
3. Pegá el **Client ID** y el **Client Secret** de Google.
4. Hacé clic en **"Sign in with Google"** y autorizá el acceso con tu cuenta de Google (la que tiene la planilla).
5. Si n8n muestra un tilde verde ✓, la credencial está lista.
6. Guardala con un nombre claro, por ejemplo: `Google Sheets OAuth2`.

---

## Paso 3 — Credencial de Gmail en n8n

WF7 usa el nodo nativo de Gmail para enviar los emails. Usa la misma app OAuth2 que creaste arriba, pero es una credencial separada en n8n.

1. En n8n, andá a **Settings → Credentials → Add credential**.
2. Buscá y seleccioná **"Gmail OAuth2"**.
3. Pegá el mismo **Client ID** y **Client Secret** de Google Cloud (los mismos del Paso 2.3).
4. Hacé clic en **"Sign in with Google"** y autorizá. Esta vez Google pedirá acceso también a Gmail — aceptá.
5. Guardala con un nombre claro: `Gmail OAuth2`.

> Si Google muestra una advertencia "Esta app no está verificada", hacé clic en **"Configuración avanzada"** → **"Ir a n8n-workflows (no seguro)"**. Es porque tu app OAuth2 está en modo de prueba — es completamente normal para uso personal.

---

## Paso 4 — Bot de Telegram

### 4.1 Crear el bot con @BotFather

1. En Telegram, buscá `@BotFather` (con tilde azul de verificación).
2. Escribí `/newbot`.
3. Elegí un nombre visible (ej: `JM Pipeline Bot`) y un username que termine en `bot` (ej: `jm_pipeline_bot`).
4. BotFather te da el **token del bot** (`1234567890:AAFxxx...`). Copialo.

### 4.2 Obtener tu Chat ID

1. Buscá tu bot en Telegram y escribile cualquier mensaje.
2. Abrí este URL en el navegador (reemplazando el token):
   ```
   https://api.telegram.org/botTU_TOKEN/getUpdates
   ```
3. En el JSON que aparece, buscá `"chat"` → `"id"`. Ese número es tu `YOUR_TELEGRAM_CHAT_ID`.

### 4.3 Crear la credencial de Telegram en n8n

EP3 usa el nodo nativo de Telegram, que tiene su propio tipo de credencial:

1. En n8n, andá a **Settings → Credentials → Add credential**.
2. Buscá y seleccioná **"Telegram API"**.
3. En el campo **"Access Token"**, pegá el token del bot que te dio BotFather.
4. Hacé clic en **"Save"**. Si aparece ✓, está bien.
5. Guardala como `Telegram Bot API`.

---

## Paso 5 — Importar los tres workflows

1. En n8n, andá a **Workflows**.
2. Para cada archivo, hacé clic en **"+"** → **"Import from File"** y seleccioná el `.json`:
   - `wf7-cvr-cold-email.json`
   - `wf4-daily-report-telegram.json`
   - `wf8-linkedin-outreach.json`
3. Cada workflow se importa por separado. Vas a ver nodos con íconos de advertencia en rojo — normal, todavía no asignaste credenciales.

---

## Paso 6 — Configurar placeholders en cada workflow

### WF7 — CVR Cold Email

Abrí el workflow `WF7 — CVR Cold Email Denmark` en el editor:

1. **Nodo "Read RAW_LEADS"**: seleccioná la credencial `Google Sheets OAuth2`. En el campo Document ID reemplazá `YOUR_GOOGLE_SHEETS_ID` con tu ID real.
2. **Nodo "Build Email — Template by Sector"**: no hay placeholders, el código está completo.
3. **Nodo "Gmail — Send"**: seleccioná la credencial `Gmail OAuth2`.
4. **Nodo "Update Estado → emailed"**: seleccioná `Google Sheets OAuth2`. Reemplazá `YOUR_GOOGLE_SHEETS_ID` con tu ID real.

### WF4 — Reporte Diario Telegram

Abrí el workflow `WF4 — Reporte Diario Telegram (CVR)`:

1. **Nodo "Sheets — Leer RAW_LEADS"**: seleccioná `Google Sheets OAuth2`. Reemplazá `YOUR_GOOGLE_SHEETS_ID` con tu ID real.
2. **Nodo "Telegram — Enviar Reporte"**: seleccioná la credencial `Telegram Bot API`. En el campo **Chat ID**, reemplazá `YOUR_TELEGRAM_CHAT_ID` con tu número de chat real.

### WF8 — LinkedIn Outreach Reminder

Abrí el workflow `WF8 — LinkedIn Outreach Reminder`:

1. **Nodo "Sheets — Leer LinkedIn"**: seleccioná `Google Sheets OAuth2`. Reemplazá `YOUR_GOOGLE_SHEETS_ID` con tu ID. En el campo **Sheet Name**, reemplazá `YOUR_LINKEDIN_SHEET_NAME` con el nombre exacto de tu hoja de LinkedIn.
2. **Nodo "Telegram — LinkedIn Reminder"**: seleccioná `Telegram Bot API`. Reemplazá `YOUR_TELEGRAM_CHAT_ID` con tu chat ID.
3. **Nodo "Sheets — Marcar Contactado"**: seleccioná `Google Sheets OAuth2`. Reemplazá `YOUR_GOOGLE_SHEETS_ID` y `YOUR_LINKEDIN_SHEET_NAME` igual que en el nodo de lectura.

### Resumen de placeholders

| Placeholder | Valor | Dónde |
|---|---|---|
| `YOUR_GOOGLE_SHEETS_ID` | ID de la planilla (de la URL) | Todos los nodos de Google Sheets en los 3 workflows |
| `YOUR_TELEGRAM_CHAT_ID` | Número de chat ID | Nodo Telegram de WF4 y WF8 |
| `YOUR_LINKEDIN_SHEET_NAME` | Nombre exacto de la hoja de LinkedIn | Nodos de Sheets en WF8 |
| `YOUR_CREDENTIAL_ID` | Asignado automáticamente por n8n al seleccionar la credencial | Se reemplaza solo — no lo tocás manualmente |

---

## Paso 7 — Probar cada workflow

### Probar WF7 (Cold Email)

1. Asegurate de tener al menos una fila en `RAW_LEADS` con `Fuente=cvr`, `Estado=nuevo`, y un email válido.
2. Abrí WF7 y hacé clic en **"Test workflow"**.
3. Resultado esperado:
   - El nodo Filter muestra el lead filtrado.
   - El nodo Build Email genera el HTML personalizado según el sector detectado.
   - El nodo Gmail muestra `200 OK` y el email llega a la bandeja de entrada del destinatario.
   - En la planilla, el campo `Estado` del lead cambia a `emailed`.

> Para probar sin enviar emails reales: temporalmente cambiá el campo `sendTo` en el nodo Gmail por tu propio email.

### Probar WF4 (Reporte Diario)

1. Abrí WF4 y hacé clic en **"Test workflow"**.
2. Resultado esperado:
   - El nodo Sheets lee todas las filas de `RAW_LEADS`.
   - El nodo Code calcula las métricas.
   - En Telegram, recibís un mensaje con el reporte formateado.

### Probar WF8 (LinkedIn Reminder)

1. Asegurate de tener filas en tu hoja de LinkedIn con el campo `Estado` vacío.
2. Abrí WF8 y hacé clic en **"Test workflow"**.
3. Resultado esperado:
   - El nodo Sheets lee los leads.
   - El nodo Code selecciona hasta 10 con `Estado` vacío y los formatea.
   - En Telegram, recibís el mensaje con los leads del día.
   - En la planilla, los leads seleccionados tienen `Estado = contactado`.

### Activar los workflows

Una vez que las pruebas funcionen, activá cada workflow con el toggle **"Active"** en la parte superior del editor. Los triggers de programación se activan automáticamente.

---

## Problemas frecuentes

| Error | Causa | Solución |
|---|---|---|
| `The caller does not have permission` (Sheets) | La cuenta de OAuth2 no tiene acceso a la planilla | La planilla tiene que estar en el Google Drive de la cuenta que usaste para autorizar OAuth2 (o compartida con esa cuenta) |
| `invalid_grant` o `Token has been expired` (OAuth2) | El token de OAuth2 expiró o fue revocado | Andá a la credencial en n8n y reconectá haciendo clic en "Sign in with Google" |
| `Unable to parse range` (Sheets) | El nombre de la hoja tiene un espacio o caracter especial | Verificá que el nombre en el nodo coincida exactamente con el nombre de la pestaña en Google Sheets |
| `400 Bad Request` (Gmail) | El campo `sendTo` tiene un email con formato inválido | Verificá que la columna Email de tus leads tenga emails válidos con `@` |
| `Forbidden: bot can't initiate conversation` (Telegram) | El bot nunca recibió un mensaje de ese chat | Buscá tu bot en Telegram y escribile cualquier mensaje antes de testear |
| `Bad Request: chat not found` (Telegram) | El Chat ID está mal | Repetí el Paso 4.2 para obtener el ID correcto |
| WF8 no actualiza `Estado` | El campo `matchingColumns` no encuentra coincidencias | Verificá que la columna `LinkedIn URL` en la planilla tenga exactamente ese nombre (mayúsculas, espacios) |
| El workflow se activa pero no hace nada | No hay leads que cumplan los filtros | WF7: verificá que haya filas con `Fuente=cvr` y `Estado=nuevo`. WF8: verificá que haya filas con `Estado` vacío |

---

## Seguridad — checklist antes de cerrar

- [ ] Las credenciales OAuth2 de Google NO están escritas en ningún archivo de texto plano.
- [ ] El token del bot de Telegram NO está hardcodeado en ningún documento compartido.
- [ ] Activaste verificación en dos pasos (2FA) en tu cuenta de Google.
- [ ] La app OAuth2 en Google Cloud Console está en modo "Usuarios de prueba" — solo vos tenés acceso.
- [ ] No subiste ningún archivo `.json` con credenciales reales a GitHub (los JSONs de esta carpeta ya están sanitizados — solo los del repo, no tus exportaciones propias).

---

*Manual generado para el EP3 del canal de YouTube de JM Consulting — [https://github.com/jmconsultingsai/n8n-workflows](https://github.com/jmconsultingsai/n8n-workflows)*
