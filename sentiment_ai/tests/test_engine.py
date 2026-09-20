from django.test import SimpleTestCase

from sentiment_ai.engine import CompanyData, NewsData, analyze_news_for_company


class SentimentEngineTests(SimpleTestCase):
    def setUp(self):
        self.company = CompanyData(
            ticker="PETR4",
            name="Petrobras",
            sector="energy",
            description="Empresa de petroleo, energia e refino.",
        )

    def test_positive_portuguese_news(self):
        result = analyze_news_for_company(
            self.company,
            NewsData(
                title="Petrobras anuncia lucro recorde e aumento de dividendos",
                summary="A empresa apresentou forte crescimento.",
            ),
        )
        self.assertEqual(result.sentiment_label, "positive")

    def test_unrelated_news_is_irrelevant(self):
        result = analyze_news_for_company(
            self.company,
            NewsData(
                title="Empresa de software lança nova plataforma",
                summary="A startup ampliou seus serviços de nuvem.",
            ),
        )
        self.assertEqual(result.sentiment_label, "irrelevant")
