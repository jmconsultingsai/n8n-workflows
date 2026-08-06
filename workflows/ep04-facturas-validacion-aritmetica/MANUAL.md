# Manual de configuración — EP4: Validación aritmética de facturas con IA

> Este manual acompaña al archivo `workflow.json`. Seguí los pasos en orden:
> primero creás las cuentas y credenciales, después preparás las planillas,
> luego importás el workflow, y al final lo probás con tus propias facturas.
>
> **Tiempo estimado: 20-35 minutos** (más si es la primera vez que configurás Google OAuth2).

---

## Qué hace este workflow

Vigila una carpeta de Google Drive. Cuando aparece un PDF, lo descarga, extrae el texto, y se lo pasa a un modelo de lenguaje para que devuelva los datos estructurados (emisor, items, subtotal, impuestos, total). Después, un nodo de código determinista re-suma los items, compara cada monto contra el texto crudo del PDF —para detectar si el modelo alteró algún número en el camino—, y escribe el resultado en dos pestañas de Google Sheets: una con la cabecera de la factura y otra con el detalle línea por línea. Si hay algún problema de severidad alta, llega una alerta a Telegram con el tipo de error y la diferencia exacta en pesos.

---

## Qué necesitás antes de empezar

| Servicio | Para qué se usa | ¿Gratis? |
|---|---|---|
| Google Drive (OAuth2) | Detectar PDFs nuevos y descargarlos | Sí |
| Google Sheets (OAuth2) | Registrar resultados en dos pestañas | Sí |
| OpenAI | Extraer datos estructurados de los PDFs | **Pago** — alternativa gratis: ver nota abajo |
| Telegram | Recibir alertas cuando hay incidencias | Sí |
| n8n | Ejecutar el workflow | Sí (self-hosted) o plan gratuito en n8n Cloud |

