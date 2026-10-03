# ResTrack — Multiple Independent Workspaces Per Teacher Account
## Implementation Plan / Specification

> **Status:** Design document — no code written yet. Review and approve before implementation.
> **Author:** Generated from a full read of `models.py`, `views.py` (3,711 lines), `exam_center_views.py`, `services.py`, `signals.py`, `notifications.py`, `middleware.py`, `guest_access.py`, `context_processors.py`, `forms.py`, `urls.py`, `admin.py`.

---

## 0. Executive Summary

Each teacher keeps **one login account** (`User` + `TeacherProfile`). A new `Workspace` model
sits between the teacher and every piece of academic data. All teacher-scoped models gain a
`workspace` FK. The active workspace lives in the **session**, is resolved once per request by
middleware, and is enforced at the **query layer** — not the template layer.

**Key design decision:** we keep the existing `teacher` FK on every model *in addition to* the new
`workspace` FK. This is deliberate:

- Zero-risk migration — existing `filter(teacher=...)` code keeps working during the transition.
- Account deletion (`delete_teacher_account`) keeps working unchanged.
- Defence in depth — a query filtered by `workspace` is *already* teacher-scoped because a
  workspace belongs to exactly one teacher. The redundant `teacher` column is a cheap consistency
  check and lets us write an integrity test asserting `exam.workspace.teacher_id == exam.teacher_id`
  for every row.

The alternative (dropping `teacher` and deriving it via `workspace__teacher`) is cleaner on paper
but requires rewriting ~200 call sites in one irreversible step. Rejected as too risky.

---

## 1. Data Model

### 1.1 New model: `Workspace`

Added to `marks/models.py`, defined **above** `Student` (it is referenced by everything).

```python
class Workspace(models.Model):
    """
    An independent teaching environment belonging to exactly one teacher.
    All academic data (students, subjects, exams, points, files) is scoped to a workspace.
    """
    teacher = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='workspaces',
        help_text="Teacher who owns this workspace",
    )
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True, default='')
    is_archived = models.BooleanField(default=False)
    # Immutable, unique-per-teacher integer used for Cloudinary folder paths.
    # Never reused, never renumbered — renaming a workspace must not orphan files.
    slug_number = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['is_archived', 'created_at']
        constraints = [
            models.UniqueConstraint(fields=['teacher', 'slug_number'],
                                    name='uniq_workspace_slug_per_teacher'),
            models.UniqueConstraint(fields=['teacher', 'name'],
                                    name='uniq_workspace_name_per_teacher'),
        ]
```

**Why `slug_number` and not the PK?** The PK is globally unique, so using it in a Cloudinary path
would leak nothing — but it makes paths unstable across a DB restore/reseed and is opaque when
browsing Cloudinary. A per-teacher counter (`1`, `2`, `3`) produces
`ResTrack/{username}/W1/...` which is human-readable and stable. Critically it is **assigned once
at creation and never changed**, including on rename — so renaming "Class 8" to "Class 8 — 2026"
does not orphan a single uploaded file.

**Counts for the manage page** — computed properties, but the list view will annotate to avoid
N+1:

```python
@property
def student_count(self):   # Student.objects.filter(workspace=self).count()
@property
def subject_count(self):   # Subject.objects.filter(workspace=self).count()
@property
def exam_count(self):      # Exam.objects.filter(workspace=self).values('exam_id').distinct().count()
```

Note `exam_count` uses `.values('exam_id').distinct()` to match the existing
`count_unique_exams()` semantics in `services.py` — a bulk exam counts as one exam.

### 1.2 Models gaining a `workspace` FK

| Model | Field to add | `on_delete` | Notes |
|---|---|---|---|
| `Student` | `workspace` | `CASCADE` | Student belongs to the workspace it was created in |
| `Subject` | `workspace` | `CASCADE` | |
| `ExamType` | `workspace` | `CASCADE` | Setup data — isolated per §12 |
| `Exam` | `workspace` | `CASCADE` | |
| `ExamQuestionPaper` | `workspace` | `CASCADE` | |
| `PointsSpent` | `workspace` | `CASCADE` | |
| `PointTransaction` | `workspace` | `CASCADE` | |
| `ExamCenterExam` | `workspace` | `CASCADE` | |
| `StudentProfile` | *(none)* | — | Reached via `student.workspace`; adding a second source of truth invites drift |

