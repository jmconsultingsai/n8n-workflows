# Scraper de Leads — EP3 JM Consulting

Scripts de Python del video **EP3: Pipeline Completo de Leads con IA** del canal
[JM Consulting](https://www.youtube.com/@jmconsultingsai).

[[LINK AL VIDEO]]

---

## Que es esto

Dos scripts que automatizan la generacion de leads B2B a partir del **registro publico de empresas de Dinamarca** (CVR — Central Business Register), con sincronizacion directa a Google Sheets.

Son los mismos scripts que se usan en produccion en JM Consulting. Se publican sin credenciales ni datos personales para que puedas usarlos como base.

---

## Arquitectura: tres fases

```
Phase 1 — Discover
  scrape_cvr.py consulta Datafordeler CVR GraphQL v2
  por branchekode (codigo de industria danes)
  -> lista de CVREnhedsIds (IDs internos de empresas)

Phase 2 — Enrich
  Por cada ID, consulta en paralelo:
  nombre, direccion, email, telefono, empleados, numero CVR publico
  -> diccionario unificado por empresa

Phase 3 — Filter + Export
  Filtra por rango de empleados (configurable en .env)
  Exporta leads.csv con 10 columnas
```

```
sync_leads.py lee leads.csv
  -> normaliza columnas
  -> deduplica contra lo que ya esta en el Sheet
  -> clasifica en CALL_LIST o LINKEDIN_VOLUME segun score
  -> escribe en Google Sheets (3 tabs: RAW_LEADS, CALL_LIST, LINKEDIN_VOLUME)
```

---

## Setup

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 2. Configurar credenciales

```bash
cp .env.example .env
```

Edita `.env` con tus valores:

**Para `scrape_cvr.py`:**
- Registrate en [datafordeler.dk](https://datafordeler.dk/)
- Crea un IT-system y suscribite al servicio **CVR**
- Obtene credenciales OAuth2 (recomendado) o API Key
- Completalas en `.env` (`DATAFORDELER_OAUTH_CLIENT_ID` + `DATAFORDELER_OAUTH_CLIENT_SECRET`)

**Para `sync_leads.py`:**
- Crea un proyecto en [Google Cloud Console](https://console.cloud.google.com/)
- Habilitá la **Google Sheets API** y la **Google Drive API**
- Crea una Service Account y descarga el JSON de la clave
- Guarda el JSON como `credentials.json` en esta carpeta (o donde quieras y apuntalo en `.env`)
- Compartí tu Google Sheet con el email de la service account (como editor)
- Ponele el ID del Sheet en `.env` (`SPREADSHEET_ID`)

### 3. Seleccionar sectores (opcional)

Edita `sectors.yaml` para agregar o quitar sectores de industria. Cada sector tiene un nombre y una lista de branchekoder (codigos NACE del registro danes).

Para ver los sectores disponibles y scrapearlo todo:
```bash
python scrape_cvr.py
```

Para scrapecar un sector especifico:
```bash
python scrape_cvr.py --sector byggeri
python scrape_cvr.py --sector fast_ejendom --sector forsikring
```

Para inspeccionar el schema del API (util si algo falla):
```bash
python scrape_cvr.py --schema
```

### 4. Correr

```bash
# Paso 1: scrapecar el CVR y generar leads.csv
python scrape_cvr.py

# Paso 2: sincronizar con Google Sheets
python sync_leads.py

# Re-clasificar leads existentes (sin agregar nuevos)
python sync_leads.py --classify
```

---

## Estructura de archivos

```
scraper/
├── scrape_cvr.py      # Scraper principal — consulta Datafordeler GraphQL
├── sync_leads.py      # Sincronizacion con Google Sheets
├── sectors.yaml       # Sectores de industria y sus branchekoder
├── .env.example       # Plantilla de configuracion
├── requirements.txt   # Dependencias pip
└── README.md          # Este archivo
```

Archivos que se generan al correr (no los commitees):
```
leads.csv              # Output de scrape_cvr.py
credentials.json       # Tu service account key (no la compartas)
.env                   # Tu configuracion local (no la compartas)
schema.graphql         # Schema del API (generado con --schema, opcional)
```

---

## Como adaptarlo a tu pais

Esta es la parte mas importante del video.

Estos scripts estan disenados para el **registro CVR de Dinamarca**, pero la logica es identica para cualquier registro publico de empresas: llamar a un API, enriquecer los datos, filtrar por tamano, exportar a CSV.

**Para adaptar a tu pais:**

1. Busca el registro publico de empresas de tu pais (ejemplos: SAT en Mexico, AFIP en Argentina, Companies House en UK, SIRET en Francia, Handelsregister en Alemania, CUIT lookup en Argentina).
2. Pega `scrape_cvr.py` y `sectors.yaml` en Claude (o cualquier LLM) junto con la documentacion del API de tu pais.
3. Usá este prompt de ejemplo:

---

**Prompt para adaptar el scraper:**

```
Tengo un scraper de leads que consulta el registro CVR de Dinamarca via GraphQL.
Quiero adaptarlo para [pais] usando [nombre del API o registro publico].

El API de [pais] esta en [URL] y usa [REST/GraphQL/SOAP].
Documentacion: [link o pega el contenido aqui]

Por favor:
1. Reemplaza las queries GraphQL de Datafordeler por llamadas al API de [pais].
2. Mantene la misma estructura de tres fases: Discover (por categoria de industria) -> Enrich (nombre, email, telefono, direccion, empleados) -> Filter + Export (CSV).
3. Mantene las mismas columnas de salida: cvr, navn, branche, ansatte, adresse, postnr, by, telefon, email, virk_url (renames OK).
4. Mantene el mismo manejo de errores y reintentos.

El archivo original es scrape_cvr.py y lo adjunto. Tambien adjunto sectors.yaml para que adaptes los codigos de industria al sistema equivalente de [pais].
```

---

## Stack

- **Python 3.11+**
- **Datafordeler GraphQL API v2** — registro CVR de Dinamarca (requiere cuenta gratuita)
- **Google Sheets API** — via service account
- **n8n** — los workflows del EP3 complementan estos scripts (ver carpeta padre)

---

## Seguridad

- Nunca commitees `.env`, `credentials.json`, ni `leads.csv`.
- Estos archivos estan en `.gitignore` por defecto (el repo padre los excluye).
- La service account de Google solo necesita permisos de editor en el Sheet especifico — no le des permisos a nivel de proyecto.
- Las credenciales de Datafordeler solo tienen acceso a datos publicos del CVR. No hay datos personales sensibles en el registro.

---

## Licencia

MIT — usa, modifica, distribuye. Una mencion al canal es bienvenida pero no obligatoria.
