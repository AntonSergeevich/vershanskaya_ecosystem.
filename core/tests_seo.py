"""robots.txt и карта сайта."""
from django.test import TestCase, override_settings

from core.models import LegalPage
from lms.models import Course
from quiz.models import Quiz


class RobotsTests(TestCase):
    def test_it_is_plain_text(self):
        response = self.client.get('/robots.txt')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/plain'))

    @override_settings(ALLOWED_HOSTS=['vershanskaya.ru'])
    def test_the_domain_is_not_hardcoded(self):
        """Захардкоженный домен уезжает на прод с тестового сервера."""
        response = self.client.get('/robots.txt', HTTP_HOST='vershanskaya.ru')
        body = response.content.decode()

        self.assertIn('Host: vershanskaya.ru', body)
        self.assertIn('Sitemap: http://vershanskaya.ru/sitemap.xml', body)

    def test_private_sections_are_closed(self):
        body = self.client.get('/robots.txt').content.decode()
        for path in ('/admin/', '/voronka/', '/obuchenie/video/', '/oplata/'):
            self.assertIn(f'Disallow: {path}', body)


class SitemapTests(TestCase):
    def setUp(self):
        Quiz.objects.create(title='Архетипы', slug='arhetipy', is_published=True)
        Course.objects.create(title='Первые шаги', slug='pervye-shagi', description='')
        Course.objects.create(title='Черновик', slug='chernovik', description='',
                              is_published=False)

    def body(self):
        return self.client.get('/sitemap.xml').content.decode()

    def test_it_is_valid_xml_with_the_public_pages(self):
        response = self.client.get('/sitemap.xml')

        self.assertEqual(response.status_code, 200)
        self.assertIn('xml', response['Content-Type'])
        self.assertIn('<loc>http://testserver/</loc>', response.content.decode())

    def test_all_six_archetypes_are_listed(self):
        body = self.body()
        for code in ('seeker', 'creator', 'sage', 'ruler', 'lover', 'hero'):
            self.assertIn(f'/kviz/arhetip/{code}/', body)

    def test_a_draft_course_is_not_promised(self):
        """Страницы черновика нет — обещать её поисковику нечестно."""
        body = self.body()
        self.assertIn('/obuchenie/kursy/pervye-shagi/', body)
        self.assertNotIn('/obuchenie/kursy/chernovik/', body)

    def test_an_unpublished_document_is_not_promised(self):
        LegalPage.objects.create(title='Оферта', slug='oferta', body='...',
                                 is_published=False)
        self.assertNotIn('/dokumenty/oferta/', self.body())

    def test_nothing_in_the_map_is_closed_in_robots(self):
        """Карта и robots.txt не должны противоречить друг другу."""
        import re

        closed = re.findall(r'Disallow: (\S+)',
                            self.client.get('/robots.txt').content.decode())
        listed = re.findall(r'<loc>http://testserver(\S*?)</loc>', self.body())

        for url in listed:
            for prefix in closed:
                self.assertFalse(url.startswith(prefix),
                                 f"{url} обещан в карте, но закрыт правилом {prefix}")

    def test_every_listed_address_really_opens(self):
        """Ссылка из карты, ведущая в 404, роняет доверие к сайту у поисковика."""
        import re

        for url in re.findall(r'<loc>http://testserver(\S*?)</loc>', self.body()):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
