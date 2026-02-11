from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import Student, TeacherProfile, StudentProfile, ExamCenterExam


class TeacherSignupForm(UserCreationForm):
    """Form for teacher registration"""
    error_messages = {
        **UserCreationForm.error_messages,
        'password_mismatch': "Passwords don't match",
    }
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'Enter your email'
        })
    )
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'Enter your first name'
        })
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'Enter your last name'
        })
    )
    institution = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'School/Institution name (optional)'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'Choose a username'
        })
        self.fields['password1'].widget.attrs.update({
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'Create a password'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'Confirm your password'
        })
        self.fields['username'].error_messages['unique'] = 'Username already taken'

    def _post_clean(self):
        """Attach password validation errors to password1 instead of password2"""
        super(UserCreationForm, self)._post_clean()
        password = self.cleaned_data.get('password2')
        if password:
            try:
                from django.contrib.auth.password_validation import validate_password
                validate_password(password, self.instance)
            except ValidationError as error:
                self.add_error('password1', error)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()
            TeacherProfile.objects.create(
                user=user,
                institution=self.cleaned_data.get('institution', '')
            )
        return user


class LoginForm(AuthenticationForm):
    """Custom login form"""
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'Enter your username'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'Enter your password'
        })
    )


class StudentAccountForm(forms.Form):
    """Form for creating student accounts by teachers"""
    # Student personal info
    first_name = forms.CharField(
        max_length=10,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'First name (max 10 chars)'
        })
    )
    last_name = forms.CharField(
        max_length=10,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'Last name (max 10 chars, optional)'
        })
    )
    class_number = forms.IntegerField(
        min_value=1,
        max_value=12,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'Class (1-12)'
        })
    )
    roll = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'Roll number'
        })
    )
    
    # Account credentials
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'Create a unique username'
        })
    )
    password = forms.CharField(
        min_length=6,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'Create password (min 6 characters)'
        })
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'Confirm password'
        })
    )

    def __init__(self, teacher=None, *args, **kwargs):
        self.teacher = teacher
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = self.cleaned_data.get('username')
        # Check if username already exists for any user
        if User.objects.filter(username=username).exists():
            raise ValidationError('This username is already taken. Please choose another.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if password and confirm_password and password != confirm_password:
            raise ValidationError('Passwords do not match.')
        
        return cleaned_data

    def save(self):
        """Create both the User account and Student record"""
        # Create the user account
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            password=self.cleaned_data['password']
        )
        
        # Create the student record
        student = Student.objects.create(
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data.get('last_name') or None,
            class_name=str(self.cleaned_data['class_number']),
            roll=self.cleaned_data['roll']
        )
        
        # Create student profile linking user to student
        StudentProfile.objects.create(
            user=user,
            student=student,
            created_by=self.teacher
        )
        
        return student, user


class EditStudentForm(forms.Form):
    """Form for editing student information"""
    first_name = forms.CharField(
        max_length=10,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'First name (max 10 chars)'
        })
    )
    last_name = forms.CharField(
        max_length=10,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all',
            'placeholder': 'Last name (max 10 chars, optional)'
        })
    )
    class_number = forms.IntegerField(
        min_value=1,
        max_value=12,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all'
        })
    )
    roll = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm transition-all'
        })
    )


# ---------------------------------------------------------------------------
# Exam Center forms
# ---------------------------------------------------------------------------

_INPUT_CLS = 'w-full px-2.5 sm:px-3 py-1.5 sm:py-2 text-xs sm:text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent bg-gray-50 hover:bg-white transition-colors'
_SELECT_CLS = _INPUT_CLS


