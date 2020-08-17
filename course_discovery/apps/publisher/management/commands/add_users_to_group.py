"""
Add users to the specified groups
"""
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import BaseCommand, CommandError
from django.db.models import Q

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    """
    Add users to the specified groups

    Example usage:
        ```
        python manage.py add_users_to_group -g "Publisher Admins" "Internal Users"\
            "ucsd-admins" "edx-admins"\
            -u edx staff -s -f filename.txt
        ```
    """
    help = 'Create required and missing groups and roles for the courses imported from studio.'

    def add_arguments(self, parser):
        parser.add_argument(
            '-g',
            '--groups',
            action='store',
            dest='groups',
            nargs='+',
            required=True,
            help=('Name of the group.')
        )

        parser.add_argument(
            '-u',
            '--users',
            action='store',
            dest='users',
            required=False,
            nargs='*',
            help=('Usernames or emails for the users.')
        )

        parser.add_argument(
            '-s',
            '--staff',
            action='store_true',
            dest='for_all_staff',
            required=False,
            help=('Add all staff users to the group.')
        )

        parser.add_argument(
            '-f',
            '--file',
            action='store',
            dest='filename',
            required=False,
            help=('Name of the file having usernames/emails of the users.')
        )

    def handle(self, *args, **options):
        users = self.get_users(options)
        groups = self.get_groups(options)
        for group in groups:
            for user in users:
                user.groups.add(group)
                logger.info('Added user {} in group {}'.format(user, group))

    def get_users(self, options):
        if (
            not options.get('for_all_staff') and
            not options.get('users') and
            not options.get('filename')
        ):
            raise CommandError(
                'At least one of the options,"-u username [username ...]",'
                ' "-s", or "-f [FILENAME]" are required'
            )

        all_users = User.objects.all()
        users = []

        if options.get('for_all_staff'):
            logger.info('Publisher roles will be created for all staff users.')
            users += all_users.filter(is_staff=True)

        if options.get('users'):
            users += all_users.filter(
                Q(username__in=options['users']) |
                Q(email__in=options['users'])
            )

        if options.get('filename'):
            usernames = self.read_usernames_from_file(options['filename'])
            users += all_users.filter(
                Q(username__in=usernames) |
                Q(email__in=usernames)
            )

        return users

    def read_usernames_from_file(self, filename):
        with open(filename, 'r') as input_file:
            return [user.strip() for user in input_file.read().split('\n') if user]

    def get_groups(self, options):
        groups = [group.strip() for group in options['groups'] if group]
        if groups == ['__ALL__']:
            return Group.objects.all()
        return Group.objects.filter(name__in=groups)
