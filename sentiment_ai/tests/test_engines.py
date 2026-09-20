"""Cobertura dos motores de analise, do relatorio e da integracao com LLM."""

from django.test import SimpleTestCase, override_settings

from sentiment_ai.engine import CompanyData, NewsData, analyze_news_for_company
from sentiment_ai.engine.english import EnglishAnalysisEngine
from sentiment_ai.engine.heuristic import lexical_score
from sentiment_ai.engine.language import EN, PT_BR, SOURCE_DECLARED, LanguageDecision
from sentiment_ai.engine.lexicons import en as en_lex
from sentiment_ai.engine.lexicons import pt_br as pt_lex
from sentiment_ai.engine.llm_engine import LlmAnalysisEngine
from sentiment_ai.engine.portuguese import PortugueseAnalysisEngine
from sentiment_ai.engine.selector import local_engine_for, select_engine
from sentiment_ai.llm import get_provider, load_config
from sentiment_ai.llm.base import (
    LlmAnalysis,
    LlmAuthError,
    LlmInvalidResponse,
    LlmProvider,
    LlmRateLimited,
    LlmRequest,
    LlmTimeout,
    LlmUnavailable,
)
from sentiment_ai.llm.config import LlmConfig
from sentiment_ai.llm.prompt import parse_response
from sentiment_ai.llm.providers import NullProvider

PETRO = CompanyData(
    ticker="PETR4",
    name="Petrobras",
    sector="energy",
    description="Empresa de petroleo, energia e refino.",
    aliases=("PETR4",),
)

PT_DECISION = LanguageDecision(PT_BR, SOURCE_DECLARED, 1.0)
EN_DECISION = LanguageDecision(EN, SOURCE_DECLARED, 1.0)


def _config(**overrides) -> LlmConfig:
    base = dict(
        enabled=True, provider="fake", model="modelo-teste", api_key="chave-de-teste",
        base_url="", timeout_seconds=5, max_retries=0, languages=(PT_BR,),
    )
    base.update(overrides)
    return LlmConfig(**base)


class StubProvider(LlmProvider):
    """Provedor falso: nenhum teste toca a rede."""

    name = "fake"

    def __init__(self, result: LlmAnalysis | None = None, error: Exception | None = None):
        self._result = result
        self._error = error
        self.calls = 0

    @property
    def enabled(self) -> bool:
        return True

    def analyze_news(self, request: LlmRequest) -> LlmAnalysis:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._result


# ---------------------------------------------------------------------------
# Selecao de motor
# ---------------------------------------------------------------------------
class EngineSelectionTests(SimpleTestCase):
    def test_portugues_usa_o_motor_novo(self):
        self.assertIsInstance(local_engine_for(PT_BR), PortugueseAnalysisEngine)

    def test_ingles_continua_no_motor_atual_com_vader(self):
        engine = local_engine_for(EN)
        self.assertIsInstance(engine, EnglishAnalysisEngine)
        self.assertTrue(engine.use_vader)

    def test_motor_portugues_nao_usa_vader(self):
        self.assertFalse(PortugueseAnalysisEngine().use_vader)

    def test_idioma_desconhecido_cai_no_motor_padrao(self):
        self.assertIsInstance(local_engine_for("klingon"), PortugueseAnalysisEngine)

    @override_settings(LLM_ENABLED=False)
    def test_llm_desabilitada_devolve_motor_local(self):
        self.assertIsInstance(select_engine(PT_BR), PortugueseAnalysisEngine)

    @override_settings(LLM_ENABLED=False)
    def test_provedor_desabilitado_e_o_null_provider(self):
        provider = get_provider(load_config())
        self.assertIsInstance(provider, NullProvider)
        self.assertFalse(provider.enabled)

    @override_settings(
        LLM_ENABLED=True, LLM_PROVIDER="anthropic", LLM_MODEL="",
        LLM_API_KEY="x", LLM_LANGUAGES=(PT_BR,),
    )
    def test_configuracao_incompleta_nao_liga_a_llm(self):
        # Sem modelo definido a configuracao nao e utilizavel.
        self.assertIsInstance(select_engine(PT_BR), PortugueseAnalysisEngine)


# ---------------------------------------------------------------------------
# Isolamento de lexico
# ---------------------------------------------------------------------------
class LexiconIsolationTests(SimpleTestCase):
    def test_lexico_portugues_ignora_termos_em_ingles(self):
        self.assertEqual(lexical_score("record profit and strong growth", pt_lex).score, 0.0)

    def test_lexico_ingles_ignora_termos_em_portugues(self):
        self.assertEqual(lexical_score("lucro recorde e forte crescimento", en_lex).score, 0.0)

    def test_negacao_inverte_a_polaridade(self):
        outcome = lexical_score("a empresa nao registrou prejuizo no trimestre", pt_lex)
        self.assertGreater(outcome.score, 0.0)
        self.assertIn("prejuizo", outcome.negated)

    def test_intensificador_amplia_o_peso(self):
        forte = lexical_score("forte crescimento", pt_lex).score
        leve = lexical_score("leve crescimento", pt_lex).score
        self.assertGreater(forte, leve)


