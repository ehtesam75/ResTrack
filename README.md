# ResTrack - Student Result Tracking & Analysis System

<div align="center">

![ResTrack Logo](static/icons/ResTrack-192x192.png)

**A comprehensive web application for managing, analyzing, and visualizing student exam performance with gamification features.**

[![Django](https://img.shields.io/badge/Django-5.1.4-092E20?style=for-the-badge&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.4-06B6D4?style=for-the-badge&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

[Features](#features) • [Installation](#installation) • [Usage](#usage) • [Documentation](#documentation) • [Contributing](#contributing)

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Technology Stack](#-technology--stack)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage Guide](#usage-guide)
- [System Architecture](#-system-architecture)
- [Grading System](#-grading-system)
- [Points & Rewards](#-points--rewards)
- [Screenshots](#-screenshots)
- [Deployment](#-deployment)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🎯 Overview

**ResTrack** (Results Tracking System) transforms traditional grade tracking into an engaging, gamified learning experience. Designed for educators and students, it provides comprehensive tools for recording exam results, analyzing performance trends, and motivating students through a points-based reward system.

### Why ResTrack?

- **Automated Grading**: Instant calculation with customizable CQ and MCQ grading scales
- **Performance Analytics**: Visual insights through interactive charts and detailed reports
- **Gamification**: Points system converts academic achievement into tangible rewards
- **Competitive Rankings**: Multiple leaderboards to motivate and track top performers
- **Responsive Design**: Fully optimized for desktop and mobile devices
- **Teacher & Student Roles**: Separate interfaces with appropriate permissions

---

## ✨ Key Features

### For Teachers

- 📊 **Comprehensive Dashboard** - Real-time analytics and performance overview
- 👥 **Student Management** - Create accounts, manage & edit profiles, and track individual progress
- 📝 **Exam Entry** - Single and bulk exam result recording with PDF question paper upload
- 📚 **Subject Organization** - Create and manage subjects with performance tracking
- 💰 **Points Management** - Track and manage student points spending
- 📈 **Advanced Analytics** - Grade distribution, subject performance, and trend analysis
- 🏆 **Leaderboards** - Overall, subject-wise, and monthly rankings

### For Students

- 📊 **Personal Dashboard** - View your performance metrics and rankings
- 📈 **Progress Tracking** - Monitor improvement over time with visual charts
- 🎯 **Subject Analysis** - Detailed breakdown by subject and exam type
- 💎 **Points Balance** - Track earned, spent, and remaining points
- 🏅 **Achievements** - View monthly wins, subject tops, and excellence rate
- 📱 **Mobile Access** - Full functionality on smartphones and tablets

### System Features

- 🔐 **Secure Authentication** - Role-based access (Teacher/Student)
- 📄 **PDF Question Papers** - Upload and access exam question papers
- 🎨 **Modern UI/UX** - Clean, intuitive interface with Tailwind CSS
- 📊 **Interactive Charts** - Chart.js visualizations for data analysis
- 🔍 **Advanced Filtering** - Filter exams by student, subject, date, and more
- 🌙 **Responsive Design** - Optimized for all screen sizes
- ⚡ **PWA Support** - Install as a Progressive Web App

---

## 🛠️ Technology Stack

### Backend
- **Framework**: Django 5.1.4
- **Database**: PostgreSQL (Production) / SQLite (Development)
- **ORM**: Django ORM with custom model methods
- **Authentication**: Django's built-in auth system

### Frontend
- **CSS Framework**: Tailwind CSS 3.4
- **Charts**: Chart.js
- **Icons**: Lucide Icons, Font Awesome
- **JavaScript**: Vanilla JS for interactivity

### Deployment & Storage
- **Server**: Render (Web Service)
- **Database**: Neon PostgreSQL
- **Static Files**: WhiteNoise
- **Media Storage**: Cloudinary
- **Environment**: Python-dotenv

---

## 🚀 Installation

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)
- PostgreSQL (for production) or SQLite (for development)
- Git

### Local Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/ehtesam75/ResTrack.git
   cd ResTrack
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   
   Create a `.env` file in the project root:
   ```env
   SECRET_KEY=your-secret-key-here
   DEBUG=True
   DATABASE_URL=postgresql://user:password@localhost/restrack
   
   # Cloudinary (for media storage)
   CLOUDINARY_CLOUD_NAME=your-cloud-name
   CLOUDINARY_API_KEY=your-api-key
   CLOUDINARY_API_SECRET=your-api-secret
   ```

5. **Run migrations**
   ```bash
   python manage.py migrate
   ```

6. **Create superuser (admin)**
   ```bash
   python manage.py createsuperuser
   ```

7. **Collect static files**
   ```bash
   python manage.py collectstatic
   ```

8. **Run development server**
   ```bash
   python manage.py runserver
   ```

9. **Access the application**
   
   Open your browser and navigate to: `http://localhost:8000`

---

## ⚙️ Configuration

### Database Configuration

**Development (SQLite)**:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

**Production (PostgreSQL)**:
```python
import dj_database_url

DATABASES = {
    'default': dj_database_url.config(
        default=os.getenv('DATABASE_URL'),
        conn_max_age=600
    )
}
```

### Cloudinary Setup

1. Sign up at [Cloudinary](https://cloudinary.com/)
2. Get your credentials from the dashboard
3. Add them to your `.env` file
4. Configure in `settings.py`:

```python
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET'),
}

DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
```

---

## 📖 Usage Guide

### For Teachers

#### 1. **Sign Up**
   - Navigate to `/signup`
   - Create a teacher account with your credentials
   - Only teachers can sign up directly

#### 2. **Add Students**
   - Go to "Manage" → "Add Student"
   - Enter student details (name, class, roll number)
   - System creates login credentials automatically
   - Share credentials with students

#### 3. **Create Subjects**
   - Navigate to "Add Subject"
   - Enter subject name
   - Subjects are teacher-specific

#### 4. **Record Exam Results**
   
   **Single Entry**:
   - Go to "Add Exam"
   - Select student, subject, exam type
   - Enter marks and optional PDF question paper
   - System auto-calculates grade and points
   
   **Bulk Entry**:
   - Go to "Bulk Exam Entry"
   - Enter number of students
   - Fill common exam details
   - Enter individual marks for each student

#### 5. **Manage Points**
   - Record when students spend points
   - View points history and balances
   - Track remaining vs. spent points

### For Students

#### 1. **Log In**
   - Use credentials provided by teacher
   - Access personal dashboard

#### 2. **View Performance**
   - Check exam results and grades
   - Monitor points balance
   - View rankings and achievements

#### 3. **Track Progress**
   - Analyze subject-wise performance
   - View performance trends over time
   - Compare with classmates

#### 4. **Access Question Papers**
   - Navigate to "Exam Papers" (mobile)
   - Enter exam ID to view/download PDFs

---

## 🏗️ System Architecture

### Data Models

```
Student
├── name, roll, class_number
├── teacher (ForeignKey to User)
├── Methods: total_marks, average_percentage, rank
└── Relations: Exam, LifetimePoints, PointsSpent

Subject
├── name
├── teacher (ForeignKey to User)
└── Methods: average_marks, best_student()

Exam
├── student, subject, exam_type
├── date, chapter, class_number
├── total_marks, mark_obtained
├── exam_id (for grouping bulk entries)
├── question_pdf (Cloudinary)
└── Properties: percentage, grade, points_earned

ExamType
├── name (CQ, MCQ, etc.)
└── teacher (ForeignKey to User)

LifetimePoints
├── student (OneToOneField)
├── points_earned (from exams)
├── points_spent
└── Properties: total_points, points_remaining

PointsSpent
├── student, points_spent
├── description, date
└── teacher (ForeignKey to User)

TeacherProfile
└── user, institution

StudentProfile
└── user, student, created_by
```

### Multi-Tenancy Design

ResTrack implements a **teacher-based multi-tenancy** system:

- Each teacher owns their data (students, subjects, exams)
- Data isolation prevents cross-teacher access
- Students see only their own data
- Leaderboards and rankings are teacher-specific

---

## 📊 Grading System

### CQ (Creative Questions) Grading Scale

| Grade    | Percentage Range  | Points | Color   |
|----------|-------------------|--------|---------|
| Superb   | ≥ 85%             | +20    | Green   |
| Good     | 70% - 84.99%      | +15    | Lime    |
| Average  | 50% - 69.99%      | 0      | Yellow  |
| Poor     | 33% - 49.99%      | -10    | Amber   |
| Fail     | 20% - 32.99%      | -15    | Red     |
| Horrible | < 20%             | -20    | Dark Red|

### MCQ (Multiple Choice Questions) Grading Scale

| Grade    | Percentage Range  | Points | Color   |
|----------|-------------------|--------|---------|
| Superb   | ≥ 93%             | +20    | Green   |
| Good     | 77% - 92.99%      | +15    | Lime    |
| Average  | 55% - 76.99%      | 0      | Yellow  |
| Poor     | 40% - 54.99%      | -10    | Amber   |
| Fail     | 30% - 39.99%      | -15    | Red     |
| Horrible | < 30%             | -20    | Dark Red|

> **Note**: MCQ has higher thresholds due to typically higher scoring potential.

---

## 💰 Points & Rewards

### How Points Work

1. **Earning Points**
   - Each exam awards points based on grade (-20 to +20)
   - Monthly wins add 40 bonus points
   - Points accumulate over time

2. **Bonus Points**
   - **Monthly Winner**: 40 points per month with #1 rank
   - **Eligibility**: ≥40% attendance AND ≥3 exams in that month

3. **Points Value**
   - **1 Point = 1 BDT** (Bangladeshi Taka)
   - Points can be spent on rewards
   - Teachers track and approve withdrawals

4. **Point Calculation**
   ```
   Lifetime Points = Exam Points + Bonus Points
   Remaining Points = Lifetime Points - Points Spent
   ```

### Excellence Rate

- **CQ**: % of exams with ≥80% score
- **MCQ**: % of exams with ≥85% score
- Measures consistency in high-level performance

---

## 📸 Screenshots

### Desktop Views

<details>
<summary>Click to expand screenshots</summary>

**Dashboard**
![Dashboard](docs/screenshots/dashboard.png)

**Student Detail**
![Student Detail](docs/screenshots/student-detail.png)

**Leaderboard**
![Leaderboard](docs/screenshots/leaderboard.png)

**Add Exam**
![Add Exam](docs/screenshots/add-exam.png)

</details>

### Mobile Views

<details>
<summary>Click to expand mobile screenshots</summary>

**Mobile Dashboard**
![Mobile Dashboard](docs/screenshots/mobile-dashboard.png)

**Mobile Leaderboard**
![Mobile Leaderboard](docs/screenshots/mobile-leaderboard.png)

</details>

---

## 🚀 Deployment

### Deploying to Render

1. **Create a Render account** at [render.com](https://render.com)

2. **Create a new Web Service**
   - Connect your GitHub repository
   - Set build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate`
   - Set start command: `gunicorn ResTrack.wsgi:application`

3. **Create a PostgreSQL database**
   - Create a new PostgreSQL database on Render
   - Copy the Internal Database URL

4. **Set environment variables**
   ```
   SECRET_KEY=<generate-a-secret-key>
   DEBUG=False
   DATABASE_URL=<your-postgres-url>
   CLOUDINARY_CLOUD_NAME=<your-cloudinary-name>
   CLOUDINARY_API_KEY=<your-cloudinary-key>
   CLOUDINARY_API_SECRET=<your-cloudinary-secret>
   ```

5. **Deploy**
   - Click "Create Web Service"
   - Wait for deployment to complete

### Post-Deployment

1. **Create superuser**
   ```bash
   python manage.py createsuperuser
   ```

2. **Access admin panel**
   - Navigate to `https://your-app.onrender.com/admin`
   - Log in with superuser credentials

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. **Fork the repository**

2. **Create a feature branch**
   ```bash
   git checkout -b feature/AmazingFeature
   ```

3. **Commit your changes**
   ```bash
   git commit -m 'Add some AmazingFeature'
   ```

4. **Push to the branch**
   ```bash
   git push origin feature/AmazingFeature
   ```

5. **Open a Pull Request**


---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


<div align="center">


</div>
