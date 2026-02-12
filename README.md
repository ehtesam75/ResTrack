# ResTrack - Student Result Tracking & Analysis System

<div align="center">

![ResTrack Logo](static/icons/ResTrack-192x192.png)

**A comprehensive web application for managing, analyzing, and visualizing student exam performance with gamification features.**

[![Django](https://img.shields.io/badge/Django-5.1.4-092E20?style=for-the-badge&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.4-06B6D4?style=for-the-badge&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

[Features](#-key-features) • [Usage Guide](#-usage-guide) • [Grading System](#-grading-system) • [Points & Rewards](#-points--rewards) • [Screenshots](#-screenshots)

</div>

---

## 🎯 Overview

**ResTrack** (Results Tracking System) transforms traditional grade tracking into an engaging, gamified learning experience. Designed for educators and students, it provides comprehensive tools for recording exam results, analyzing performance trends, and motivating students through a points-based reward system.

### Why ResTrack?

- **Automated Grading**: Instant calculation with customizable CQ and MCQ grading scales
- **Real-time Exam Center**: Schedule and conduct live timed exams with countdown timers
- **Performance Analytics**: Visual insights through interactive charts and detailed reports
- **Gamification**: Points system converts academic achievement into tangible rewards
- **Competitive Rankings**: Multiple leaderboards to motivate and track top performers
- **Responsive Design**: Fully optimized for desktop and mobile devices
- **Teacher & Student Roles**: Separate interfaces with appropriate permissions

---

## ✨ Key Features

### For Teachers

-  **Live Exam Center** - Schedule and manage real-time timed exams with countdown timers
  - Create online and offline exams with custom duration
  - Live status tracking (Upcoming → Running → Submission → Finished)
  - Grant bonus time during active exams or submission periods
  - View all student answer submissions with attempt tracking
  - Question paper PDF upload and management

-  **Comprehensive Dashboard** - Real-time analytics and performance overview
-  **Student Management** - Create accounts, manage & edit profiles, and track individual progress
-  **Exam Entry** - Single and bulk exam result recording with PDF question paper upload
-  **Subject Organization** - Create and manage subjects with performance tracking
-  **Points Management** - Track and manage student points spending
-  **Advanced Analytics** - Grade distribution, subject performance, and trend analysis
-  **Leaderboards** - Overall, subject-wise, and monthly rankings

### For Students

-  **Exam Participation** - Attend real-time timed exams in online or offline modes
  - Live countdown timers for exam duration
  - Online: View question papers and submit answer sheets (PDF/ZIP/RAR)
  - Up to 3 submission attempts per online exam
  - Automatic page reload on status changes
  - Bonus time automatically extends your timer

-  **Exam Documents** - Look up any exam by ID to access question papers and marked answers
-  **Personal Dashboard** - View your performance metrics and rankings
-  **Progress Tracking** - Monitor improvement over time with visual charts
-  **Subject Analysis** - Detailed breakdown by subject and exam type
-  **Points Balance** - Track earned, spent, and remaining points
-  **Achievements** - View monthly wins, subject tops, and excellence rate
-  **Mobile Access** - Full functionality on smartphones and tablets

### System Features

-  **Secure Authentication** - Role-based access (Teacher/Student)
-  **Real-time Exam System** - Live countdown timers with auto-refresh
-  **PDF Management** - Upload and access exam question papers and answer sheets
-  **Modern UI/UX** - Clean, intuitive interface with Tailwind CSS
-  **Interactive Charts** - Chart.js visualizations for data analysis
-  **Advanced Filtering** - Filter exams by student, subject, date, and more
-  **Responsive Design** - Optimized for desktop and mobile screen size
-  **PWA Support** - Install as a Progressive Web App

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
- **Real-time Updates**: AJAX polling for live exam status

### Deployment & Storage
- **Server**: Render (Web Service)
- **Database**: Neon PostgreSQL
- **Static Files**: WhiteNoise
- **Media Storage**: Cloudinary
- **Environment**: Python-dotenv

---

## 📖 Usage Guide

### For Teachers

#### 1. Getting Started
- Sign up as a teacher
- Complete your profile
- Set up your grading scales (optional)

#### 2. Student Management
- Create student accounts with usernames and passwords
- Edit student profiles and class information
- View individual student performance

#### 3. Exam Center - Schedule Live Exams
- Navigate to **Exam Center** from the dashboard
- Click **"Create New Exam"**
- Fill in exam details:
  - **Exam ID**: Unique identifier for students to reference
  - **Class & Subject**: Select from your existing subjects
  - **Mode**: Choose Online or Offline
  - **Type**: CQ or MCQ
  - **Date & Time**: When the exam starts
  - **Duration**: Exam writing time in minutes
  - **Submission Window**: (Online only) Time for students to upload answers
  - **Question Paper**: (Online only) Upload PDF (required, max 1 MB)
- Click **"Create Exam"**
- View exam status on the main Exam Center page

**Exam Status Flow:**
-  **Upcoming** - Not yet started, can edit or delete
-  **Running** - Exam in progress, timer counting down
-  **Submission** - (Online only) Students uploading answer sheets
-  **Finished** - Exam completed, view submissions

**During Active Exams:**
- Grant bonus time (1-10 minutes per grant)
- Monitor real-time countdown
- View participant list
- For online exams: Download student submissions after finish

**Limitations:**
- Maximum 3 active (non-finished) exams at once
- Only upcoming exams can be edited or deleted
- Online exams require question paper PDF

#### 4. Exam Entry - Record Results
- Click **"Add Exam"** from dashboard
- Select student, subject, and exam type (CQ/MCQ)
- Enter marks and exam date
- Optionally upload question paper PDF
- **Bulk Entry**: Upload multiple exams via CSV file

#### 5. View Analytics
- Access dashboard for overview
- Check subject-wise performance
- Monitor grade distribution
- Track points and rankings

#### 6. Manage Points
- View student lifetime points
- Track points spent
- Monitor monthly rankings

### For Students

#### 1. Login & Dashboard
- Login with username and password provided by teacher
- View your performance summary on dashboard
- Check your current rankings and points balance

#### 2. Attend Live Exams
- Navigate to **Exam Center**
- Find your scheduled exam by ID or list
- Click **"View Exam"** to see details
- Watch the live countdown timer

**For Online Exams:**
- When status is **Running**: View question paper PDF
- Write your answers on paper/offline
- When status changes to **Submission**: Upload answer sheet
  - Supported formats: PDF, ZIP, RAR
  - Maximum file size: 10 MB
  - Up to 3 submission attempts allowed
- Latest submission is marked as final

**For Offline Exams:**
- Attend the exam in person at the scheduled time
- Timer helps you track time remaining
- No answer submission needed

**Live Timer Features:**
- Automatic countdown to zero
- Page auto-reloads on status change
- Bonus time automatically extends your timer
- Shows elapsed time during exam

#### 3. Access Exam Documents
- Navigate to **Exam Documents**
- Enter the Exam ID to search
- View and download:
  - Question paper PDF
  - Marked answer paper (if uploaded by teacher)

#### 4. Track Performance
- View your exam history
- Check subject-wise analysis
- Monitor your improvement trends
- Compare with class averages

#### 5. Check Rankings
- **Overall Leaderboard**: Ranked by lifetime points
- **Subject Rankings**: Average score per subject
- **Monthly Rankings**: Current month performance
- **Best Students**: Top performer per subject

#### 6. Monitor Points
- View lifetime points earned
- Track points spent on rewards
- Check remaining balance
- See monthly bonus points from #1 ranks

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

## 🏆 Rankings & Leaderboards

### 1. Overall Leaderboard
- Ranked by **lifetime points** (exam + bonus)
- Shows top performers across all subjects
- Updates automatically as new exams are recorded

### 2. Subject Rankings
- Separate ranking for each subject
- Ranked by **average score** in that subject
- Minimum 3 exams required to appear

### 3. Monthly Rankings
- Ranked by **monthly average score**
- Resets at the start of each month
- #1 position earns 40 bonus points
- Eligibility: ≥40% attendance AND ≥3 exams in month

### 4. Best Student per Subject
- Top performer in each subject
- Based on **weighted average** considering exam type
- Displayed on dashboard and leaderboard page

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

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


<div align="center">


</div>