# ---------------------------------------------------------------------------
# Analise local
# ---------------------------------------------------------------------------
class PortugueseAnalysisTests(SimpleTestCase):
    def setUp(self):
        self.engine = PortugueseAnalysisEngine()

    def test_noticia_positiva_em_portugues(self):
        result = self.engine.analyze(
            PETRO,
            NewsData(
                title="Petrobras anuncia lucro recorde e aumento de dividendos",
                summary="A empresa apresentou forte crescimento no trimestre.",
            ),
            PT_DECISION,
        )
        self.assertEqual(result.sentiment_label, "positive")
        self.assertEqual(result.language, PT_BR)
        self.assertEqual(result.engine, "rules-ptbr")
        self.assertFalse(result.llm_used)

    def test_noticia_negativa_em_portugues(self):
        result = self.engine.analyze(
            PETRO,
            NewsData(
                title="Petrobras registra prejuizo e acoes despencam",
                summary="A companhia divulgou forte queda no resultado do trimestre.",
            ),
            PT_DECISION,
        )
        self.assertEqual(result.sentiment_label, "negative")

    def test_juros_sobre_capital_proprio_nao_e_negativo(self):
        # Regressao: "juros" estava no lexico negativo e derrubava a nota de
        # uma noticia de provento, que e positiva.
        result = self.engine.analyze(
            PETRO,
            NewsData(
                title="Petrobras aprova pagamento de juros sobre capital próprio",
                summary="O provento sera distribuido aos acionistas no proximo mes.",
            ),
            PT_DECISION,
        )
        self.assertEqual(result.sentiment_label, "positive")

    def test_negacao_no_titulo_nao_vira_noticia_negativa(self):
        result = self.engine.analyze(
            PETRO,
            NewsData(title="Petrobras nao registrou prejuizo no trimestre", summary=""),
            PT_DECISION,
        )
        self.assertNotEqual(result.sentiment_label, "negative")

    def test_noticia_sem_relacao_e_irrelevante(self):
        result = self.engine.analyze(
            PETRO,
            NewsData(
                title="Empresa de software lanca nova plataforma",
                summary="A startup ampliou seus servicos de nuvem.",
            ),
            PT_DECISION,
        )
        self.assertEqual(result.sentiment_label, "irrelevant")

    def test_score_permanece_na_faixa_valida(self):
        for title in (
            "Petrobras lucro recorde crescimento alta dividendos ganhos supera valorizacao",
            "Petrobras prejuizo crise fraude colapso falencia rombo queda perdas escandalo",
        ):
            result = self.engine.analyze(PETRO, NewsData(title=title), PT_DECISION)
            self.assertGreaterEqual(result.impact_score, -1.0)
            self.assertLessEqual(result.impact_score, 1.0)
            self.assertGreaterEqual(result.relevance_score, 0.0)
            self.assertLessEqual(result.relevance_score, 1.0)
            self.assertGreaterEqual(result.confidence, 0.0)
            self.assertLessEqual(result.confidence, 1.0)

    def test_texto_vazio_nao_quebra(self):
        result = self.engine.analyze(PETRO, NewsData(title="", summary=""), PT_DECISION)
        self.assertIn(result.sentiment_label, ("irrelevant", "neutral"))


class EnglishAnalysisTests(SimpleTestCase):
    def setUp(self):
        self.engine = EnglishAnalysisEngine()

    def test_noticia_em_ingles_continua_funcionando(self):
        result = self.engine.analyze(
            PETRO,
            NewsData(
                title="Petrobras posts record profit and raises dividend",
                summary="The company reported strong growth in the quarter.",
            ),
            EN_DECISION,
        )
        self.assertEqual(result.sentiment_label, "positive")
        self.assertEqual(result.engine, "rules-en")
        self.assertEqual(result.language, EN)

    def test_noticia_negativa_em_ingles(self):
        result = self.engine.analyze(
            PETRO,
            NewsData(
                title="Petrobras shares plunge after fraud investigation",
                summary="The company faces a lawsuit and weak quarterly results.",
            ),
            EN_DECISION,
        )
        self.assertEqual(result.sentiment_label, "negative")


