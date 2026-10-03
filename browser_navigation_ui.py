"""Real-browser regression coverage for the responsive navigation.

Run with an installed Playwright Chromium browser:
    python manage.py test browser_navigation_ui -v 2

The page's real Tailwind CDN must load; an unstyled page fails these tests.
Optional screenshots: set NAV_SCREENSHOT_DIR to a local output directory.
"""

import os
from pathlib import Path

os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', '1')

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings, tag

from marks.models import Student, StudentProfile, TeacherProfile, Workspace


MOBILE_SIZES = (
    {'width': 320, 'height': 568},
    {'width': 390, 'height': 700},
    {'width': 844, 'height': 390},
)
DESKTOP = {'width': 1440, 'height': 900}


@tag('browser')
@override_settings(DEBUG=True)
class NavigationBrowserUITests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from playwright.sync_api import sync_playwright

        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        cls.browser = cls.playwright.chromium.launch(headless=True)
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.teacher = User.objects.create_user(username='navteacher', first_name='Teacher')
        TeacherProfile.objects.create(user=self.teacher)
        self.workspace = Workspace.objects.create(
            teacher=self.teacher, name='Class 9', slug_number=1,
        )
        self.other_workspace = Workspace.objects.create(
            teacher=self.teacher, name='Class 10', slug_number=2,
        )
        self.student_user = User.objects.create_user(username='navstudent')
        student = Student.objects.create(
            first_name='Student', teacher=self.teacher, workspace=self.workspace,
        )
        StudentProfile.objects.create(
            user=self.student_user, student=student, created_by=self.teacher,
        )

    def new_page(self, user=None, viewport=None):
        # Cache/update behavior is covered separately; this suite isolates the UI.
        context = self.browser.new_context(
            viewport=viewport or MOBILE_SIZES[1], service_workers='block',
            has_touch=True,
        )
        self.addCleanup(context.close)
        if user is not None:
            self.client.force_login(user)
            context.add_cookies([{
                'name': settings.SESSION_COOKIE_NAME,
                'value': self.client.cookies[settings.SESSION_COOKIE_NAME].value,
                'url': self.live_server_url,
            }])
            self.client.cookies.clear()
        page = context.new_page()
        page.set_default_timeout(15000)
        return page

    def ready(self, page):
        # Do not silently accept CDN failures: visibility needs actual styles.
        page.wait_for_function("""() => {
            const probe = document.createElement('div');
            probe.className = 'hidden';
            document.body.append(probe);
            const styled = getComputedStyle(probe).display === 'none';
            probe.remove();
            return styled;
        }""")

    def open_menu(self, page):
        from playwright.sync_api import expect

        page.locator('#mobile-menu-button').click()
        expect(page.locator('#mobile-menu')).to_have_class('mobile-menu-panel open')
        expect(page.locator('#mobile-menu-button')).to_have_attribute('aria-expanded', 'true')
        page.wait_for_function("""() => {
            const box = document.querySelector('#mobile-menu').getBoundingClientRect();
            return Math.abs(box.right - innerWidth) < 2;
        }""")

    def screenshot(self, page, filename):
        output = os.environ.get('NAV_SCREENSHOT_DIR')
        if output:
            directory = Path(output)
            directory.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(directory / filename))

    def assert_column_layout(self, page):
        boxes = page.evaluate("""() => {
            const rect = selector => {
                const box = document.querySelector(selector).getBoundingClientRect();
                return {x: box.x, y: box.y, width: box.width, height: box.height,
                        bottom: box.bottom};
            };
            return {panel: rect('#mobile-menu'), header: rect('#mobile-menu-header'),
                    content: rect('.mobile-menu-content'), viewport: innerHeight};
        }""")
        self.assertAlmostEqual(boxes['header']['x'], boxes['content']['x'], delta=1)
        self.assertAlmostEqual(boxes['header']['width'], boxes['content']['width'], delta=1)
        self.assertGreaterEqual(boxes['content']['y'], boxes['header']['bottom'] - 1)
        self.assertGreater(boxes['content']['height'], 0)
        self.assertLessEqual(boxes['panel']['bottom'], boxes['viewport'] + 1)
        self.assertLessEqual(boxes['content']['bottom'], boxes['viewport'] + 1)

    def test_teacher_student_and_public_links_remain_reachable_at_mobile_sizes(self):
        from playwright.sync_api import expect

        for role, user, last_href in (
            ('teacher', self.teacher, '/logout/'),
            ('student', self.student_user, '/logout/'),
            ('public', None, '/signup/'),
        ):
            page = self.new_page(user)
            for viewport in MOBILE_SIZES:
                with self.subTest(role=role, viewport=viewport):
                    page.set_viewport_size(viewport)
                    page.goto(f'{self.live_server_url}/dashboard/' if user else f'{self.live_server_url}/guide/')
                    self.ready(page)
                    self.open_menu(page)
                    self.assert_column_layout(page)
                    content = page.locator('.mobile-menu-content')
                    top_header = page.locator('#mobile-menu-header').bounding_box()
                    capture = role == 'teacher' and viewport == MOBILE_SIZES[1]
                    if capture:
                        self.screenshot(page, 'teacher-390x700-top.png')

                    # Real input must scroll the drawer, not the page beneath it.
                    content.hover()
                    page.mouse.wheel(0, 5000)
                    page.wait_for_function("""() => {
                        const el = document.querySelector('.mobile-menu-content');
                        return el.scrollTop + el.clientHeight >= el.scrollHeight - 2;
                    }""")
                    last_link = content.locator(f'a[href="{last_href}"]')
                    expect(last_link).to_be_in_viewport(ratio=1)
                    last_link.click(trial=True)
                    self.assertAlmostEqual(
                        page.locator('#mobile-menu-header').bounding_box()['y'],
                        top_header['y'], delta=1,
                    )
                    self.assertFalse(content.evaluate('el => el.scrollWidth > el.clientWidth'))
                    if capture:
                        self.screenshot(page, 'teacher-390x700-bottom.png')

                    # Every top-level item, including the final account actions,
                    # must be reachable without being covered by the header.
                    for link in content.locator(':scope > a').all():
                        link.scroll_into_view_if_needed()
                        expect(link).to_be_in_viewport(ratio=1)
                        link.click(trial=True)
                    page.locator('#mobile-menu-close').click()
                    expect(page.locator('#mobile-menu-button')).to_have_attribute('aria-expanded', 'false')

            # Verify a real bottom-link navigation, beyond geometric assertions.
            self.open_menu(page)
            with page.expect_navigation(wait_until='domcontentloaded'):
                page.locator(f'.mobile-menu-content a[href="{last_href}"]').click()
            self.assertTrue(page.url.endswith('/signup/') if user is None else not page.url.endswith('/dashboard/'))
            page.close()

    def test_workspace_switch_and_manage_links_work_inside_the_scrolling_drawer(self):
        from playwright.sync_api import expect

        page = self.new_page(self.teacher)
        page.goto(f'{self.live_server_url}/dashboard/')
        self.ready(page)
        self.open_menu(page)
        page.locator('[data-ws-mobile-toggle]').click()
        switch = page.locator(
            f'[data-ws-mobile-menu] form[action="/workspaces/{self.other_workspace.pk}/switch/"] button'
        )
        with page.expect_navigation(wait_until='domcontentloaded'):
            switch.click()
        self.ready(page)
        self.open_menu(page)
        expect(page.locator('[data-ws-mobile-toggle]')).to_contain_text('Class 10')
        page.locator('[data-ws-mobile-toggle]').click()
        with page.expect_navigation(wait_until='domcontentloaded'):
            page.locator('[data-ws-mobile-menu] a[href="/workspaces/"]').click()
        self.assertTrue(page.url.endswith('/workspaces/'))

    def test_close_restores_scroll_keyboard_focus_and_desktop_navigation(self):
        from playwright.sync_api import expect

        page = self.new_page(self.teacher)
        page.goto(f'{self.live_server_url}/guide/')
        self.ready(page)
        page.evaluate('window.scrollTo({top: 350, behavior: "instant"})')
        initial_scroll = page.evaluate('window.scrollY')
        self.assertGreater(initial_scroll, 0)

        self.open_menu(page)
        self.assertEqual(page.evaluate('getComputedStyle(document.body).position'), 'fixed')
        page.keyboard.press('Escape')
        expect(page.locator('#mobile-menu-button')).to_have_attribute('aria-expanded', 'false')
        expect(page.locator('#mobile-menu-button')).to_be_focused()
        self.assertAlmostEqual(page.evaluate('window.scrollY'), initial_scroll, delta=1)

        self.open_menu(page)
        page.locator('#mobile-menu-overlay').click(position={'x': 5, 'y': 100})
        expect(page.locator('#mobile-menu-button')).to_have_attribute('aria-expanded', 'false')
        self.assertAlmostEqual(page.evaluate('window.scrollY'), initial_scroll, delta=1)

        self.open_menu(page)
        page.set_viewport_size(DESKTOP)
        expect(page.locator('#mobile-menu')).to_be_hidden()
        expect(page.locator('#mobile-menu-overlay')).to_be_hidden()
        expect(page.locator('#mobile-menu-button')).to_have_attribute('aria-expanded', 'false')
        self.assertNotEqual(page.evaluate('getComputedStyle(document.body).position'), 'fixed')
        page.evaluate('window.scrollTo({top: 0, behavior: "instant"})')
        desktop_link = page.locator('nav a[href="/students/"]')
        expect(desktop_link).to_be_visible()
        desktop_link.click(trial=True)
        self.screenshot(page, 'desktop-1440x900.png')

        page.set_viewport_size(MOBILE_SIZES[0])
        expect(page.locator('#mobile-menu-button')).to_be_visible()
        expect(page.locator('#mobile-menu-overlay')).to_be_hidden()
        self.open_menu(page)
        self.assert_column_layout(page)
        page.locator('#mobile-menu-close').click()
        self.assertNotEqual(page.evaluate('getComputedStyle(document.body).position'), 'fixed')
