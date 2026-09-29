{
    'name': "Server Tools: Let's Encrypt Nginx Rules",
    'version': '18.0.1.1.0',
    'summary': 'Create nginx configs for SSL.',
    'category': 'Technical',
    'description': '''
Let's Encrypt Nginx Rules
=========================

    Create nginx configs for SSL.

    Features:

        - UI Integration: Extends 1 view(s) in the Odoo interface.
        - Extends Odoo: Builds on website, website.nginx.rules.
    ''',
    'author': 'Vertel AB',
    'website': 'https://vertel.se/apps/odoo-server-tools/letsencrypt_nginx_rules',
    'images': ['static/description/banner.png'], # 560x280 px.
    'license': 'AGPL-3',
    'contributor': '',
    'maintainer': 'Vertel AB',
    'repository': 'https://github.com/vertelab/odoo-server-tools',
    'depends': ['letsencrypt_nginx', 'website'],
    "data": [
        'security/ir.model.access.csv',
        'views/website_views.xml'
    ],
    "installable": True,
}