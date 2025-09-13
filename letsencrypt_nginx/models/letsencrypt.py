##############################################################################
#
#    Copyright (C) 2019 Vertel (<http://www.vertel.se>).
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
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import logging
import os
import shutil
from urllib.parse import urlparse

from odoo import _, api, exceptions, models
from odoo.tools import config

from odoo.addons.letsencrypt.models.letsencrypt import (
    get_data_dir as get_letsencrypt_data_dir,
)

_logger = logging.getLogger(__name__)


def get_data_dir():
    data_dir = os.path.join(config.options.get("data_dir"), "letsencrypt_nginx")
    if not os.path.isdir(data_dir):
        os.makedirs(data_dir)
    return data_dir


# TODO: Make this configurable somehow.
# TODO: Make this use the alternative server domains and hook them to
# the correct letsencrypt files.
# Example: vertel.se should be configured with the alternative domain
# vertel.azzar.se. Each domain will have a separate certificate and this
# nginx conf should reflect that.
CONF = """# http -> https
server {
\tlisten 80;
\tserver_name %HOSTNAMES%;
\tproxy_read_timeout 720s;
\tproxy_connect_timeout 720s;
\tproxy_send_timeout 720s;

\t# Add Headers for odoo proxy mode
\tproxy_set_header X-Forwarded-Host $host;
\tproxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
\tproxy_set_header X-Forwarded-Proto $scheme;
\tproxy_set_header X-Real-IP $remote_addr;
\tlocation /.well-known/acme-challenge/ {
\t\tproxy_redirect off;
\t\tproxy_pass http://odoo;
\t}
\tlocation / {
\t\trewrite ^(.*) https://$host$1 permanent;
\t}
}

server {
\tlisten 443;
\tserver_name %HOSTNAMES%;
\tproxy_read_timeout 720s;
\tproxy_connect_timeout 720s;
\tproxy_send_timeout 720s;
\t
\t# Add Headers for odoo proxy mode
\tproxy_set_header X-Forwarded-Host $host;
\tproxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
\tproxy_set_header X-Forwarded-Proto $scheme;
\tproxy_set_header X-Real-IP $remote_addr;
\t
\t# SSL parameters
\tssl on;
\tssl_certificate %CRT_PATH%;
\tssl_certificate_key %KEY_PATH%;
\tssl_session_timeout 30m;
\tssl_protocols TLSv1 TLSv1.1 TLSv1.2;
\tssl_ciphers 'ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-DSS-AES128-GCM-SHA256:kEDH+AESGCM:ECDHE-RSA-AES128-SHA256:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA:ECDHE-ECDSA-AES128-SHA:ECDHE-RSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA384:ECDHE-RSA-AES256-SHA:ECDHE-ECDSA-AES256-SHA:DHE-RSA-AES128-SHA256:DHE-RSA-AES128-SHA:DHE-DSS-AES128-SHA256:DHE-RSA-AES256-SHA256:DHE-DSS-AES256-SHA:DHE-RSA-AES256-SHA:AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA256:AES256-SHA256:AES128-SHA:AES256-SHA:AES:CAMELLIA:DES-CBC3-SHA:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!MD5:!PSK:!aECDH:!EDH-DSS-DES-CBC3-SHA:!EDH-RSA-DES-CBC3-SHA:!KRB5-DES-CBC3-SHA';
\tssl_prefer_server_ciphers on;
\t
\t# log
\taccess_log /var/log/nginx/odoo.access.log;
\terror_log /var/log/nginx/odoo.error.log;
\t
\t# Redirect longpoll requests to odoo longpolling port
\tlocation /longpolling {
\t\tproxy_pass http://longpolling;
\t}
\t
\t# Redirect requests to odoo backend server
\tlocation / {
\t\tproxy_redirect off;
\t\tproxy_pass http://odoo;
\t}
\t
\t# common gzip
\tgzip_types text/css text/scss text/plain text/xml application/xml application/json application/javascript;
\tgzip on;
}
"""


class Letsencrypt(models.AbstractModel):
    _inherit = "letsencrypt"

    @api.model
    def generate_nginx_conf(self):
        parameter_obj = self.env["ir.config_parameter"]
        domain = urlparse(parameter_obj.get_param("web.base.url", "localhost")).netloc
        domains = [domain]
        altnames = parameter_obj.search(
            [("key", "like", "letsencrypt.altname.")], order="key"
        )
        for altname in altnames:
            domains.append(altname.value)
        hostname = " ".join(domains)
        data_dir = get_letsencrypt_data_dir()

        crt = os.path.join(data_dir, "%s.crt" % domain)
        key = os.path.join(data_dir, "%s.key" % domain)

        conf_template = CONF
        conf_template_name = parameter_obj.get_param(
            "letsencrypt_nginx.template_conf", "nginx_template.conf")
        conf_template_path = os.path.join(config.options.get("data_dir"),
                                          conf_template_name)
        if (os.path.exists(conf_template_path) and
                os.path.isfile(conf_template_path)):
            with open(conf_template_path) as mfile:
                conf_template = mfile.read()
        else:
            _logger.warn("Nginx template file not found. Using fallback.")

        conf_text = (
            conf_template.replace("%HOSTNAMES%", hostname)
            .replace("%CRT_PATH%", crt)
            .replace("%KEY_PATH%", key)
        )
        conf_path = os.path.join(get_data_dir(), "%s.conf" % domain)
        if not os.path.exists(conf_path):
            with open(conf_path, "w") as conf:
                conf.write(conf_text)
        #with open(conf_path, "w") as conf:
        #    conf.write(conf_text)
        reload_cmd = parameter_obj.get_param("letsencrypt.reload_command", False)
        if reload_cmd:
            _logger.info("reloading webserver...")
            try:
                self.call_cmdline(["sh", "-c", reload_cmd])
            except:
                _logger.warn(
                    "Failed to reload webserver. Removing config for %s and restarting!\n\nFailed config saved as %s."
                    % (domain, conf_path + "_failed")
                )
                self.shutil(conf_path, conf_path + "_failed")
                self.call_cmdline(["sh", "-c", reload_cmd])

    @api.model
    def cron(self):
        super(Letsencrypt, self).cron()
        self.generate_nginx_conf()

    @api.model
    def _set_domain(self):
        domain = os.getenv("DOMAIN")
        cron_job = self.env.ref('letsencrypt.cronjob')
        if domain and cron_job:

            self.env['ir.config_parameter'].sudo().set_param('web.base.url', f'https://{domain}')
            self.env['ir.config_parameter'].sudo().set_param('letsencrypt.altname.1', f'www.{domain}')

            cron_job.active = True
            cron_job.method_direct_trigger()
