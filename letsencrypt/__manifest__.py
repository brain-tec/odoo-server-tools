# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo SA, Open Source Management Solution, third party addon
#    Copyright (C) 2022- Vertel AB (<https://vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program. If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
# © 2016 Therp BV <http://therp.nl>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    'name': 'Server Tools: Let''s Encrypt',
    'version': '1.1',
    'summary': 'Request SSL certificates from letsencrypt.org',
    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/14.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Technical',
    'description': """
    Request SSL certificates from letsencrypt.org
    """,
    #'sequence': '1',
    'author': 'Therp BV, Tecnativa, Vertel AB, Odoo Community Association (OCA)',
    'website': 'https://therp.nl/',
    'images': ['static/description/banner.png'], # 560x280 px.
    'license': 'AGPL-3',
    'contributor': '',
    'maintainer': 'Vertel AB',
    'repository': 'https://github.com/vertelab/odoo-server-tools',
    # Any module necessary for this one to work correctly


    'depends': ['base',],
    "data": ["data/ir_config_parameter.xml", "data/ir_cron.xml", "demo/ir_cron.xml",],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "external_dependencies": {"bin": ["openssl",], "python": ["acme_tiny", "IPy",],},
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
