import logging
import os
from odoo import models, fields, api
from odoo.tools import config

_logger = logging.getLogger(__name__)


class Website(models.Model):
    _inherit = "website"

    nginx_config = fields.Text(string="Nginx Config")
    nginx_db_filter = fields.Boolean(string="DB Filter")
    nginx_rules = fields.One2many('website.nginx.rules', 'website_id', string="Nginx Rules")

    def _get_domain_host(self, domain_str):
        if not domain_str:
            return ""
        host = domain_str
        if "://" in host:
            host = host.split("://")[1]
        if "/" in host:
            host = host.split("/")[0]
        return host

    def _get_domain_apex(self, host):
        if host.startswith("www."):
            return host.replace("www.", "", 1)
        return host

    def _get_proxy_headers(self, db_filter=False):
        headers = [
            "proxy_set_header X-Forwarded-Host $host;",
            "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
            "proxy_set_header X-Forwarded-Proto $scheme;",
            "proxy_set_header X-Real-IP $remote_addr;"
        ]
        if db_filter:
            db_name = self.env.cr.dbname
            # Using $dollar trick as requested by user
            headers.append(f'proxy_set_header X-Odoo-dbfilter "^{db_name}$dollar";')
        return "\n    ".join(headers)

    def generate_new_config(self):
        for website in self:
            if not website.domain:
                continue
            
            dest_domain = self._get_domain_host(website.domain)
            main_apex = self._get_domain_apex(dest_domain)
            
            data_dir = config.options.get("data_dir") or "/var/lib/odoo/.local/share/Odoo"
            letsencrypt_crt_dir = os.path.join(data_dir, "letsencrypt")
            
            main_crt_path = os.path.join(letsencrypt_crt_dir, f"{main_apex}.crt")
            main_key_path = os.path.join(letsencrypt_crt_dir, f"{main_apex}.key")

            config_blocks = []

            # 1. Determine redirect domains
            redirect_domains = set()
            for rule in website.nginx_rules:
                if rule.domain:
                    dom = rule.domain.strip()
                    if dom != dest_domain:
                        redirect_domains.add(dom)

            # 2. Redirect blocks - Port 80 first
            for dom in sorted(redirect_domains):
                config_blocks.append(self._block_redirect_80(dom, dest_domain))

            # 3. Redirect blocks - Port 443 next
            for dom in sorted(redirect_domains):
                config_blocks.append(self._block_redirect_443(dom, dest_domain, main_crt_path, main_key_path))

            # 4. Main site Port 80
            config_blocks.append(self._block_main_80(dest_domain, website.nginx_db_filter))

            # 5. Main site Port 443 (Proxy)
            config_blocks.append(self._block_main_443(dest_domain, main_crt_path, main_key_path, website.nginx_db_filter))

            full_config = "\n".join(config_blocks)
            website.nginx_config = full_config
            self._write_nginx_config_file(main_apex, full_config)

    def _block_redirect_80(self, domain, destination):
        return f"""server {{
    listen 80;
    server_name {domain};
    return 302 https://{destination}$request_uri;
}}
"""

    def _block_redirect_443(self, domain, destination, crt, key):
        return f"""server {{
    listen 443 ssl;
    server_name {domain};
    ssl_certificate {crt};
    ssl_certificate_key {key};
    return 302 https://{destination}$request_uri;
}}
"""

    def _block_main_80(self, domain, db_filter=False):
        return f"""server {{
    listen 80;
    server_name {domain};
    proxy_read_timeout 720s;
    proxy_connect_timeout 720s;
    proxy_send_timeout 720s;

    # Add Headers for odoo proxy mode
    {self._get_proxy_headers(db_filter)}

    location /.well-known/acme-challenge/ {{
        proxy_pass http://odoo;
        proxy_redirect off;
    }}
    location / {{
        rewrite ^(.*) https://$host$1 permanent;
    }}
}}
"""

    def _block_main_443(self, domain, crt, key, db_filter=False):
        return f"""server {{
    listen 443 ssl;
    server_name {domain};
    proxy_read_timeout 720s;
    proxy_connect_timeout 720s;
    proxy_send_timeout 720s;

    # Add Headers for odoo proxy mode
    {self._get_proxy_headers(db_filter)}

    # SSL parameters
    ssl_certificate {crt};
    ssl_certificate_key {key};
    ssl_session_timeout 30m;
    ssl_protocols TLSv1 TLSv1.1 TLSv1.2;
    ssl_ciphers 'ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-DSS-AES128-GCM-SHA256:kEDH+AESGCM:ECDHE-RSA-AES128-SHA256:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA:ECDHE-ECDSA-AES128-SHA:ECDHE-RSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA384:ECDHE-RSA-AES256-SHA:ECDHE-ECDSA-AES256-SHA:DHE-RSA-AES128-SHA256:DHE-RSA-AES128-SHA:DHE-DSS-AES128-SHA256:DHE-RSA-AES256-SHA256:DHE-DSS-AES256-SHA:DHE-RSA-AES256-SHA:AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA256:AES256-SHA256:AES128-SHA:AES256-SHA:AES:CAMELLIA:DES-CBC3-SHA:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!MD5:!PSK:!aECDH:!EDH-DSS-DES-CBC3-SHA:!EDH-RSA-DES-CBC3-SHA:!KRB5-DES-CBC3-SHA';
    ssl_prefer_server_ciphers on;

    # log
    access_log /var/log/nginx/{domain}.access.log;
    error_log /var/log/nginx/{domain}.error.log;

    # Redirect websocket requests to odoo longpolling port
    location /websocket {{
        proxy_pass http://odoochat;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
    }}

    # Redirect requests to odoo backend server
    location / {{
        proxy_redirect off;
        proxy_pass http://odoo;
    }}

    # common gzip
    gzip_types text/css text/scss text/plain text/xml application/xml application/json application/javascript;
    gzip on;
}}
"""

    def _write_nginx_config_file(self, domain, content):
        data_dir = config.options.get("data_dir")
        if not data_dir:
            _logger.warning("No data_dir configured, cannot save nginx config.")
            return

        letsencrypt_dir = os.path.join(data_dir, "letsencrypt_nginx")
        os.makedirs(letsencrypt_dir, exist_ok=True)

        safe_domain = "".join([c for c in domain if c.isalnum() or c in ".-_"])
        file_path = os.path.join(letsencrypt_dir, f"{safe_domain}.conf")

        try:
            with open(file_path, 'w') as f:
                f.write(content)
            _logger.info(f"Saved nginx config for {domain} to {file_path}")
        except IOError as e:
            _logger.error(f"Failed to write nginx config to {file_path}: {e}")

    def cron(self):
        for website in self.search([]):
            if website.domain:
                website.generate_new_config()


class WebsiteNginxRules(models.Model):
    _name = "website.nginx.rules"
    _description = "Nginx Rules"

    website_id = fields.Many2one('website', string="Website")
    domain = fields.Char(string="Redirect Domain")