All declared `null=True` initially (required for the migration — see §2), then tightened to
`null=False` in a follow-up migration once backfilled.

`LifetimePoints` and `AnswerSubmission` deliberately get **no** `workspace` field — they are
1:1/N:1 children of `Student` and `ExamCenterExam` respectively and inherit scope through their
parent. Adding a redundant FK creates a second source of truth that can drift.

### 1.3 Constraint changes

**`ExamQuestionPaper.Meta`** — this is a hard blocker for the "both workspaces have Exam #1"
requirement:

```python
# BEFORE
unique_together = ['exam_id', 'teacher']
# AFTER
constraints = [models.UniqueConstraint(fields=['exam_id', 'workspace'],
                                       name='uniq_question_paper_per_workspace')]
```

`ExamNotificationLog.unique_together = ('exam', 'notification_type')` is already correct —
`exam` is an `ExamCenterExam` FK which is itself workspace-scoped.

---

## 2. Migration Strategy

Four migrations, deliberately separated so each is individually reversible and the risky data step
is isolated.

### `0032_add_workspace_model.py` — schema only
Creates the `Workspace` table. Adds nullable `workspace` FK to the 8 models. No data touched.
Safe to deploy and roll back.

### `0033_backfill_default_workspace.py` — data migration
The critical step. Idempotent (safe to re-run) and fully reversible.

```python
def forwards(apps, schema_editor):
    User      = apps.get_model('auth', 'User')
    Workspace = apps.get_model('marks', 'Workspace')
    models_to_backfill = ['Student', 'Subject', 'ExamType', 'Exam',
                          'ExamQuestionPaper', 'PointsSpent',
                          'PointTransaction', 'ExamCenterExam']

    # Every user who owns any teacher-scoped row, or has a TeacherProfile.
    # Using the historical models via apps.get_model is mandatory here.
    teacher_ids = set(
        apps.get_model('marks', 'TeacherProfile').objects.values_list('user_id', flat=True)
    )
    for name in models_to_backfill:
        teacher_ids |= set(
            apps.get_model('marks', name).objects
                .exclude(teacher__isnull=True)
                .values_list('teacher_id', flat=True).distinct()
        )

    for tid in teacher_ids:
        ws, _ = Workspace.objects.get_or_create(
            teacher_id=tid, slug_number=1,
            defaults={'name': 'Default Workspace',
                      'description': 'Your original ResTrack data.'},
        )
        for name in models_to_backfill:
            apps.get_model('marks', name).objects.filter(
                teacher_id=tid, workspace__isnull=True
            ).update(workspace=ws)

def backwards(apps, schema_editor):
    # Null out the FKs and drop the auto-created workspaces.
    ...
```

**Guarantees this provides (requirement §3):**
- Every existing row is assigned to that teacher's `slug_number=1` workspace.
- `get_or_create` + `workspace__isnull=True` makes it re-runnable without duplicating.
- Rows with `teacher=NULL` (legacy data — `teacher` is `null=True` on these models) are swept by a
  final pass that logs them and leaves them orphaned rather than guessing an owner. **These rows
  are invisible to the app after this change**, which is a behaviour change I want explicitly
  signed off — see §11 Open Questions.

### `0034_make_workspace_required.py`
Flips the 8 FKs to `null=False`. Will hard-fail the deploy if `0033` missed anything — which is
exactly what we want, rather than silently shipping orphaned rows.

### `0035_workspace_unique_constraints.py`
Drops `ExamQuestionPaper.unique_together`, adds the per-workspace `UniqueConstraint`.
Sequenced last so it runs against already-backfilled data.

**Deployment note:** `build.sh` runs `migrate` — these apply automatically. On SQLite (local dev)
the constraint swap in `0035` triggers a table rebuild; harmless but slow on large tables.

