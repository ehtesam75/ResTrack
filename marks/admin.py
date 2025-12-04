from django.contrib import admin
from .models import Student, Subject, ExamType, Exam, GradeScale, LifetimePoints, PointsSpent


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['name', 'roll', 'class_name', 'total_marks', 'total_exams', 'average_percentage']
    search_fields = ['name', 'roll']
    list_filter = ['class_name']


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'average_marks']
    search_fields = ['name']


@admin.register(ExamType)
class ExamTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ['exam_id', 'student', 'subject', 'exam_type', 'date', 'mark_obtained', 'total_marks', 'percentage', 'grade', 'class_number']
    list_filter = ['subject', 'exam_type', 'date', 'student', 'class_number']
    search_fields = ['student__name', 'subject__name', 'chapter']
    date_hierarchy = 'date'
    ordering = ['-exam_id']
    
    # Make fields editable in admin
    fields = ['student', 'subject', 'exam_type', 'date', 'chapter', 'class_number', 'total_marks', 'mark_obtained', 'group_id', 'exam_id']
    list_editable = ['mark_obtained', 'total_marks']
    
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


@admin.register(LifetimePoints)
class LifetimePointsAdmin(admin.ModelAdmin):
    list_display = ['student', 'points_earned', 'points_spent', 'points_remaining']
    search_fields = ['student__name']
    
    def points_remaining(self, obj):
        return obj.points_remaining
    points_remaining.short_description = 'Points Remaining'


@admin.register(PointsSpent)
class PointsSpentAdmin(admin.ModelAdmin):
    list_display = ['student', 'points_spent', 'description', 'date', 'created_at']
    list_filter = ['date', 'student']
    search_fields = ['student__name', 'description']
    date_hierarchy = 'date'
    readonly_fields = ['created_at']
    
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
