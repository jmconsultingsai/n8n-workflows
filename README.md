<div align="center">

<img src="https://github.com/jmconsultingsai.png" width="100" alt="JM Consulting logo" />

# n8n Workflows — JM Consulting

Free, production-tested n8n workflows from the [JM Consulting YouTube channel](https://www.youtube.com/@jmconsultingsai).

Every workflow ships as a pair: a **fully sanitized JSON** (no credentials, no personal IDs — nothing to leak) and a **step-by-step manual** that walks you through creating your own credentials and API keys, even if you have never created one before.

</div>

---

## How to use a workflow

1. Pick a workflow from the index below and open its folder.
2. Read `MANUAL.md` first — it tells you exactly which accounts, API keys, and credentials you need and how to create each one (exact URLs, tabs, and buttons).
3. In n8n: **Workflows → Import from File** → select `workflow.json`.
4. Assign your credentials to each node, replace the `{PLACEHOLDER}` values, and run the test described at the end of the manual.

## Workflow index

| # | Workflow | What it does | Services used | Video |
|---|---|---|---|---|
| EP01 | [Daily Executive Report](workflows/ep01-daily-executive-report/) | Reads sales, marketing & support data → AI summary → Telegram | Google Sheets, OpenAI, Telegram | [Watch](https://www.youtube.com/@jmconsultingsai) |
| EP02 | [AI Release Notes](workflows/ep02-release-notes-ai/) | Webhook receives deploy data → AI generates release notes → Telegram | Webhook, OpenAI, Telegram | [Watch](https://www.youtube.com/@jmconsultingsai) |
| EP03 | [Pipeline Completo](workflows/ep03-pipeline-completo/) | Full lead gen pipeline: cold email by sector + daily Telegram report + LinkedIn outreach reminders | Google Sheets, Gmail, Telegram | [Watch](https://www.youtube.com/@jmconsultingsai) |
| EP03 | [CVR Scraper](workflows/ep03-pipeline-completo/scraper/) | Python scripts that scrape Denmark's public business registry (Datafordeler CVR GraphQL), enrich leads, and sync to Google Sheets. Adaptable to any country's registry via LLM. | Datafordeler API, Google Sheets | [Watch](https://www.youtube.com/@jmconsultingsai) |
| EP04 | [Validación aritmética de facturas](workflows/ep04-facturas-validacion-aritmetica/) | Watches a Drive folder for PDFs, extracts invoice data with an LLM, re-adds every line item in deterministic code, audits extracted values against the raw PDF text, writes results to two Sheets tabs, and alerts via Telegram only when there are incidents. | Google Drive, Google Sheets, OpenAI, Telegram | [Watch](https://www.youtube.com/@jmconsultingsai) |
| Deep dive | [Pseudonimización de PII](workflows/deepdive-pseudonimizacion/) | Hashes the structured contact field and scrubs emails, national IDs and phone numbers out of the free-text field before anything reaches an external LLM. The manual leads with the 5-step decision rule and states explicitly what the scrub does **not** cover — names and card last-4 still go through. | OpenAI | [Watch](https://www.youtube.com/@jmconsultingsai) |

## Repository structure

```
workflows/
└── ep{NN}-{workflow-name}/        # or deepdive-{topic}/
    ├── workflow.json    # Sanitized n8n export — import this
    ├── MANUAL.md        # Credentials & setup guide, step by step
    └── assets/          # Screenshots (optional)
```

Episode folders match the episode number on the channel (`ep01-...`, `ep02-...`).
Deep dives are not numbered episodes — they go under `deepdive-{topic}/`.

## Security

- All JSONs are exported from a working n8n instance and then **fully sanitized**: no credential values, no credential names or IDs, no account IDs, emails, or webhook URLs.
- You always create and own your credentials. **Never share your API keys** or commit them anywhere.
- The manuals prefer free tiers and open-source options; when a service is paid, the manual says so and names a free alternative when one exists.

## Language

Manuals are written in **Spanish**, matching the channel. The workflow JSONs are language-neutral.

## License

[MIT](LICENSE) — use them, modify them, build on them. A mention of the channel is appreciated but not required.
