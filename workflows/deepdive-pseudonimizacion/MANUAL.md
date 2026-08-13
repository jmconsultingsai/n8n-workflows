# Manual — Pseudonimización de PII antes de mandar datos a un LLM

> Este manual acompaña al archivo `workflow.json`. A diferencia de los otros
> episodios, acá lo importante **no es el workflow: es la regla de decisión**.
> Leé la sección "La regla" antes de importar nada.
>
> **Tiempo estimado: 10-15 minutos.**

---

## El problema

Pseudonimizar el email de un cliente antes de mandarlo a un LLM externo suena
bien. Y sirve — para ese campo.

El problema es que en un ticket de soporte real hay **dos clases de campos**:

| Clase | Ejemplo | Quién lo llenó |
|---|---|---|
| Con esquema | `email`, `phone`, `customer_id`, `dni` | Un formulario. Sabés qué hay adentro. |
| Texto libre | `issue_description`, `notas`, `comentario` | Una persona. No sabés qué hay adentro. |

Un control que solo cubre la primera clase **se anula a sí mismo**: hasheás el
email del campo `email` y el mismo email viaja en texto plano dentro de
`issue_description`, porque el cliente lo escribió ahí.

Eso no es una fuga parcial. Es un control que existe, corre, pasa la auditoría,
y no cubre el caso que importa.

---

## La regla

Antes de escribir una sola línea de código, pasá cada campo por estos cinco pasos:

| # | Pregunta | Acción |
|---|---|---|
| 1 | ¿El campo tiene esquema, o lo escribió un humano? | Separalos. Son dos problemas distintos. |
| 2 | **Con esquema** → ¿lo necesita la tarea? | No → excluilo. Sí → pseudonimizalo. Determinístico y verificable. |
| 3 | **Texto libre** → ¿la tarea necesita el TEXTO, o un DATO de adentro? | Definilo antes de codear. |
| 4 | Necesita un dato | Extraelo y mandá **el dato**, no el párrafo. |
| 5 | Necesita el texto entero | **No hay solución del lado del prompt.** El control se mueve de capa: DPA con el proveedor, retención cero, o modelo local. |

El paso 5 es el incómodo, y es el que hace falta decir en voz alta. Si tu tarea
necesita el párrafo completo escrito por una persona, ningún regex te va a
salvar. Lo que cambia es **dónde** ponés el control, no cuánto lo apretás.

---

## Los dos workflows

Este video compara dos versiones. **Solo una de las dos se publica como
importable.**

| | Qué es | Dónde está |
|---|---|---|
| **PSEUDO-A** | El ingenuo. Pseudonimiza el campo con esquema y manda el texto libre en crudo. | Solo como bloque de código acá abajo. **No se publica como `workflow.json`.** |
| **PSEUDO-B** | El corregido. Lo mismo + un nodo de scrub sobre el texto libre. | `workflow.json` — este es el que importás. |

PSEUDO-A no se publica importable a propósito. Es un antipatrón: cualquiera que
lo importe se lleva la vulnerabilidad puesta.

---

## PSEUDO-A — el antipatrón

Un solo nodo de código entre el ticket y el LLM:

```javascript
// Nodo Code — "Pseudonymize"
const crypto = require('crypto');

function pseudonymize(value, salt) {
  return crypto.createHash('sha256')
    .update(value + salt)
    .digest('hex')
    .slice(0, 12); // Hash corto — suficiente para correlacionar internamente
}

const PSEUDONYM_SALT = $env["PSEUDONYM_SALT"];

const contact = $input.all()[0].json;

const pseudonymMap = {
  original_email: contact.email,
  pseudo_id: pseudonymize(contact.email, PSEUDONYM_SALT)
};

// Lo que va al LLM
return {
  json: {
    pseudo_id: pseudonymMap.pseudo_id,
    company: contact.company,
    issue_description: contact.issue_description, // ⚠️ acá está el problema
    ticket_category: contact.ticket_category
  }
};
```

El código está bien escrito. El hash es correcto, el salt sale de una variable
de entorno, el `pseudo_id` es estable. **El problema no es el código: es que
`issue_description` pasa sin tocar.**

Con un ticket donde el cliente escribió su nombre, su DNI, su mail y su teléfono
dentro de la descripción, esto es lo que sale hacia el LLM externo:

```json
{
  "pseudo_id": "<hash de 12 chars>",
  "company": "Distribuidora Andes SA",
  "issue_description": "Hola, soy María González, DNI 34.567.890. No me llegó la factura de julio a mi mail maria.gonzalez@distribuidoraandes.com y la necesito para cerrar el mes. Mi teléfono es +54 9 11 5555-1234 por si me quieren llamar. La tarjeta que tengo cargada termina en 4417.",
  "ticket_category": "facturacion"
}
```

Contá: **1 campo protegido, 5 datos personales en texto plano** — nombre, DNI,
email, teléfono y los últimos 4 de la tarjeta. Y el email es exactamente el
campo que el nodo se molestó en hashear.

---

## PSEUDO-B — el corregido

El delta es **un nodo**. Nada más.

