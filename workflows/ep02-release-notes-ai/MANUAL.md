# Manual de configuración — EP2: Release Notes Automáticas con IA

> Este manual acompaña al archivo `workflow.json`. Seguí los pasos en orden:
> primero creás las cuentas y credenciales, después preparás la planilla,
> luego importás el workflow, y al final lo probás con un request de prueba.
>
> **Tiempo estimado: 15-25 minutos.**

---

## Qué hace este workflow

Cuando una nueva versión de software está lista, los desarrolladores escriben changelogs técnicos que solo ellos entienden. Este workflow toma esos cambios técnicos, los procesa con OpenAI, y genera release notes claras y atractivas que cualquier usuario puede entender. El resultado llega como mensaje a un bot de Telegram.

El disparo es un **webhook**: en lugar de ejecutarse a horario fijo como EP1, este workflow espera que algo externo lo llame (un pipeline de CI/CD, un script, Postman, o una llamada desde GitHub Actions). Esto introduce un concepto nuevo respecto a EP1.

**Los 6 nodos del workflow:**

1. **Webhook** — recibe el evento de nueva release (con la versión como payload)
2. **Sheets — Changelog** — lee todos los cambios de la planilla
3. **Code — Filter Latest Version** — agrupa por versión y selecciona la más reciente (o la indicada en el webhook)
4. **OpenAI — Generate Release Notes** — transforma el changelog técnico en notas amigables
5. **Code — Format for Telegram** — prepara el mensaje final con Markdown
6. **Telegram — Send Release Notes** — envía las notas al canal o chat configurado

---

## Qué necesitás antes de empezar

| Servicio | Para qué se usa | ¿Gratis? |
|---|---|---|
| Google Cloud Console | Habilitar la API de Sheets y crear credenciales | Sí — la API de Sheets tiene tier gratuito más que suficiente |
| Google Sheets | Almacenar el changelog de versiones | Sí |
| OpenAI | Transformar el changelog técnico en lenguaje de usuario | Pago — se cobra por uso. Para este workflow: menos de USD 0.01 por release con GPT-4o-mini |
| Telegram | Recibir las release notes como mensaje | Sí — completamente gratis |
| n8n | Ejecutar el workflow | Sí (self-hosted) o plan gratuito en n8n Cloud |

> **Sobre el costo de OpenAI:** GPT-4o-mini cuesta aproximadamente USD 0.15 por millón de tokens de entrada. Un changelog de 8-10 cambios consume alrededor de 800-1.200 tokens. Si publicás 10 releases por mes, el costo total es menor a USD 0.02/mes.

---

## Paso 1 — Crear la Google Spreadsheet de demo

Antes de configurar las credenciales, necesitás tener la planilla lista. El workflow lee datos de una sola hoja: **Changelog**.

### 1.1 Crear la planilla