---

## 3. Active Workspace Resolution (request layer)

### 3.1 New module: `marks/workspaces.py`

Mirrors the structure of the existing `guest_access.py` so it feels native.

```python
ACTIVE_WORKSPACE_SESSION_KEY = 'active_workspace_id'

def get_active_workspace(request):
    """
    Resolve the active workspace for this request, with strict ownership enforcement.
    Cached on the request object. Returns None for students/anonymous.
    """
```

Resolution order:
1. Cached `request._cached_workspace` → return it.
2. Not authenticated, or user is a student → `None`.
3. **Guest session** → the workspace pinned on `GuestTeacherAccount.workspace` (§7).
4. Session key present → fetch `Workspace.objects.get(id=<session>, teacher=request.user,
   is_archived=False)`. **The `teacher=request.user` filter is the security boundary** — a
   tampered session ID resolves to nothing, not to another teacher's workspace.
5. Miss/archived/deleted → fall back to the teacher's oldest active workspace and rewrite the
   session.
6. Teacher has zero active workspaces → auto-create "Default Workspace" (satisfies §9's
   "never leave the teacher in a broken state").

Also provides:
```python
def set_active_workspace(request, workspace)  # validates ownership before writing session
def get_workspace_for_user(user)              # non-request contexts: mgmt commands, cron
def get_student_workspace(user)               # user.student_profile.student.workspace
```

### 3.2 `WorkspaceMiddleware`

Registered in `settings.MIDDLEWARE` **immediately after** `GuestReadOnlyMiddleware` (it must see
`request.guest_account`, which that middleware sets).

Responsibilities:
- Set `request.workspace` once per request.
- Block students from workspace-management URLs (`/workspaces/...`) → 403/redirect, satisfying
  §10 and §19.

Deliberately **not** doing query filtering in middleware — implicit global filtering (a
thread-local "current tenant") is the classic multi-tenancy footgun. Filtering stays explicit and
greppable at the call site.

### 3.3 Context processor

Extend `marks/context_processors.py`:
```python
def workspace_context(request):
    return {
        'active_workspace':     ...,   # for the switcher label
        'available_workspaces': ...,   # active only, for the dropdown
        'show_workspace_switcher': is_teacher and not is_guest,   # §5: students never see it
    }
```
Registered in `settings.TEMPLATES.OPTIONS.context_processors`.

---

## 4. Query Layer — file-by-file changelist

### 4.1 `marks/signals.py` — **Exam ID isolation (§11)**

The single most important change in the whole feature.

```python
# BEFORE (per-teacher numbering)
max_id = Exam.objects.filter(teacher=instance.teacher).aggregate(Max('exam_id'))['exam_id__max']
# AFTER (per-workspace numbering)
max_id = Exam.objects.filter(workspace=instance.workspace).aggregate(Max('exam_id'))['exam_id__max']
```
Same change in the `group_id` branch. Effect: a fresh workspace starts at Exam #1, and two
workspaces holding Exam #1 is valid.

**Race condition:** two concurrent bulk creates in one workspace could both read the same `max_id`.
This race **exists today** at the teacher level — I am not introducing it. Mitigation is a
`select_for_update` on the workspace row inside `add_exam`/`add_bulk_exam`; flagged in §11 as a
recommended follow-up rather than silently changing transaction behaviour here.

### 4.2 `marks/services.py` — **pre-existing cross-teacher leak**

`LeaderboardService`, `DashboardService`, and `ChartDataService` currently query
`Student.objects.all()`, `Subject.objects.all()`, `Exam.objects.all()` with **no teacher filter at
all**. Any view calling these today can surface another teacher's data.

Every method gains a **required** `workspace` parameter (not optional with a `None` default — an
optional filter that defaults to "no filter" is how leaks get reintroduced):

```python
# BEFORE
def total_marks_leaderboard():
    students = Student.objects.all()
# AFTER
def total_marks_leaderboard(workspace):
    students = Student.objects.filter(workspace=workspace)
```

