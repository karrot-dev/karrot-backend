from dateutil.relativedelta import relativedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from karrot.groups.factories import GroupFactory
from karrot.users.factories import VerifiedUserFactory
from karrot.utils.tests.fake import faker


def create_agreement_content(**kwargs):
    return {
        'active_from': timezone.now(),
        'title': faker.text()[:200],
        'summary': faker.text(),
        'content': faker.text(),
        **kwargs,
    }


class TestCreateAgreement(APITestCase):
    def setUp(self):
        self.editor = VerifiedUserFactory()
        self.newcomer = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.editor], newcomers=[self.newcomer])

    def create_agreement_data(self, **kwargs):
        return {
            'group': self.group.id,
            **create_agreement_content(),
            **kwargs,
        }

    def test_can_create_agreement(self):
        self.client.force_login(user=self.editor)
        response = self.client.post(
            '/api/agreements/',
            self.create_agreement_data(),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_cannot_create_agreement_as_newcomer(self):
        self.client.force_login(user=self.newcomer)
        response = self.client.post(
            '/api/agreements/',
            self.create_agreement_data(),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannot_create_agreement_for_other_group(self):
        other_group = GroupFactory()
        self.client.force_login(user=self.editor)
        response = self.client.post(
            '/api/agreements/',
            self.create_agreement_data(group=other_group.id),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)


class TestUpdateAgreement(APITestCase):
    def setUp(self):
        self.editor = VerifiedUserFactory()
        self.newcomer = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.editor], newcomers=[self.newcomer])
        self.agreement = self.group.agreements.create(**create_agreement_content())

    def test_can_update_agreement(self):
        self.client.force_login(user=self.editor)
        new_content = faker.text()
        response = self.client.patch(
            f'/api/agreements/{self.agreement.id}/', {
                'content': new_content,
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.agreement.refresh_from_db()
        self.assertEqual(self.agreement.content, new_content)

    def test_updates_last_changed_by(self):
        self.client.force_login(user=self.editor)
        self.assertEqual(self.agreement.last_changed_by, None)
        self.client.patch(
            f'/api/agreements/{self.agreement.id}/', {
                'content': faker.text(),
            }, format='json'
        )
        self.agreement.refresh_from_db()
        self.assertEqual(self.agreement.last_changed_by, self.editor)

    def test_cannot_update_agreement_as_newcomer(self):
        self.client.force_login(user=self.newcomer)
        new_content = faker.text()
        response = self.client.patch(
            f'/api/agreements/{self.agreement.id}/', {
                'content': new_content,
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_cannot_change_group(self):
        other_group = GroupFactory(members=[self.editor])
        self.client.force_login(user=self.editor)
        response = self.client.patch(
            f'/api/agreements/{self.agreement.id}/', {
                'group': other_group.id,
            }, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)


class TestReadAgreements(APITestCase):
    def setUp(self):
        self.editor = VerifiedUserFactory()
        self.newcomer = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.editor], newcomers=[self.newcomer])
        self.other_group = GroupFactory(members=[self.editor], newcomers=[self.newcomer])

        # active
        for _ in range(3):
            self.group.agreements.create(**create_agreement_content(review_at=timezone.now() + relativedelta(weeks=4)))

        # active and review due
        for _ in range(5):
            self.group.agreements.create(**create_agreement_content(review_at=timezone.now() - relativedelta(days=2)))

        # expired
        for _ in range(12):
            self.group.agreements.create(
                **create_agreement_content(
                    active_from=timezone.now() - relativedelta(weeks=3),
                    active_to=timezone.now() - relativedelta(weeks=1),
                )
            )

    def test_can_get_agreement(self):
        self.client.force_login(user=self.newcomer)
        agreement = self.group.agreements.first()
        response = self.client.get(f'/api/agreements/{agreement.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(
            set(response.data.keys()), {
                'id',
                'title',
                'summary',
                'content',
                'active_from',
                'active_to',
                'review_at',
                'group',
                'last_changed_by',
                'created_by',
            }
        )
        check_fields = {'id', 'title', 'summary', 'content'}
        for field in check_fields:
            self.assertEqual(response.data[field], getattr(agreement, field))

    def test_can_list_agreements(self):
        self.client.force_login(user=self.newcomer)
        response = self.client.get('/api/agreements/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['results']), 20)

    def test_can_list_agreements_by_group(self):
        self.client.force_login(user=self.newcomer)
        response = self.client.get('/api/agreements/', {'group': self.other_group.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['results']), 0)

    def test_can_filter_by_active(self):
        self.client.force_login(user=self.newcomer)
        response = self.client.get('/api/agreements/', {
            'active': 'true',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['results']), 8)

    def test_can_filter_by_inactive(self):
        self.client.force_login(user=self.newcomer)
        response = self.client.get('/api/agreements/', {
            'active': 'false',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['results']), 12)

    def test_can_filter_by_review_due(self):
        self.client.force_login(user=self.newcomer)
        response = self.client.get('/api/agreements/', {
            'review_due': True,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['results']), 5)