> **OpenAI es el único servicio pago.** El workflow usa el nodo `Information Extractor` de n8n, que acepta cualquier proveedor compatible. Alternativas gratuitas probadas con este nodo:
> - **Ollama** (local): descargá Ollama, correlo localmente, y en el nodo `OpenAI Chat Model` cambiá la credencial por una de tipo `Ollama`. No tiene costo de API.
> - **Google Gemini** (free tier): creá una API key en [aistudio.google.com](https://aistudio.google.com), creá una credencial de tipo `Google Gemini(PaLM) Api` en n8n, y reemplazá el nodo `OpenAI Chat Model` por un nodo `Google Gemini Chat Model`. El free tier tiene cuota diaria suficiente para pruebas.

---

## Paso 1 — Credenciales de Google (Drive + Sheets)

Drive y Sheets comparten la misma app OAuth2 en Google Cloud Console. Se crea una sola app y se crean dos credenciales en n8n.

### 1.1 Crear un proyecto en Google Cloud Console

1. Abrí [https://console.cloud.google.com](https://console.cloud.google.com).
2. Si ya tenés un proyecto `n8n-workflows` de episodios anteriores, podés reutilizarlo: sólo tenés que habilitar las APIs nuevas. Si no, hacé clic en el selector de proyecto arriba a la izquierda → **"Nuevo proyecto"** → poné el nombre que quieras y hacé clic en **"Crear"**.

### 1.2 Habilitar Google Drive API y Google Sheets API

1. Andá a [https://console.cloud.google.com/apis/library](https://console.cloud.google.com/apis/library).
2. Buscá `Google Drive API` → hacé clic → **"Habilitar"**.
3. Buscá `Google Sheets API` → hacé clic → **"Habilitar"**.

### 1.3 Configurar la pantalla de consentimiento OAuth

Si es la primera vez que usás OAuth en este proyecto, Google te pide configurarla antes de crear credenciales:

1. En el menú de la izquierda, andá a **"APIs y servicios" → "Pantalla de consentimiento de OAuth"**.
2. Tipo de usuario: **Externo** → **"Crear"**.
3. Completá los campos obligatorios: nombre de la app (ej. `n8n-workflows`), email de soporte, email del desarrollador. Guardá y continuá.
4. En "Alcances", no hace falta agregar nada manualmente — n8n los solicita durante la autorización.
5. En **"Usuarios de prueba"**, hacé clic en **"+ Add users"** y agregá tu propio email de Google. Guardá.

> Mientras la app esté en modo "Usuarios de prueba", solo el email que agregaste puede autorizarla. Es suficiente para uso personal.

### 1.4 Crear el Client ID OAuth2

1. En el menú de la izquierda, hacé clic en **"Credenciales"**.
2. Hacé clic en **"+ Crear credenciales"** → **"ID de cliente de OAuth"**.
3. Tipo de aplicación: **Aplicación web**.
4. Nombre: `n8n OAuth2` (o el que prefieras).
5. En **"URIs de redireccionamiento autorizados"**, hacé clic en **"+ Agregar URI"** y pegá la URL de callback de tu instancia de n8n:
   - n8n Cloud: `https://app.n8n.cloud/rest/oauth2-credential/callback`
   - Self-hosted local: `http://localhost:5678/rest/oauth2-credential/callback`
   - Self-hosted con dominio propio: `https://tu-dominio.com/rest/oauth2-credential/callback`
6. Hacé clic en **"Crear"**. Google muestra el **Client ID** y el **Client Secret**. Copialos a un lugar seguro — los necesitás en los pasos 1.5 y 1.6.

### 1.5 Crear la credencial de Google Drive en n8n

1. En n8n, andá a **Settings → Credentials → Add credential**.
2. Buscá y seleccioná **"Google Drive OAuth2 API"**.
3. Pegá el **Client ID** y el **Client Secret** del paso anterior.
4. Hacé clic en **"Sign in with Google"** y autorizá con la cuenta de Google que tiene la carpeta de facturas.
5. Si aparece el tilde verde ✓, la credencial está lista. Guardala con un nombre claro, por ejemplo: `Google Drive OAuth2`.

> Si Google muestra una advertencia "Esta app no está verificada", hacé clic en **"Configuración avanzada"** → **"Ir a n8n-workflows (no seguro)"**. Es el comportamiento normal para apps en modo de prueba.

### 1.6 Crear la credencial de Google Sheets en n8n

Mismo Client ID y Client Secret — es una credencial separada en n8n porque el tipo es distinto.

1. En n8n, andá a **Settings → Credentials → Add credential**.
2. Buscá y seleccioná **"Google Sheets OAuth2 API"**.
3. Pegá el mismo **Client ID** y **Client Secret**.
4. Hacé clic en **"Sign in with Google"** y autorizá. Esta vez Google puede pedir permisos para Sheets — aceptalos.
5. Guardala con un nombre claro: `Google Sheets OAuth2`.

---

## Paso 2 — OpenAI

1. Creá una cuenta en [https://platform.openai.com](https://platform.openai.com) si no tenés una.
2. Andá a [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys).
3. Hacé clic en **"Create new secret key"**, poné un nombre descriptivo, y copiá la clave generada. Es la única vez que se muestra completa.
4. En n8n, andá a **Settings → Credentials → Add credential**.
5. Buscá y seleccioná **"OpenAI API"**.
6. En el campo **"API Key"**, pegá la clave que copiaste.
7. Guardala como `OpenAI API`.

> La API de OpenAI es paga por uso. El modelo configurado (`gpt-4o-mini`) es el más económico de la línea. Para uso de prueba con algunos PDFs, el costo es centavos de dólar. Si preferís no gastar nada, usá Ollama o Gemini (ver sección "Qué necesitás antes de empezar").

---

## Paso 3 — Bot de Telegram

### 3.1 Crear el bot con @BotFather

1. En Telegram, buscá `@BotFather` (el oficial tiene tilde azul de verificación).
2. Escribile `/newbot`.
3. Elegí un nombre visible (ej. `Facturas Bot`) y un username que termine en `bot` (ej. `mis_facturas_bot`).
4. BotFather te responde con el **token del bot** (formato `1234567890:AAFxxx...`). Copialo.

### 3.2 Obtener tu Chat ID

El `{YOUR_TELEGRAM_CHAT_ID}` que necesitás no es el del bot, sino el de tu propia cuenta de Telegram.

1. Buscá tu nuevo bot en Telegram y escribile cualquier mensaje (ej. `hola`).
2. Abrí este URL en el navegador (reemplazando `TU_TOKEN` por el token real):
   ```
   https://api.telegram.org/botTU_TOKEN/getUpdates
   ```
3. En el JSON que aparece, buscá el campo `"chat"` → `"id"`. Ese número es tu Chat ID.

### 3.3 Crear la credencial de Telegram en n8n

1. En n8n, andá a **Settings → Credentials → Add credential**.
2. Buscá y seleccioná **"Telegram API"**.
3. En el campo **"Access Token"**, pegá el token del bot.
4. Hacé clic en **"Save"**. Si aparece ✓, está bien.
5. Guardala como `Telegram Bot API`.

---

## Paso 4 — Preparar las dos pestañas en Google Sheets

El workflow escribe en dos pestañas. Tenés que crearlas con los nombres y encabezados **exactamente** como se muestran abajo: el nodo de Sheets resuelve la pestaña por nombre, y mapea cada columna por su encabezado exacto. Un espacio de más o una mayúscula distinta hace que el nodo escriba en la columna equivocada sin mostrar ningún error.

### 4.1 Crear la planilla

1. Andá a [https://sheets.google.com](https://sheets.google.com) y creá una planilla nueva.
2. Ponele el nombre que quieras al archivo (el workflow la localiza por ID, no por nombre).
3. Copiá el ID de la URL. El formato es:
   ```
   https://docs.google.com/spreadsheets/d/AQUI_ESTA_EL_ID/edit
   ```
   El ID es la parte entre `/d/` y `/edit`. Guardalo — lo necesitás en el Paso 5.

> **Gotcha importante**: Google nombra `Untitled` (o `Hoja 1`) a toda pestaña creada por defecto. Si dejás ese nombre, el nodo no la va a encontrar y no va a escribir nada — sin error visible, sin fila. Esta es exactamente la misma falla silenciosa que el episodio demuestra con la factura manipulada. El nombre de la pestaña tiene que coincidir con el que espera el nodo.

### 4.2 Pestaña EP4_FACTURAS (cabecera de factura — 18 columnas)

1. Renombrá la primera pestaña a `EP4_FACTURAS` (clic derecho sobre la pestaña → "Rename").
2. En la fila 1, escribí los siguientes encabezados exactamente en este orden, uno por celda:

```
procesado_en | archivo | numero_factura | emisor | cuit_emisor | fecha_emision | fecha_vencimiento | moneda | cantidad_items | suma_items | subtotal_declarado | impuestos_total | impuestos_recalculado | total_declarado | total_recalculado | estado | cantidad_problemas | problemas
```

### 4.3 Pestaña EP4_ITEMS (detalle línea por línea — 13 columnas)

1. Creá una segunda pestaña: clic en el **"+"** abajo a la izquierda.
2. Renombrala a `EP4_ITEMS`.
3. En la fila 1, escribí estos encabezados en orden:

```
procesado_en | archivo | numero_factura | emisor | moneda | item_nro | descripcion | cantidad | precio_unitario | importe_declarado | importe_recalculado | diferencia | estado_item
```

La relación entre las dos pestañas es cabecera/detalle: se unen por `numero_factura`. `EP4_FACTURAS` responde "¿esta factura cierra?"; `EP4_ITEMS` responde "¿qué se compró y a qué precio?".

---

## Paso 5 — Importar el workflow y configurar los placeholders

### 5.1 Importar

1. En n8n, andá a **Workflows**.
2. Hacé clic en **"+"** → **"Import from File"** y seleccioná `workflow.json`.
3. El workflow se importa con los nodos en rojo — normal, todavía no asignaste credenciales.

### 5.2 Reemplazar placeholders y asignar credenciales

Abrí cada nodo indicado en la tabla y completá los valores:

| Nodo | Placeholder / campo | Qué poner |
|---|---|---|
| `Drive — Nueva factura` | Credencial | Seleccioná `Google Drive OAuth2` |
| `Drive — Nueva factura` | `{YOUR_DRIVE_FOLDER_ID}` | ID de tu carpeta de Drive (de la URL: `drive.google.com/drive/folders/ESTE_ES_EL_ID`) |
| `Drive — Nueva factura` | `{YOUR_DRIVE_FOLDER_NAME}` | Nombre de tu carpeta (para referencia visual) |
| `Drive — Descargar PDF` | Credencial | Seleccioná `Google Drive OAuth2` |
| `OpenAI Chat Model` | Credencial | Seleccioná `OpenAI API` |
| `Sheets — Registrar factura` | Credencial | Seleccioná `Google Sheets OAuth2` |
| `Sheets — Registrar factura` | `{YOUR_SPREADSHEET_ID}` | ID de tu planilla (del Paso 4.1) |
| `Sheets — Registrar items` | Credencial | Seleccioná `Google Sheets OAuth2` |
| `Sheets — Registrar items` | `{YOUR_SPREADSHEET_ID}` | El mismo ID de planilla |
| `Telegram — Avisar` | Credencial | Seleccioná `Telegram Bot API` |
| `Telegram — Avisar` | `{YOUR_TELEGRAM_CHAT_ID}` | Tu Chat ID (del Paso 3.2) |

---

## Paso 6 — Probar que funciona

### 6.1 Cómo activar el workflow antes de subir facturas

**El trigger de Drive es un poll (consulta periódica), no un webhook.** Esto tiene una consecuencia importante: el trigger solo detecta archivos nuevos a partir del momento en que el workflow se activa. Los PDFs que ya estaban en la carpeta cuando lo activás NO se levantan.

El orden correcto es:

1. **Primero activá el workflow** con el toggle "Active" en la parte superior del editor.
2. **Después subí el PDF** a la carpeta vigilada.
3. Esperá hasta un minuto: el poll corre cada minuto.

Si subís el PDF antes de activar, no pasa nada — sin error, sin fila. Es exactamente la falla silenciosa que el episodio muestra.

### 6.2 Resultado esperado para una factura sin problemas

- En `EP4_FACTURAS`, aparece una nueva fila con `estado = OK` y `cantidad_problemas = 0`.
- En `EP4_ITEMS`, aparecen tantas filas como líneas tenga la factura, todas con `estado_item = OK`.
- No llega ningún mensaje a Telegram.

### 6.3 Resultado esperado para una factura con problemas

- En `EP4_FACTURAS`, aparece la fila con `estado = REVISAR` o `estado = ADVERTENCIA`.
- La columna `problemas` lista los códigos de error separados por coma (ej. `SUBTOTAL_NO_CIERRA, IA_ALTERO_EL_DATO`).
- Llega un mensaje a Telegram con el detalle de cada problema y la diferencia en dinero.

### 6.4 Cómo repetir una prueba con el mismo PDF

El trigger es `fileCreated`: para volver a procesar el mismo PDF tenés que borrarlo de la carpeta y subirlo de nuevo — eso cuenta como archivo nuevo. También borrá las filas de las dos pestañas entre tandas para que la planilla empiece limpia.

### 6.5 Importante: no usar "Execute workflow" mientras está activo

Si el workflow está activo y presionás "Execute workflow", el archivo se procesa dos veces — una ejecución manual y una del trigger — y quedan dos filas idénticas por factura. Subí el PDF y esperá el poll.

---

## Códigos de severidad

El campo `estado` de `EP4_FACTURAS` toma uno de tres valores:

| Estado | Severidad | Significado |
|---|---|---|
| `OK` | — | Sin problemas. La factura pasó todas las validaciones. |
| `ADVERTENCIA` | Media | Algo raro, pero no bloquea el pago. Requiere revisión eventual. |
| `REVISAR` | Alta | Hay al menos un problema grave. No debe avanzar a pago sin revisión humana. |

**Problemas de severidad alta** (`REVISAR`):
`CAMPO_FALTANTE`, `SIN_ITEMS`, `ITEM_NO_CIERRA`, `SUBTOTAL_NO_CIERRA`, `TOTAL_NO_CIERRA`, `TOTAL_VS_ITEMS`, `TOTAL_NO_POSITIVO`, `IA_ALTERO_EL_DATO`

**Problemas de severidad media** (`ADVERTENCIA`):
`ITEM_SIN_IMPORTE`, `FECHA_INVALIDA`, `FECHA_FUERA_RANGO`, `MONEDA_DESCONOCIDA`

**Tolerancia aritmética**: 0,01. Suficiente para cubrir el redondeo normal de dos decimales; cualquier diferencia mayor a un centavo se reporta.

`IA_ALTERO_EL_DATO` merece atención especial: significa que el modelo devolvió un número distinto al que figura en el PDF. El workflow usa el valor del PDF, no el del modelo, y lo registra con la diferencia exacta.

---

## Problemas frecuentes

| Error | Causa | Solución |
|---|---|---|
| El PDF se subió pero no aparece ninguna fila | El workflow estaba inactivo cuando se subió el archivo | Activá el workflow, borrá el PDF, volvé a subirlo |
| Aparecen filas duplicadas por factura | Se presionó "Execute workflow" mientras el workflow estaba activo | Borrá las filas duplicadas y evitá ejecutar manualmente cuando está activo |
| `estado = REVISAR` con `CAMPO_FALTANTE` | El modelo no encontró el campo en el PDF | Puede ser un escaneo (sin capa de texto), un PDF con formato inusual, o un campo genuinamente ausente |
| `estado = REVISAR` con `SIN_CAPA_DE_TEXTO` | El PDF es un escaneo sin texto extraíble | Hay que pasar el PDF por OCR antes de procesarlo. Esta validación corta antes de tocar la IA |
| No llega alerta a Telegram | El Chat ID está mal o el bot nunca recibió un mensaje | Verificá que hayas escrito al bot al menos una vez, y repetí el Paso 3.2 para obtener el ID correcto |
| Las filas van a la planilla pero en columnas equivocadas | Los encabezados de la pestaña no coinciden exactamente con los esperados | Verificá que los encabezados del Paso 4.2 y 4.3 estén escritos tal cual, sin espacios extra ni mayúsculas distintas |
| La pestaña no escribe nada (sin error) | El nombre de la pestaña no coincide con `EP4_FACTURAS` o `EP4_ITEMS` | Renombrá la pestaña exactamente así. Google nombra `Hoja 1` por defecto — hay que cambiarlo a mano |
| `invalid_grant` o `Token has been expired` | El token OAuth2 expiró o fue revocado | Andá a la credencial en n8n y reconectá haciendo clic en "Sign in with Google" |
| `The caller does not have permission` (Sheets o Drive) | La cuenta OAuth2 no tiene acceso al archivo o carpeta | La planilla y la carpeta tienen que estar en el Drive de la cuenta que autorizaste, o compartidas con esa cuenta |
| `Forbidden: bot can't initiate conversation` (Telegram) | El bot nunca recibió un mensaje de ese chat | Buscá el bot en Telegram y escribile cualquier mensaje antes de testear |

---

## Seguridad — checklist antes de cerrar

- [ ] Las credenciales OAuth2 de Google no están escritas en ningún archivo de texto plano.
- [ ] La API key de OpenAI no está en ningún documento compartido ni en el JSON exportado.
- [ ] El token del bot de Telegram no está hardcodeado en ningún lugar.
- [ ] La app OAuth2 en Google Cloud Console tiene solo tu email en "Usuarios de prueba".
- [ ] El `workflow.json` que subiste a GitHub es el de esta carpeta (ya sanitizado), no el exportado directamente de tu n8n.

---

*Manual generado para el EP4 del canal de YouTube de JM Consulting — [https://github.com/jmconsultingsai/n8n-workflows](https://github.com/jmconsultingsai/n8n-workflows)*