Applies to: `total_marks_leaderboard`, `average_leaderboard`, `subject_wise_leaderboard`,
`exam_type_leaderboard`, `lifetime_points_leaderboard`, `get_dashboard_summary`,
`get_subject_performance_table`, `get_exam_type_performance_table`, `get_grade_distribution`,
`get_recent_exams`, `marks_over_time`, `subject_performance_chart`, `grade_distribution_chart`,
`student_comparison_chart`, `overall_grade_distribution`.

`subject_wise_leaderboard(subject_id)` and friends additionally re-validate the object:
`Subject.objects.get(id=subject_id, workspace=workspace)` — so a tampered `subject_id` in the URL
404s instead of resolving cross-workspace (§19).

This fixes rankings/leaderboards/points/dashboard isolation (§13, §14, §15) at the source, which
is why it is done in `services.py` rather than patched per-view.

### 4.3 `marks/models.py` — model-level ranking helpers

Ranking logic also lives **inside models**, exactly as the task warned. These must be scoped or
the service-layer fix is bypassed:

- `Student.rank` / `overall_rank` → compare only against `Student.objects.filter(workspace=self.workspace)`
- `Student.subject_rank(subject)` → same
- `Subject.best_student()` → `Exam.objects.filter(subject=self, workspace=self.workspace)`
- `Student.recalculate_lifetime_points()` → all internal queries scoped to `self.workspace`
- Monthly-champion / monthly-winner-bonus logic → scoped to workspace

**No formula changes** (§15, §23) — only the candidate set each formula runs over.