```javascript
// Nodo Code — "Scrub PII"
// El unico delta con el workflow ingenuo: limpiar el texto libre.
// El orden importa: el email va primero, o los otros patrones le comen los digitos.

const PATTERNS = [
  [/[\w.+-]+@[\w-]+\.[\w.]+/g,                 '[EMAIL]'],
  [/\b\d{1,2}\.?\d{3}\.?\d{3}\b/g,             '[DNI]'],
  [/(?:\+?\d{1,3}[ -]?)?(?:\d[ -]?){8,13}\d/g, '[TELEFONO]']
];

function scrub(text) {
  return PATTERNS.reduce((acc, [re, tag]) => acc.replace(re, tag), text || '');
}

const data = $input.all()[0].json;

return {
  json: {
    ...data,
    issue_description: scrub(data.issue_description)
  }
};
```

> **El orden de los patrones no es decorativo.** El email va primero. Si corrés
> el patrón de DNI o de teléfono antes, se comen los dígitos que están dentro
> de la dirección de mail y el patrón de email ya no matchea nada.

Mismo ticket, ahora el `issue_description` que sale:

```
Hola, soy María González, DNI [DNI]. No me llegó la factura de julio a mi mail
[EMAIL] y la necesito para cerrar el mes. Mi teléfono es [TELEFONO] por si me
quieren llamar. La tarjeta que tengo cargada termina en 4417.
```

El `pseudo_id` es **idéntico** al de PSEUDO-A: mismo salt, mismo hash
determinístico. No perdés capacidad operativa — seguís pudiendo correlacionar
tickets del mismo cliente.

### Qué NO cubre este scrub

Esto no es una nota al pie. Es la mitad del punto.

| Qué se escapa | Por qué | Qué hacer |
|---|---|---|
| **El nombre** (`María González`) | No tiene forma. No existe un regex para "un nombre propio". | Paso 5 de la regla. |
| **`termina en 4417`** | Cuatro dígitos sueltos son indistinguibles de un número de factura o un año. | Paso 5 de la regla. |
| **Direcciones, nombres de terceros, datos de salud** | Misma razón: no tienen forma distinguible. | Paso 5 de la regla. |

**¿Y por qué no le ponemos un NER (reconocimiento de entidades)?**

Porque un control de seguridad probabilístico falla **en silencio**. Con el
regex sabés exactamente qué cubre y qué no: es determinístico y auditable.
Con un NER pasás de *"sé que no cubro nombres"* a *"creo que cubro nombres"* —
y el día que falla no te enterás.

Eso es el mismo teatro de seguridad que este workflow denuncia, un piso más
arriba. Si necesitás cubrir nombres, la respuesta es el paso 5: mover el
control de capa. No un modelo que acierta casi siempre.

---

## Qué necesitás antes de empezar

| Servicio | Para qué se usa | ¿Gratis? |
|---|---|---|
| OpenAI | Generar la respuesta de soporte | **Pago** — ver alternativas abajo |
| n8n | Ejecutar el workflow | Sí (self-hosted) o plan gratuito en n8n Cloud |

> **OpenAI es el único servicio pago**, y solo se usa para el nodo final que
> escribe la respuesta al cliente. Podés reemplazarlo por **Ollama** (local, sin
> costo de API) o **Google Gemini** free tier: cambiá el nodo
> `OpenAI Chat Model` por el modelo de chat correspondiente. El scrub y la
> pseudonimización no dependen del proveedor.

---

## Paso 1 — Requisitos de entorno en n8n

Este workflow usa `require('crypto')` y `$env` dentro de un nodo Code. n8n
bloquea las dos cosas por defecto. **Si no configurás esto, el nodo falla o —
peor — devuelve un salt vacío sin avisar.**

| Variable | Valor | Para qué |
|---|---|---|
| `NODE_FUNCTION_ALLOW_BUILTIN` | `crypto` | Habilita `require('crypto')` en nodos Code |
| `N8N_BLOCK_ENV_ACCESS_IN_NODE` | `false` | Habilita `$env[...]` en nodos Code |
| `PSEUDONYM_SALT` | 64 caracteres hex, generados al azar | El salt del hash |

Generá el salt así (nunca lo escribas a mano, nunca lo commitees):

```bash
openssl rand -hex 32
```

> ⚠️ **`N8N_BLOCK_ENV_ACCESS_IN_NODE` tiene que ser el string literal `false`.**
> n8n lo evalúa como `process.env.N8N_BLOCK_ENV_ACCESS_IN_NODE !== 'false'`.
> Si ponés `0`, `False` o `FALSE`, el acceso queda **bloqueado en silencio** y
> `$env["PSEUDONYM_SALT"]` te devuelve `undefined`. El hash sale igual, sin
> error — y es un hash sin salt.

> ⚠️ **`N8N_RESTRICT_ENVIRONMENT_VARIABLES_ACCESS` no existe en n8n.** Si la
> tenés en tu `docker-compose.yml`, es inerte. No confíes en ella para nada.

En Docker Compose:

```yaml
services:
  n8n:
    environment:
      - NODE_FUNCTION_ALLOW_BUILTIN=crypto
      - N8N_BLOCK_ENV_ACCESS_IN_NODE=false
      - PSEUDONYM_SALT=${PSEUDONYM_SALT}   # el valor real va en el .env, nunca acá
```

Reiniciá n8n después de cambiar las variables (`docker compose up -d`).

### Verificar que quedó bien

Creá un nodo Code temporal, ejecutalo, y borralo:

```javascript
const crypto = require('crypto');
return [{ json: {
  require_crypto: typeof crypto.createHash === 'function' ? 'OK' : 'FALLA',
  env_access:     $env["PSEUDONYM_SALT"] ? 'OK len=' + $env["PSEUDONYM_SALT"].length : 'FALLA'
}}];
```

Esperado: `{"require_crypto":"OK","env_access":"OK len=64"}`.

> Fijate que imprime la **longitud** del salt, nunca el valor. Un salt en
> pantalla es un salt quemado — y si estás grabando o compartiendo pantalla,
> queda para siempre.

---

## Paso 2 — Credencial de OpenAI

1. Andá a [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys).
2. Hacé clic en **"Create new secret key"** y copiá la clave. Es la única vez que se muestra completa.
3. En n8n: **Settings → Credentials → Add credential**.
4. Buscá **"OpenAI API"**, pegá la clave y guardala como `OpenAI API`.

---

## Paso 3 — Importar el workflow

1. En n8n, andá a **Workflows** → **"+"** → **"Import from File"** → seleccioná `workflow.json`.
2. Asigná la credencial:

| Nodo | Placeholder / campo | Qué poner |
|---|---|---|
| `OpenAI Chat Model` | Credencial | Seleccioná `OpenAI API` |

3. El nodo `Ticket entrante` trae un ticket de ejemplo hardcodeado
   (**datos ficticios** — María González / Distribuidora Andes SA). En producción
   reemplazalo por tu trigger real: webhook, Gmail, formulario, lo que sea.

---

## Paso 4 — Probar que funciona

1. Hacé clic en **"Execute workflow"** (el trigger es manual, no hay poll ni webhook).
2. Abrí el nodo `Scrub PII` y mirá el output.

Resultado esperado en `issue_description`:

```
Hola, soy María González, DNI [DNI]. No me llegó la factura de julio a mi mail
[EMAIL] y la necesito para cerrar el mes. Mi teléfono es [TELEFONO] por si me
quieren llamar. La tarjeta que tengo cargada termina en 4417.
```

Si ves `[EMAIL]`, `[DNI]` y `[TELEFONO]` en su lugar, el scrub anda.
Si ves `María González` y `4417` todavía ahí — **es correcto**. Eso es lo que el
scrub no cubre, y saberlo es el punto del ejercicio.

El `pseudo_id` va a ser un hash de 12 caracteres. Ejecutá dos veces: tiene que
dar **el mismo valor**. Si cambia entre ejecuciones, el salt no se está leyendo
(volvé al Paso 1).

---

## Problemas frecuentes

| Error | Causa | Solución |
|---|---|---|
| `Cannot find module 'crypto'` | Falta `NODE_FUNCTION_ALLOW_BUILTIN=crypto` | Agregala y reiniciá n8n (Paso 1) |
| `$env is not defined` / el salt viene `undefined` | `N8N_BLOCK_ENV_ACCESS_IN_NODE` no está en el string literal `false` | Poné exactamente `false`, no `0` ni `False` |
| El `pseudo_id` cambia en cada ejecución | El salt está vacío y cambia el input, o se está leyendo mal | Corré el nodo de verificación del Paso 1 |
| El email queda a medias, tipo `[DNI]@dominio.com` | Alguien reordenó los patrones y el DNI corre antes que el email | El email va **primero** en el array `PATTERNS` |
| Un número de factura se convirtió en `[DNI]` | Falso positivo: 7-8 dígitos son 7-8 dígitos | Esperable. Un scrub por regex sobre-captura; es el costo de no sub-capturar |
| El nombre del cliente sigue apareciendo | No es un bug | Ver "Qué NO cubre este scrub" |

---

## Seguridad — checklist antes de cerrar

- [ ] El `PSEUDONYM_SALT` está en el `.env`, no en el `docker-compose.yml` ni en el JSON.
- [ ] El `.env` está en el `.gitignore`.
- [ ] El salt nunca se imprimió en un output de n8n ni en un log.
- [ ] La API key de OpenAI no está en ningún documento compartido ni en el JSON exportado.
- [ ] El nodo Code de verificación del Paso 1 se borró después de usarlo.
- [ ] Pasaste **todos** tus campos por la regla de 5 pasos, no solo el email.
- [ ] Si algún campo de texto libre viaja entero, tenés el control en otra capa (DPA, retención cero, o modelo local) — y está escrito en algún lado.

---

*Manual del deep dive de pseudonimización del canal de YouTube de JM Consulting — [https://github.com/jmconsultingsai/n8n-workflows](https://github.com/jmconsultingsai/n8n-workflows)*
