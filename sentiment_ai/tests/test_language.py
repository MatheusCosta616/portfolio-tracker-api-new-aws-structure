"""Cobertura da identificacao de idioma (P0)."""

from django.test import SimpleTestCase, override_settings

from sentiment_ai.engine.language import (
    EN,
    PT_BR,
    SOURCE_DECLARED,
    SOURCE_DETECTED,
    SOURCE_FALLBACK,
    SOURCE_STORED,
    UNKNOWN,
    detect_language,
    normalize_language_code,
    resolve_language,
    strip_tickers,
)


class DetectLanguageTests(SimpleTestCase):
    def test_noticia_claramente_em_portugues(self):
        decision = detect_language(
            "Petrobras anuncia lucro recorde no trimestre",
            "A empresa informou que o resultado veio acima do esperado pelo mercado.",
        )
        self.assertEqual(decision.language, PT_BR)
        self.assertEqual(decision.source, SOURCE_DETECTED)

    def test_portugues_com_acentos_e_cedilha(self):
        decision = detect_language(
            "Ações da Vale sobem após inspeção da produção",
            "A avaliação considerou o preço do minério e a manutenção do dividendo.",
        )
        self.assertEqual(decision.language, PT_BR)

    def test_titulo_curto_em_portugues(self):
        self.assertEqual(detect_language("Vale despenca na B3").language, PT_BR)

    def test_titulo_curto_apenas_com_acento(self):
        # Poucos tokens, mas a cedilha e evidencia suficiente de portugues.
        self.assertEqual(detect_language("Ação sobe").language, PT_BR)

    def test_noticia_em_ingles(self):
        decision = detect_language(
            "Petrobras posts record profit for the quarter",
            "The company said results came in above analyst expectations.",
        )
        self.assertEqual(decision.language, EN)

    def test_ticker_misturado_com_texto_em_portugues(self):
        decision = detect_language("PETR4: Petrobras aprova aumento de dividendos")
        self.assertEqual(decision.language, PT_BR)

    def test_termos_financeiros_em_ingles_nao_viram_noticia_em_ingles(self):
        decision = detect_language(
            "VALE3 fecha em alta com guidance de produção acima do esperado",
            "O resultado do trimestre superou as projeções do mercado.",
        )
        self.assertEqual(decision.language, PT_BR)

    def test_texto_vazio_devolve_unknown(self):
        self.assertEqual(detect_language("", "").language, UNKNOWN)

    def test_texto_insuficiente_devolve_unknown(self):
        self.assertEqual(detect_language("B3 XP11").language, UNKNOWN)

    def test_tickers_sao_removidos_antes_da_deteccao(self):
        limpo = strip_tickers("PETR4 e HGLG11 e BTC-USD e VALE3.SA")
        self.assertNotIn("PETR4", limpo)
        self.assertNotIn("HGLG11", limpo)
        self.assertNotIn("BTC-USD", limpo)


class NormalizeLanguageCodeTests(SimpleTestCase):
    def test_variacoes_de_portugues(self):
        for value in ("pt", "pt-BR", "pt_br", "PT-br", "pt-PT"):
            self.assertEqual(normalize_language_code(value), PT_BR, value)

    def test_variacoes_de_ingles(self):
        for value in ("en", "en-US", "EN_gb"):
            self.assertEqual(normalize_language_code(value), EN, value)

    def test_desconhecido(self):
        for value in ("", None, "es", "fr-FR"):
            self.assertEqual(normalize_language_code(value), UNKNOWN)


class ResolveLanguageChainTests(SimpleTestCase):
    def test_1_idioma_da_fonte_tem_prioridade(self):
        decision = resolve_language(
            "Petrobras posts record profit", "", source_language="pt-BR", stored_language="en"
        )
        self.assertEqual(decision.language, PT_BR)
        self.assertEqual(decision.source, SOURCE_DECLARED)

    def test_2_idioma_do_banco_vem_depois_da_fonte(self):
        decision = resolve_language(
            "Petrobras posts record profit", "", source_language=None, stored_language="en"
        )
        self.assertEqual(decision.language, EN)
        self.assertEqual(decision.source, SOURCE_STORED)

    def test_3_deteccao_quando_nao_ha_fonte_nem_banco(self):
        decision = resolve_language("Vale anuncia forte alta do lucro no trimestre")
        self.assertEqual(decision.language, PT_BR)
        self.assertEqual(decision.source, SOURCE_DETECTED)

    def test_4_fallback_configuravel_quando_nada_decide(self):
        decision = resolve_language("B3 XP11", fallback="pt-BR")
        self.assertEqual(decision.language, PT_BR)
        self.assertEqual(decision.source, SOURCE_FALLBACK)

    def test_idioma_ausente_nao_vira_ingles_automaticamente(self):
        decision = resolve_language("", "", fallback="pt-BR")
        self.assertNotEqual(decision.language, EN)
        self.assertEqual(decision.source, SOURCE_FALLBACK)

    def test_fallback_invalido_cai_para_portugues(self):
        decision = resolve_language("", "", fallback="klingon")
        self.assertEqual(decision.language, PT_BR)
