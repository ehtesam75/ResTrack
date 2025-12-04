# 🚀 QUICK START GUIDE

## Get Started in 30 Seconds

### Step 1: Start the Server
```bash
cd D:\Code-repos\ResTrack
python manage.py runserver
```

### Step 2: Open Your Browser
Visit: **http://127.0.0.1:8000/**

### Step 3: Explore!
- 📊 **Dashboard**: See all analytics and charts
- 👥 **Students**: View student profiles
- 📚 **Subjects**: Analyze subject performance
- ➕ **Add Exam**: Record new exam results

---

## 🔑 Admin Access
URL: **http://127.0.0.1:8000/admin/**
- Username: `admin`
- Password: `admin`

---

## 📝 Quick Actions

### Add a New Student
1. Click "Students" in navigation
2. Click "+ Add Student"
3. Fill in name (required), roll & class (optional)
4. Click "Add Student"

### Record an Exam
1. Click "Add Exam" in navigation
2. Select student, subject, exam type
3. Enter date, marks (total & obtained)
4. Click "Add Exam"

### View Analytics
1. Go to Dashboard
2. See leaderboards, charts, and stats
3. Click on any student/subject for details

---

## 🎯 Sample Data Included

The system comes pre-loaded with:
- ✅ 5 students
- ✅ 5 subjects (Math, Physics, Chemistry, Biology, English)
- ✅ 4 exam types (MCQ, Creative, Direct, CQ)
- ✅ 95 sample exams
- ✅ Grade scales configured

---

## 🛠️ Management Commands

```bash
# Reset and reload sample data
python manage.py load_sample_data

# Setup grade scales
python manage.py setup_grades

# Create admin user
python manage.py create_admin
```

---

## 📊 What You'll See

### Dashboard Features
- 📈 Total exams, subjects, students
- 🏆 Top performers leaderboards
- 📊 Grade distribution chart
- 📉 Subject performance chart
- 🕒 Recent exams table

### Student Profile Features
- 🎯 Rank & statistics
- 💎 Lifetime points
- 📈 Marks over time (line chart)
- 🎯 Subject performance (radar chart)
- 🥧 Grade distribution (pie chart)
- 📋 Subject-wise & exam-type summaries

### Subject Page Features
- 📊 Average performance
- 🎯 Difficulty level
- 🏆 Best student
- 📈 Student comparison chart

---

## 🎨 Color Coding

Grades are color-coded for easy identification:
- 🟢 **Superb** (CQ ≥85% / MCQ ≥93%): Green
- 🔵 **Good** (CQ 70-84.99% / MCQ 77-92.99%): Blue
- 🟡 **Average** (60-74%): Yellow
- 🟠 **Poor** (40-59%): Orange
- 🔴 **Fail** (0-39%): Red

---

## 💡 Pro Tips

1. **Use the admin panel** for bulk operations
2. **Check leaderboards** to motivate students
3. **Analyze subject difficulty** to adjust teaching
4. **Track marks over time** to see progress
5. **Use lifetime points** as a reward system

---

## 🆘 Troubleshooting

**Server won't start?**
- Make sure you're in the ResTrack directory
- Check if Python is installed: `python --version`

**Database errors?**
- Run: `python manage.py migrate`

**No data showing?**
- Run: `python manage.py load_sample_data`

**Forgot admin password?**
- Run: `python manage.py create_admin` (resets to admin/admin)

---

## 📱 Mobile Friendly

The application is fully responsive and works great on:
- 💻 Desktop
- 📱 Tablet
- 📱 Mobile phones

---

## 🎓 Perfect For

- Teachers tracking student performance
- Students monitoring their progress
- Tutors analyzing exam results
- Schools managing marks data
- Parents viewing student performance

---

**Ready to get started? Run `python manage.py runserver` and visit http://127.0.0.1:8000/**

**Enjoy! 🎉**
