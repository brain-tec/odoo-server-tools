# odoo-server-tools — gren 19.0

> **Denna gren är avsiktligt tom.** Modulerna är INTE portade till Odoo 19.
> Grenen finns så att dev-miljöer (`hansolo19`) kan klona den utan att falla,
> men den påstår ingenting om att koden är portad.

## Baseline

| | |
|---|---|
| Källa | `20.0` |
| Moduler | **4** |
| Grenar i repot | `12.0`, `12.0-af`, `13.0`, `14.0`, `16.0`, `17.0`, `18.0`, `20.0`, `Dev-12.0`, `Dev-12.0-Fenix-Sprint-02`, `master` |

## Moduler

- `database_backup_s3_endpoint`
- `letsencrypt`
- `letsencrypt_nginx`
- `letsencrypt_nginx_rules`

## Blockerare

**1 externa beroenden saknas** i Odoo 19-kärnan och OCA 19.0:

| Beroende | Behövs av |
|---|---|
| `auto_database_backup` | `database_backup_s3_endpoint` |

### Prioritering

Ett beroende som blockerar många moduler ger mest nytta att lösa först:

- `auto_database_backup` — frisläpper **1** modul(er)

## Nästa steg

Portering sker på `*-pfile`-maskin med versionsagnostisk kod
(`.p.py` / `.p.xml`). Se `/skill:odoo-pfiles`.
