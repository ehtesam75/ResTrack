"""Real-browser check of the workspace UI (desktop + mobile).

Unlike repro_workspace_ui.py (which asserts on rendered markup), this drives an
actual Chromium browser against a live server and asserts the workspace controls
are *visible and clickable*: it opens the switcher by clicking, switches
workspaces by clicking, and walks create/manage/edit/archive/restore/delete.

    pip install playwright && python -m playwright install chromium
    python manage.py test browser_workspace_ui -v 2

Run with --headed by setting HEADED=1 to watch it happen in a real window.
"""
import os

# Playwright's sync API runs its own event loop, and Django's async guard then
# refuses ORM calls from this thread ("SynchronousOnlyOperation"). This is the
# documented escape hatch for exactly this situation, and it is safe here
# because the test itself is single-threaded. Must be set before the ORM is
# touched.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', '1')

from django.contrib.auth.models import User
from django.test import LiveServerTestCase, tag


from marks.models import TeacherProfile, Workspace

PASSWORD = 'pw12345!'
DESKTOP = {'width': 1440, 'height': 900}
MOBILE = {'width': 390, 'height': 844}


class WorkspaceBrowserUITests(LiveServerTestCase):
    """Click through the workspace UI the way a teacher actually would."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from playwright.sync_api import sync_playwright

        cls._pw = sync_playwright().start()
        cls.browser = cls._pw.chromium.launch(headless=not os.environ.get('HEADED'))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pw.stop()
        super().tearDownClass()

    def setUp(self):
        self.teacher = User.objects.create_user(username='browserteacher',
                                                password=PASSWORD)
        TeacherProfile.objects.create(user=self.teacher)
        self.checks = []

    def tearDown(self):
        for line in self.checks:
            print(line)

    # -- helpers ---------------------------------------------------------

    def ok(self, label, condition):
        self.checks.append(f'  [{"PASS" if condition else "FAIL"}] {label}')
        self.assertTrue(condition, label)

    def new_page(self, viewport):
        page = self.browser.new_page(viewport=viewport)
        # Archive/delete may use confirm(); always accept so clicks complete.
        page.on('dialog', lambda d: d.accept())
        return page

    def submit_form_with(self, page, field):
        """Submit the form that owns `field`.

        A bare 'button[type=submit]' also matches the hidden workspace-switch
        buttons in the nav, so scope the click to the form actually being
        filled in.
        """
        page.locator(
            f'form:has(input[name="{field}"]) button[type="submit"], '
            f'form:has(input[name="{field}"]) input[type="submit"]'
        ).first.click()
        page.wait_for_load_state()

    def login(self, page):
        page.goto(f'{self.live_server_url}/login/')
        page.fill('input[name="username"]', self.teacher.username)
        page.fill('input[name="password"]', PASSWORD)
        self.submit_form_with(page, 'password')


    def tailwind_ready(self, page):
        """True when Tailwind actually applied (so .hidden really hides).

        The CDN build is remote; if it did not load, every 'hidden' element
        would look visible and visibility assertions would be meaningless.
        """
        return page.evaluate(
            """() => {
                const d = document.createElement('div');
                d.className = 'hidden';
                document.body.appendChild(d);
                const hidden = getComputedStyle(d).display === 'none';
                d.remove();
                return hidden;
            }"""
        )

    # -- the actual flow -------------------------------------------------

    @tag('browser')
    def test_desktop_teacher_can_discover_and_use_every_workspace_control(self):
        page = self.new_page(DESKTOP)
        self.login(page)
        page.goto(f'{self.live_server_url}/dashboard/')
        styled = self.tailwind_ready(page)
        self.checks.append(f'\n  (Tailwind CDN applied: {styled})')

        toggle = page.locator('[data-ws-switcher-toggle]')
        menu = page.locator('[data-ws-switcher-menu]')

        self.ok('desktop: switcher button is visible', toggle.is_visible())
        self.ok('desktop: switcher button is enabled', toggle.is_enabled())
        self.ok('desktop: active workspace name shown on the button',
                'Default Workspace' in toggle.inner_text())
        if styled:
            self.ok('desktop: menu starts closed', not menu.is_visible())

        # Open by clicking, like a user.
        toggle.click()
        self.ok('desktop: clicking the button opens the menu', menu.is_visible())
        create_link = menu.locator('a[href="/workspaces/create/"]')
        manage_link = menu.locator('a[href="/workspaces/"]')
        self.ok('desktop: "Create workspace" is visible in the menu',
                create_link.is_visible())
        self.ok('desktop: "Manage workspaces" is visible in the menu',
                manage_link.is_visible())

        if styled:
            page.keyboard.press('Escape')
            self.ok('desktop: Escape closes the menu', not menu.is_visible())
            toggle.click()
            page.mouse.click(5, 400)
            self.ok('desktop: clicking outside closes the menu',
                    not menu.is_visible())
            toggle.click()

        # Create a second workspace by clicking through the UI.
        menu.locator('a[href="/workspaces/create/"]').click()
        page.wait_for_load_state()
        self.ok('desktop: create page opened from the menu',
                page.url.endswith('/workspaces/create/'))
        page.fill('input[name="name"]', 'Class 9')
        self.submit_form_with(page, 'name')
        self.ok('desktop: workspace created via the form',

                Workspace.objects.filter(teacher=self.teacher,
                                         name='Class 9').exists())

        ws1 = Workspace.objects.get(teacher=self.teacher, slug_number=1)
        ws2 = Workspace.objects.get(teacher=self.teacher, slug_number=2)
        self.ok('desktop: the new workspace became active',
                'Class 9' in page.locator('[data-ws-switcher-toggle]').inner_text())

        # Switch back to the first workspace by clicking its entry.
        page.locator('[data-ws-switcher-toggle]').click()
        switch_btn = page.locator(
            f'[data-ws-switcher-menu] form[action="/workspaces/{ws1.pk}/switch/"] button')
        self.ok('desktop: the other workspace is listed and clickable',
                switch_btn.is_visible() and switch_btn.is_enabled())
        switch_btn.click()
        page.wait_for_load_state()
        self.ok('desktop: clicking it switched the active workspace',
                'Default Workspace' in
                page.locator('[data-ws-switcher-toggle]').inner_text())

        # Manage page, reached by clicking (not by typing a URL).
        page.locator('[data-ws-switcher-toggle]').click()
        page.locator('[data-ws-switcher-menu] a[href="/workspaces/"]').click()
        page.wait_for_load_state()
        self.ok('desktop: Manage workspaces page opened from the menu',
                page.url.rstrip('/').endswith('/workspaces'))
        self.ok('desktop: Edit control visible on the manage page',
                page.locator(f'a[href="/workspaces/{ws2.pk}/edit/"]').is_visible())
        self.ok('desktop: Archive control visible on the manage page',
                page.locator(
                    f'form[action="/workspaces/{ws2.pk}/archive/"] button').is_visible())
        self.ok('desktop: Delete control visible on the manage page',
                page.locator(f'a[href="/workspaces/{ws2.pk}/delete/"]').is_visible())

        # Edit by clicking.
        page.locator(f'a[href="/workspaces/{ws2.pk}/edit/"]').click()
        page.wait_for_load_state()
        page.fill('input[name="name"]', 'Class 9 - 2026')
        self.submit_form_with(page, 'name')
        ws2.refresh_from_db()

        self.ok('desktop: edit saved the new name', ws2.name == 'Class 9 - 2026')

        # Archive, then restore, by clicking.
        page.locator(f'form[action="/workspaces/{ws2.pk}/archive/"] button').click()
        page.wait_for_load_state()
        ws2.refresh_from_db()
        self.ok('desktop: archive button worked', ws2.is_archived)
        restore = page.locator(f'form[action="/workspaces/{ws2.pk}/restore/"] button')
        self.ok('desktop: Restore control appears for archived workspaces',
                restore.is_visible())
        restore.click()
        page.wait_for_load_state()
        ws2.refresh_from_db()
        self.ok('desktop: restore button worked', not ws2.is_archived)

        # Delete with type-to-confirm.
        page.locator(f'a[href="/workspaces/{ws2.pk}/delete/"]').click()
        page.wait_for_load_state()
        page.fill('input[name="confirm_name"]', ws2.name)
        self.submit_form_with(page, 'confirm_name')
        self.ok('desktop: delete removed the workspace',

                not Workspace.objects.filter(pk=ws2.pk).exists())
        self.ok('desktop: the remaining workspace survived',
                Workspace.objects.filter(pk=ws1.pk).exists())

        if styled:
            self.ok('desktop: mobile-only switcher is not shown at desktop width',
                    not page.locator('[data-ws-mobile-toggle]').is_visible())
        page.close()

    @tag('browser')
    def test_mobile_teacher_can_discover_and_use_the_workspace_switcher(self):
        # Two workspaces so there is something to switch between.
        ws1 = Workspace.objects.create(teacher=self.teacher, name='Default Workspace',
                                       slug_number=1)
        ws2 = Workspace.objects.create(teacher=self.teacher, name='Class 10',
                                       slug_number=2)

        page = self.new_page(MOBILE)
        self.login(page)
        page.goto(f'{self.live_server_url}/dashboard/')
        styled = self.tailwind_ready(page)
        self.checks.append(f'\n  (Tailwind CDN applied: {styled})')

        if styled:
            self.ok('mobile: desktop switcher is not shown at phone width',
                    not page.locator('[data-ws-switcher-toggle]').is_visible())

        hamburger = page.locator('#mobile-menu-button')
        self.ok('mobile: hamburger button is visible', hamburger.is_visible())
        hamburger.click()

        toggle = page.locator('[data-ws-mobile-toggle]')
        menu = page.locator('[data-ws-mobile-menu]')
        self.ok('mobile: workspace switcher is visible in the slide-in menu',
                toggle.is_visible())
        self.ok('mobile: active workspace name shown',
                'Default Workspace' in toggle.inner_text())
        if styled:
            self.ok('mobile: workspace list starts collapsed', not menu.is_visible())

        toggle.click()
        self.ok('mobile: tapping the switcher expands the workspace list',
                menu.is_visible())
        self.ok('mobile: "Create workspace" is visible',
                menu.locator('a[href="/workspaces/create/"]').is_visible())
        self.ok('mobile: "Manage workspaces" is visible',
                menu.locator('a[href="/workspaces/"]').is_visible())

        switch_btn = menu.locator(
            f'form[action="/workspaces/{ws2.pk}/switch/"] button')
        self.ok('mobile: the other workspace is listed and clickable',
                switch_btn.is_visible() and switch_btn.is_enabled())
        switch_btn.click()
        page.wait_for_load_state()

        page.locator('#mobile-menu-button').click()
        self.ok('mobile: tapping a workspace switched the active one',
                'Class 10' in page.locator('[data-ws-mobile-toggle]').inner_text())

        # Manage page is reachable by tapping, at phone width too.
        page.locator('[data-ws-mobile-toggle]').click()
        page.locator('[data-ws-mobile-menu] a[href="/workspaces/"]').click()
        page.wait_for_load_state()
        self.ok('mobile: Manage workspaces opened from the menu',
                page.url.rstrip('/').endswith('/workspaces'))
        # Scope to <main>: the nav also has a create link, but it lives inside
        # the closed slide-in menu and is therefore not visible.
        self.ok('mobile: New workspace button visible on the manage page',
                page.locator('main a[href="/workspaces/create/"]').first.is_visible())
        self.ok('mobile: per-workspace Edit control visible on the manage page',
                page.locator(f'main a[href="/workspaces/{ws1.pk}/edit/"]').is_visible())
        self.ok('mobile: per-workspace Delete control visible on the manage page',
                page.locator(f'main a[href="/workspaces/{ws1.pk}/delete/"]').is_visible())
        page.close()


