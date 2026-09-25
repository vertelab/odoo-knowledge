# -*- coding: utf-8 -*-
{
    'name': 'Kunskap & anteckningar i Vertel',
    'version': '18.0.1.0.0',
    'summary': 'Onboardingskurs: kunskapsbas, anteckningar och dokument-pages',
    'description': """
Lär dig bygga en kunskapsbas, skriva anteckningar och hitta bland allt ni vet.
""",
    'author': 'Vertel AB',
    'website': 'https://vertel.se',
    'license': 'LGPL-3',
    'category': 'Website/eLearning',
    'depends': ['website_slides'],
    'data': [
        'views/slide_channel_data.xml',
    ],
    'demo': [
        'demo/slide_slide_demo.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