class ReportTests(SimpleTestCase):
    def test_relatorio_cita_elementos_da_noticia(self):
        result = PortugueseAnalysisEngine().analyze(
            PETRO,
            NewsData(
                title="Petrobras anuncia lucro recorde e aumento de dividendos",
                summary="A empresa apresentou forte crescimento no trimestre.",
            ),
            PT_DECISION,
        )
        self.assertTrue(result.report)
        self.assertIn("PETR4", result.report)
        self.assertIn("positiva", result.report)
        self.assertIn("relevancia", result.report.lower())
        # Fundamentado no texto, nao generico.
        self.assertTrue(any(t in result.report.lower() for t in ("lucro", "dividend")))
        self.assertNotIn("A IA analisou", result.report)

    def test_relatorio_de_irrelevante_explica_o_motivo(self):
        result = PortugueseAnalysisEngine().analyze(
            PETRO,
            NewsData(title="Novo aplicativo de receitas chega ao mercado"),
            PT_DECISION,
        )
        self.assertIn("nao foi considerada relevante", result.report)

    def test_explanation_recebe_o_mesmo_texto_do_relatorio(self):
        # O app mobile ja le 'explanation'; ele passa a mostrar o texto bom
        # sem precisar de mudanca no cliente.
        result = PortugueseAnalysisEngine().analyze(
            PETRO, NewsData(title="Petrobras anuncia lucro recorde"), PT_DECISION
        )
        self.assertEqual(result.explanation, result.report)


class BackwardCompatibilityTests(SimpleTestCase):
    def test_assinatura_antiga_continua_valendo(self):
        result = analyze_news_for_company(
            PETRO,
            NewsData(
                title="Petrobras anuncia lucro recorde e aumento de dividendos",
                summary="A empresa apresentou forte crescimento.",
            ),
        )
        self.assertEqual(result.sentiment_label, "positive")

    def test_contrato_do_dicionario_preserva_as_chaves_antigas(self):
        payload = analyze_news_for_company(
            PETRO, NewsData(title="Petrobras anuncia lucro recorde")
        ).to_dict()
        for key in (
            "ticker", "company_name", "language", "relevance_score",
            "text_sentiment_score", "adjustment_score", "impact_score",
            "sentiment_label", "confidence", "detected_topics",
            "positive_signals", "negative_signals", "explanation",
        ):
            self.assertIn(key, payload, key)
        for key in ("report", "engine", "llm_used", "fallback_reason"):
            self.assertIn(key, payload, key)


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
class LlmEngineTests(SimpleTestCase):
    def _engine(self, provider, config=None):
        return LlmAnalysisEngine(
            provider=provider,
            config=config or _config(),
            fallback=PortugueseAnalysisEngine(),
        )

    def _news(self):
        return NewsData(
            title="Petrobras anuncia lucro recorde",
            summary="A empresa apresentou forte crescimento.",
        )

    def test_saida_da_llm_vira_modelo_interno(self):
        provider = StubProvider(LlmAnalysis(
            sentiment_score=0.72, sentiment_label="positive", relevance_score=0.88,
            summary="Lucro acima do esperado.",
            reasoning="O titulo cita lucro recorde, o que sustenta o resultado positivo.",
            language=PT_BR,
        ))
        result = self._engine(provider).analyze(PETRO, self._news(), PT_DECISION)

        self.assertTrue(result.llm_used)
        self.assertEqual(result.sentiment_label, "positive")
        self.assertEqual(result.impact_score, 0.72)
        self.assertEqual(result.relevance_score, 0.88)
        self.assertIn("lucro recorde", result.report)
        self.assertEqual(result.fallback_reason, "")
        self.assertEqual(provider.calls, 1)

    def test_json_invalido_cai_no_motor_local(self):
        provider = StubProvider(error=LlmInvalidResponse("JSON invalido"))
        result = self._engine(provider).analyze(PETRO, self._news(), PT_DECISION)

        self.assertFalse(result.llm_used)
        self.assertEqual(result.fallback_reason, "invalid_response")
        self.assertEqual(result.engine, "rules-ptbr")
        self.assertEqual(result.sentiment_label, "positive")
        self.assertIn("motor local", result.report)

    def test_timeout_cai_no_motor_local(self):
        result = self._engine(StubProvider(error=LlmTimeout("estourou"))).analyze(
            PETRO, self._news(), PT_DECISION
        )
        self.assertEqual(result.fallback_reason, "timeout")
        self.assertFalse(result.llm_used)

    def test_limite_de_requisicoes_cai_no_motor_local(self):
        result = self._engine(StubProvider(error=LlmRateLimited("429"))).analyze(
            PETRO, self._news(), PT_DECISION
        )
        self.assertEqual(result.fallback_reason, "rate_limited")

    def test_credencial_rejeitada_cai_no_motor_local(self):
        result = self._engine(StubProvider(error=LlmAuthError("401"))).analyze(
            PETRO, self._news(), PT_DECISION
        )
        self.assertEqual(result.fallback_reason, "auth_error")

    def test_provedor_indisponivel_cai_no_motor_local(self):
        result = self._engine(StubProvider(error=LlmUnavailable("fora do ar"))).analyze(
            PETRO, self._news(), PT_DECISION
        )
        self.assertEqual(result.fallback_reason, "unavailable")

    def test_erro_inesperado_tambem_cai_no_motor_local(self):
        result = self._engine(StubProvider(error=ValueError("boom"))).analyze(
            PETRO, self._news(), PT_DECISION
        )
        self.assertFalse(result.llm_used)
        self.assertIn("unexpected", result.fallback_reason)

    def test_versao_do_motor_muda_quando_o_modelo_muda(self):
        a = self._engine(StubProvider(), _config(model="modelo-a")).engine_id
        b = self._engine(StubProvider(), _config(model="modelo-b")).engine_id
        self.assertNotEqual(a, b)

    def test_versao_do_motor_muda_quando_o_provedor_muda(self):
        a = self._engine(StubProvider(), _config(provider="anthropic")).engine_id
        b = self._engine(StubProvider(), _config(provider="openai")).engine_id
        self.assertNotEqual(a, b)

    def test_configuracao_nao_expoe_a_chave(self):
        config = _config(api_key="chave-super-secreta")
        self.assertNotIn("chave-super-secreta", config.describe())
        self.assertNotIn("chave-super-secreta", config.fingerprint)


