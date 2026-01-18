from django.contrib import admin
from .models import Student, Subject, ExamType, Exam, GradeScale, LifetimePoints, PointsSpent, TeacherProfile, StudentProfile


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'institution', 'created_at']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'institution']
    list_filter = ['created_at']


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'student', 'created_by', 'created_at']
    search_fields = ['user__username', 'student__first_name', 'student__last_name', 'created_by__username']
    list_filter = ['created_at', 'created_by']


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['name', 'first_name', 'last_name', 'roll', 'class_name', 'total_marks', 'total_exams', 'average_percentage']
    search_fields = ['first_name', 'last_name', 'roll']
    list_filter = ['class_name']
    fields = ['first_name', 'last_name', 'roll', 'class_name']
    list_display_links = ['total_marks']
    list_editable = ['first_name', 'last_name', 'roll', 'class_name']


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'average_marks']
    search_fields = ['name']
    list_display_links = ['average_marks']
    list_editable = ['name']


@admin.register(ExamType)
class ExamTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']
    list_display_links = ['created_at']
    list_editable = ['name']


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ['exam_id', 'student', 'subject', 'exam_type', 'date', 'chapter', 'mark_obtained', 'total_marks', 'percentage', 'grade', 'class_number', 'has_pdf']
    list_filter = ['subject', 'exam_type', 'date', 'student', 'class_number']
    search_fields = ['student__first_name', 'student__last_name', 'subject__name', 'chapter', 'exam_id']
    date_hierarchy = 'date'
    ordering = ['-exam_id']
    
    # Make fields editable in admin
    fields = ['student', 'subject', 'exam_type', 'date', 'chapter', 'class_number', 'total_marks', 'mark_obtained', 'group_id', 'exam_id', 'question_pdf']
    
    def has_pdf(self, obj):
        return bool(obj.question_pdf)
    has_pdf.boolean = True
    has_pdf.short_description = 'PDF'
    list_editable = ['chapter', 'mark_obtained', 'total_marks']
    
    def percentage(self, obj):
        return f"{obj.percentage}%"
    
    def grade(self, obj):
        return obj.grade
    
    def save_model(self, request, obj, form, change):
        """Override save to recalculate points when exam is edited"""
        super().save_model(request, obj, form, change)
        # Recalculate points for the student
        obj.student.recalculate_lifetime_points()
    
    def delete_model(self, request, obj):
        """Override delete to recalculate points when exam is deleted"""
        student = obj.student
        super().delete_model(request, obj)
        student.recalculate_lifetime_points()
    
    def delete_queryset(self, request, queryset):
        """Override bulk delete to recalculate points for affected students"""
        # Get all affected students before deletion
        students = set(queryset.values_list('student', flat=True))
        # Delete the records
        super().delete_queryset(request, queryset)
        # Recalculate points for affected students
        from .models import Student
        for student_id in students:
            try:
                student = Student.objects.get(id=student_id)
                student.recalculate_lifetime_points()
            except Student.DoesNotExist:
                pass


@admin.register(GradeScale)
class GradeScaleAdmin(admin.ModelAdmin):
    list_display = ['grade_name', 'points', 'color_code']
    ordering = ['grade_name']
    list_editable = ['points', 'color_code']


@admin.register(LifetimePoints)
class LifetimePointsAdmin(admin.ModelAdmin):
    list_display = ['student', 'points_earned', 'points_spent', 'points_remaining']
    search_fields = ['student__first_name', 'student__last_name']
    
    def points_remaining(self, obj):
        return obj.points_remaining
    points_remaining.short_description = 'Points Remaining'


@admin.register(PointsSpent)
class PointsSpentAdmin(admin.ModelAdmin):
    list_display = ['student', 'points_spent', 'description', 'date', 'created_at']
    list_filter = ['date', 'student']
    search_fields = ['student__first_name', 'student__last_name', 'description']
    date_hierarchy = 'date'
    readonly_fields = ['created_at']
    list_editable = ['points_spent', 'description']
    
    def delete_queryset(self, request, queryset):
        """Override bulk delete to update student points"""
        from django.db.models import Sum
        # Get all affected students
        students = set(queryset.values_list('student', flat=True))
        # Delete the records
        super().delete_queryset(request, queryset)
        # Update points for affected students
        for student_id in students:
            try:
                lifetime_points = LifetimePoints.objects.get(student_id=student_id)
                total_spent = PointsSpent.objects.filter(student_id=student_id).aggregate(
                    total=Sum('points_spent')
                )['total'] or 0
                lifetime_points.points_spent = total_spent
                lifetime_points.save()
            except LifetimePoints.DoesNotExist:
                pass
