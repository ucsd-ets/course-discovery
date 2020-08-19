"""
Create/update required groups and roles for courses
imported from metadata into publisher.
"""
import logging

import six

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import BaseCommand

from course_discovery.apps.course_metadata.models import Organization
from course_discovery.apps.publisher.assign_permissions import assign_permissions
from course_discovery.apps.publisher.choices import InternalUserRole, PublisherUserRole

from course_discovery.apps.publisher.models import Course as PublisherCourse
from course_discovery.apps.publisher.models import CourseUserRole, OrganizationExtension, OrganizationUserRole


logger = logging.getLogger(__name__)
User = get_user_model()


PARTNER_MANAGER_USER_USERNAME = 'edx_partner_manager_user'
PROJECT_COORDINATOR_USER_USERNAME = 'edx_project_cordinator_user'
MARKETING_USER_USERNAME = 'edx_marketing_user'
PUBLISHER_USER_USERNAME = 'edx_publisher_user'
COURSE_TEAM_USER_USERNAME = 'edx_course_team_user'

PARTNER_MANAGER = InternalUserRole.PartnerManager
PROJECT_COORDINATOR = InternalUserRole.ProjectCoordinator
MARKETING_REVIEWER = InternalUserRole.MarketingReviewer
PUBLISHER = InternalUserRole.Publisher
COURSE_TEAM = PublisherUserRole.CourseTeam

INTERNAL_USER_ROLES = InternalUserRole.values.keys()
PUBLISHER_USER_ROLES = PublisherUserRole.values.keys()


def log_message_prefix(is_created):
    if is_created:
        return 'Created '
    return 'Found existing'


