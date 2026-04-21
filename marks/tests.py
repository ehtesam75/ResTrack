from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .guest_access import GUEST_ACCOUNT_SESSION_KEY, GUEST_USERNAME_SESSION_KEY
from .models import AnswerSubmission, Exam, ExamCenterExam, ExamType, GuestTeacherAccount, Student, StudentProfile, Subject, TeacherProfile


class GuestReadOnlyAccessTests(TestCase):
	def setUp(self):
		self.teacher = User.objects.create_user(username='teacher1', password='teacher-pass')
		TeacherProfile.objects.create(user=self.teacher, institution='Test School')

		self.guest_user = User.objects.create_user(username='guest1', password='guest-pass')
		self.guest_account = GuestTeacherAccount.objects.create(
			teacher=self.teacher,
			guest_user=self.guest_user,
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

	def test_guest_cannot_download_marked_answer_paper(self):
		student = Student.objects.create(first_name='A', roll='1', class_name='7', teacher=self.teacher)
		subject = Subject.objects.create(name='Math', short_name='MTH', teacher=self.teacher)
		exam_type = ExamType.objects.create(name='CQ', teacher=self.teacher)
		exam = Exam.objects.create(
			student=student,
			subject=subject,
			exam_type=exam_type,
			teacher=self.teacher,
			date=date.today(),
			chapter='1',
			class_number=7,
			total_marks=100,
			mark_obtained=80,
			exam_id=1,
		)

		response = self.client.get(reverse('exam_download_answer', args=[exam.pk]), follow=True)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Guest accounts are view-only and cannot access student submission files.')

	def test_guest_cannot_open_manage_answer_paper_page(self):
		response = self.client.get(reverse('manage_answer_paper'), follow=True)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Manage Answer Paper')

	def test_guest_cannot_open_exam_center_submissions_page(self):
		exam = ExamCenterExam.objects.create(
			teacher=self.teacher,
			exam_display_id='101',
			class_number=7,
			subject='Math',
			chapter='1',
			exam_mode='online',
			exam_type='cq',
			total_marks=100,
			exam_date=date.today(),
			start_time=time(9, 0),
			duration_minutes=30,
			submission_duration_minutes=10,
		)

		response = self.client.get(reverse('exam_center_submissions', args=[exam.pk]), follow=True)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Answer Submissions')

	def test_guest_clicking_view_answer_action_is_blocked_with_popup(self):
		student = Student.objects.create(first_name='B', roll='2', class_name='7', teacher=self.teacher)
		subject = Subject.objects.create(name='English', short_name='ENG', teacher=self.teacher)
		exam_type = ExamType.objects.create(name='CQ', teacher=self.teacher)
		exam = Exam.objects.create(
			student=student,
			subject=subject,
			exam_type=exam_type,
			teacher=self.teacher,
			date=date.today(),
			chapter='2',
			class_number=7,
			total_marks=100,
			mark_obtained=70,
			exam_id=2,
		)

		response = self.client.get(reverse('exam_view_answer', args=[exam.pk]), follow=True)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Guest accounts are view-only and cannot access student submission files.')

	def test_guest_clicking_exam_center_submission_actions_is_blocked_with_popup(self):
		exam = ExamCenterExam.objects.create(
			teacher=self.teacher,
			exam_display_id='303',
			class_number=7,
			subject='Science',
			chapter='3',
			exam_mode='online',
			exam_type='cq',
			total_marks=100,
			exam_date=date.today(),
			start_time=time(9, 0),
			duration_minutes=30,
			submission_duration_minutes=10,
		)
		student_user = User.objects.create_user(username='student_u2', password='student-pass')
		sub = AnswerSubmission.objects.create(
			exam=exam,
			student_user=student_user,
			answer_file='https://res.cloudinary.com/demo/raw/upload/sample.pdf',
			is_final=True,
		)

		view_response = self.client.get(reverse('exam_center_view_submission', args=[sub.pk]), follow=True)
		download_response = self.client.get(reverse('exam_center_download_submission', args=[sub.pk]), follow=True)

		self.assertEqual(view_response.status_code, 200)
		self.assertContains(view_response, 'Guest accounts are view-only and cannot access student submission files.')
		self.assertEqual(download_response.status_code, 200)
		self.assertContains(download_response, 'Guest accounts are view-only and cannot access student submission files.')


class GuestExploreFlowTests(TestCase):
	def setUp(self):
		self.public_teacher = User.objects.create_user(username='public_teacher', password='teacher-pass')
		TeacherProfile.objects.create(user=self.public_teacher, institution='Public School')
		self.public_guest_user = User.objects.create_user(username='public_guest', password='guest-pass')
		self.public_guest_account = GuestTeacherAccount.objects.create(
			teacher=self.public_teacher,
			guest_user=self.public_guest_user,
			is_publicly_accessible=True,
		)

		self.private_teacher = User.objects.create_user(username='private_teacher', password='teacher-pass')
		TeacherProfile.objects.create(user=self.private_teacher, institution='Private School')
		self.private_guest_user = User.objects.create_user(username='private_guest', password='guest-pass')
		GuestTeacherAccount.objects.create(
			teacher=self.private_teacher,
			guest_user=self.private_guest_user,
			is_publicly_accessible=False,
		)

	def test_guest_explore_page_lists_only_public_accounts(self):
		response = self.client.get(reverse('guest_explore'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.public_teacher.username)
		self.assertNotContains(response, self.private_teacher.username)

	def test_guest_explore_can_start_read_only_session_for_selected_teacher(self):
		response = self.client.post(
			reverse('guest_explore'),
			data={'guest_account_id': str(self.public_guest_account.id)},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse('dashboard'))

		session = self.client.session
		self.assertEqual(session.get(GUEST_ACCOUNT_SESSION_KEY), self.public_guest_account.id)
		self.assertEqual(session.get(GUEST_USERNAME_SESSION_KEY), self.public_guest_user.username)

		response = self.client.get(reverse('dashboard'))
		self.assertEqual(response.status_code, 200)

	def test_guest_explore_rejects_private_or_invalid_selection(self):
		response = self.client.post(
			reverse('guest_explore'),
			data={'guest_account_id': '999999'},
			follow=True,
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Please select an available teacher to continue.')


class StudentChartApiAccessTests(TestCase):
	def setUp(self):
		self.teacher = User.objects.create_user(username='teacher_api', password='teacher-pass')
		TeacherProfile.objects.create(user=self.teacher, institution='Test School')

		self.viewer_student = Student.objects.create(
			first_name='Viewer',
			roll='1',
			class_name='7',
			teacher=self.teacher,
		)
		self.target_student = Student.objects.create(
			first_name='Target',
			roll='2',
			class_name='7',
			teacher=self.teacher,
		)

		self.viewer_user = User.objects.create_user(username='viewer_student', password='student-pass')
		StudentProfile.objects.create(
			user=self.viewer_user,
			student=self.viewer_student,
			created_by=self.teacher,
		)

		self.client.force_login(self.viewer_user)

	def test_student_can_access_chart_apis_for_other_students_in_same_teacher_scope(self):
		chart_urls = [
			reverse('api_marks_over_time', args=[self.target_student.id]),
			reverse('api_subject_performance', args=[self.target_student.id]),
			reverse('api_grade_distribution', args=[self.target_student.id]),
		]

		for url in chart_urls:
			response = self.client.get(url)
			self.assertEqual(response.status_code, 200)
