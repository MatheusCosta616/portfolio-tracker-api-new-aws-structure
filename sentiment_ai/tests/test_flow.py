"""Fluxo completo: signal -> pedido -> fila -> worker -> linha concluida."""

from __future__ import annotations

import json
from unittest.mock import patch

from celery.exceptions import SoftTimeLimitExceeded
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.utils import timezone

from news.models import Analysis, NewsArticle, NewsSource
from portfolios.models import Asset, Portfolio
from sentiment_ai.engine import CompanyData, NewsData
from sentiment_ai.engine.language import EN, PT_BR, SOURCE_STORED, LanguageDecision
from sentiment_ai.engine.portuguese import PortugueseAnalysisEngine
from sentiment_ai.services import request_analysis
from sentiment_ai.tasks import process_analysis

PUBLISH_TARGET = "sentiment_ai.tasks.process_analysis.apply_async"


class CountingEngine:
    """Motor falso que conta quantas vezes foi chamado."""

    name = "fake-engine"
    version = "1.0.0"
    engine_id = "fake-engine-1.0.0"
    language = PT_BR

    def __init__(self, result):
        self._result = result
        self.calls = 0

    def analyze(self, company, news, decision):
        self.calls += 1
        return self._result


class SentimentQueueFlowTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="flow@example.com", username="flow", password="x"
        )
        self.portfolio = Portfolio.objects.create(user=self.user, name="Carteira")
        self.asset = Asset.objects.create(
            portfolio=self.portfolio, ticker="PETR4", name="Petrobras",
            asset_type=Asset.AssetType.STOCK,
        )
        self.google = NewsSource.objects.create(name="Google News", slug="google_news")
        self.yahoo = NewsSource.objects.create(name="Yahoo Finance", slug="yfinance")

    def _article(self, source=None, **kwargs):
        defaults = dict(
            source=source or self.google,
            title="Petrobras anuncia lucro recorde e aumento de dividendos",
            summary="A empresa apresentou forte crescimento no trimestre.",
            url="https://veiculo.com/noticia/1",
            published_at=timezone.now(),
        )
        defaults.update(kwargs)
        return NewsArticle.objects.create(**defaults)

    # --- signal + pedido ----------------------------------------------------
    def test_signal_cria_pedido_e_publica_uma_unica_vez(self):
        article = self._article()
        with patch(PUBLISH_TARGET) as publisher:
            article.tickers.add(self.asset)

        analysis = Analysis.objects.get()
        self.assertEqual(analysis.status, Analysis.Status.PENDING)
        self.assertEqual(analysis.language, PT_BR)
        self.assertIsNotNone(analysis.queued_at)
        publisher.assert_called_once_with(args=(analysis.pk,), queue="sentiment_analysis")

        # Uma nova solicitacao para a mesma linha pendente NAO republica.
        with patch(PUBLISH_TARGET) as republisher:
            mesma = request_analysis(article.pk, "PETR4")
        self.assertEqual(mesma.pk, analysis.pk)
        republisher.assert_not_called()

    # --- worker -------------------------------------------------------------
    def test_worker_conclui_a_mesma_linha_e_grava_o_relatorio(self):
        article = self._article()
        with patch(PUBLISH_TARGET):
            analysis = request_analysis(article.pk, "PETR4")

        process_analysis.apply(args=(analysis.pk,), throw=True)
        analysis.refresh_from_db()

        self.assertEqual(analysis.status, Analysis.Status.COMPLETED)
        self.assertEqual(analysis.attempts, 1)
        self.assertEqual(analysis.language, PT_BR)
        self.assertEqual(analysis.engine, "rules-ptbr")
        self.assertEqual(analysis.sentiment_label, "positive")
        self.assertIsNotNone(analysis.sentiment_score)
        self.assertIsNotNone(analysis.relevance_score)
        self.assertFalse(analysis.llm_used)
        self.assertEqual(analysis.fallback_reason, "")
        self.assertIsNotNone(analysis.finished_at)

        # Relatorio persistido em coluna propria e fundamentado no texto.
        self.assertTrue(analysis.report)
        self.assertIn("PETR4", analysis.report)
        self.assertTrue(any(t in analysis.report.lower() for t in ("lucro", "dividend")))

        # O JSON completo continua no campo 'analise', com o contrato antigo.
        payload = json.loads(analysis.analise)
        self.assertEqual(payload["ticker"], "PETR4")
        self.assertEqual(payload["sentiment_label"], "positive")
        self.assertIn("explanation", payload)
        self.assertIn("report", payload)
        self.assertIn("processing_time_ms", payload)
        self.assertEqual(payload["analysis_id"], analysis.pk)

    def test_noticia_em_portugues_usa_o_motor_de_portugues(self):
        article = self._article(
            title="Vale registra forte queda no lucro do trimestre",
            summary="A mineradora informou recuo na producao de minerio de ferro.",
            url="https://veiculo.com/pt",
        )
        with patch(PUBLISH_TARGET):
            analysis = request_analysis(article.pk, "PETR4")
        process_analysis.apply(args=(analysis.pk,), throw=True)
        analysis.refresh_from_db()
        self.assertEqual(analysis.language, PT_BR)
        self.assertEqual(analysis.engine, "rules-ptbr")

    def test_noticia_em_ingles_usa_o_motor_de_ingles(self):
        article = self._article(
            source=self.yahoo,
            title="Petrobras posts record profit and raises dividend",
            summary="The company reported strong growth in the quarter.",
            url="https://veiculo.com/en",
        )
        with patch(PUBLISH_TARGET):
            analysis = request_analysis(article.pk, "PETR4")
        self.assertEqual(analysis.language, EN)

        process_analysis.apply(args=(analysis.pk,), throw=True)
        analysis.refresh_from_db()
        self.assertEqual(analysis.engine, "rules-en")
        self.assertEqual(analysis.sentiment_label, "positive")

    def test_fonte_declara_o_idioma_e_vence_a_deteccao(self):
        # Titulo em ingles, mas coletado do Google News pt-BR.
        article = self._article(
            title="Petrobras posts record profit",
            summary="",
            url="https://veiculo.com/decl",
        )
        with patch(PUBLISH_TARGET):
            analysis = request_analysis(article.pk, "PETR4")
        self.assertEqual(analysis.language, PT_BR)

    def test_analise_concluida_nao_e_reprocessada(self):
        article = self._article()
        with patch(PUBLISH_TARGET):
            analysis = request_analysis(article.pk, "PETR4")

        process_analysis.apply(args=(analysis.pk,), throw=True)
        analysis.refresh_from_db()
        primeira_conclusao = analysis.finished_at

        resultado = process_analysis.apply(args=(analysis.pk,), throw=True).get()
        analysis.refresh_from_db()

        self.assertEqual(resultado["status"], "already_completed")
        self.assertEqual(analysis.attempts, 1)
        self.assertEqual(analysis.finished_at, primeira_conclusao)

    def test_motor_nao_e_chamado_de_novo_para_analise_concluida(self):
        # Equivale a "nao consultar a LLM outra vez": o motor inteiro nao roda.
        article = self._article()
        with patch(PUBLISH_TARGET):
            analysis = request_analysis(article.pk, "PETR4")

        pronto = PortugueseAnalysisEngine().analyze(
            CompanyData(ticker="PETR4", name="Petrobras"),
            NewsData(title=article.title, summary=article.summary),
            LanguageDecision(PT_BR, SOURCE_STORED, 1.0),
        )
        espiao = CountingEngine(pronto)

        with patch("sentiment_ai.tasks.select_engine", return_value=espiao):
            process_analysis.apply(args=(analysis.pk,), throw=True)
            process_analysis.apply(args=(analysis.pk,), throw=True)

        self.assertEqual(espiao.calls, 1)

    def test_analise_inexistente_nao_quebra_o_worker(self):
        resultado = process_analysis.apply(args=(999999,), throw=True).get()
        self.assertEqual(resultado["status"], "not_found")

    def test_estouro_de_tempo_marca_failed_e_nao_deixa_preso_em_pending(self):
        article = self._article()
        with patch(PUBLISH_TARGET):
            analysis = request_analysis(article.pk, "PETR4")

        class Estourando:
            name = "boom"
            engine_id = "boom-1"

            def analyze(self, *args, **kwargs):
                raise SoftTimeLimitExceeded()

        with patch("sentiment_ai.tasks.select_engine", return_value=Estourando()):
            resultado = process_analysis.apply(args=(analysis.pk,), throw=True).get()

        analysis.refresh_from_db()
        self.assertEqual(resultado["status"], "failed")
        self.assertEqual(analysis.status, Analysis.Status.FAILED)
        self.assertIsNotNone(analysis.finished_at)

    def test_todos_os_status_do_contrato_existem(self):
        self.assertEqual(
            {s.value for s in Analysis.Status},
            {"pending", "processing", "completed", "failed"},
        )


