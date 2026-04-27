import boto3
import dropbox
import errno
import ftplib
import json
import logging
import nextcloud_client
import os
import paramiko
import requests
import tempfile
from nextcloud import NextCloud
from requests.auth import HTTPBasicAuth

from odoo import api, fields, models, _
from odoo.exceptions import UserError, AccessError, ValidationError

_logger = logging.getLogger(__name__)

class DbBackupConfigure(models.Model):
    _inherit = 'db.backup.configure'

    endpoint = fields.Char(help="The endpoint of your bucket. This field should be used if the bucket isn't stored on Amazon but with a different provider.")
    region = fields.Char(help="The region of the bucket.")

    def action_s3cloud(self):
        """If it has aws_secret_access_key, which will perform s3cloud
        operations for connection test"""
        if self.aws_access_key and self.aws_secret_access_key:
            try:
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=self.aws_access_key,
                    aws_secret_access_key=self.aws_secret_access_key,
                    endpoint_url=self.endpoint if self.endpoint else None,
                    region_name=self.region if self.region else None
                )
                response = s3_client.head_bucket(Bucket=self.bucket_file_name)
                if response['ResponseMetadata']['HTTPStatusCode'] == 200:
                    self.active = self.hide_active = True
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'type': 'success',
                            'title': _("Connection Test Succeeded!"),
                            'message': _(
                                "Everything seems properly set up!"),
                            'sticky': False,
                        }
                    }
                raise UserError(
                    _("Bucket not found. Please check the bucket name and"
                    " try again."))
            except Exception:
                self.active = self.hide_active = False
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'type': 'danger',
                        'title': _("Connection Test Failed!"),
                        'message': _("An error occurred while testing the "
                                    "connection."),
                        'sticky': False,
                    }
                }


    def _schedule_auto_backup(self, frequency):
        """Function for generating and storing backup.
           Database backup for all the active records in backup configuration
           model will be created."""
        records = self.search([('backup_frequency', '=', frequency)])
        mail_template_success = self.env.ref(
            'auto_database_backup.mail_template_data_db_backup_successful')
        mail_template_failed = self.env.ref(
            'auto_database_backup.mail_template_data_db_backup_failed')
        for rec in records:
            backup_time = fields.Datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_filename = f"{rec.db_name}_{backup_time}.{rec.backup_format}"
            rec.backup_filename = backup_filename
            # Local backup
            if rec.backup_destination == 'local':
                try:
                    if not os.path.isdir(rec.backup_path):
                        os.makedirs(rec.backup_path)
                    backup_file = os.path.join(rec.backup_path,
                                               backup_filename)
                    f = open(backup_file, "wb")
                    self.dump_data(rec.db_name, f, rec.backup_format, rec.backup_frequency)
                    f.close()
                    # Remove older backups
                    if rec.auto_remove:
                        for filename in os.listdir(rec.backup_path):
                            file = os.path.join(rec.backup_path, filename)
                            create_time = fields.datetime.fromtimestamp(
                                os.path.getctime(file))
                            backup_duration = fields.datetime.utcnow() - create_time
                            if backup_duration.days >= rec.days_to_remove:
                                os.remove(file)
                    if rec.notify_user:
                        mail_template_success.send_mail(rec.id, force_send=True)
                except Exception as e:
                    rec.generated_exception = e
                    _logger.info('FTP Exception: %s', e)
                    if rec.notify_user:
                        mail_template_failed.send_mail(rec.id, force_send=True)
            # FTP backup
            elif rec.backup_destination == 'ftp':
                try:
                    ftp_server = ftplib.FTP()
                    ftp_server.connect(rec.ftp_host, int(rec.ftp_port))
                    ftp_server.login(rec.ftp_user, rec.ftp_password)
                    ftp_server.encoding = "utf-8"
                    temp = tempfile.NamedTemporaryFile(
                        suffix='.%s' % rec.backup_format)
                    try:
                        ftp_server.cwd(rec.ftp_path)
                    except ftplib.error_perm:
                        ftp_server.mkd(rec.ftp_path)
                        ftp_server.cwd(rec.ftp_path)
                    with open(temp.name, "wb+") as tmp:
                        self.dump_data(rec.db_name, tmp,
                                                rec.backup_format, rec.backup_frequency)
                    ftp_server.storbinary('STOR %s' % backup_filename,
                                          open(temp.name, "rb"))
                    if rec.auto_remove:
                        files = ftp_server.nlst()
                        for file in files:
                            create_time = fields.datetime.strptime(
                                ftp_server.sendcmd('MDTM ' + file)[4:],
                                "%Y%m%d%H%M%S")
                            diff_days = (
                                    fields.datetime.now() - create_time).days
                            if diff_days >= rec.days_to_remove:
                                ftp_server.delete(file)
                    ftp_server.quit()
                    if rec.notify_user:
                        mail_template_success.send_mail(rec.id,
                                                        force_send=True)
                except Exception as e:
                    rec.generated_exception = e
                    _logger.info('FTP Exception: %s', e)
                    if rec.notify_user:
                        mail_template_failed.send_mail(rec.id, force_send=True)
            # SFTP backup
            elif rec.backup_destination == 'sftp':
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                try:
                    client.connect(hostname=rec.sftp_host,
                                   username=rec.sftp_user,
                                   password=rec.sftp_password,
                                   port=rec.sftp_port)
                    sftp = client.open_sftp()
                    temp = tempfile.NamedTemporaryFile(
                        suffix='.%s' % rec.backup_format)
                    with open(temp.name, "wb+") as tmp:
                        self.dump_data(rec.db_name, tmp, rec.backup_format, rec.backup_frequency)
                    try:
                        sftp.chdir(rec.sftp_path)
                    except IOError as e:
                        if e.errno == errno.ENOENT:
                            sftp.mkdir(rec.sftp_path)
                            sftp.chdir(rec.sftp_path)
                    sftp.put(temp.name, backup_filename)
                    if rec.auto_remove:
                        files = sftp.listdir()
                        expired = list(filter(
                            lambda fl: (fields.datetime.now()
                                        - fields.datetime.fromtimestamp(
                                        sftp.stat(fl).st_mtime)).days >=
                                       rec.days_to_remove, files))
                        for file in expired:
                            sftp.unlink(file)
                    sftp.close()
                    if rec.notify_user:
                        mail_template_success.send_mail(rec.id,
                                                        force_send=True)
                except Exception as e:
                    rec.generated_exception = e
                    _logger.info('SFTP Exception: %s', e)
                    if rec.notify_user:
                        mail_template_failed.send_mail(rec.id, force_send=True)
                finally:
                    client.close()
            # Google Drive backup
            elif rec.backup_destination == 'google_drive':
                try:
                    if rec.gdrive_token_validity <= fields.Datetime.now():
                        rec.generate_gdrive_refresh_token()
                    temp = tempfile.NamedTemporaryFile(
                        suffix='.%s' % rec.backup_format)
                    with open(temp.name, "wb+") as tmp:
                        self.dump_data(rec.db_name, tmp,
                                                rec.backup_format, rec.backup_frequency)
                    try:
                        headers = {
                            "Authorization": "Bearer %s" % rec.gdrive_access_token}
                        para = {
                            "name": backup_filename,
                            "parents": [rec.google_drive_folder_key],
                        }
                        files = {
                            'data': ('metadata', json.dumps(para),
                                     'application/json; charset=UTF-8'),
                            'file': open(temp.name, "rb")
                        }
                        requests.post(
                            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                            headers=headers,
                            files=files
                        )
                        if rec.auto_remove:
                            query = "parents = '%s'" % rec.google_drive_folder_key
                            files_req = requests.get(
                                "https://www.googleapis.com/drive/v3/files?q=%s" % query,
                                headers=headers)
                            for file in files_req.json()['files']:
                                file_date_req = requests.get(
                                    "https://www.googleapis.com/drive/v3/files/%s?fields=createdTime" %
                                    file['id'], headers=headers)
                                create_time = file_date_req.json()[
                                                  'createdTime'][
                                              :19].replace('T', ' ')
                                diff_days = (
                                        fields.datetime.now() - fields.datetime.strptime(
                                    create_time, '%Y-%m-%d %H:%M:%S')).days
                                if diff_days >= rec.days_to_remove:
                                    requests.delete(
                                        "https://www.googleapis.com/drive/v3/files/%s" %
                                        file['id'], headers=headers)
                        if rec.notify_user:
                            mail_template_success.send_mail(rec.id,
                                                            force_send=True)
                    except Exception as e:

                        rec.generated_exception = e
                        _logger.info('Google Drive Exception: %s', e)
                        if rec.notify_user:
                            mail_template_failed.send_mail(rec.id,
                                                           force_send=True)
                except Exception:
                    if rec.notify_user:
                        mail_template_failed.send_mail(rec.id, force_send=True)
                        raise ValidationError(
                            'Please check the credentials before activation')
                    else:
                        raise ValidationError('Please check connection')
            # Dropbox backup
            elif rec.backup_destination == 'dropbox':
                temp = tempfile.NamedTemporaryFile(
                    suffix='.%s' % rec.backup_format)
                with open(temp.name, "wb+") as tmp:
                    self.dump_data(rec.db_name, tmp,
                                            rec.backup_format, rec.backup_frequency)
                try:
                    dbx = dropbox.Dropbox(
                        app_key=rec.dropbox_client_key,
                        app_secret=rec.dropbox_client_secret,
                        oauth2_refresh_token=rec.dropbox_refresh_token)
                    dropbox_destination = (rec.dropbox_folder + '/' +
                                           backup_filename)
                    dbx.files_upload(temp.read(), dropbox_destination)
                    if rec.auto_remove:
                        files = dbx.files_list_folder(rec.dropbox_folder)
                        file_entries = files.entries
                        expired_files = list(filter(
                            lambda fl: (fields.datetime.now() -
                                        fl.client_modified).days >=
                                       rec.days_to_remove,
                            file_entries))
                        for file in expired_files:
                            dbx.files_delete_v2(file.path_display)
                    if rec.notify_user:
                        mail_template_success.send_mail(rec.id,
                                                        force_send=True)
                except Exception as error:
                    rec.generated_exception = error
                    _logger.info('Dropbox Exception: %s', error)
                    if rec.notify_user:
                        mail_template_failed.send_mail(rec.id, force_send=True)
            # Onedrive Backup
            elif rec.backup_destination == 'onedrive':
                try:
                    if rec.onedrive_token_validity <= fields.Datetime.now():
                        rec.generate_onedrive_refresh_token()

                    with tempfile.NamedTemporaryFile(suffix=f'.{rec.backup_format}') as temp:
                        with open(temp.name, "wb+") as tmp:
                            self.dump_data(rec.db_name, tmp, rec.backup_format, rec.backup_frequency)

                        headers = {
                            'Authorization': f'Bearer {rec.onedrive_access_token}',
                            'Content-Type': 'application/json'
                        }

                        upload_session_url = (
                            f"{MICROSOFT_GRAPH_END_POINT}/v1.0/me/drive/items/"
                            f"{rec.onedrive_folder_key}:/{backup_filename}:/createUploadSession"
                        )

                        upload_session = requests.post(upload_session_url, headers=headers)
                        upload_session.raise_for_status()

                        upload_url = upload_session.json().get('uploadUrl')
                        if not upload_url:
                            raise ValueError("Failed to get upload URL from OneDrive")

                        file_size = os.path.getsize(temp.name)
                        with open(temp.name, 'rb') as f:
                            headers_upload = {
                                'Content-Length': str(file_size),
                                'Content-Range': f'bytes 0-{file_size - 1}/{file_size}'
                            }
                            upload_response = requests.put(upload_url, headers=headers_upload, data=f)
                            upload_response.raise_for_status()


                        if rec.auto_remove:
                            verify_url = (
                                f"{MICROSOFT_GRAPH_END_POINT}/v1.0/me/drive/items/"
                                f"{rec.onedrive_folder_key}:/{backup_filename}"
                            )
                            verify_response = requests.get(verify_url, headers=headers)

                            if verify_response.status_code == 200:
                                list_url = (
                                    f"{MICROSOFT_GRAPH_END_POINT}/v1.0/me/drive/items/"
                                    f"{rec.onedrive_folder_key}/children"
                                )
                                response = requests.get(list_url, headers=headers)
                                response.raise_for_status()

                                files = response.json().get('value', [])
                                current_time = fields.datetime.now()

                                for file in files:
                                    if file['name'] == backup_filename:
                                        continue

                                    create_time_str = file['createdDateTime'][:19].replace('T', ' ')
                                    create_time = fields.datetime.strptime(create_time_str, '%Y-%m-%d %H:%M:%S')
                                    diff_days = (current_time - create_time).days

                                    if diff_days >= rec.days_to_remove:
                                        delete_url = f"{MICROSOFT_GRAPH_END_POINT}/v1.0/me/drive/items/{file['id']}"
                                        requests.delete(delete_url, headers=headers).raise_for_status()

                        # Notify user on success
                        if rec.notify_user:
                            mail_template_success.send_mail(rec.id, force_send=True)

                except requests.exceptions.RequestException as req_error:
                    rec.generated_exception = str(req_error)
                    _logger.error('OneDrive API Error: %s', req_error, exc_info=True)
                    if rec.notify_user:
                        mail_template_failed.send_mail(rec.id, force_send=True)

                except Exception as error:
                    rec.generated_exception = str(error)
                    _logger.error('OneDrive Backup Error: %s', error, exc_info=True)
                    if rec.notify_user:
                        mail_template_failed.send_mail(rec.id, force_send=True)
            elif rec.backup_destination == 'next_cloud':
                try:
                    if rec.domain and rec.next_cloud_password and \
                            rec.next_cloud_user_name:
                        try:
                            # Connect to NextCloud using the provided username
                            # and password
                            ncx = NextCloud(rec.domain,
                                            auth=HTTPBasicAuth(
                                                rec.next_cloud_user_name,
                                                rec.next_cloud_password))
                            # Connect to NextCloud again to perform additional
                            # operations
                            nc = nextcloud_client.Client(rec.domain)
                            nc.login(rec.next_cloud_user_name,
                                     rec.next_cloud_password)
                            # Get the folder name from the NextCloud folder ID
                            folder_name = rec.nextcloud_folder_key
                            # If auto_remove is enabled, remove backup files
                            # older than specified days
                            if rec.auto_remove:
                                folder_path = "/" + folder_name
                                for item in nc.list(folder_path):
                                    backup_file_name = item.path.split("/")[-1]
                                    backup_date_str = \
                                        backup_file_name.split("_")[1]
                                    backup_date = fields.datetime.strptime(
                                        backup_date_str, '%Y-%m-%d').date()
                                    if (fields.date.today() - backup_date).days \
                                            >= rec.days_to_remove:
                                        nc.delete(item.path)
                            # If notify_user is enabled, send a success email
                            # notification
                            if rec.notify_user:
                                mail_template_success.send_mail(rec.id,
                                                                force_send=True)
                        except Exception as error:
                            rec.generated_exception = error
                            _logger.info('NextCloud Exception: %s', error)
                            if rec.notify_user:
                                # If an exception occurs, send a failed email
                                # notification
                                mail_template_failed.send_mail(rec.id,
                                                               force_send=True)
                        # Get the list of folders in the root directory of NextCloud
                        data = ncx.list_folders('/').__dict__
                        folders = [
                            [file_name['href'].split('/')[-2],
                             file_name['file_id']]
                            for file_name in data['data'] if
                            file_name['href'].endswith('/')]
                        # If the folder name is not found in the list of folders,
                        # create the folder
                        if folder_name not in [file[0] for file in folders]:
                            nc.mkdir(folder_name)
                            # Dump the database to a temporary file
                            temp = tempfile.NamedTemporaryFile(
                                suffix='.%s' % rec.backup_format)
                            with open(temp.name, "wb+") as tmp:
                                self.dump_data(rec.db_name, tmp,
                                                        rec.backup_format, rec.backup_frequency)
                            backup_file_name = temp.name
                            remote_file_path = f"/{folder_name}/{rec.db_name}_" \
                                               f"{backup_time}.{rec.backup_format}"
                            nc.put_file(remote_file_path, backup_file_name)
                        else:
                            # Dump the database to a temporary file
                            temp = tempfile.NamedTemporaryFile(
                                suffix='.%s' % rec.backup_format)
                            with open(temp.name, "wb+") as tmp:
                                self.dump_data(rec.db_name, tmp,
                                                        rec.backup_format, rec.backup_frequency)
                            backup_file_name = temp.name
                            remote_file_path = f"/{folder_name}/{rec.db_name}_" \
                                               f"{backup_time}.{rec.backup_format}"
                            nc.put_file(remote_file_path, backup_file_name)
                except Exception:
                    raise ValidationError('Please check connection')
            # Amazon S3 Backup
            elif rec.backup_destination == 'amazon_s3':
                if rec.aws_access_key and rec.aws_secret_access_key:
                    try:
                        # Create a boto3 client for Amazon S3 with provided
                        # access key id and secret access key
                        bo3 = boto3.client(
                            's3',
                            aws_access_key_id=rec.aws_access_key,
                            aws_secret_access_key=rec.aws_secret_access_key,
                            endpoint_url=rec.endpoint if rec.endpoint else None,
                            region_name=rec.region if rec.region else None)

                        # If auto_remove is enabled, remove the backups that
                        # are older than specified days from the S3 bucket
                        if rec.auto_remove:
                            folder_path = rec.aws_folder_name
                            response = bo3.list_objects(
                                Bucket=rec.bucket_file_name,
                                Prefix=folder_path)
                            today = fields.date.today()
                            for file in response['Contents']:
                                file_path = file['Key']
                                last_modified = file['LastModified']
                                date = last_modified.date()
                                age_in_days = (today - date).days
                                if age_in_days >= rec.days_to_remove:
                                    bo3.delete_object(
                                        Bucket=rec.bucket_file_name,
                                        Key=file_path)
                        # Create a boto3 resource for Amazon S3 with provided
                        # access key id and secret access key
                        s3 = boto3.resource(
                            's3',
                            aws_access_key_id=rec.aws_access_key,
                            aws_secret_access_key=rec.aws_secret_access_key,
                            endpoint_url=rec.endpoint if rec.endpoint else None,
                            region_name=rec.region if rec.region else None)
                        # Create a folder in the specified bucket, if it
                        # doesn't already exist
                        s3.Object(rec.bucket_file_name,
                                  rec.aws_folder_name + '/').put()
                        bucket = s3.Bucket(rec.bucket_file_name)
                        # Get all the prefixes in the bucket
                        prefixes = set()
                        for obj in bucket.objects.all():
                            key = obj.key
                            if key.endswith('/'):
                                prefix = key[:-1]  # Remove the trailing slash
                                prefixes.add(prefix)
                        # If the specified folder is present in the bucket,
                        # take a backup of the database and upload it to the
                        # S3 bucket
                        if rec.aws_folder_name in prefixes:
                            temp = tempfile.NamedTemporaryFile(
                                suffix='.%s' % rec.backup_format)
                            with open(temp.name, "wb+") as tmp:
                                self.dump_data(rec.db_name, tmp,
                                                        rec.backup_format, rec.backup_frequency)
                            backup_file_name = temp.name
                            remote_file_path = f"{rec.aws_folder_name}/{rec.db_name}_" \
                                               f"{backup_time}.{rec.backup_format}"
                            s3.Object(rec.bucket_file_name,
                                      remote_file_path).upload_file(
                                backup_file_name)
                            # If notify_user is enabled, send an email to the
                            # user notifying them about the successful backup
                            if rec.notify_user:
                                mail_template_success.send_mail(rec.id,
                                                                force_send=True)
                    except Exception as error:
                        # If any error occurs, set the 'generated_exception'
                        # field to the error message and log the error
                        rec.generated_exception = error
                        _logger.info('Amazon S3 Exception: %s', error)
                        # If notify_user is enabled, email the user
                        # notifying them about the failed backup
                        if rec.notify_user:
                            mail_template_failed.send_mail(rec.id, force_send=True)
