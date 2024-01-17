import filecmp
from os.path import isfile, join
from tarfile import TarFile
from tempfile import TemporaryDirectory

import orjson
from django.test import TransactionTestCase

from karrot.activities.factories import ActivitySeriesFactory
from karrot.activities.models import ActivitySeries
from karrot.groups.factories import GroupFactory
from karrot.groups.models import Group, GroupMembership
from karrot.migrate.exporter import export_to_file
from karrot.migrate.importer import import_from_file
from karrot.places.factories import PlaceFactory
from karrot.places.models import Place
from karrot.users.factories import UserFactory
from karrot.users.models import User
from karrot.utils.tests.fake import faker
from karrot.utils.tests.uploads import image_path


class TestExportImport(TransactionTestCase):
    def setUp(self):
        self._tmpdir = TemporaryDirectory()
        self.tmpdir = self._tmpdir.name

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_creates_archive_file(self):
        group = GroupFactory()
        export_filename = self.export(group)
        self.assertTrue(isfile(export_filename))

    def test_can_import_exported_file(self):
        group = GroupFactory()
        group_name = group.name
        export_filename = self.export(group)
        self.reset_db()
        self.assertFalse(Group.objects.filter(name=group_name).exists())
        import_from_file(export_filename)
        self.assertTrue(Group.objects.filter(name=group_name).exists())

    def test_can_migrate_group_photo(self):
        group = GroupFactory(photo=image_path)
        group_name = group.name
        original_photo_file = group.photo.path
        export_filename = self.export(group)
        self.reset_db()
        import_from_file(export_filename)
        imported_group = Group.objects.get(name=group_name)
        imported_photo_file = imported_group.photo.path
        self.assertNotEqual(original_photo_file, imported_photo_file)
        self.assertTrue(filecmp.cmp(original_photo_file, imported_photo_file))

    def test_exports_memberships(self):
        user = UserFactory()
        group = GroupFactory(members=[user])
        membership = GroupMembership.objects.get(user=user, group=group)
        export_filename = self.export(group)
        with TarFile.open(export_filename, "r|xz") as tarfile:
            memberships = []
            for member in tarfile:
                if member.name == "groups.groupmembership.json":
                    for line in tarfile.extractfile(member).readlines():
                        memberships.append(orjson.loads(line))
            self.assertIsNotNone(memberships)
            self.assertEqual(len(memberships), 1)
            self.assertEqual(memberships[0]["notification_types"], membership.notification_types)

    def test_migrates_users_and_memberships(self):
        users = [UserFactory() for _ in range(10)]
        group = GroupFactory(members=users)
        export_filename = self.export(group)
        self.assertEqual(group.members.count(), 10)
        self.reset_db()
        self.assertEqual(User.objects.count(), 0)
        import_from_file(export_filename)
        self.assertEqual(User.objects.count(), 10)
        self.assertEqual(Group.objects.first().members.count(), 10)

    def test_migrates_place(self):
        group = GroupFactory()
        PlaceFactory(group=group)
        export_filename = self.export(group)
        self.reset_db()
        self.assertEqual(Place.objects.count(), 0)
        import_from_file(export_filename)
        self.assertEqual(Place.objects.count(), 1)

    def test_migrates_activity_series(self):
        group = GroupFactory()
        place = PlaceFactory(group=group)
        ActivitySeriesFactory(place=place)
        export_filename = self.export(group)
        self.reset_db()
        self.assertEqual(ActivitySeries.objects.count(), 0)
        import_from_file(export_filename)
        self.assertEqual(ActivitySeries.objects.count(), 1)

    def reset_db(self):
        self._fixture_teardown()

    def export(self, *groups):
        export_filename = join(self.tmpdir, faker.file_name(extension="tar.xz"))
        export_to_file([group.id for group in groups], export_filename)
        return export_filename
