# odoo-knowledge

## Porteringsstatus

18.0 är baseline. 19.0/20.0 visar om p-filen har ett villkor för utgåvan
— inte om grenen finns. Blockerare är `depends` som saknas i 20.0
(kärna + alla 20.0-grenar).

| Modul | Beskrivning | Manifest | p-fil | 19.0 | 20.0 | Blockerare |
|---|---|---|---|---|---|---|
| document_law | Short (1 phrase/line) summary of the module's purpose, us... | 1.0 | 9 | — | — | — |
| document_publish | Publishes document pages to the website. | 1.0.0 | 0 | — | — | — |
| intelligence_studies | Adds templates and articles for intelligence studies. | 1.0.0 | 0 | — | — | — |
| knowledge_ai | OKF-indexering av joplin.note | 1.0.0 | 1 | — | — | — |
| knowledge_category_access | Adds access group capability to document category via doc... | 1.0.0 | 1 | — | — | `document_page_access_group` |
| knowledge_forum_website | Knowledge Forum Website | 1.0 | 7 | — | — | — |
| knowledge_graphdb | Publish Odoo model changes to RabbitMQ for graph database... | 1.0.4 | 1 | ✓ | — | — |
| knowledge_joplin | Joplin-compatible note-taking backend with REST API and s... | 1.0.0 | 2 | ✓ | — | — |
| knowledge_onboarding | Onboardingskurs: kunskapsbas, anteckningar och dokument-p... | 1.0.0 | 0 | — | — | — |
