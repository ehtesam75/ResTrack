from django.urls import path
from . import views

urlpatterns = [
    # Main pages
    path('', views.dashboard, name='dashboard'),
    
    # Student pages
    path('students/', views.student_list, name='student_list'),
    path('students/<int:student_id>/', views.student_detail, name='student_detail'),
    path('students/add/', views.add_student, name='add_student'),
    path('students/compare/<int:student1_id>/<int:student2_id>/', views.compare_students, name='compare_students'),
    
    # Subject pages
    path('subjects/', views.subject_list, name='subject_list'),
    path('subjects/<int:subject_id>/', views.subject_detail, name='subject_detail'),
    path('subjects/add/', views.add_subject, name='add_subject'),
    
    # Exam pages
    path('exams/', views.all_exams, name='all_exams'),
    path('exams/add/', views.add_exam, name='add_exam'),
    path('exams/add-bulk/', views.add_bulk_exam, name='add_bulk_exams'),
    path('exam-types/add/', views.add_exam_type, name='add_exam_type'),
    
    # Points page
    path('points/', views.points, name='points'),
    path('points/add/', views.add_points_spent, name='add_points_spent'),
    
    # Leaderboard page
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    
    # Guide page
    path('guide/', views.guide, name='guide'),
    
    # API endpoints for charts
    path('api/marks-over-time/<int:student_id>/', views.api_marks_over_time, name='api_marks_over_time'),
    path('api/subject-performance/<int:student_id>/', views.api_subject_performance, name='api_subject_performance'),
    path('api/grade-distribution/<int:student_id>/', views.api_grade_distribution, name='api_grade_distribution'),
    path('api/student-comparison/<int:subject_id>/', views.api_student_comparison, name='api_student_comparison'),
    path('api/overall-grade-distribution/', views.api_overall_grade_distribution, name='api_overall_grade_distribution'),
]
