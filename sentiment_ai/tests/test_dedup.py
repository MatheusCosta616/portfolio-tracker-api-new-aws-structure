"""Cobertura de deduplicacao, idempotencia e concorrencia (P0)."""

from __future__ import annotations

import json
import threading
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connections, transaction
from django.test import SimpleTestCase, TransactionTestCase
from django.utils import timezone

from news.models import Analysis, NewsArticle, NewsSource
from portfolios.models import Asset, Portfolio
from sentiment_ai.dedup import canonical_url, engine_model_version, news_fingerprint
from sentiment_ai.services import request_analysis

PUBLISH_TARGET = "sentiment_ai.tasks.process_analysis.apply_async"


class CanonicalUrlTests(SimpleTestCase):
    def test_remove_parametros_de_rastreamento(self):
        a = canonical_url("https://veiculo.com/materia?utm_source=rss&utm_medium=feed&id=10")
        b = canonical_url("https://veiculo.com/materia?id=10")
        self.assertEqual(a, b)

    def test_remove_www_barra_final_e_fragmento(self):
        a = canonical_url("https://www.veiculo.com/materia/#topo")
        b = canonical_url("http://veiculo.com/materia")
        self.assertEqual(a, b)

    def test_url_vazia_nao_quebra(self):
        self.assertEqual(canonical_url(""), "")

    def test_paths_diferentes_continuam_diferentes(self):
        self.assertNotEqual(
            canonical_url("https://veiculo.com/a"), canonical_url("https://veiculo.com/b")
        )


class FingerprintTests(SimpleTestCase):
    def test_mesma_materia_com_rastreamento_diferente_tem_a_mesma_impressao(self):
        base = dict(title="Petrobras anuncia lucro recorde", summary="Resultado do trimestre.", source="google_news")
        a = news_fingerprint(url="https://v.com/n1?utm_source=rss", **base)
        b = news_fingerprint(url="https://www.v.com/n1/", **base)
        self.assertEqual(a, b)

    def test_acentuacao_nao_muda_a_impressao(self):
        a = news_fingerprint(title="Ações sobem após balanço", url="https://v.com/x")
        b = news_fingerprint(title="Acoes sobem apos balanco", url="https://v.com/x")
        self.assertEqual(a, b)

    def test_noticias_parecidas_mas_diferentes_nao_colidem(self):
        # Mesmo titulo, veiculos e materias diferentes: continuam separadas.
        a = news_fingerprint(title="Balanco do trimestre", summary="Texto A", url="https://v1.com/n", source="google_news")
        b = news_fingerprint(title="Balanco do trimestre", summary="Texto B", url="https://v2.com/n", source="yfinance")
        self.assertNotEqual(a, b)

    def test_titulo_igual_e_resumo_diferente_nao_colide(self):
        a = news_fingerprint(title="Vale divulga producao", summary="Minerio de ferro subiu.", url="https://v.com/n")
        b = news_fingerprint(title="Vale divulga producao", summary="Minerio de ferro caiu.", url="https://v.com/n")
        self.assertNotEqual(a, b)


class FakeEngine:
    def __init__(self, engine_id: str):
        self.engine_id = engine_id
        self.name = engine_id


class DeduplicationFlowTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="dedup@example.com", username="dedup", password="x"
        )
        self.portfolio = Portfolio.objects.create(user=self.user, name="Carteira")
        self.petr = Asset.objects.create(
            portfolio=self.portfolio, ticker="PETR4", name="Petrobras",
            asset_type=Asset.AssetType.STOCK,
        )
        self.vale = Asset.objects.create(
            portfolio=self.portfolio, ticker="VALE3", name="Vale",
            asset_type=Asset.AssetType.STOCK,
        )
        self.source = NewsSource.objects.create(name="Google News", slug="google_news")
        self.article = NewsArticle.objects.create(
            source=self.source,
            title="Petrobras anuncia lucro recorde e aumento de dividendos",
            summary="A empresa apresentou forte crescimento no trimestre.",
            url="https://veiculo.com/noticia/1",
            published_at=timezone.now(),
        )

    # --- identidade ---------------------------------------------------------
    def test_mesma_noticia_e_mesmo_ticker_retornam_o_mesmo_registro(self):
        with patch(PUBLISH_TARGET):
            primeira = request_analysis(self.article.pk, "PETR4")
            segunda = request_analysis(self.article.pk, "PETR4")
        self.assertEqual(primeira.pk, segunda.pk)
        self.assertEqual(Analysis.objects.count(), 1)

    def test_ticker_em_caixa_diferente_e_o_mesmo_registro(self):
        with patch(PUBLISH_TARGET):
            a = request_analysis(self.article.pk, "petr4")
            b = request_analysis(self.article.pk, "  PETR4 ")
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(Analysis.objects.count(), 1)

    def test_mesma_noticia_com_ticker_diferente_gera_analises_diferentes(self):
        with patch(PUBLISH_TARGET):
            a = request_analysis(self.article.pk, "PETR4")
            b = request_analysis(self.article.pk, "VALE3")
        self.assertNotEqual(a.pk, b.pk)
        self.assertEqual(Analysis.objects.count(), 2)

    def test_nova_versao_do_motor_gera_nova_analise(self):
        with patch(PUBLISH_TARGET):
            antiga = request_analysis(self.article.pk, "PETR4")
            with patch(
                "sentiment_ai.services.select_engine",
                return_value=FakeEngine("rules-ptbr-9.9.9"),
            ):
                nova = request_analysis(self.article.pk, "PETR4")
        self.assertNotEqual(antiga.pk, nova.pk)
        self.assertEqual(Analysis.objects.count(), 2)
        self.assertEqual(nova.model_version, "rules-ptbr-9.9.9")

    def test_ticker_vazio_e_rejeitado(self):
        with self.assertRaises(ValueError):
            request_analysis(self.article.pk, "   ")

    def test_artigo_inexistente_e_rejeitado(self):
        with self.assertRaises(ValueError):
            request_analysis(999999, "PETR4")

    # --- protecao no banco --------------------------------------------------
    def test_o_banco_recusa_duplicata_na_tripla(self):
        with patch(PUBLISH_TARGET):
            existente = request_analysis(self.article.pk, "PETR4")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Analysis.objects.create(
                    article=self.article,
                    ticker="PETR4",
                    model_version=existente.model_version,
                    status=Analysis.Status.PENDING,
                )

    def test_colisao_simultanea_e_tratada_sem_criar_duplicata(self):
        # Simula a corrida: o get_or_create levanta IntegrityError porque outra
        # requisicao inseriu a linha primeiro.
        with patch(PUBLISH_TARGET):
            vencedora = request_analysis(self.article.pk, "PETR4")

        original = Analysis.objects.get_or_create

        def boom(*args, **kwargs):
            raise IntegrityError("unique constraint violated")

        with patch(PUBLISH_TARGET), patch.object(
            Analysis.objects.__class__, "get_or_create", side_effect=boom
        ):
            perdedora = request_analysis(self.article.pk, "PETR4")

        self.assertEqual(perdedora.pk, vencedora.pk)
        self.assertEqual(Analysis.objects.count(), 1)

    def test_duas_requisicoes_simultaneas_nao_criam_duplicatas(self):
        barreira = threading.Barrier(4)
        resultados: list[int] = []
        erros: list[Exception] = []
        trava = threading.Lock()

        def worker():
            try:
                barreira.wait(timeout=10)
                with patch(PUBLISH_TARGET):
                    analysis = request_analysis(self.article.pk, "PETR4")
                with trava:
                    resultados.append(analysis.pk)
            except Exception as exc:  # pragma: no cover - depende do backend
                with trava:
                    erros.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(Analysis.objects.count(), 1, f"erros: {erros}")
        self.assertTrue(resultados, f"nenhuma thread concluiu; erros: {erros}")
        self.assertEqual(len(set(resultados)), 1)

    # --- publicacao na fila -------------------------------------------------
    def test_pendente_ja_enfileirada_nao_e_publicada_de_novo(self):
        with patch(PUBLISH_TARGET) as publisher:
            request_analysis(self.article.pk, "PETR4")
        self.assertEqual(publisher.call_count, 1)

        with patch(PUBLISH_TARGET) as republisher:
            request_analysis(self.article.pk, "PETR4")
        republisher.assert_not_called()

    def test_pendente_nunca_publicada_e_reenfileirada(self):
        with patch(PUBLISH_TARGET):
            analysis = request_analysis(self.article.pk, "PETR4")
        # Simula a queda do broker: a linha ficou pendente sem ter ido para a fila.
        Analysis.objects.filter(pk=analysis.pk).update(queued_at=None)

        with patch(PUBLISH_TARGET) as republisher:
            request_analysis(self.article.pk, "PETR4")
        self.assertEqual(republisher.call_count, 1)

    def test_falha_anterior_e_reenfileirada(self):
        with patch(PUBLISH_TARGET):
            analysis = request_analysis(self.article.pk, "PETR4")
        Analysis.objects.filter(pk=analysis.pk).update(
            status=Analysis.Status.FAILED, last_error="erro antigo"
        )

        with patch(PUBLISH_TARGET) as republisher:
            reenviada = request_analysis(self.article.pk, "PETR4")
        self.assertEqual(republisher.call_count, 1)
        self.assertEqual(reenviada.status, Analysis.Status.PENDING)
        self.assertEqual(reenviada.last_error, "")

    def test_analise_concluida_nao_reprocessa_nem_republica(self):
        with patch(PUBLISH_TARGET):
            analysis = request_analysis(self.article.pk, "PETR4")
        Analysis.objects.filter(pk=analysis.pk).update(
            status=Analysis.Status.COMPLETED, analise=json.dumps({"sentiment_label": "positive"})
        )

        with patch(PUBLISH_TARGET) as republisher:
            reaproveitada = request_analysis(self.article.pk, "PETR4")
        republisher.assert_not_called()
        self.assertEqual(reaproveitada.pk, analysis.pk)
        self.assertEqual(reaproveitada.status, Analysis.Status.COMPLETED)

    def test_materia_repetida_em_outra_url_reaproveita_o_resultado(self):
        with patch(PUBLISH_TARGET):
            original = request_analysis(self.article.pk, "PETR4")
        Analysis.objects.filter(pk=original.pk).update(
            status=Analysis.Status.COMPLETED,
            analise=json.dumps({"sentiment_label": "positive"}),
            sentiment_label="positive",
            report="relatorio original",
        )

        # Mesma materia coletada de novo, com parametro de rastreamento na URL.
        gemea = NewsArticle.objects.create(
            source=self.source,
            title=self.article.title,
            summary=self.article.summary,
            url="https://www.veiculo.com/noticia/1?utm_source=rss",
            published_at=timezone.now(),
        )

        with patch(PUBLISH_TARGET) as publisher:
            reaproveitada = request_analysis(gemea.pk, "PETR4")

        publisher.assert_not_called()
        self.assertEqual(reaproveitada.status, Analysis.Status.COMPLETED)
        self.assertEqual(reaproveitada.report, "relatorio original")
        self.assertNotEqual(reaproveitada.pk, original.pk)

    def test_noticias_diferentes_continuam_sendo_analisadas_separadamente(self):
        outra = NewsArticle.objects.create(
            source=self.source,
            title="Petrobras enfrenta investigacao por fraude",
            summary="A companhia foi alvo de uma acao judicial.",
            url="https://veiculo.com/noticia/2",
            published_at=timezone.now(),
        )
        with patch(PUBLISH_TARGET):
            a = request_analysis(self.article.pk, "PETR4")
            b = request_analysis(outra.pk, "PETR4")
        self.assertNotEqual(a.pk, b.pk)
        self.assertEqual(Analysis.objects.count(), 2)
