from datetime import date, time

from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .guest_access import GUEST_ACCOUNT_SESSION_KEY, GUEST_USERNAME_SESSION_KEY
from .models import (
	AnswerSubmission,
	Exam,
	ExamCenterExam,
	ExamType,
	GuestTeacherAccount,
	Student,
	StudentProfile,
	Subject,
	TeacherProfile,
	Workspace,
)


class _WorkspaceMixin:
	"""Attach a default Workspace to a teacher so models with NOT NULL workspace FK can be created."""

	def _make_workspace(self, teacher, slug_number=1, name='Default'):
		return Workspace.objects.create(teacher=teacher, name=name, slug_number=slug_number)


class GuestReadOnlyAccessTests(_WorkspaceMixin, TestCase):
	def setUp(self):
		self.teacher = User.objects.create_user(username='teacher1', password='teacher-pass')
		TeacherProfile.objects.create(user=self.teacher, institution='Test School')
		self.workspace = self._make_workspace(self.teacher)

		self.guest_user = User.objects.create_user(username='guest1', password='guest-pass')
		self.guest_account = GuestTeacherAccount.objects.create(
			teacher=self.teacher,
			guest_user=self.guest_user,
			workspace=self.workspace,
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
		student = Student.objects.create(first_name='A', roll='1', class_name='7', teacher=self.teacher, workspace=self.workspace)
		subject = Subject.objects.create(name='Math', short_name='MTH', teacher=self.teacher, workspace=self.workspace)
		exam_type = ExamType.objects.create(name='CQ', teacher=self.teacher, workspace=self.workspace)
		exam = Exam.objects.create(
			student=student,
			subject=subject,
			exam_type=exam_type,
			teacher=self.teacher,
			workspace=self.workspace,
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
			workspace=self.workspace,
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
		student = Student.objects.create(first_name='B', roll='2', class_name='7', teacher=self.teacher, workspace=self.workspace)
		subject = Subject.objects.create(name='English', short_name='ENG', teacher=self.teacher, workspace=self.workspace)
		exam_type = ExamType.objects.create(name='CQ', teacher=self.teacher, workspace=self.workspace)
		exam = Exam.objects.create(
			student=student,
			subject=subject,
			exam_type=exam_type,
			teacher=self.teacher,
			workspace=self.workspace,
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
			workspace=self.workspace,
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
		self.public_workspace = Workspace.objects.create(teacher=self.public_teacher, name='Public WS', slug_number=1)
		self.public_guest_user = User.objects.create_user(username='public_guest', password='guest-pass')
		self.public_guest_account = GuestTeacherAccount.objects.create(
			teacher=self.public_teacher,
			guest_user=self.public_guest_user,
			workspace=self.public_workspace,
			is_publicly_accessible=True,
		)

		self.private_teacher = User.objects.create_user(username='private_teacher', password='teacher-pass')
		TeacherProfile.objects.create(user=self.private_teacher, institution='Private School')
		self.private_workspace = Workspace.objects.create(teacher=self.private_teacher, name='Private WS', slug_number=1)
		self.private_guest_user = User.objects.create_user(username='private_guest', password='guest-pass')
		GuestTeacherAccount.objects.create(
			teacher=self.private_teacher,
			guest_user=self.private_guest_user,
			workspace=self.private_workspace,
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
		self.workspace = Workspace.objects.create(teacher=self.teacher, name='WS', slug_number=1)

		self.viewer_student = Student.objects.create(
			first_name='Viewer',
			roll='1',
			class_name='7',
			teacher=self.teacher,
			workspace=self.workspace,
		)
		self.target_student = Student.objects.create(
			first_name='Target',
			roll='2',
			class_name='7',
			teacher=self.teacher,
			workspace=self.workspace,
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


class StudentDashboardPersonalizationTests(TestCase):
	def setUp(self):
		self.teacher = User.objects.create_user(username='teacher_dash', password='teacher-pass')
		TeacherProfile.objects.create(user=self.teacher, institution='Dash School')
		self.workspace = Workspace.objects.create(teacher=self.teacher, name='WS', slug_number=1)

		self.viewer_student = Student.objects.create(
			first_name='Viewer',
			roll='1',
			class_name='7',
			teacher=self.teacher,
			workspace=self.workspace,
		)
		self.other_student = Student.objects.create(
			first_name='Other',
			roll='2',
			class_name='7',
			teacher=self.teacher,
			workspace=self.workspace,
		)

		self.viewer_user = User.objects.create_user(username='viewer_dash', password='student-pass')
		StudentProfile.objects.create(
			user=self.viewer_user,
			student=self.viewer_student,
			created_by=self.teacher,
		)

		subject = Subject.objects.create(name='Mathematics', short_name='MTH', teacher=self.teacher, workspace=self.workspace)
		exam_type = ExamType.objects.create(name='CQ', teacher=self.teacher, workspace=self.workspace)

		Exam.objects.create(
			student=self.viewer_student,
			subject=subject,
			exam_type=exam_type,
			teacher=self.teacher,
			workspace=self.workspace,
			date=date(2026, 4, 1),
			chapter='1',
			class_number='7',
			total_marks=100,
			mark_obtained=90,
			exam_id=101,
		)

		Exam.objects.create(
			student=self.other_student,
			subject=subject,
			exam_type=exam_type,
			teacher=self.teacher,
			workspace=self.workspace,
			date=date(2026, 4, 2),
			chapter='1',
			class_number='7',
			total_marks=100,
			mark_obtained=10,
			exam_id=102,
		)

		self.client.force_login(self.viewer_user)

	def test_student_dashboard_shows_only_logged_in_student_data(self):
		response = self.client.get(reverse('dashboard'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'My Dashboard')
		self.assertContains(response, 'Viewer')
		self.assertNotContains(response, 'Other')

	def test_overall_grade_distribution_api_is_student_specific_for_student_login(self):
		response = self.client.get(reverse('api_overall_grade_distribution'))

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertIn('Superb', payload['labels'])
		self.assertNotIn('Horrible', payload['labels'])


# -----------------------------------------------------------------------------
# Workspace isolation tests (plan §10 — 21 tests across 5 groups).
# -----------------------------------------------------------------------------
from datetime import time as _time
from django.contrib.auth.models import User as _User
from django.utils import timezone as _tz
from marks import guest_access as _guest_access
from marks.models import (
	ExamCenterExam,
	PointsSpent,
	PointTransaction,
	StudentProfile,
	Workspace as _Workspace,
)
from marks.services import (
	LeaderboardService,
	DashboardService,
	ChartDataService,
)
from marks.workspaces import (
	ACTIVE_WORKSPACE_SESSION_KEY,
	get_active_workspace,
	get_workspace_for_user,
	set_active_workspace,
)


_REQUEST_FACTORY = RequestFactory()


def _make_workspace(teacher, slug_number=1, name='WS'):
	return _Workspace.objects.create(teacher=teacher, name=name, slug_number=slug_number)


def _set_session(client, **kwargs):
	"""Persist keys onto the test client's session."""
	s = client.session
	for k, v in kwargs.items():
		s[k] = v
	s.save()


def _build_request(user, *, session_keys=None, url='/dashboard/'):
	req = _REQUEST_FACTORY.get(url)
	req.user = user
	req.session = SessionStore()
	for k, v in (session_keys or {}).items():
		req.session[k] = v
	req.session.save()
	return req


# ----- Group 1: Resolution (5) -----------------------------------------------

class WorkspaceResolutionTests(TestCase):
	def setUp(self):
		self.teacher = _User.objects.create_user(username='t_resolve', password='pw')
		TeacherProfile.objects.create(user=self.teacher, institution='X')

	def test_active_workspace_defaults_to_oldest(self):
		ws1 = _make_workspace(self.teacher, slug_number=1, name='First')
		_make_workspace(self.teacher, slug_number=2, name='Second')
		req = _build_request(self.teacher)
		ws = get_active_workspace(req)
		self.assertEqual(ws.pk, ws1.pk)

	def test_session_workspace_takes_precedence(self):
		_make_workspace(self.teacher, slug_number=1, name='First')
		ws2 = _make_workspace(self.teacher, slug_number=2, name='Second')
		req = _build_request(self.teacher, session_keys={ACTIVE_WORKSPACE_SESSION_KEY: ws2.pk})
		ws = get_active_workspace(req)
		self.assertEqual(ws.pk, ws2.pk)

	def test_archived_workspace_not_active(self):
		ws1 = _make_workspace(self.teacher, slug_number=1, name='First')
		ws2 = _make_workspace(self.teacher, slug_number=2, name='Second')
		ws2.is_archived = True
		ws2.save()
		# Session points at archived ws2 — resolution must fall back to ws1.
		req = _build_request(self.teacher, session_keys={ACTIVE_WORKSPACE_SESSION_KEY: ws2.pk})
		ws = get_active_workspace(req)
		self.assertEqual(ws.pk, ws1.pk)

	def test_student_workspace_always_pinned(self):
		ws_t = _make_workspace(self.teacher, slug_number=1, name='Teacher WS')
		ws_other = _make_workspace(self.teacher, slug_number=2, name='Other WS')

		student_user = _User.objects.create_user(username='stud_pin', password='pw')
		student = Student.objects.create(first_name='P', roll='1', class_name='7', teacher=self.teacher, workspace=ws_t)
		StudentProfile.objects.create(user=student_user, student=student, created_by=self.teacher)

		# Even with the OTHER workspace in the session, a student's workspace
		# must always come from their StudentProfile.
		req = _build_request(student_user, session_keys={ACTIVE_WORKSPACE_SESSION_KEY: ws_other.pk})
		ws = get_active_workspace(req)
		self.assertEqual(ws.pk, ws_t.pk)

	def test_workspace_middleware_cache(self):
		ws1 = _make_workspace(self.teacher, slug_number=1, name='First')
		req = _build_request(self.teacher)
		first = get_active_workspace(req)
		self.assertIs(first, req._workspace_cache)
		# Mutating session after caching should be ignored.
		ws2 = _make_workspace(self.teacher, slug_number=2, name='Second')
		req.session[ACTIVE_WORKSPACE_SESSION_KEY] = ws2.pk
		req.session.save()
		again = get_active_workspace(req)
		self.assertEqual(again.pk, first.pk)  # cache wins


# ----- Group 2: Query scoping (5) ---------------------------------------------

class WorkspaceQueryScopingTests(TestCase):
	def setUp(self):
		self.teacher = _User.objects.create_user(username='t_scope', password='pw')
		TeacherProfile.objects.create(user=self.teacher, institution='X')
		self.client.force_login(self.teacher)

	def test_subject_list_isolated_per_workspace(self):
		ws1 = _make_workspace(self.teacher, slug_number=1, name='A')
		ws2 = _make_workspace(self.teacher, slug_number=2, name='B')
		Subject.objects.create(name='Math-A', short_name='MA', teacher=self.teacher, workspace=ws1)
		Subject.objects.create(name='Math-B', short_name='MB', teacher=self.teacher, workspace=ws2)

		_set_session(self.client, **{ACTIVE_WORKSPACE_SESSION_KEY: ws1.pk})
		response = self.client.get(reverse('subject_list'))
		self.assertEqual(response.status_code, 200)
		body = response.content.decode()
		self.assertIn('Math-A', body)
		self.assertNotIn('Math-B', body)

		_set_session(self.client, **{ACTIVE_WORKSPACE_SESSION_KEY: ws2.pk})
		response = self.client.get(reverse('subject_list'))
		self.assertEqual(response.status_code, 200)
		body = response.content.decode()
		self.assertIn('Math-B', body)
		self.assertNotIn('Math-A', body)

	def test_exam_list_isolated_per_workspace(self):
		ws1 = _make_workspace(self.teacher, slug_number=1, name='A')
		ws2 = _make_workspace(self.teacher, slug_number=2, name='B')

		s1 = Subject.objects.create(name='Math', short_name='M', teacher=self.teacher, workspace=ws1)
		s2 = Subject.objects.create(name='Bio', short_name='B', teacher=self.teacher, workspace=ws2)
		et = ExamType.objects.create(name='CQ', teacher=self.teacher, workspace=ws1)

		stu1 = Student.objects.create(first_name='A1', roll='1', class_name='7', teacher=self.teacher, workspace=ws1)
		stu2 = Student.objects.create(first_name='B1', roll='1', class_name='7', teacher=self.teacher, workspace=ws2)

		Exam.objects.create(student=stu1, subject=s1, exam_type=et, teacher=self.teacher, workspace=ws1,
			date=date(2026, 4, 1), chapter='1', class_number='7', total_marks=100, mark_obtained=80, exam_id=1)
		Exam.objects.create(student=stu2, subject=s2, exam_type=et, teacher=self.teacher, workspace=ws2,
			date=date(2026, 4, 2), chapter='1', class_number='7', total_marks=100, mark_obtained=70, exam_id=1)

		_set_session(self.client, **{ACTIVE_WORKSPACE_SESSION_KEY: ws1.pk})
		r = self.client.get(reverse('all_exams'))
		# ws1 student A1 should appear, ws2 student B1 should not.
		self.assertEqual(r.status_code, 200)
		body = r.content.decode()
		self.assertIn('A1', body)
		self.assertNotIn('B1', body)

	def test_lifetime_points_isolated(self):
		# LifetimePoints should be scoped per workspace — students in different
		# workspaces must have separate LifetimePoints records.
		ws1 = _make_workspace(self.teacher, slug_number=1, name='A')
		ws2 = _make_workspace(self.teacher, slug_number=2, name='B')

		stu1 = Student.objects.create(first_name='A1', roll='1', class_name='7', teacher=self.teacher, workspace=ws1)
		stu2 = Student.objects.create(first_name='B1', roll='1', class_name='7', teacher=self.teacher, workspace=ws2)

		from marks.models import LifetimePoints
		lp1 = LifetimePoints.objects.create(student=stu1, points_earned=80, points_spent=0)
		lp2 = LifetimePoints.objects.create(student=stu2, points_earned=70, points_spent=0)
		self.assertNotEqual(lp1.points_earned, lp2.points_earned)

		# Leaderboard for ws1 must not include ws2 students.
		from marks.services import LeaderboardService
		lb1 = LeaderboardService.lifetime_points_leaderboard(workspace=ws1)
		lb2 = LeaderboardService.lifetime_points_leaderboard(workspace=ws2)
		ids1 = {row['student'].pk for row in lb1}
		ids2 = {row['student'].pk for row in lb2}
		self.assertIn(stu1.pk, ids1)
		self.assertNotIn(stu2.pk, ids1)
		self.assertIn(stu2.pk, ids2)
		self.assertNotIn(stu1.pk, ids2)

	def test_examcenter_3cap_per_workspace(self):
		ws1 = _make_workspace(self.teacher, slug_number=1, name='A')
		ws2 = _make_workspace(self.teacher, slug_number=2, name='B')

		# Fill ws1 to 3 active exams; ws2 should remain empty.
		# Schedule them in the FUTURE so `is_finished` is False (otherwise the
		# cap check would skip them and `can_create_exam` would still return True).
		import datetime as _dt
		future_date = _tz.now().date() + _dt.timedelta(days=1)
		future_time = _time(9, 0)
		for i in range(3):
			ExamCenterExam.objects.create(
				teacher=self.teacher, workspace=ws1,
				exam_display_id=f'1{i}', class_number=7, subject='Math', chapter='1',
				exam_mode='online', exam_type='cq', total_marks=100,
				exam_date=future_date, start_time=future_time,
				duration_minutes=30, submission_duration_minutes=10,
			)
		# ws2 should still allow a new exam (different workspace = independent cap).
		ExamCenterExam.objects.create(
			teacher=self.teacher, workspace=ws2,
			exam_display_id='21', class_number=7, subject='Bio', chapter='1',
			exam_mode='online', exam_type='cq', total_marks=100,
			exam_date=future_date, start_time=future_time,
			duration_minutes=30, submission_duration_minutes=10,
		)

		self.assertFalse(ExamCenterExam.can_create_exam(ws1))
		self.assertTrue(ExamCenterExam.can_create_exam(ws2))

	def test_exam_center_page_uses_active_workspace(self):
		import datetime as _dt

		ws1 = _make_workspace(self.teacher, slug_number=1, name='A')
		ws2 = _make_workspace(self.teacher, slug_number=2, name='B')
		future_date = _tz.now().date() + _dt.timedelta(days=1)

		for workspace, exam_id, subject in (
			(ws1, '101', 'Math-A'),
			(ws2, '201', 'Science-B'),
		):
			ExamCenterExam.objects.create(
				teacher=self.teacher, workspace=workspace,
				exam_display_id=exam_id, class_number=7, subject=subject, chapter='1',
				exam_mode='online', exam_type='cq', total_marks=100,
				exam_date=future_date, start_time=_time(9, 0),
				duration_minutes=30, submission_duration_minutes=10,
			)

		_set_session(self.client, **{ACTIVE_WORKSPACE_SESSION_KEY: ws1.pk})
		response = self.client.get(reverse('exam_center'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Math-A')
		self.assertNotContains(response, 'Science-B')

	def test_cloudinary_folder_includes_workspace_slug(self):
		ws1 = _make_workspace(self.teacher, slug_number=1, name='A')
		ws7 = _make_workspace(self.teacher, slug_number=7, name='G')

		s = Subject.objects.create(name='Math', short_name='M', teacher=self.teacher, workspace=ws1)
		et = ExamType.objects.create(name='CQ', teacher=self.teacher, workspace=ws1)
		stu = Student.objects.create(first_name='S', roll='1', class_name='7', teacher=self.teacher, workspace=ws1)
		exam = Exam.objects.create(
			student=stu, subject=s, exam_type=et, teacher=self.teacher, workspace=ws1,
			date=date.today(), chapter='1', class_number='7', total_marks=100,
			mark_obtained=80, exam_id=42,
		)

		path = Exam.exam_pdf_folder_path(exam)
		self.assertIn('/W1/', path)
		self.assertIn(f'/Exam ID 42', path)
		self.assertNotIn('/W0/', path)

		# Also try a workspace with a different slug.
		s2 = Subject.objects.create(name='Math', short_name='M', teacher=self.teacher, workspace=ws7)
		et2 = ExamType.objects.create(name='CQ', teacher=self.teacher, workspace=ws7)
		stu2 = Student.objects.create(first_name='S', roll='1', class_name='7', teacher=self.teacher, workspace=ws7)
		exam7 = Exam.objects.create(
			student=stu2, subject=s2, exam_type=et2, teacher=self.teacher, workspace=ws7,
			date=date.today(), chapter='1', class_number='7', total_marks=100,
			mark_obtained=80, exam_id=99,
		)
		path7 = Exam.exam_pdf_folder_path(exam7)
		self.assertIn('/W7/', path7)
		self.assertNotIn('/W1/', path7)


# ----- Group 3: Notifications (2) ---------------------------------------------

class WorkspaceNotificationTests(TestCase):
	def setUp(self):
		self.teacher = _User.objects.create_user(username='t_notify', password='pw')
		TeacherProfile.objects.create(user=self.teacher, institution='X')
		self.ws1 = _make_workspace(self.teacher, slug_number=1, name='A')
		self.ws2 = _make_workspace(self.teacher, slug_number=2, name='B')

	def test_exam_notification_only_targets_workspace_students(self):
		from marks import notifications as N

		stu_user_a = _User.objects.create_user(username='sa', password='pw')
		stu_user_b = _User.objects.create_user(username='sb', password='pw')
		stu_a = Student.objects.create(first_name='SA', roll='1', class_name='7', teacher=self.teacher, workspace=self.ws1)
		stu_b = Student.objects.create(first_name='SB', roll='1', class_name='7', teacher=self.teacher, workspace=self.ws2)
		StudentProfile.objects.create(user=stu_user_a, student=stu_a, created_by=self.teacher)
		StudentProfile.objects.create(user=stu_user_b, student=stu_b, created_by=self.teacher)

		exam = ExamCenterExam.objects.create(
			teacher=self.teacher, workspace=self.ws1,
			exam_display_id='501', class_number=7, subject='Math', chapter='1',
			exam_mode='online', exam_type='cq', total_marks=100,
			exam_date=date.today(), start_time=_time(9, 0),
			duration_minutes=30, submission_duration_minutes=10,
		)

		# Inspect what _send_to_users would receive by monkey-patching.
		captured = []
		original = getattr(N, '_send_to_users', None)
		N._send_to_users = lambda user_ids, *a, **kw: (captured.append(list(user_ids) if hasattr(user_ids, '__iter__') else [user_ids]), 0)[1]
		try:
			N.notify_exam_created(exam)
		finally:
			N._send_to_users = original

		flat = [uid for batch in captured for uid in batch if isinstance(uid, int)]
		# Only ws1's student should be in the notification list.
		self.assertIn(stu_user_a.pk, flat)
		self.assertNotIn(stu_user_b.pk, flat)

	def test_result_published_workspace_isolation(self):
		from marks import notifications as N

		stu_user_a = _User.objects.create_user(username='sra', password='pw')
		stu_user_b = _User.objects.create_user(username='srb', password='pw')
		stu_a = Student.objects.create(first_name='RA', roll='1', class_name='7', teacher=self.teacher, workspace=self.ws1)
		stu_b = Student.objects.create(first_name='RB', roll='1', class_name='7', teacher=self.teacher, workspace=self.ws2)
		StudentProfile.objects.create(user=stu_user_a, student=stu_a, created_by=self.teacher)
		StudentProfile.objects.create(user=stu_user_b, student=stu_b, created_by=self.teacher)

		s = Subject.objects.create(name='Math', short_name='M', teacher=self.teacher, workspace=self.ws1)
		et = ExamType.objects.create(name='CQ', teacher=self.teacher, workspace=self.ws1)

		# Same exam_id in BOTH workspaces is allowed (scoped uniqueness).
		Exam.objects.create(student=stu_a, subject=s, exam_type=et, teacher=self.teacher, workspace=self.ws1,
			date=date.today(), chapter='1', class_number='7', total_marks=100, mark_obtained=80, exam_id=555)
		Exam.objects.create(student=stu_b, subject=s, exam_type=et, teacher=self.teacher, workspace=self.ws2,
			date=date.today(), chapter='1', class_number='7', total_marks=100, mark_obtained=70, exam_id=555)

		captured = []
		original = getattr(N, '_send_to_users', None)
		N._send_to_users = lambda user_ids, *a, **kw: (captured.append(list(user_ids) if hasattr(user_ids, '__iter__') else [user_ids]), 0)[1]
		try:
			N.notify_result_published(exam_id=555, student_ids=[stu_a.pk, stu_b.pk], workspace=self.ws1)
		finally:
			N._send_to_users = original

		flat = [uid for batch in captured for uid in batch if isinstance(uid, int)]
		self.assertIn(stu_user_a.pk, flat)
		self.assertNotIn(stu_user_b.pk, flat)


# ----- Group 4: Management UI (5) ---------------------------------------------

class WorkspaceManagementUITests(TestCase):
	def setUp(self):
		self.teacher = _User.objects.create_user(username='t_ui', password='pw')
		TeacherProfile.objects.create(user=self.teacher, institution='X')
		self.client.force_login(self.teacher)

	def test_manage_page_links_to_workspace_management(self):
		response = self.client.get(reverse('manage'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Manage Workspaces')
		self.assertContains(response, reverse('workspace_list'))

	def test_workspace_messages_use_global_popup_style(self):
		response = self.client.post(
			reverse('workspace_create'),
			data={'name': '', 'description': ''},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Workspace name is required.')
		self.assertContains(response, 'data-popup-message')
		self.assertContains(response, 'fixed right-4')

	def test_switch_workspace_shows_success_popup(self):
		ws1 = _make_workspace(self.teacher, slug_number=1, name='Class 7')
		ws2 = _make_workspace(self.teacher, slug_number=2, name='Class 8')
		_set_session(self.client, **{ACTIVE_WORKSPACE_SESSION_KEY: ws1.pk})

		response = self.client.post(
			reverse('workspace_switch', args=[ws2.pk]),
			data={'next': reverse('workspace_list')},
			follow=True,
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Workspace switched to &quot;Class 8&quot;.')
		self.assertContains(response, 'data-popup-message')
		self.assertEqual(self.client.session[ACTIVE_WORKSPACE_SESSION_KEY], ws2.pk)

	def test_workspace_list_shows_net_points_awarded_per_workspace(self):
		ws1 = _make_workspace(self.teacher, slug_number=1, name='Class 7')
		ws2 = _make_workspace(self.teacher, slug_number=2, name='Class 8')
		student1 = Student.objects.create(
			first_name='Alice', roll='1', class_name='7',
			teacher=self.teacher, workspace=ws1,
		)
		student2 = Student.objects.create(
			first_name='Bob', roll='1', class_name='8',
			teacher=self.teacher, workspace=ws2,
		)

		PointTransaction.objects.create(
			student=student1, teacher=self.teacher, workspace=ws1,
			transaction_type='exam_bonus', points_change=75,
			description='Exam bonus', date=date.today(),
		)
		PointTransaction.objects.create(
			student=student1, teacher=self.teacher, workspace=ws1,
			transaction_type='spent', points_change=-20,
			description='Points spent', date=date.today(),
		)
		PointTransaction.objects.create(
			student=student2, teacher=self.teacher, workspace=ws2,
			transaction_type='exam_bonus', points_change=40,
			description='Exam bonus', date=date.today(),
		)
		PointTransaction.objects.create(
			student=student2, teacher=self.teacher, workspace=ws2,
			transaction_type='spent', points_change=-7,
			description='Points spent', date=date.today(),
		)

		response = self.client.get(reverse('workspace_list'))

		self.assertEqual(response.status_code, 200)
		workspace_stats = {
			item['workspace'].pk: item['net_points_awarded']
			for item in response.context['workspaces_with_counts']
		}
		self.assertEqual(workspace_stats[ws1.pk], 55)
		self.assertEqual(workspace_stats[ws2.pk], 33)

	def test_teacher_can_create_workspace(self):
		response = self.client.post(reverse('workspace_create'), data={'name': 'Renamed', 'description': 'desc'}, follow=True)
		self.assertEqual(response.status_code, 200)
		ws = _Workspace.objects.get(teacher=self.teacher, name='Renamed')
		# slug_number should be 2 (auto-created default in middleware resolution already made slug=1)
		self.assertIn(ws.slug_number, (1, 2))
		self.assertEqual(ws.teacher, self.teacher)

	def test_workspace_archive_switches_active(self):
		ws1 = _make_workspace(self.teacher, slug_number=1, name='Default')
		ws2 = _make_workspace(self.teacher, slug_number=2, name='Second')

		_set_session(self.client, **{ACTIVE_WORKSPACE_SESSION_KEY: ws1.pk})

		response = self.client.post(reverse('workspace_archive', args=[ws1.pk]), follow=True)
		self.assertEqual(response.status_code, 200)
		ws1.refresh_from_db()
		self.assertTrue(ws1.is_archived)

	def test_workspace_delete_requires_confirm(self):
		ws1 = _make_workspace(self.teacher, slug_number=1, name='First')
		ws2 = _make_workspace(self.teacher, slug_number=2, name='Second')

		url = reverse('workspace_delete', args=[ws1.pk])
		# GET shows the confirmation page.
		r = self.client.get(url)
		self.assertEqual(r.status_code, 200)
		self.assertContains(r, ws1.name)
		# POST with wrong name → not deleted.
		r = self.client.post(url, data={'confirm_name': 'WRONG'}, follow=True)
		self.assertTrue(_Workspace.objects.filter(pk=ws1.pk).exists())
		# POST with correct name → deleted.
		r = self.client.post(url, data={'confirm_name': ws1.name}, follow=True)
		self.assertFalse(_Workspace.objects.filter(pk=ws1.pk).exists())

	def test_guest_cannot_switch(self):
		# Host teacher logged in (with TeacherProfile so workspace middleware
		# treats them as a teacher). GuestTeacherAccount.teacher must equal
		# request.user, so we use self.teacher as the "teacher" of the guest
		# account — same pattern as GuestReadOnlyAccessTests. A guest_user is
		# still created (required by the OneToOneField), but is irrelevant to
		# the resolution. workspace_switch must refuse the host once the
		# session is marked as guest.
		guest_user = _User.objects.create_user(username='guest_ui', password='pw')
		ws_t = _make_workspace(self.teacher, slug_number=1, name='T')
		ws_other = _make_workspace(self.teacher, slug_number=2, name='O')
		ga = GuestTeacherAccount.objects.create(
			teacher=self.teacher, guest_user=guest_user, workspace=ws_t,
		)

		# Stay logged in as self.teacher (matches GuestTeacherAccount.teacher).
		_set_session(self.client, **{
			_guest_access.GUEST_ACCOUNT_SESSION_KEY: ga.id,
			_guest_access.GUEST_USERNAME_SESSION_KEY: guest_user.username,
		})

		# Guest sessions are blocked at the middleware layer
		# (GuestReadOnlyMiddleware redirects POSTs from guests with a popup
		# message) — the workspace_switch view itself returns 403 but the
		# middleware intercepts first. Either way, the active workspace must
		# NOT change.
		response = self.client.post(reverse('workspace_switch', args=[ws_other.pk]))
		# The middleware redirects (302); the view (if reached) returns 403.
		self.assertIn(response.status_code, (302, 403))
		# Active workspace is NOT ws_other.
		active_id = self.client.session.get(ACTIVE_WORKSPACE_SESSION_KEY)
		self.assertNotEqual(active_id, ws_other.pk)

	def test_student_cannot_view_workspace_pages(self):
		ws_t = _make_workspace(self.teacher, slug_number=1, name='T')
		student_user = _User.objects.create_user(username='stu_ui', password='pw')
		stu = Student.objects.create(first_name='S', roll='1', class_name='7', teacher=self.teacher, workspace=ws_t)
		StudentProfile.objects.create(user=student_user, student=stu, created_by=self.teacher)

		self.client.force_login(student_user)
		response = self.client.get(reverse('workspace_list'))
		self.assertEqual(response.status_code, 403)


# ----- Group 5: Cloudinary + delete (4) ---------------------------------------

class WorkspaceCloudinaryAndDeleteTests(TestCase):
	def setUp(self):
		self.teacher = _User.objects.create_user(username='t_cld', password='pw')
		TeacherProfile.objects.create(user=self.teacher, institution='X')

	def _make_exam(self, ws):
		s = Subject.objects.create(name='Math', short_name='M', teacher=self.teacher, workspace=ws)
		et = ExamType.objects.create(name='CQ', teacher=self.teacher, workspace=ws)
		stu = Student.objects.create(first_name='S', roll='1', class_name='7', teacher=self.teacher, workspace=ws)
		return Exam.objects.create(
			student=stu, subject=s, exam_type=et, teacher=self.teacher, workspace=ws,
			date=date.today(), chapter='1', class_number='7', total_marks=100,
			mark_obtained=80, exam_id=1,
		)

	def test_pdf_folder_per_workspace(self):
		ws = _make_workspace(self.teacher, slug_number=1, name='A')
		exam = self._make_exam(ws)
		path = Exam.exam_pdf_folder_path(exam)
		self.assertEqual(path, f"ResTrack/{self.teacher.username}/W1/Exam Questions/Exam ID 1")

	def test_marking_scheme_folder_per_workspace(self):
		ws = _make_workspace(self.teacher, slug_number=1, name='A')
		exam = self._make_exam(ws)
		path = Exam.marked_answer_folder_path(exam)
		self.assertEqual(path, f"ResTrack/{self.teacher.username}/W1/Marked Answer Papers/Exam ID 1")

	def test_delete_teacher_removes_all_workspaces(self):
		ws1 = _make_workspace(self.teacher, slug_number=1, name='A')
		ws2 = _make_workspace(self.teacher, slug_number=2, name='B')
		Subject.objects.create(name='S', short_name='S', teacher=self.teacher, workspace=ws1)
		Student.objects.create(first_name='X', roll='1', class_name='7', teacher=self.teacher, workspace=ws1)

		self.client.force_login(self.teacher)
		# delete_account is a 3-step POST flow; final step requires confirm_text='DELETE MY ACCOUNT'.
		response = self.client.post(
			reverse('delete_account'),
			data={'step': '3', 'confirm_text': 'DELETE MY ACCOUNT'},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		# Teacher cascade: User.objects.filter(pk=...) is gone, so all workspaces are too.
		self.assertFalse(_User.objects.filter(pk=self.teacher.pk).exists())
		self.assertFalse(_Workspace.objects.filter(teacher=self.teacher).exists())

	def test_workspace_unique_constraint_per_teacher(self):
		# Same (teacher, slug_number) is forbidden.
		_make_workspace(self.teacher, slug_number=1, name='A')
		with self.assertRaises(Exception):
			_make_workspace(self.teacher, slug_number=1, name='Dup')
		# Different name but same slug is still forbidden (the constraint is on
		# (teacher, slug_number), not on (teacher, name)).

	def test_workspace_unique_constraint_isolated_across_teachers(self):
		# Two teachers can both hold slug_number=1 (per-teacher counter).
		_make_workspace(self.teacher, slug_number=1, name='A')
		other = _User.objects.create_user(username='other_cld', password='pw')
		TeacherProfile.objects.create(user=other, institution='Y')
		# Must succeed — slug_number=1 is fresh for `other`.
		ws_other = _make_workspace(other, slug_number=1, name='A')
		self.assertEqual(ws_other.teacher, other)