class LlmResponseParsingTests(SimpleTestCase):
    def _request(self):
        return LlmRequest(
            ticker="PETR4", company_name="Petrobras", sector="energia",
            title="Petrobras anuncia lucro recorde", summary="", language=PT_BR,
        )

    def test_json_estrito_e_aceito(self):
        raw = (
            '{"sentiment_score": 0.6, "sentiment_label": "positive", '
            '"relevance_score": 0.9, "summary": "ok", "reasoning": "cita lucro recorde", '
            '"language": "pt-BR"}'
        )
        analysis = parse_response(raw, self._request())
        self.assertEqual(analysis.sentiment_label, "positive")
        self.assertEqual(analysis.sentiment_score, 0.6)

    def test_cerca_de_codigo_e_removida(self):
        raw = '```json\n{"sentiment_score": -0.4, "sentiment_label": "negative", "relevance_score": 0.5, "summary": "s", "reasoning": "r"}\n```'
        self.assertEqual(parse_response(raw, self._request()).sentiment_label, "negative")

    def test_texto_fora_do_json_e_tratado(self):
        raw = 'Claro! Segue a analise:\n{"sentiment_score": 0.2, "sentiment_label": "neutral", "relevance_score": 0.4, "summary": "s", "reasoning": "r"}\nEspero ter ajudado.'
        self.assertEqual(parse_response(raw, self._request()).sentiment_label, "neutral")

    def test_json_invalido_e_rejeitado(self):
        with self.assertRaises(LlmInvalidResponse):
            parse_response("desculpe, nao consegui analisar", self._request())

    def test_resposta_vazia_e_rejeitada(self):
        with self.assertRaises(LlmInvalidResponse):
            parse_response("", self._request())

    def test_resposta_incompleta_sem_reasoning_e_rejeitada(self):
        raw = '{"sentiment_score": 0.5, "sentiment_label": "positive", "relevance_score": 0.7, "summary": "s"}'
        with self.assertRaises(LlmInvalidResponse):
            parse_response(raw, self._request())

    def test_score_fora_da_faixa_e_limitado(self):
        raw = '{"sentiment_score": 7.3, "sentiment_label": "positive", "relevance_score": 4.1, "summary": "s", "reasoning": "r"}'
        analysis = parse_response(raw, self._request())
        self.assertEqual(analysis.sentiment_score, 1.0)
        self.assertEqual(analysis.relevance_score, 1.0)

    def test_rotulo_invalido_e_derivado_da_nota(self):
        raw = '{"sentiment_score": -0.8, "sentiment_label": "muito ruim", "relevance_score": 0.9, "summary": "s", "reasoning": "r"}'
        self.assertEqual(parse_response(raw, self._request()).sentiment_label, "negative")

    def test_campo_nao_numerico_e_rejeitado(self):
        raw = '{"sentiment_score": "muito bom", "sentiment_label": "positive", "relevance_score": 0.9, "summary": "s", "reasoning": "r"}'
        with self.assertRaises(LlmInvalidResponse):
            parse_response(raw, self._request())

    def test_reasoning_longo_e_truncado(self):
        raw = (
            '{"sentiment_score": 0.5, "sentiment_label": "positive", "relevance_score": 0.9, '
            '"summary": "s", "reasoning": "' + ("x" * 5000) + '"}'
        )
        analysis = parse_response(raw, self._request())
        self.assertLessEqual(len(analysis.reasoning), 700)