`ExamCenterExam.active_exams_for_teacher(teacher)` → `active_exams_for_workspace(workspace)`, and
`can_create_exam(teacher)` → `can_create_exam(workspace)`. Per §16 the 3-exam cap becomes
**per-workspace**, which is the logical reading ("an Exam Center exam created inside Class 8 should
only appear in Class 8").

### 4.4 `marks/views.py` — ~200 call sites

Mechanical transformation, applied consistently:
```python
teacher = request.user                      →   workspace = request.workspace
Exam.objects.filter(teacher=teacher)        →   Exam.objects.filter(workspace=workspace)
get_object_or_404(Exam, pk=x, teacher=t)    →   get_object_or_404(Exam, pk=x, workspace=workspace)
```
On create, stamp **both** fields: `exam.workspace = request.workspace; exam.teacher = request.user`.

Specific views needing more than the mechanical change:
- `dashboard` — pass `workspace` into every `DashboardService` call
- `leaderboard`, `points`, `add_points_spent` — workspace-scoped
- `add_exam`, `add_bulk_exam`, `edit_exam` — duplicate-exam-ID validation must be per-workspace
- `exam_lookup`, `exam_lookup_api`, `exam_info_api`, `exam_id_lookup_api`, `answer_paper_info_api` —
  the `max_exam_id` and lookups all become per-workspace
- `manage_question_paper`, `manage_answer_paper` — per-workspace
- 5 chart APIs — pass workspace through
- **Student-facing paths** — resolve workspace from `student.workspace`, *never* from the session,
  so a student cannot influence their own scope (§10, §19)
- `delete_account` / `delete_teacher_account` — see §8

### 4.5 `marks/notifications.py` — **cross-workspace notification leak (§17)**

Seven functions share this bug:
```python
StudentProfile.objects.filter(created_by=teacher, user__isnull=False)
```
This targets **every student the teacher ever created, across all workspaces**. Without this fix a
Class 8 exam notifies Class 9 students.

```python
StudentProfile.objects.filter(student__workspace=exam_center_exam.workspace,
                              user__isnull=False)
```
Applies to: `notify_exam_created`, `notify_exam_edited`, `notify_exam_reminder_5min`,
`notify_exam_started`, `notify_exam_ending_soon`, `notify_exam_ended`, `notify_bonus_time_granted`.

`notify_result_published(exam_id, student_ids, teacher)` → takes `workspace`; the
`Exam.objects.filter(exam_id=exam_id, teacher=teacher)` metadata lookup becomes workspace-scoped
(otherwise with duplicate exam IDs it can pull the **wrong workspace's subject name**).
`notify_result_edited` is already student-specific — safe, but its `Exam` lookup gets scoped too.

Teacher-facing notifications (`notify_teacher_exam_started` etc.) correctly target
`exam.teacher` — unchanged.

### 4.6 `marks/exam_center_views.py`

`_get_ordered_active_exams(teacher)` / `_get_finished_exams(teacher)` → take `workspace`.
Every `get_object_or_404(ExamCenterExam, pk=..., teacher=...)` → `workspace=...`.
`exam_center_create`'s next-ID computation → per-workspace.
`AnswerSubmission` lookups guarded via `exam__workspace`.

### 4.7 `marks/forms.py`

`ExamCenterExamForm` and the subject-choice form take `workspace` instead of `teacher`:
```python
subjects = Subject.objects.filter(workspace=workspace).order_by('name')
```
This is what makes the "teacher only sees the active workspace's subjects" requirement (§12) real
at the form level — a tampered POST with another workspace's subject ID fails validation.

### 4.8 `marks/management/commands/send_exam_reminders.py`

Iterates exams globally; each exam now resolves its own workspace, and notification helpers are
workspace-scoped, so this is largely automatic. Will be audited for any `created_by=teacher` usage.

---

## 5. Uploaded Files (§18)

Current Cloudinary folder:
```
ResTrack/{username}/Exam Center/Questions/Exam ID {exam_display_id}
```
With per-workspace exam IDs, **Class 8 Exam #1 and Class 9 Exam #1 collide and overwrite each
other.** This is the highest-severity data-loss risk in the whole feature.

New scheme inserts the immutable workspace slug:
```
ResTrack/{username}/W{slug_number}/Exam Center/Questions/Exam ID {exam_display_id}
ResTrack/{username}/W{slug_number}/Exam Center/Answers/Exam ID {exam_display_id}
```

Applies to `ExamCenterExam._question_pdf_folder`, `AnswerSubmission._answer_folder`, and the
`Exam.question_pdf` / `Exam.marked_answer_paper` / `ExamQuestionPaper.question_pdf` folder
callables.

**Existing files are not migrated** (§18: "Do not unnecessarily break or migrate working existing
uploads"). Cloudinary stores the resolved path in the DB column, so old rows keep pointing at their
original location and old links keep working. Only *new* uploads use the new path. Since existing
data all lands in `W1`, and `W1`'s exam IDs are unchanged by the migration, the old and new schemes
don't collide either.

---

## 6. Caching (§20)

Audit found the app-level cache keys are:
- `'grade_color_map'` in `services.py` — global `GradeScale` reference data, **not** teacher-scoped.
  Correctly shared; leave alone.
- `CRON_NO_EXAMS_CACHE_KEY` in `push_views.py` — a global "no active exams anywhere" short-circuit.
  Already invalidated on Exam Center create/edit. Remains global and correct.

**Conclusion: no teacher-scoped cache keys exist today**, so there is no cross-workspace cache-leak
risk to fix. The rule going forward — any future per-teacher cache key must include
`workspace.id` — will be documented as a comment at each cache call site.

---

## 7. Guest Accounts

`GuestTeacherAccount` gains `workspace = FK(Workspace, null=True, on_delete=CASCADE)`. A guest
login is pinned to exactly one workspace and cannot switch (the switcher is hidden and
`set_active_workspace` refuses guest sessions). Backfilled to the teacher's default workspace in
`0033`. `manage_guest_account` gets a workspace selector so the teacher chooses what the guest sees.

---

## 8. Archive & Deletion (§8, §9, §21)

**Archive** — sets `is_archived=True`. Preserves all data. If the archived workspace was active,
the teacher is switched to another active one (never left on an archived workspace). Archiving the
*last* active workspace is refused with a clear message.

**Delete workspace** — 2-step confirmation showing a summary (students / subjects / exams / uploaded
papers), then requires typing the exact workspace name. Because every FK is `CASCADE` **from the
workspace**, `workspace.delete()` removes precisely that workspace's rows and nothing else. Student
`User` accounts are deleted explicitly (mirroring the existing pattern in `delete_teacher_account`,
which already handles this because CASCADE doesn't reach `User`). **Deleting the last remaining
workspace is refused** — safest reading of §9's "do not allow a broken state".

**Full account deletion (§21)** — `delete_teacher_account` keeps working *unchanged*, because we
retained the `teacher` FK on every model. It already filters by `teacher=` and deletes everything
across all workspaces. One line added to delete `Workspace.objects.filter(teacher=teacher)`.
This is the concrete payoff of the dual-FK decision in §0.

---

## 9. UI / UX (§5, §6, §22)

Built with the existing Tailwind + Alpine.js patterns already in `base.html` (the user dropdown
there uses `x-data="{ open: false }"` — the switcher mirrors it exactly).

**Switcher** — in `base.html`, in the existing user dropdown area, rendered only when
`show_workspace_switcher`. Desktop: compact pill showing the active name + chevron. Mobile: a row
in the existing slide-out sidebar. Active workspace marked with a ✓. Footer links: *Create new
workspace* / *Manage workspaces*.

**New templates** (following existing card/table styling):
- `workspace_list.html` — Active and Archived sections, per-card counts + status badge
- `workspace_form.html` — create/edit (name + description only, §7)
- `workspace_confirm_delete.html` — summary + type-to-confirm

**Empty state (§4)** — a `workspace_empty_state.html` partial included by `dashboard.html` when the
workspace has 0 students *and* 0 subjects: "Welcome to {name}" + three CTAs (Add subject → Add
students → Create first exam). Makes an empty workspace feel intentional, not broken.

**New URLs** (teacher-only, enforced in middleware):
```
/workspaces/                      workspace_list
/workspaces/create/               workspace_create
/workspaces/<id>/edit/            workspace_edit
/workspaces/<id>/archive/         workspace_archive     (POST)
/workspaces/<id>/restore/         workspace_restore     (POST)
/workspaces/<id>/delete/          workspace_delete
/workspaces/<id>/switch/          workspace_switch      (POST + CSRF)
```
`switch` is POST-only so a malicious link can't silently change a teacher's active workspace (CSRF).

---

## 10. Test Matrix (§24)

New `marks/tests.py` suite building the exact fixture from the task: **Teacher A** (Workspace A1,
A2) and **Teacher B** (Workspace B1).

| # | Test | Asserts |
|---|---|---|
| 1 | `test_exam_ids_independent` | A1 and A2 can both create Exam #1 |
| 2 | `test_fresh_workspace_is_empty` | New workspace: 0 students/subjects/exams/points |
| 3 | `test_subjects_isolated` | A1 subjects invisible in A2 |
| 4 | `test_students_isolated` | A1 students absent from A2 lists |
| 5 | `test_rankings_isolated` | A2 student never appears in A1 rankings |
| 6 | `test_points_isolated` | Points recalc in A1 unaffected by A2 |
| 7 | `test_dashboard_isolated` | Dashboard counts match active workspace only |
| 8 | `test_exam_center_isolated` | A1 Exam Center exam not visible in A2 |
| 9 | `test_notifications_isolated` | A1 exam notifies only A1 students |
| 10 | `test_teacher_cannot_access_other_teacher` | Teacher A → B1 URLs = 404 |
| 11 | `test_url_tampering_blocked` | Forged `exam_id`/`student_id`/`subject_id` = 404 |
| 12 | `test_session_tampering_blocked` | Forged `active_workspace_id` falls back, no leak |
| 13 | `test_student_cannot_switch` | Student POST to `workspace_switch` = 403 |
| 14 | `test_student_sees_only_own_workspace` | Student scope from `student.workspace`, not session |
| 15 | `test_archive_preserves_data` | Counts identical after archive→restore |
| 16 | `test_delete_a1_preserves_a2` | A2 fully intact after A1 deletion |
| 17 | `test_cannot_delete_last_workspace` | Refused |
| 18 | `test_account_deletion_still_works` | All A workspaces gone, B1 untouched |
| 19 | `test_migration_preserves_data` | Pre-migration rows all land in `slug_number=1` |
| 20 | `test_file_paths_isolated` | A1/A2 Exam #1 resolve to different Cloudinary folders |
| 21 | `test_workspace_teacher_consistency` | `row.workspace.teacher_id == row.teacher_id` for all |

Plus `python manage.py check` and `makemigrations --check --dry-run` (asserts no missing migrations).

---

## 11. Risks & Open Questions

**Needs your decision before implementation:**

1. **Orphaned `teacher=NULL` rows.** `Student.teacher`, `Subject.teacher` etc. are `null=True`, so
   pre-`0010` legacy rows may have no owner. They cannot be assigned to a workspace and become
   invisible to the app. Options: (a) leave orphaned + log, (b) attach to the oldest teacher's
   default workspace, (c) delete. **My recommendation: (a)** — never guess at data ownership.
   *Do you have such rows in production?*

2. **Exam Center 3-exam cap.** Becoming per-workspace means a teacher with 4 workspaces can run 12
   concurrent exams. §16 points this way, but confirm it's acceptable load-wise.

3. **Deleting the last workspace** — I plan to refuse it. Alternative is auto-creating a fresh empty
   one. Confirm.

**Known risks I'll manage during implementation:**

4. **`views.py` is 3,711 lines with ~200 call sites.** A single missed `filter(teacher=...)` is a
   silent cross-workspace leak. Mitigation: after the sweep, grep for any surviving
   `teacher=` in query context and justify each remaining one; test #21 catches consistency drift.

5. **Exam ID race** (§4.1) — pre-existing, documented, `select_for_update` recommended as follow-up.

6. **Migration on large tables** — `0033` uses bulk `.update()` per teacher (not per row), so it's a
   handful of queries per teacher. Fine at expected scale. Take a DB snapshot before deploying.

7. **Cloudinary path change is one-way** for new uploads. Old rows unaffected (§5).

---

## 12. Implementation Order

Each phase independently deployable and testable.

| Phase | Scope | Deployable? |
|---|---|---|
| 1 | `Workspace` model, 8 FKs, migrations `0032`–`0035`, `signals.py` exam IDs | Yes — app behaves identically |
| 2 | `workspaces.py`, middleware, context processor, settings wiring | Yes — resolution active, nothing consumes it |
| 3 | `services.py` + `models.py` ranking/points scoping | Yes — **closes the pre-existing cross-teacher leak** |
| 4 | `views.py` + `exam_center_views.py` + `forms.py` sweep | Yes |
| 5 | `notifications.py` scoping | Yes — closes cross-workspace notification leak |
| 6 | Cloudinary folder paths | Yes |
| 7 | Switcher UI, manage pages, empty states, archive/delete | Yes — feature visible to teachers |
| 8 | Test suite + full verification + final report | — |

Phases 1–2 are the foundation and should land together. Phase 3 is worth prioritising since it
fixes a leak that exists in production **today**, independent of this feature.

---

## Confirmation of the Core Guarantee

Once implemented as specified, data cannot leak across workspaces or teacher accounts because:

1. Every academic row carries a `workspace_id`, and every query filters on it.
2. A `Workspace` belongs to exactly one teacher, so workspace-filtering is inherently
   teacher-filtering.
3. The active workspace is resolved server-side with `teacher=request.user` in the lookup — session
   tampering cannot select another teacher's workspace.
4. Students are scoped from `student.workspace`, never from a client-controllable session value.
5. Object lookups re-validate ownership (`get_object_or_404(..., workspace=request.workspace)`), so
   URL/form/API ID tampering 404s.
6. Uploaded files are namespaced by an immutable per-workspace slug, so identical exam IDs in
   different workspaces cannot collide.
7. Test #21 continuously asserts `row.workspace.teacher_id == row.teacher_id` across all models.