class PortfolioAnalysisPipelineTests(TransactionTestCase):
    """O P0 de verdade: a analise sob demanda passa a receber noticia em pt-BR.

    Antes desta mudanca ``analyse_portfolio`` consultava somente o Yahoo
    Finance, que devolve materia em ingles. O motor nunca via portugues porque
    o pipeline nunca entregava portugues.
    """

    reset_sequences = True

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="pipe@example.com", username="pipe", password="x"
        )
        self.portfolio = Portfolio.objects.create(user=self.user, name="Carteira")
        Asset.objects.create(
            portfolio=self.portfolio, ticker="PETR4", name="Petrobras",
            asset_type=Asset.AssetType.STOCK,
        )

    def test_analise_da_carteira_coleta_das_duas_fontes(self):
        from datetime import timezone as dt_timezone

        from news.fetchers.base import FetchedArticle
        from portfolios.tasks import analyse_portfolio

        agora = timezone.now().astimezone(dt_timezone.utc)

        class FakeFetcher:
            def __init__(self, artigos):
                self._artigos = artigos

            def fetch(self, tickers, asset_types=None):
                return self._artigos

        ingles = FakeFetcher([FetchedArticle(
            title="Petrobras posts record profit and raises dividend",
            url="https://yahoo.com/en/1",
            published_at=agora,
            summary="The company reported strong growth in the quarter.",
            related_tickers=["PETR4"],
        )])
        portugues = FakeFetcher([FetchedArticle(
            title="Petrobras anuncia lucro recorde e aumento de dividendos",
            url="https://google.com/pt/1",
            published_at=agora,
            summary="A empresa apresentou forte crescimento no trimestre.",
            related_tickers=["PETR4"],
        )])

        fontes = [
            ("yfinance", "Yahoo Finance", ingles),
            ("google_news", "Google News", portugues),
        ]

        with patch(PUBLISH_TARGET), patch("portfolios.tasks._analysis_sources", return_value=iter(fontes)):
            resultado = analyse_portfolio.apply(
                args=(self.portfolio.pk, ["PETR4"]), throw=True
            ).get()

        self.assertEqual(resultado["articles_queued"], 2)
        self.assertEqual(NewsArticle.objects.count(), 2)

        idiomas = set(Analysis.objects.values_list("language", flat=True))
        self.assertEqual(idiomas, {PT_BR, EN})

        # A analise em portugues existe e aponta para o motor de portugues.
        for analysis in Analysis.objects.all():
            process_analysis.apply(args=(analysis.pk,), throw=True)

        pt = Analysis.objects.get(language=PT_BR)
        en = Analysis.objects.get(language=EN)
        self.assertEqual(pt.engine, "rules-ptbr")
        self.assertEqual(en.engine, "rules-en")
        self.assertEqual(pt.sentiment_label, "positive")
        self.assertTrue(pt.report)

    def test_fonte_fora_do_ar_nao_derruba_a_analise(self):
        from datetime import timezone as dt_timezone

        from news.fetchers.base import FetchedArticle
        from portfolios.tasks import analyse_portfolio

        class Quebrada:
            def fetch(self, tickers, asset_types=None):
                raise RuntimeError("fonte fora do ar")

        class Boa:
            def fetch(self, tickers, asset_types=None):
                return [FetchedArticle(
                    title="Petrobras anuncia lucro recorde",
                    url="https://google.com/pt/2",
                    published_at=timezone.now().astimezone(dt_timezone.utc),
                    summary="Resultado do trimestre.",
                    related_tickers=["PETR4"],
                )]

        fontes = [
            ("yfinance", "Yahoo Finance", Quebrada()),
            ("google_news", "Google News", Boa()),
        ]

        with patch(PUBLISH_TARGET), patch("portfolios.tasks._analysis_sources", return_value=iter(fontes)):
            resultado = analyse_portfolio.apply(
                args=(self.portfolio.pk, ["PETR4"]), throw=True
            ).get()

        self.assertEqual(resultado["articles_queued"], 1)
        self.assertEqual(Analysis.objects.count(), 1)


