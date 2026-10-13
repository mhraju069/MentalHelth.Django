import os
from storages.backends.s3boto3 import S3Boto3Storage


class PublicMediaStorage(S3Boto3Storage):
    """
    Storage backend for Backblaze B2 / S3-compatible media uploads.
    Uploaded media files (e.g., profile pictures, cover images) are stored
    under the 'media/' folder prefix in the bucket and served publicly.
    """
    location = os.getenv('BACKBLAZE_MEDIA_LOCATION', 'media')
    default_acl = None  # Backblaze B2 does not support object-level ACLs
    file_overwrite = False
    querystring_auth = os.getenv('BACKBLAZE_QUERYSTRING_AUTH', 'True').lower() in ('true', '1', 't')


class PrivateMediaStorage(S3Boto3Storage):
    """
    Storage backend for private media uploads that require signed expiring URLs.
    """
    location = os.getenv('BACKBLAZE_PRIVATE_MEDIA_LOCATION', 'private')
    default_acl = None
    file_overwrite = False
    custom_domain = False
    querystring_auth = True
    querystring_expire = int(os.getenv('BACKBLAZE_EXPIRATION', '3600'))
