# Developer Guide: Unique Exam Counting

## Overview
This application uses a special system to count exams that accounts for bulk-entered exams. When multiple students take the same exam and their results are entered via the bulk entry feature, they share a `group_id`. These grouped exams should count as **one exam** in statistics, not multiple.

## Helper Functions

### 1. `Student._count_unique_exams(queryset)` (Static Method)
**Location:** `marks/models.py`

**Purpose:** Count unique exams for a queryset, treating grouped exams as one.

**Usage:**
```python
# In Student model methods
exams = self.exam_set.filter(subject=some_subject)
count = Student._count_unique_exams(exams)
```

**Example:**
```python
# Get unique exam count for a student in a specific subject
class Student(models.Model):
    def get_subject_exam_count(self, subject):
        exams = self.exam_set.filter(subject=subject)
        return self._count_unique_exams(exams)
```

### 2. `count_unique_exams(queryset)` (Module Function)
**Location:** `marks/services.py`

**Purpose:** Same as above, but for use in views and services.

**Usage:**
```python
from marks.services import count_unique_exams

# In views
exams = Exam.objects.filter(subject=subject)
unique_count = count_unique_exams(exams)

# In services
total_exams = count_unique_exams(Exam.objects.all())
```

**Example:**
```python
def my_custom_view(request):
    # Get all exams for a specific class
    class_exams = Exam.objects.filter(class_number=5)
    
    # Count unique exams (grouped bulk entries count as 1)
    exam_count = count_unique_exams(class_exams)
    
    return render(request, 'template.html', {'exam_count': exam_count})
```

## How It Works

### The Algorithm
```python
def count_unique_exams(queryset):
    # Step 1: Count distinct group_ids (each bulk entry exam = 1)
    grouped_count = queryset.exclude(
        Q(group_id__isnull=True) | Q(group_id='')
    ).values('group_id').distinct().count()
    
    # Step 2: Count individual exams (no group_id)
    individual_count = queryset.filter(
        Q(group_id__isnull=True) | Q(group_id='')
    ).count()
    
    # Step 3: Sum them up
    return grouped_count + individual_count
```

### Example Scenario

**Database State:**
```
Exam 1: Student A, Math, group_id='uuid-123'
Exam 2: Student B, Math, group_id='uuid-123'  
Exam 3: Student C, Math, group_id='uuid-123'
Exam 4: Student A, English, group_id=None
Exam 5: Student B, Science, group_id='uuid-456'
Exam 6: Student C, Science, group_id='uuid-456'
```

**Counting:**
- Grouped exams: 2 (uuid-123 and uuid-456)
- Individual exams: 1 (English exam with no group_id)
- **Total unique exams: 3**

## When to Use

### ✅ Use Helper Functions When:
- Displaying exam counts in dashboards
- Calculating statistics (total exams per subject, per type, etc.)
- Generating reports
- Comparing student performance
- Any time you need to count exams for display/analysis

### ❌ Don't Use When:
- You need the actual number of exam records (for admin/debugging)
- Processing individual exam results (grading, points calculation)
- Iterating through exams (use `.all()` or `.filter()` directly)

## Common Patterns

### Pattern 1: Subject Statistics
```python
def get_subject_stats(subject):
    exams = Exam.objects.filter(subject=subject)
    return {
        'unique_exams': count_unique_exams(exams),
        'total_records': exams.count(),  # Actual DB records
        'average_score': exams.aggregate(Avg('percentage'))
    }
```

### Pattern 2: Student Performance
```python
class Student(models.Model):
    def subject_wise_summary(self):
        summary = []
        subjects = Subject.objects.filter(exam__student=self).distinct()
        
        for subject in subjects:
            exams = self.exam_set.filter(subject=subject)
            summary.append({
                'subject': subject,
                'exam_count': self._count_unique_exams(exams),  # Use helper!
                'average': calculate_average(exams)
            })
        
        return summary
```

### Pattern 3: Dashboard Overview
```python
class DashboardService:
    @staticmethod
    def get_overview():
        all_exams = Exam.objects.all()
        return {
            'total_unique_exams': count_unique_exams(all_exams),
            'total_students': Student.objects.count(),
            'total_subjects': Subject.objects.count()
        }
```

## Best Practices

1. **Always use helpers for counts displayed to users**
   - Users think in terms of "exams taken", not "exam records in database"

2. **Import from the right place**
   - In models: Use `self._count_unique_exams()` or `Student._count_unique_exams()`
   - In views/services: `from marks.services import count_unique_exams`

3. **Pass the right queryset**
   - Make sure to filter your queryset before passing to helper
   - The helper doesn't filter - it only counts what you give it

4. **Document your code**
   - When using helpers, add a comment explaining why
   - Example: `# Count unique exams (grouped bulk entries as 1)`

## Troubleshooting

### Problem: Count seems too low
**Cause:** You're seeing unique exam count, not total records
**Solution:** This is expected! Use `.count()` if you need actual records

### Problem: Import error
**Cause:** Circular import or wrong import path
**Solution:** 
- In models: Use the static method (no import needed)
- In views/services: Import from `marks.services`

### Problem: Count doesn't match expectations
**Cause:** Filtering before counting
**Solution:** Check your queryset filters before passing to helper

## Additional Resources

- See `marks/models.py` for model implementation
- See `marks/services.py` for service implementation
- See `marks/views.py` for view examples
- See `REFACTORING_SUMMARY.md` for refactoring details

## Questions?

If you're unsure whether to use the helper or not, ask yourself:
- "Am I showing this count to a user?" → **Use helper**
- "Is this for statistics/analytics?" → **Use helper**
- "Do I need the actual DB record count?" → **Use `.count()` directly**

When in doubt, use the helper - it's the safer choice for user-facing data!
