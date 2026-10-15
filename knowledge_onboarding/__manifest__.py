# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    'name': 'Knowledge: Onboarding (LMS)',
    'version': '18.0.2.0.0',
    'summary': 'Onboardingskurs: kunskapsbas, anteckningar och dokument-pages',
    'description': """
Kunskap & anteckningar i Vertel
===============================

Onboardingskurs som lär ut hur du bygger en kunskapsbas, skriver anteckningar
som går att återanvända och hittar bland allt ni vet.

4 sektioner, 11 slides (6 article, 1 infographic, 4 quiz):

- Sektion 1: Varför en kunskapsbas — kunskap som försvinner
- Sektion 2: Skriva och strukturera — för den som inte var där
- Sektion 3: Anteckningar i mobilen — skriv där du är
- Sektion 4: Hitta och återanvända — sökning, länkar och AI

Innehållet ligger i data/ (inte demo/) så att det laddas i alla databaser.
    """,
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se/apps/odoo-knowledge/knowledge_onboarding',
    'license': 'AGPL-3',
    'category': 'Website/eLearning',
    'depends': ['website_slides'],
    'data': [
        'data/slide_channel.xml',
        'data/slide_slides_s1.xml',
        'data/slide_slides_s2.xml',
        'data/slide_slides_s3.xml',
        'data/slide_slides_s4.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