class ExamCenterExamForm(forms.ModelForm):
    """Form for creating / editing Exam Center exams."""

    class Meta:
        model = ExamCenterExam
        fields = [
            'exam_display_id', 'class_number', 'subject', 'chapter', 'exam_mode',
            'exam_type', 'total_marks', 'exam_date', 'start_time',
            'duration_minutes', 'submission_duration_minutes', 'question_pdf',
        ]
        widgets = {
            'exam_display_id': forms.TextInput(attrs={'class': _INPUT_CLS, 'placeholder': 'e.g. EX-101'}),
            'class_number': forms.NumberInput(attrs={'class': _INPUT_CLS, 'min': 1, 'max': 12, 'placeholder': '1–12'}),
            'subject': forms.Select(attrs={'class': _SELECT_CLS}),
            'chapter': forms.TextInput(attrs={'class': _INPUT_CLS, 'placeholder': 'e.g. 5 or Ch-3', 'maxlength': '10'}),
            'exam_mode': forms.Select(attrs={'class': _SELECT_CLS}),
            'exam_type': forms.Select(attrs={'class': _SELECT_CLS}),
            'total_marks': forms.NumberInput(attrs={'class': _INPUT_CLS, 'min': 1, 'placeholder': 'Total marks'}),
            'exam_date': forms.DateInput(attrs={'class': _INPUT_CLS, 'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'class': _INPUT_CLS, 'type': 'time'}),
            'duration_minutes': forms.NumberInput(attrs={'class': _INPUT_CLS, 'min': 1, 'max': 300, 'placeholder': 'Minutes (max 300)'}),
            'submission_duration_minutes': forms.NumberInput(attrs={'class': _INPUT_CLS, 'min': 1, 'max': 30, 'placeholder': 'Default 10 min (max 30)'}),
            'question_pdf': forms.ClearableFileInput(attrs={'class': _INPUT_CLS, 'accept': '.pdf'}),
        }

    def __init__(self, *args, teacher=None, **kwargs):
        self.teacher = teacher
        super().__init__(*args, **kwargs)
        self.fields['submission_duration_minutes'].required = False
        self.fields['chapter'].required = True

        # Build subject choices from teacher's subjects
        from .models import Subject
        subject_choices = [('', 'Select Subject')]
        if teacher:
            subjects = Subject.objects.filter(teacher=teacher).order_by('name')
            subject_choices += [(s.name, s.name) for s in subjects]
        self.fields['subject'] = forms.ChoiceField(
            choices=subject_choices,
            widget=forms.Select(attrs={'class': _SELECT_CLS}),
            required=True,
        )

        # Add blank default for exam_mode, exam_type, start_time
        mode_choices = [('', 'Select Mode')] + list(ExamCenterExam.MODE_CHOICES)
        type_choices = [('', 'Select Type')] + list(ExamCenterExam.TYPE_CHOICES)
        self.fields['exam_mode'].choices = mode_choices
        self.fields['exam_type'].choices = type_choices

        # Pre-select values when editing
        if self.instance and self.instance.pk:
            # Subject: set initial to existing value, ensure it's in choices
            existing_subject = self.instance.subject
            if existing_subject and not any(c[0] == existing_subject for c in subject_choices):
                self.fields['subject'].choices.append((existing_subject, existing_subject))
            self.fields['subject'].initial = existing_subject

    def clean_class_number(self):
        val = self.cleaned_data.get('class_number')
        if val is not None and (val < 1 or val > 12):
            raise ValidationError('Class must be between 1 and 12.')
        return val

    def clean_duration_minutes(self):
        val = self.cleaned_data.get('duration_minutes')
        if val is not None and val > 300:
            raise ValidationError('Exam duration cannot exceed 300 minutes.')
        return val

    def clean_submission_duration_minutes(self):
        val = self.cleaned_data.get('submission_duration_minutes')
        if val is not None and val > 30:
            raise ValidationError('Submission window cannot exceed 30 minutes.')
        return val

    def clean_question_pdf(self):
        pdf = self.cleaned_data.get('question_pdf')
        if pdf and hasattr(pdf, 'size'):
            if pdf.size > 1 * 1024 * 1024:
                raise ValidationError('Question paper must be 1 MB or smaller.')
            if not pdf.name.lower().endswith('.pdf'):
                raise ValidationError('Only PDF files are allowed.')
        return pdf

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get('exam_mode')

        # Validate that exam date/time is in the future (only for new exams)
        exam_date = cleaned.get('exam_date')
        start_time = cleaned.get('start_time')
        if exam_date and start_time:
            import datetime as _dt
            from django.utils import timezone as _tz
            exam_dt = _tz.make_aware(
                _dt.datetime.combine(exam_date, start_time),
                _tz.get_current_timezone(),
            )
            if not (self.instance and self.instance.pk) and exam_dt <= _tz.now():
                raise ValidationError('Exam date and time must be in the future.')

        # Require question PDF for online exams (only on create, or if no existing PDF)
        if mode == 'online':
            pdf = cleaned.get('question_pdf')
            if not pdf and not (self.instance and self.instance.pk and self.instance.question_pdf):
                self.add_error('question_pdf', 'Question paper is mandatory for online exams.')

        # Default submission duration
        if not cleaned.get('submission_duration_minutes'):
            cleaned['submission_duration_minutes'] = 10

        # Enforce 3-exam limit (skip for edits)
        if self.teacher and not self.instance.pk:
            if not ExamCenterExam.can_create_exam(self.teacher):
                raise ValidationError('You already have 3 active exams. Wait until one finishes before creating another.')

        return cleaned
