# odoo-knowledge — gren 19.0

> **Denna gren är avsiktligt tom.** Modulerna är INTE portade till Odoo 19.
> Grenen finns så att dev-miljöer (`hansolo19`) kan klona den utan att falla,
> men den påstår ingenting om att koden är portad.

## Baseline

| | |
|---|---|
| Källa | `20.0` |
| Moduler | **9** |
| Grenar i repot | `16.0`, `17.0`, `18.0`, `20.0`, `master` |

## Moduler

- `document_law`
- `document_publish`
- `intelligence_studies`
- `knowledge_ai`
- `knowledge_category_access`
- `knowledge_forum_website`
- `knowledge_graphdb`
- `knowledge_joplin`
- `knowledge_onboarding`

## Blockerare

✅ Inga externa beroenden saknas i Odoo 19-kärnan eller OCA 19.0.

Modulerna kan troligen portas utan att vänta på externa bidrag.

## Nästa steg

Portering sker på `*-pfile`-maskin med versionsagnostisk kod
(`.p.py` / `.p.xml`). Se `/skill:odoo-pfiles`.
