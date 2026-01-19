from django.urls import path
from django.views.generic import TemplateView
from . import views

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
    
    # Points page
    path('points/', views.points, name='points'),
    path('points/add/', views.add_points_spent, name='add_points_spent'),
    
    # Leaderboard page
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    
    # Guide page
    path('guide/', views.guide, name='guide'),
    
    # About page
    path('about/', views.about, name='about'),
    
    # Exam lookup page (mobile)
    path('exam-lookup/', views.exam_lookup, name='exam_lookup'),
    path('exam-lookup-api/', views.exam_lookup_api, name='exam_lookup_api'),

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
]
