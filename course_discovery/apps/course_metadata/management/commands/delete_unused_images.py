import logging
import sys

import boto

from boto.exception import AWSConnectionError, BotoClientError, S3PermissionsError
from django.core.management import BaseCommand
from django.conf import settings

from course_discovery.apps.course_metadata.models import Course


IMAGES_POSTFIXES = [
    'small',
    'original'
]

S3_MEDIA_STORAGE_NAME = 'storages.backends.s3boto.S3BotoStorage'
S3_REGION = settings.AWS_SES_REGION_NAME
BUCKET_NAME = settings.MEDIA_STORAGE_BACKEND.get('AWS_STORAGE_BUCKET_NAME')

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete unused images from AWS S3 bucket"

    def handle(self, *args, **kwargs):
        current_media_storage = settings.MEDIA_STORAGE_BACKEND['DEFAULT_FILE_STORAGE']
        if current_media_storage != S3_MEDIA_STORAGE_NAME:
            logger.error(
                ('This command can only be used for S3 storage\n'
                 'Current media storage: {}\n'
                 'Required media storage: {}').format(current_media_storage, S3_MEDIA_STORAGE_NAME)
            )
            sys.exit(1)

        try:
            bucket = self._get_bucket()
            logger.info('Successfully made connection to s3 bucket')
        except AWSConnectionError, BotoClientError:
            logger.error('AWS connection error occurred while trying to connect to AWS service')
            sys.exit(1)
        except Exception as ex:
            logger.error('An error occurred while trying to connect to AWS service: %s', str(ex))
            sys.exit(1)

        try:
            uploaded_images_keys = bucket.get_all_keys(prefix='media/course/image')
        except S3PermissionsError:
            logger.error('Permission denied while trying to get S3 bucket keys')

        all_uploaded_images_names = self._get_all_uploaded_image_set(uploaded_images_keys)
        logger.info('Number of images uploaded on s3 bucket: {}'.format(
            len(all_uploaded_images_names))
        )

        all_courses_images = self._get_all_courses_image_set()
        logger.info('Number of images being used in courses: {}'.format(
            len(all_courses_images))
        )

        obsolete_images = all_uploaded_images_names - all_courses_images
        logger.info('Number of obsolete images: {}'.format(
            len(obsolete_images))
        )

        if len(len(obsolete_images)):
            obsolete_images_keys = [key for key in uploaded_images_keys if key.key in obsolete_images]
            try:
                bucket.delete_keys(obsolete_images_keys)
            except S3PermissionsError:
                logger.error('Permission denied while trying to get S3 bucket keys')
                sys.exit(1)

            logger.info('Successfully deleted {} images: {}'.format(
                len(obsolete_images), obsolete_images
            ))
        else:
            logger.info('There are no obsolete images to be deleted')

    def _get_bucket(self):
        s3 = boto.connect_s3(S3_REGION)
        bucket = s3.get_bucket(BUCKET_NAME)
        return bucket

    def _get_all_courses_image_set(self):
        return {
            image for course in Course.objects.all() if course.image.name
            for image in self._make_thumbnail_names(course.image.name)
        }

    def _make_thumbnail_names(self, image_name):
        last_dot_index = image_name.rindex('.')
        images = []
        images.append(image_name)
        for postfix in IMAGES_POSTFIXES:
            images.append(
                image_name[:last_dot_index] + '.{}'.format(postfix) + image_name[last_dot_index:]
            )
        return images

    def _get_all_uploaded_image_set(self, bucket_keys):
        return {key.key for key in bucket_keys}