class FiiPortugueseNewsTests(TransactionTestCase):
    """Regressao do caso relatado no teste do app: FII com notícia só em pt-BR.

    Sintoma na `main`: a aba de notícias mostrava matéria em português para um
    FII (porque `news/controller.py::_fetch_live` já chamava o GoogleNewsFetcher
    para FII), mas `POST /analyse` devolvia lista vazia — a task de análise só
    consultava o Yahoo Finance, e `MXRF11.SA` não tem notícia lá.

    Este teste usa o GoogleNewsFetcher real, incluindo o parsing do RSS, com a
    chamada HTTP substituída por um XML no formato que o Google devolve de fato:
    `description` em HTML, link com parâmetro de rastreamento e `pubDate` RFC822.
    """

    reset_sequences = True

    RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>MXRF11</title>
<item>
<title>MXRF11 anuncia dividendo de R$ 0,12 por cota e mantem distribuicao mensal - InfoMoney</title>
<link>https://news.google.com/rss/articles/CBMiK2h0dHBz?oc=5&amp;hl=pt-BR</link>
<pubDate>Fri, 19 Sep 2026 12:00:00 GMT</pubDate>
<description>&lt;a href="https://news.google.com/rss/articles/CBMiK2h0dHBz?oc=5"&gt;MXRF11&lt;/a&gt;&amp;nbsp;&lt;font color="#6f6f6f"&gt;InfoMoney&lt;/font&gt;</description>
</item>
<item>
<title>Maxi Renda (MXRF11) registra queda no resultado e cota recua na B3 - Seu Dinheiro</title>
<link>https://news.google.com/rss/articles/CBMiQWh0dHB?oc=5</link>
<pubDate>Thu, 18 Sep 2026 09:30:00 GMT</pubDate>
<description>&lt;a href="https://news.google.com/rss/articles/CBMiQWh0dHB?oc=5"&gt;Maxi Renda&lt;/a&gt;&amp;nbsp;&lt;font color="#6f6f6f"&gt;Seu Dinheiro&lt;/font&gt;</description>
</item>
</channel></rss>"""

    class _FakeResponse:
        status_code = 200

        def __init__(self, content):
            self.content = content

        def raise_for_status(self):
            return None

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="fii@example.com", username="fii", password="x"
        )
        self.portfolio = Portfolio.objects.create(user=self.user, name="FIIs")
        Asset.objects.create(
            portfolio=self.portfolio, ticker="MXRF11", name="Maxi Renda",
            asset_type=Asset.AssetType.FII,
        )

    def _run(self):
        from news.fetchers.yfinance_fetcher import YFinanceFetcher
        from portfolios.tasks import analyse_portfolio

        resposta = self._FakeResponse(self.RSS)
        # O Yahoo Finance nao tem noticia para MXRF11.SA: devolve vazio, que e
        # exatamente o cenario do bug.
        with patch("news.fetchers.google_news_fetcher.requests.get", return_value=resposta), \
             patch.object(YFinanceFetcher, "fetch", return_value=[]), \
             patch(PUBLISH_TARGET):
            return analyse_portfolio.apply(
                args=(self.portfolio.pk, ["MXRF11"]), throw=True
            ).get()

    def test_fii_com_noticia_so_em_portugues_gera_analises(self):
        resultado = self._run()

        self.assertEqual(resultado["articles_queued"], 2)
        self.assertEqual(NewsArticle.objects.count(), 2)
        self.assertEqual(Analysis.objects.count(), 2)
        self.assertEqual(
            set(Analysis.objects.values_list("language", flat=True)), {PT_BR}
        )

    def test_analises_do_fii_concluem_com_rotulo_e_relatorio(self):
        self._run()
        for analysis in Analysis.objects.all():
            process_analysis.apply(args=(analysis.pk,), throw=True)

        analises = list(Analysis.objects.order_by("id"))
        for analysis in analises:
            analysis.refresh_from_db()
            self.assertEqual(analysis.status, Analysis.Status.COMPLETED)
            self.assertEqual(analysis.engine, "rules-ptbr")
            self.assertIn("MXRF11", analysis.report)
            # Relevante: o ticker aparece no titulo, entao nunca pode dar
            # 'irrelevant' e sumir da tela.
            self.assertNotEqual(analysis.sentiment_label, "irrelevant")

        rotulos = {a.sentiment_label for a in analises}
        self.assertIn("positive", rotulos)   # noticia de dividendo
        self.assertIn("negative", rotulos)   # noticia de queda
