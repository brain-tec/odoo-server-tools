{
    'name': "Server Tools: Let's Encrypt Nginx Rules",
    'version': '1.1',
    'summary': 'Create nginx configs for SSL.',
    'category': 'Technical',
    'description': """
    Create Nginx configs for SSL.
    """,
    'author': 'Vertel AB',
    'website': 'https://vertel.se/apps/odoo-server-tools/letsencrypt_nginx',
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