1. Abrí [https://sheets.google.com](https://sheets.google.com) e iniciá sesión con tu cuenta de Google.
2. Hacé clic en el botón **"+"** (Hoja de cálculo en blanco) para crear una nueva planilla.
3. En la parte superior izquierda, hacé clic en "Hoja de cálculo sin título" y renombrala: `TaskFlow Changelog`.

### 1.2 Crear la hoja Changelog con sus columnas

La planilla necesita exactamente **1 hoja** con este nombre y columnas:

**Hoja — Changelog**

1. Hacé clic en la pestaña que dice **"Hoja 1"** en la parte inferior.
2. Hacé doble clic sobre esa pestaña y renombrala: `Changelog`.
3. En la fila 1, escribí estos encabezados (una palabra por celda, comenzando en A1):

   | A | B | C | D | E |
   |---|---|---|---|---|
   | Version | Fecha | Tipo | Cambio_Tecnico | Componente |

4. Agrega los datos de ejemplo para la versión 2.4.0 y versiones anteriores:

   | Version | Fecha | Tipo | Cambio_Tecnico | Componente |
   |---|---|---|---|---|
   | 2.4.0 | 2026-06-15 | feature | Bulk task assignment endpoint for team leads via /api/tasks/bulk-assign | Tasks |
   | 2.4.0 | 2026-06-15 | feature | Kanban board view with react-beautiful-dnd drag-and-drop reordering | Board |
   | 2.4.0 | 2026-06-15 | feature | WebSocket-based real-time notifications for @mentions | Notifications |
   | 2.4.0 | 2026-06-15 | improvement | Reduced dashboard SQL queries from 12 to 3 — 40% faster load time | Dashboard |
   | 2.4.0 | 2026-06-15 | improvement | Migrated file storage from local disk to S3 with CDN | Files |
   | 2.4.0 | 2026-06-15 | fix | Fixed race condition in WebSocket handler causing duplicate notifications | Notifications |
   | 2.4.0 | 2026-06-15 | fix | Calendar sync no longer drops recurring events when timezone differs | Calendar |
   | 2.4.0 | 2026-06-15 | fix | CSV export now handles UTF-8 special characters correctly | Export |
   | 2.3.1 | 2026-05-20 | fix | Resolved login loop when session token expires mid-task | Auth |
   | 2.3.1 | 2026-05-20 | fix | Fixed broken attachment preview for PDF files over 10MB | Files |
   | 2.3.1 | 2026-05-20 | improvement | Reduced API response time for /tasks/list endpoint by 30% | API |
   | 2.3.0 | 2026-04-30 | feature | Time tracking module with per-task timers and weekly summary | Time |
   | 2.3.0 | 2026-04-30 | feature | Guest access — invite external collaborators without full account | Auth |
   | 2.3.0 | 2026-04-30 | improvement | Dark mode now applies to all modals and dropdowns | UI |
   | 2.2.0 | 2026-03-12 | feature | Recurring tasks with configurable intervals (daily, weekly, monthly) | Tasks |
   | 2.2.0 | 2026-03-12 | improvement | Onboarding checklist for new users — guides first 5 actions | Onboarding |
   | 2.2.0 | 2026-03-12 | fix | Fixed pagination bug causing duplicated items in long task lists | Tasks |

   > Los valores válidos para la columna **Tipo** son: `feature`, `improvement`, `fix`. El nodo de código los filtra por este campo para agrupar correctamente.

### 1.3 Copiar el ID de la planilla

La URL de tu planilla tiene este formato:

```
https://docs.google.com/spreadsheets/d/AQUI_ESTA_EL_ID/edit
```

Copiá la parte que está entre `/d/` y `/edit`. Eso es tu `YOUR_GOOGLE_SHEETS_ID`. Guardálo en un bloc de notas — lo vas a necesitar en el Paso 5.

![Paso 1.3 — ID de la planilla en la URL](assets/paso-01-sheets-id.png)

---

## Paso 2 — Credencial de Google Sheets (Service Account)

Vamos a usar una **Service Account** (cuenta de servicio). Es la forma recomendada para workflows automáticos: no requiere que estés logueado, y funciona aunque cierres sesión en tu navegador.

### 2.1 Crear un proyecto en Google Cloud Console

1. Abrí [https://console.cloud.google.com](https://console.cloud.google.com) e iniciá sesión con tu cuenta de Google.
2. En la barra superior, hacé clic en el selector de proyecto (al lado del logo de Google Cloud).
3. En el popup que aparece, hacé clic en **"Nuevo proyecto"** (esquina superior derecha del popup).
4. En el campo **"Nombre del proyecto"**, escribí: `n8n-workflows`.
5. Dejá la organización como está y hacé clic en **"Crear"**.
6. Esperá unos segundos. Cuando aparezca la notificación "Se creó el proyecto n8n-workflows", hacé clic en **"Seleccionar proyecto"**.

![Paso 2.1 — Crear proyecto en Google Cloud Console](assets/paso-02-crear-proyecto.png)

### 2.2 Habilitar la API de Google Sheets

1. Con el proyecto `n8n-workflows` seleccionado, andá a [https://console.cloud.google.com/apis/library](https://console.cloud.google.com/apis/library).
2. En el buscador que dice "Buscar APIs y servicios", escribí: `Google Sheets`.
3. Hacé clic en el resultado **"Google Sheets API"**.
4. Hacé clic en el botón azul **"Habilitar"**.
5. Esperá a que cargue la página de confirmación. Vas a ver el panel de la API con métricas en cero — eso está bien.

![Paso 2.2 — Habilitar Google Sheets API](assets/paso-03-habilitar-api.png)

### 2.3 Crear la Service Account

1. En el menú de la izquierda, hacé clic en **"Credenciales"** (ícono de llave).
2. En la parte superior, hacé clic en **"+ Crear credenciales"**.
3. Del menú desplegable, seleccióna **"Cuenta de servicio"**.
4. En el campo **"Nombre de la cuenta de servicio"**, escribí: `n8n-sheets-reader`.
5. El campo "ID de cuenta de servicio" se llena automáticamente — dejálo como está.
6. Hacé clic en **"Crear y continuar"**.
7. En el paso "Otorgar acceso a este proyecto": en el selector de rol, buscá **"Visor"** (dentro de la categoría "Básico") y selecciónalo.
8. Hacé clic en **"Continuar"** y luego en **"Listo"**.

![Paso 2.3 — Crear Service Account](assets/paso-04-service-account.png)

### 2.4 Descargar la clave JSON

1. En la lista de Service Accounts, hacé clic en el email de la cuenta que acabás de crear (termina en `@n8n-workflows.iam.gserviceaccount.com`).
2. Hacé clic en la pestaña **"Claves"**.
3. Hacé clic en **"Agregar clave"** → **"Crear clave nueva"**.
4. Aseguráte de que esté seleccionado el formato **"JSON"** y hacé clic en **"Crear"**.
5. El archivo JSON se descarga automáticamente a tu carpeta de Descargas. **Guardálo en un lugar seguro** — no lo subas a GitHub ni lo compartas.

> ⚠️ Este archivo JSON contiene las credenciales privadas de tu cuenta de servicio. Si alguien lo obtiene, puede acceder a tus datos. Guardálo como guardarías una contraseña.

### 2.5 Compartir la planilla con la Service Account

Para que la Service Account pueda leer tu planilla, tenés que compartirla con ella como si fuera una persona.

1. Abrí el archivo JSON que descargaste con cualquier editor de texto (Notepad, etc.).
2. Buscá el campo `"client_email"` — el valor es algo como: `n8n-sheets-reader@n8n-workflows.iam.gserviceaccount.com`. Copiálo.
3. Volvé a tu Google Spreadsheet `TaskFlow Changelog`.
4. Hacé clic en el botón **"Compartir"** (esquina superior derecha, botón verde/azul).
5. En el campo "Agregar personas y grupos", pegá el email de la Service Account.
6. Aseguráte de que el rol sea **"Lector"** (no hace falta darle permiso de edición).
7. Hacé clic en **"Enviar"** (o "Compartir").

![Paso 2.5 — Compartir planilla con Service Account](assets/paso-05-compartir-planilla.png)

### 2.6 Crear la credencial en n8n

1. En n8n, andá a **Settings** (ícono de engranaje, barra lateral izquierda) → **Credentials**.
2. Hacé clic en **"Add credential"** (esquina superior derecha).
3. En el buscador, escribí `Google Sheets` y seleccióna **"Google Sheets API"**.
4. En el campo **"Authentication"**, seleccióna **"Service Account"**.
5. Abrí el archivo JSON descargado con un editor de texto.
6. Copiá el contenido completo del archivo (Ctrl+A, Ctrl+C) y pegálo en el campo **"Service Account JSON"** de n8n.
7. Hacé clic en **"Save"**.
8. Si aparece un tilde verde ✓, la credencial está bien configurada.

> Guardá el nombre que le pusiste a esta credencial — por ejemplo `Google Sheets — Service Account`. Lo vas a necesitar en el Paso 5.

---

## Paso 3 — API Key de OpenAI

### 3.1 Crear cuenta (si no tenés una)

1. Abrí [https://platform.openai.com/signup](https://platform.openai.com/signup).
2. Completá el registro con tu email y una contraseña, o usá "Continue with Google".
3. Verificá tu email si te lo pide.

### 3.2 Agregar crédito (requerido)

OpenAI requiere al menos USD 5 de crédito antes de darte acceso a la API.

1. Una vez logueado, andá a [https://platform.openai.com/settings/organization/billing](https://platform.openai.com/settings/organization/billing).
2. Hacé clic en **"Add payment method"** y completá con tu tarjeta.
3. En **"Add to credit balance"**, ingresá `5` (el mínimo) y confirmá.

> El crédito de USD 5 es más que suficiente para cientos de releases con este workflow. No se cobra suscripción mensual — solo pagás lo que usás.

### 3.3 Crear la API Key

1. Andá a [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys).
2. Hacé clic en **"Create new secret key"**.
3. En el campo "Name", escribí algo descriptivo: `n8n-release-notes`.
4. Dejá los permisos en **"All"** y hacé clic en **"Create secret key"**.
5. **Copiá la key AHORA** — empieza con `sk-proj-...`. OpenAI la muestra una sola vez. Si la cerrás sin copiarla, tenés que crear una nueva.

![Paso 3.3 — Crear API Key en OpenAI](assets/paso-06-openai-key.png)

Guardála en tu bloc de notas como: `YOUR_OPENAI_API_KEY = sk-proj-...`

> ⚠️ Nunca publiques esta key en GitHub, en el código, ni en mensajes. Cualquiera que la tenga puede gastar tus créditos.

### 3.4 Crear la credencial en n8n

Este workflow usa un nodo **HTTP Request** para llamar a la API de OpenAI directamente (sin el nodo nativo de OpenAI). La key se ingresa como header de autorización.

1. En n8n, andá a **Settings → Credentials → Add credential**.
2. Buscá y seleccióna **"Header Auth"**.
3. En el campo **"Name"**, escribí `OpenAI API Key`.
4. En el campo **"Name"** (del header), escribí: `Authorization`.
5. En el campo **"Value"**, escribí: `Bearer YOUR_OPENAI_API_KEY` (reemplazando con tu key real, sin las comillas. Ejemplo: `Bearer sk-proj-abc123...`).
6. Hacé clic en **"Save"**.

---

## Paso 4 — Bot de Telegram

### 4.1 Crear el bot con @BotFather

1. Abrí Telegram en tu teléfono o en [https://web.telegram.org](https://web.telegram.org).
2. En el buscador de Telegram, buscá `@BotFather` (el oficial tiene un tilde azul de verificación).
3. Hacé clic en **"Start"** o escribí `/start`.
4. Escribí el comando: `/newbot`
5. BotFather te va a pedir un **nombre** para el bot (es el nombre visible, puede tener espacios): escribí algo como `Release Notes TaskFlow`.
6. Después te pide un **username** (sin espacios, debe terminar en `bot`): escribí algo como `taskflow_releases_bot`.
7. Si el username ya está tomado, probá con variaciones hasta encontrar uno disponible.
8. BotFather te responde con un mensaje que incluye el **token del bot**. Tiene este formato: `1234567890:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`. Copiálo.

![Paso 4.1 — Crear bot con BotFather](assets/paso-07-botfather.png)

Guardálo como: `YOUR_TELEGRAM_BOT_TOKEN = 1234567890:AAFxxx...`

> ⚠️ El token del bot es equivalente a una contraseña. Quien lo tenga puede controlar tu bot.

### 4.2 Obtener tu Chat ID

El `chat_id` le dice al bot a dónde enviar el mensaje. Puede ser tu chat personal con el bot, un grupo, o un canal.

**Para obtener tu chat ID personal:**

1. Buscá tu bot recién creado en Telegram (por su username: `@taskflow_releases_bot`).
2. Hacé clic en **"Start"** o escribí cualquier mensaje (ej: `hola`).
3. Abrí este URL en tu navegador, reemplazando el token:

   ```
   https://api.telegram.org/botYOUR_TELEGRAM_BOT_TOKEN/getUpdates
   ```

   Ejemplo real:
   ```
   https://api.telegram.org/bot1234567890:AAFxxx.../getUpdates
   ```

4. El navegador muestra un JSON. Buscá el campo `"chat"` → `"id"`. Ese número es tu `chat_id`. Ejemplo: `987654321`.

![Paso 4.2 — Obtener Chat ID desde la API de Telegram](assets/paso-08-chat-id.png)

Guardálo como: `YOUR_TELEGRAM_CHAT_ID = 987654321`

> Si el JSON muestra `"result":[]` (vacío), aseguráte de haber enviado al menos un mensaje al bot antes de consultar la URL.

### 4.3 Crear la credencial en n8n

Este workflow usa un nodo **HTTP Request** para enviar mensajes vía Telegram. El token se ingresa directamente en la URL del nodo (no como credencial separada de n8n). No necesitás crear una credencial en n8n para Telegram — los valores van como placeholders en el nodo, y los reemplazás en el Paso 5.

---

## Paso 5 — Importar el workflow

1. Descargá el archivo `workflow.json` desde la misma carpeta de GitHub donde encontraste este manual.
2. En n8n, hacé clic en el menú **"Workflows"** (barra lateral izquierda).
3. Hacé clic en el botón **"+"** (o **"New workflow"**) y en el menú que aparece, seleccióna **"Import from File"**.
4. Seleccióna el archivo `workflow.json` que descargaste.
5. El workflow se abre en el editor. Vas a ver los nodos con íconos de advertencia rojos — eso es normal porque todavía no asignaste las credenciales.

![Paso 5 — Importar workflow en n8n](assets/paso-09-importar.png)

---

## Paso 6 — Configurar las credenciales y placeholders en el workflow

### 6.1 Nodo de Google Sheets (1 nodo)

El workflow tiene un solo nodo que lee la hoja Changelog: **"Sheets — Changelog"**.

1. Hacé clic en el nodo **"Sheets — Changelog"**.
2. En el panel derecho, en el campo **"Credential to connect with"**, seleccióna la credencial que creaste: `Google Sheets — Service Account` (o el nombre que le pusiste).
3. En el campo **"Document ID"** (o "Spreadsheet ID"), reemplazá `YOUR_GOOGLE_SHEETS_ID` con el ID de tu planilla (el que copiaste en el Paso 1.3).
4. En el campo **"Sheet Name"**, verificá que diga `Changelog`.
5. Hacé clic en **"Save"** dentro del nodo.

### 6.2 Nodo HTTP Request — OpenAI

1. Hacé clic en el nodo **"OpenAI — Generate Release Notes"**.
2. En el campo **"Credential to connect with"**, seleccióna `OpenAI API Key`.
3. Verificá que la URL sea `https://api.openai.com/v1/chat/completions`.
4. Hacé clic en **"Save"**.

### 6.3 Nodo HTTP Request — Telegram

1. Hacé clic en el nodo **"Telegram — Send Release Notes"**.
2. En el campo **"URL"**, reemplazá `YOUR_TELEGRAM_BOT_TOKEN` con tu token real. La URL debería quedar así:

   ```
   https://api.telegram.org/bot1234567890:AAFxxx.../sendMessage
   ```

3. En el campo **"Body"** (JSON), buscá el campo `"chat_id"` y reemplazá `YOUR_TELEGRAM_CHAT_ID` con tu chat ID real (ej: `987654321`).
4. Hacé clic en **"Save"**.

### 6.4 URL del Webhook

El nodo **"Webhook — GitHub Release"** genera dos URLs automáticamente:

- **URL de prueba** (solo funciona mientras el editor está abierto):
  ```
  http://localhost:5678/webhook-test/release
  ```
- **URL de producción** (funciona cuando el workflow está activo):
  ```
  http://localhost:5678/webhook/release
  ```

Si usás n8n Cloud, el dominio es algo como `https://tu-nombre.app.n8n.cloud/webhook/release`.

Para ver la URL exacta: hacé clic en el nodo Webhook y copiála desde el panel derecho.

### Resumen de placeholders a reemplazar

| Placeholder | Valor propio | Dónde se pega |
|---|---|---|
| `YOUR_GOOGLE_SHEETS_ID` | ID de tu planilla (de la URL) | Nodo Google Sheets (Document ID) |
| `YOUR_OPENAI_API_KEY` | `sk-proj-...` | Credencial "Header Auth" en n8n |
| `YOUR_TELEGRAM_BOT_TOKEN` | Token de BotFather | URL del nodo HTTP de Telegram |
| `YOUR_TELEGRAM_CHAT_ID` | Número de chat ID | Body del nodo HTTP de Telegram |

---

## Paso 7 — Probar que funciona

### 7.1 Entender la diferencia entre URL de prueba y URL de producción

A diferencia de EP1 (que se ejecuta solo con "Test workflow"), este workflow necesita recibir un request externo para arrancar. Por eso hay dos modos de prueba:

**Modo test (editor abierto):** El webhook escucha en la URL de prueba. El workflow queda esperando el request. Cuando llega, ejecuta UNA VEZ en modo debug.

**Modo producción (workflow activo):** El webhook escucha en la URL de producción. Funciona permanentemente mientras el toggle esté activo.

### 7.2 Ejecutar la prueba con curl

1. Con el workflow abierto en el editor, hacé clic en el botón **"Test workflow"** (barra superior). El nodo Webhook muestra el texto "Waiting for test event..."
2. Abrí una terminal (en tu computadora o en el servidor donde corre n8n).
3. Ejecutá este comando:

   ```bash
   curl -X POST http://localhost:5678/webhook-test/release \
     -H "Content-Type: application/json" \
     -d '{"version": "2.4.0"}'
   ```

   > Si usás Windows sin WSL, podés usar PowerShell:
   > ```powershell
   > Invoke-RestMethod -Method POST -Uri "http://localhost:5678/webhook-test/release" -ContentType "application/json" -Body '{"version": "2.4.0"}'
   > ```

4. En el editor de n8n, los nodos empiezan a ejecutarse en cascada. Cada uno se pone verde cuando termina.

### 7.3 Probar sin especificar versión (usa la más reciente)

Si querés que el workflow elija automáticamente la versión más reciente del changelog, enviá el request sin el campo `version`:

```bash
curl -X POST http://localhost:5678/webhook-test/release \
  -H "Content-Type: application/json" \
  -d '{}'
```

El nodo de código ordena las versiones y elige la más alta automáticamente.

### 7.4 Resultado esperado

- El nodo Webhook recibe el payload y lo pasa al siguiente.
- El nodo de Google Sheets lee todas las filas del Changelog.
- El nodo de código filtra las filas de la versión indicada (o la más reciente).
- El nodo de OpenAI recibe el prompt y devuelve las release notes redactadas.
- El nodo de Telegram muestra `200 OK` en su output.
- **En Telegram**, en tu chat con el bot, recibís un mensaje con las release notes formateadas.

![Paso 7.4 — Ejecución exitosa y release notes en Telegram](assets/paso-10-resultado.png)

### 7.5 Activar el workflow para producción

Una vez que la prueba manual funciona:

1. En la parte superior del editor, activá el toggle **"Active"** (o **"Inactive"** → cambia a **"Active"**).
2. El nodo Webhook pasa a escuchar en la URL de producción:
   ```
   http://localhost:5678/webhook/release
   ```
3. Desde este momento, cualquier sistema externo (GitHub Actions, un script de deploy, Postman) puede llamar a esa URL para disparar el workflow.

**Ejemplo de integración con un script de deploy:**

```bash
# Al final de tu script de deploy, después de publicar la nueva versión:
curl -X POST https://tu-n8n.com/webhook/release \
  -H "Content-Type: application/json" \
  -d "{\"version\": \"$(cat VERSION)\"}"
```

---

## Problemas frecuentes

| Error | Causa | Solución |
|---|---|---|
| `The caller does not have permission` (Google Sheets) | La planilla no está compartida con la Service Account | Volvé al Paso 2.5 y compartí la planilla con el email de la Service Account |
| `Could not load the spreadsheet` (Google Sheets) | El ID de la planilla está mal pegado | Copiá el ID nuevamente desde la URL de la planilla. No incluyas el `/edit` ni los parámetros `?...` |
| `No changes found for version X` | La versión enviada en el webhook no existe en la planilla | Verificá que el valor de `version` en el request coincida exactamente con la columna Version del Changelog (ej: `2.4.0` no `v2.4.0`) |
| `401 Unauthorized` (OpenAI) | La API key está mal o tiene un error de formato en el header | Verificá que el valor del header sea exactamente `Bearer sk-proj-...` con un espacio entre "Bearer" y la key |
| `429 Too Many Requests` (OpenAI) | Llegaste al límite de velocidad de la API | Esperá un minuto y volvé a ejecutar. Si pasa seguido, tu cuenta puede necesitar más crédito |
| `Insufficient funds` (OpenAI) | Tu saldo de crédito en OpenAI llegó a cero | Recargué crédito en [https://platform.openai.com/settings/organization/billing](https://platform.openai.com/settings/organization/billing) |
| El webhook no responde al curl | El workflow no está en modo test ni activo | En el editor, hacé clic en "Test workflow" antes de enviar el curl. Para producción, activá el toggle "Active" |
| `Connection refused` al ejecutar curl | n8n no está corriendo o está en un puerto diferente | Verificá que n8n esté corriendo con `docker compose ps` y que el puerto sea el correcto |
| `Bad Request: chat not found` (Telegram) | El Chat ID está mal o el bot nunca recibió un mensaje de ese chat | Enviá un mensaje a tu bot desde Telegram y repetí el Paso 4.2 para obtener el chat ID correcto |
| `401 Unauthorized` (Telegram) | El token del bot está mal copiado | Verificá que el token en la URL no tenga espacios ni caracteres de más |
| `getUpdates` devuelve `"result":[]` | Nunca enviaste un mensaje al bot | Buscá tu bot en Telegram y escribílé cualquier mensaje, luego volvé a consultar la URL de getUpdates |
| Nodo aparece en rojo pero no hay mensaje de error | Credencial no asignada al nodo | Abrí el nodo y aseguráte de que el campo "Credential to connect with" tenga una credencial seleccionada, no vacío |

---

## Seguridad — checklist antes de cerrar

- [ ] El archivo JSON de la Service Account NO está en ninguna carpeta que sincronices con GitHub o la nube.
- [ ] La API key de OpenAI NO está escrita en ningún archivo del workflow (solo en la credencial de n8n).
- [ ] El token del bot de Telegram NO está hardcodeado en texto plano en ningún documento compartido.
- [ ] La URL del webhook de producción tiene algún mecanismo de validación si va a ser pública (ej: un secret en el header, o está detrás de una VPN).
- [ ] Activaste el 2FA en tu cuenta de Google Cloud Console.
- [ ] Activaste el 2FA en tu cuenta de OpenAI.

---

*Manual generado para el EP2 del canal de YouTube de JM Consulting — [https://github.com/jmconsultingsai/n8n-workflows](https://github.com/jmconsultingsai/n8n-workflows)*