class Command(BaseCommand):
    """
    Run this command after importing courses metadata into publisher.

    Running this command will create the following for the specified organizations:
    - Organization Extension
    - Groups
    - Organization User roles
    - Course user roles
    - Update course(s)' number.

    Example usage:
        ```
        python manage.py create_publisher_roles -o __ALL__ \
            --partner_manager  edx_partner_manager_user\
            --project_coordinator edx_project_cordinator_user\
            --marketing_reviewer edx_marketing_user\
            --publisher edx_publisher_user\
            --course_team edx
        ```
    """
    help = 'Create required and missing groups and roles for the courses imported from studio.'

    def add_arguments(self, parser):
        parser.add_argument(
            '-o',
            '--organizations',
            action='store',
            dest='organizations',
            required=True,
            nargs='+',
            help=('Organization(s) for which to create the groups and roles. '
                  'use "__ALL__" for all organizations')
        )

        parser.add_argument(
            '--partner_manager',
            action='store',
            dest=PARTNER_MANAGER,
            default=PARTNER_MANAGER_USER_USERNAME,
            required=False,
            help=('Username for the role "Partner Manager" for organization and course.')
        )

        parser.add_argument(
            '--project_coordinator',
            action='store',
            dest=PROJECT_COORDINATOR,
            default=PROJECT_COORDINATOR_USER_USERNAME,
            required=False,
            help=('Username for the role "Project Coordinator" for organization and course.')
        )

        parser.add_argument(
            '--marketing_reviewer',
            action='store',
            dest=MARKETING_REVIEWER,
            default=MARKETING_USER_USERNAME,
            required=False,
            help=('Username for the role "Marketing Reviewer" for organization and course.')
        )

        parser.add_argument(
            '--publisher',
            action='store',
            dest=PUBLISHER,
            default=PUBLISHER_USER_USERNAME,
            required=False,
            help=('Username for the role "Publisher" for organization and course.')
        )

        parser.add_argument(
            '--course_team',
            action='store',
            dest=COURSE_TEAM,
            default=COURSE_TEAM_USER_USERNAME,
            required=False,
            help=('Username for the role "Course Team" for course.')
        )

    def handle(self, *args, **options):
        users = self.get_users(options)
        organizations = self.get_organizations(options)

        org_roles = self.create_organization_roles(users, organizations)
        groups = self.create_organization_group(organizations)
        self.link_groups_with_users(users, groups)

        org_courses = self.get_authored_courses(organizations)

        self.update_publisher_courses(org_courses, users)

    def get_users(self, options):
        return {
            PARTNER_MANAGER: User.objects.get(username=options[PARTNER_MANAGER]),
            PROJECT_COORDINATOR: User.objects.get(username=options[PROJECT_COORDINATOR]),
            MARKETING_REVIEWER: User.objects.get(username=options[MARKETING_REVIEWER]),
            PUBLISHER: User.objects.get(username=options[PUBLISHER]),
            COURSE_TEAM: User.objects.get(username=options[COURSE_TEAM]),
        }

    def get_organizations(self, options):
        organizations = options.get('organizations')
        if organizations == ['__ALL__']:
            logger.info('Publisher roles will be created for all existing organizations.')
            return Organization.objects.all()
        return Organization.objects.filter(key__in=organizations)

    def create_organization_roles(self, users, organizations):
        org_roles = {}
        for org in organizations:
            roles = []
            for role in INTERNAL_USER_ROLES:
                try:
                    org.organization_user_roles.get(
                        role=role,
                    )
                    logger.info('{} role {} for organization {}'.format(
                        log_message_prefix(False), role, org
                    ))
                except OrganizationUserRole.DoesNotExist:
                    org.organization_user_roles.create(
                        role=role,
                        user=users[role]
                    )
                    logger.info('{} role {} for organization {}'.format(
                        log_message_prefix(True), role, org
                    ))
                roles.append(role)

            org_roles[org.key] = roles

        return org_roles

    def create_organization_group(self, organizations):
        groups = {}
        for org in organizations:
            group, created = Group.objects.get_or_create(name='{}-admins'.format(org.key))
            logger.info('{} group {} for organization {}'.format(
                log_message_prefix(created), group, org
            ))

            extension, created = OrganizationExtension.objects.get_or_create(
                group=group,
                organization=org
            )

            # Assign appropriate permission to the group so that any user
            # can change the users for course roles
            assign_permissions(extension)

            logger.info('{} organization extension {} for organization {}'.format(
                log_message_prefix(created), extension, org
            ))

            groups[org.key] = group
        return groups

    def link_groups_with_users(self, users, groups):
        for user in six.itervalues(users):
            for _, group in six.iteritems(groups):
                user.groups.add(group)
                logger.info('Added user {} to group {}'.format(
                    user, group
                ))

    def get_authored_courses(self, organizations):
        return {
            org.key: org.authored_courses.all() for org in organizations
        }

    def update_publisher_courses(self, org_courses, users):
        publisher_courses = PublisherCourse.objects.all()
        for org, courses in six.iteritems(org_courses):
            for course in courses:
                pub_course = publisher_courses.get(course_metadata_pk=course.pk)
                course_number = course.key.split('+')[1]
                pub_course.number = course_number
                pub_course.save()
                logger.info('Updated course number {} for course {}'.format(
                    course_number, course
                ))
                self.create_roles_for_course(pub_course, users)

    def create_roles_for_course(self, course, users):
        # TODO add every user to "Publisher Admins" groups to display courses and edit courses team users
        # TODO: make a separate command for managing user roles
        # Publisher admin users can view all courses but can edit only the courses
        # authored by their organizations
        # Internal users can change the users for different roles
        for role in PUBLISHER_USER_ROLES:
            try:
                course_user_role = CourseUserRole.objects.get(
                    course=course,
                    role=role
                )
                logger.info('{} course user role {} for course {}'.format(
                    log_message_prefix(False), course_user_role, course
                ))

            except CourseUserRole.DoesNotExist:
                course_user_role = CourseUserRole.objects.create(
                    course=course,
                    user=users[role],
                    role=role
                )
                logger.info('{} course user role {} for course {}'.format(
                    log_message_prefix(True), course_user_role, course
                ))
