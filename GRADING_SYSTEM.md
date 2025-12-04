# Grading System Documentation

## Overview
The ResTrack system uses a dual-threshold grading system with different percentage requirements for CQ (Creative Questions) and MCQ (Multiple Choice Questions) exam types.

## Point System

### 1. Superb — **+20 points**
- **CQ marks:** ≥ 85%
- **MCQ marks:** ≥ 93%

### 2. Good — **+15 points**
- **CQ marks:** 70-84.99%
- **MCQ marks:** 77-92.99%

### 3. Average — **0 points**
- **CQ marks:** 50-69.99%
- **MCQ marks:** 55-76.99%

### 4. Poor — **-10 points**
- **CQ marks:** 33-49.99%
- **MCQ marks:** 40-54.99%

### 5. Fail — **-15 points**
- **CQ marks:** 20-32.99%
- **MCQ marks:** 30-39.99%

### 6. Horrible — **-20 points**
- **CQ marks:** < 20%
- **MCQ marks:** < 30%

## Bonus Points

### Monthly Win Bonus — **+40 points per win**
- Students who rank **#1** in any completed month receive a 40-point bonus
- Only fully completed months are counted (current/running month excluded)
- Calculated automatically when recalculating lifetime points
- Multiple monthly wins stack (e.g., 3 monthly wins = 120 bonus points)

## Exam Types

The system only accepts two exam types:
- **CQ** (Creative Questions)
- **MCQ** (Multiple Choice Questions)

These are the only options available in the exam entry forms (both single and bulk entry).

## Implementation Details

### Code Location
- **Point Calculation:** `marks/models.py` → `Exam.points_earned` property
- **Monthly Wins Calculation:** `marks/models.py` → `Student.calculate_monthly_wins()` method
- **Lifetime Points Recalculation:** `marks/models.py` → `Student.recalculate_lifetime_points()` method
- **Grade Display (CQ-based):** `marks/management/commands/setup_grades.py`
- **Excellence Rate:** Counts exams meeting excellence criteria (CQ ≥80%, MCQ ≥85%)
- **Form Dropdowns:** 
  - `marks/templates/marks/add_exam.html`
  - `marks/templates/marks/add_bulk_exam.html`
- **View Logic:**
  - `marks/views.py` → `add_exam()` function
  - `marks/views.py` → `add_bulk_exam()` function

### How It Works
1. When an exam is created, the exam type is stored as "CQ" or "MCQ"
2. The `points_earned` property checks the exam type
3. Based on the exam type, it applies the appropriate percentage thresholds
4. Points are automatically calculated and added to the student's lifetime points
5. Monthly wins are calculated (excluding current month) and each win adds 40 bonus points
6. Total lifetime points = sum of exam points + (monthly wins × 40)
7. Grade names displayed in UI use CQ thresholds (since most exams are CQ-type)

### Excellence Rate
The "Excellence Rate" metric counts exams that meet the following excellence criteria:
- **CQ exams:** ≥80%
- **MCQ exams:** ≥85%

## After Changes

Whenever the grading thresholds are modified in `models.py`, you **MUST** run:

```bash
python manage.py recalculate_all_points
```

This will recalculate all students' lifetime points based on the new thresholds.

## Notes
- MCQ exams have **higher** percentage requirements because they are typically easier
- CQ exams have **lower** percentage requirements due to their subjective nature
- The point values (+20, +15, 0, -10, -15, -20) are the same for both exam types
- Only the percentage thresholds differ between CQ and MCQ
