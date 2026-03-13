from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .guest_access import GUEST_ACCOUNT_SESSION_KEY, GUEST_USERNAME_SESSION_KEY
from .models import GuestTeacherAccount, TeacherProfile


class GuestReadOnlyAccessTests(TestCase):
	def setUp(self):
		self.teacher = User.objects.create_user(username='teacher1', password='teacher-pass')
		TeacherProfile.objects.create(user=self.teacher, institution='Test School')

		self.guest_user = User.objects.create_user(username='guest1', password='guest-pass')
		self.guest_account = GuestTeacherAccount.objects.create(
			teacher=self.teacher,
			guest_user=self.guest_user,
			raw_password='guest-pass',
		)

		self.client.force_login(self.teacher)
		session = self.client.session
		session[GUEST_ACCOUNT_SESSION_KEY] = self.guest_account.id
		session[GUEST_USERNAME_SESSION_KEY] = self.guest_user.username
		session.save()

	def test_guest_post_to_forbidden_action_shows_clear_message(self):
		response = self.client.post(reverse('add_subject'), data={'name': 'Math'}, follow=True)

		self.assertNotEqual(response.status_code, 500)
		self.assertContains(response, 'Guest accounts are view-only and cannot perform this action.')

	def test_guest_cannot_open_manage_guest_account_page(self):
		response = self.client.get(reverse('manage_guest_account'), follow=True)

		self.assertNotEqual(response.status_code, 500)
		self.assertContains(response, 'Guest accounts are view-only and cannot perform this action.')

	def test_guest_login_shows_one_time_popup_message(self):
		self.client.logout()

		response = self.client.post(
			reverse('login'),
			data={'username': 'guest1', 'password': 'guest-pass'},
			follow=True,
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(
			response,
			'View-Only Guest Session: You are logged in as a guest. Modifications are not permitted.',
		)

	def test_guest_dashboard_does_not_show_persistent_session_banner(self):
		response = self.client.get(reverse('dashboard'), follow=True)

		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, 'View-only guest session:')
		self.assertNotContains(response, 'Signed in as guest1. Changes are blocked by the server.')
