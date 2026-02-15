from django.urls import path
from django.views.generic import TemplateView
from . import views
from . import exam_center_views
from . import push_views

urlpatterns = [
    # Authentication URLs
    path('', views.home, name='home'),
    path('login/', views.user_login, name='login'),
    path('signup/', views.teacher_signup, name='signup'),
    path('logout/', views.user_logout, name='logout'),
    path('delete-account/', views.delete_account, name='delete_account'),
    
    # Teacher management dashboard
    path('manage/', views.manage, name='manage'),
    
    # Main dashboard (authenticated)
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Student pages
    path('students/', views.student_list, name='student_list'),
    path('students/<int:student_id>/', views.student_detail, name='student_detail'),
    path('students/add/', views.add_student, name='add_student'),
    path('students/<int:student_id>/edit/', views.edit_student, name='edit_student'),
    path('students/compare/<int:student1_id>/<int:student2_id>/', views.compare_students, name='compare_students'),
    
    # Subject pages
    path('subjects/', views.subject_list, name='subject_list'),
    path('subjects/<int:subject_id>/', views.subject_detail, name='subject_detail'),
    path('subjects/add/', views.add_subject, name='add_subject'),
    
    # Exam pages
    path('exams/', views.all_exams, name='all_exams'),
    path('exams/add/', views.add_exam, name='add_exam'),
    path('exams/add-bulk/', views.add_bulk_exam, name='add_bulk_exams'),
    path('exams/<int:exam_id>/edit/', views.edit_exam, name='edit_exam'),
    path('exams/detail/<int:exam_id>/', views.exam_detail, name='exam_detail'),
    path('exams/detail/<int:exam_id>/download-question/', views.exam_download_question, name='exam_download_question'),
    path('exams/download-answer/<int:exam_pk>/', views.exam_download_answer, name='exam_download_answer'),
    
    # Points page
    path('points/', views.points, name='points'),
    path('points/add/', views.add_points_spent, name='add_points_spent'),
    
    # Leaderboard page
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    
    # Guide page
    path('guide/', views.guide, name='guide'),
    
    # About page
    path('about/', views.about, name='about'),

    # Privacy Policy page
    path('privacy-policy/', TemplateView.as_view(template_name='marks/privacy_policy.html'), name='privacy_policy'),

    # Privacy Policy page
    path('privacy-policy/', views.privacy_policy, name='privacy_policy'),

    # Exam lookup page (mobile)
    path('exam-lookup/', views.exam_lookup, name='exam_lookup'),
    path('exam-lookup-api/', views.exam_lookup_api, name='exam_lookup_api'),

    # Question paper management
    path('manage-question-paper/', views.manage_question_paper, name='manage_question_paper'),
    path('api/exam-info/', views.exam_info_api, name='exam_info_api'),
    path('api/exam-id-lookup/', views.exam_id_lookup_api, name='exam_id_lookup_api'),

    # Answer paper management
    path('manage-answer-paper/', views.manage_answer_paper, name='manage_answer_paper'),
    path('api/answer-paper-info/', views.answer_paper_info_api, name='answer_paper_info_api'),

    # Favicon test page
    path('favicon-test/', TemplateView.as_view(template_name='marks/favicon_test.html'), name='favicon_test'),

    # Edit subject
    path('subjects/edit/', views.edit_subject, name='edit_subject'),

    # API endpoints for charts
    path('api/marks-over-time/<int:student_id>/', views.api_marks_over_time, name='api_marks_over_time'),
    path('api/subject-performance/<int:student_id>/', views.api_subject_performance, name='api_subject_performance'),
    path('api/grade-distribution/<int:student_id>/', views.api_grade_distribution, name='api_grade_distribution'),
    path('api/student-comparison/<int:subject_id>/', views.api_student_comparison, name='api_student_comparison'),
    path('api/overall-grade-distribution/', views.api_overall_grade_distribution, name='api_overall_grade_distribution'),

    # Exam Center
    path('exam-center/', exam_center_views.exam_center, name='exam_center'),
    path('exam-center/create/', exam_center_views.exam_center_create, name='exam_center_create'),
    path('exam-center/<int:exam_id>/edit/', exam_center_views.exam_center_edit, name='exam_center_edit'),
    path('exam-center/<int:exam_id>/delete/', exam_center_views.exam_center_delete, name='exam_center_delete'),
    path('exam-center/<int:exam_id>/', exam_center_views.exam_center_detail, name='exam_center_detail'),
    path('exam-center/<int:exam_id>/submit/', exam_center_views.exam_center_submit_answer, name='exam_center_submit_answer'),
    path('exam-center/<int:exam_id>/bonus-time/', exam_center_views.exam_center_bonus_time, name='exam_center_bonus_time'),
    path('exam-center/<int:exam_id>/submissions/', exam_center_views.exam_center_submissions, name='exam_center_submissions'),
    path('exam-center/submissions/<int:submission_id>/download/', exam_center_views.exam_center_download_submission, name='exam_center_download_submission'),
    path('api/exam-center/<int:exam_id>/status/', exam_center_views.exam_center_status_api, name='exam_center_status_api'),

    # Push notification endpoints
    path('api/push/vapid-key/', push_views.vapid_public_key, name='vapid_public_key'),
    path('api/push/subscribe/', push_views.push_subscribe, name='push_subscribe'),
    path('api/push/unsubscribe/', push_views.push_unsubscribe, name='push_unsubscribe'),

    # Cron endpoint (called by cron-job.org)
    path('api/cron/send-exam-reminders/', push_views.cron_send_exam_reminders, name='cron_send_exam_reminders'),
]
