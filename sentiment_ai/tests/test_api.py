"""Contratos da API: o que ja existia continua valendo; o que e novo e aditivo."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from feedback.models import Feedback
from news.dto import AnalysisSerializer
from news.models import Analysis, NewsArticle, NewsSource
from portfolios.models import Asset, Portfolio

PUBLISH_TARGET = "sentiment_ai.tasks.process_analysis.apply_async"


class AnalysisContractTests(TestCase):
    """O app mobile le esses campos. Nenhum pode sumir ou mudar de nome."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="api@example.com", username="api", password="x"
        )
        cls.portfolio = Portfolio.objects.create(user=cls.user, name="Carteira")
        cls.asset = Asset.objects.create(
            portfolio=cls.portfolio, ticker="PETR4", name="Petrobras",
            asset_type=Asset.AssetType.STOCK,
        )
        source = NewsSource.objects.create(name="Google News", slug="google_news")
        cls.article = NewsArticle.objects.create(
            source=source,
            title="Petrobras anuncia lucro recorde",
            summary="Resultado acima do esperado.",
            url="https://veiculo.com/api/1",
            published_at=timezone.now(),
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _analysis(self, **kwargs):
        defaults = dict(
            article=self.article,
            ticker="PETR4",
            status=Analysis.Status.COMPLETED,
            model_version="rules-ptbr-3.0.0",
            analise=json.dumps({
                "ticker": "PETR4", "sentiment_label": "positive", "impact_score": 0.6,
                "explanation": "texto", "report": "texto", "language": "pt-BR",
            }),
            language="pt-BR",
            engine="rules-ptbr",
            sentiment_label="positive",
            sentiment_score=0.6,
            relevance_score=0.85,
            report="A noticia foi classificada como positiva para PETR4.",
        )
        defaults.update(kwargs)
        return Analysis.objects.create(**defaults)

    def test_serializer_preserva_os_campos_do_contrato_antigo(self):
        data = AnalysisSerializer(self._analysis()).data
        for campo in (
            'id', 'ticker', 'status', 'result', 'model_version', 'attempts',
            'started_at', 'finished_at', 'created_at', 'updated_at',
            'article_title', 'article_url',
        ):
            self.assertIn(campo, data, campo)

    def test_campos_novos_chegam_ao_cliente_dentro_de_result(self):
        # Nenhuma mudanca foi necessaria no serializer: o JSON completo ja
        # trafega em 'result', entao clientes antigos simplesmente ignoram as
        # chaves novas.
        data = AnalysisSerializer(self._analysis()).data
        self.assertEqual(data['result']['report'], 'texto')
        self.assertEqual(data['result']['language'], 'pt-BR')

    def test_result_nulo_quando_ainda_nao_ha_analise(self):
        data = AnalysisSerializer(
            self._analysis(status=Analysis.Status.PENDING, analise='')
        ).data
        self.assertIsNone(data['result'])

    def test_result_nao_quebra_com_json_corrompido(self):
        data = AnalysisSerializer(self._analysis(analise='{isso nao e json')).data
        self.assertEqual(data['result'], '{isso nao e json')

    def test_listagem_de_analises_da_carteira(self):
        self._analysis()
        url = reverse('portfolio-analyses', kwargs={'portfolio_pk': self.portfolio.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['ticker'], 'PETR4')

    def test_todos_os_status_aparecem_na_listagem(self):
        for index, status in enumerate(Analysis.Status):
            NewsArticle.objects.create(
                source=self.article.source,
                title=f'Noticia {index}',
                summary='',
                url=f'https://veiculo.com/status/{index}',
                published_at=timezone.now(),
            )
        for index, status in enumerate(Analysis.Status):
            self._analysis(
                article=NewsArticle.objects.get(url=f'https://veiculo.com/status/{index}'),
                status=status,
                analise='',
            )
        url = reverse('portfolio-analyses', kwargs={'portfolio_pk': self.portfolio.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {row['status'] for row in response.data},
            {s.value for s in Analysis.Status},
        )

    def test_carteira_de_outro_usuario_retorna_404_sem_vazar_detalhe(self):
        outro = get_user_model().objects.create_user(
            email='outro@example.com', username='outro', password='x'
        )
        alheia = Portfolio.objects.create(user=outro, name='Alheia')
        url = reverse('portfolio-analyses', kwargs={'portfolio_pk': alheia.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data, {'detail': 'Portfolio not found.'})

    def test_analise_sem_ativos_devolve_400_com_mensagem_tratada(self):
        vazia = Portfolio.objects.create(user=self.user, name='Vazia')
        url = reverse('portfolio-analyse', kwargs={'portfolio_pk': vazia.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)

    def test_analise_da_carteira_continua_respondendo_202_com_task_id(self):
        url = reverse('portfolio-analyse', kwargs={'portfolio_pk': self.portfolio.pk})
        with patch('portfolios.tasks.analyse_portfolio.apply_async') as task:
            task.return_value.id = 'task-123'
            response = self.client.post(url)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data, {'task_id': 'task-123', 'status': 'queued'})

    def test_sem_autenticacao_a_listagem_e_negada(self):
        anonimo = APIClient()
        url = reverse('portfolio-analyses', kwargs={'portfolio_pk': self.portfolio.pk})
        self.assertIn(anonimo.get(url).status_code, (401, 403))


class FeedbackApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email='fb@example.com', username='fb', password='x'
        )
        cls.staff = get_user_model().objects.create_user(
            email='staff@example.com', username='staff', password='x', is_staff=True
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_envio_de_feedback(self):
        response = self.client.post(reverse('feedback-create'), {
            'rating': 5,
            'made_sense': 'yes',
            'summary_clear': 'partially',
            'problem': 'O resumo ficou longo.',
            'suggestion': 'Mostrar a fonte da noticia.',
            'app_version': '1.0.0',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Feedback.objects.count(), 1)

    def test_feedback_aceita_campos_opcionais_vazios(self):
        response = self.client.post(reverse('feedback-create'), {'rating': 3}, format='json')
        self.assertEqual(response.status_code, 201)
        registro = Feedback.objects.get()
        self.assertEqual(registro.name, '')
        self.assertEqual(registro.contact, '')

    def test_nota_fora_da_faixa_e_rejeitada(self):
        for nota in (0, 6, 99):
            response = self.client.post(
                reverse('feedback-create'), {'rating': nota}, format='json'
            )
            self.assertEqual(response.status_code, 400, nota)
        self.assertEqual(Feedback.objects.count(), 0)

    def test_nota_obrigatoria(self):
        response = self.client.post(reverse('feedback-create'), {}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_listagem_exige_staff(self):
        self.assertEqual(self.client.get(reverse('feedback-list')).status_code, 403)

    def test_staff_consulta_os_feedbacks(self):
        Feedback.objects.create(rating=4, app_version='1.0.0')
        staff_client = APIClient()
        staff_client.force_authenticate(user=self.staff)
        response = staff_client.get(reverse('feedback-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_feedback_nao_guarda_quem_enviou(self):
        self.client.post(reverse('feedback-create'), {'rating': 5}, format='json')
        campos = {f.name for f in Feedback._meta.get_fields()}
        self.assertNotIn('user', campos)
