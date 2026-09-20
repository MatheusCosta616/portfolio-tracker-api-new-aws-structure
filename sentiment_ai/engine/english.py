"""Motor de analise para noticias em ingles.

Mantem o comportamento historico: lexico em ingles mais VADER, que e um modelo
treinado em ingles. A unica mudanca de fundo e que o lexico em portugues nao
contamina mais a pontuacao.
"""

from __future__ import annotations

from .language import EN
from .lexicons import en
from .local import LocalLexicalEngine


class EnglishAnalysisEngine(LocalLexicalEngine):
    name = "rules-en"
    language = EN
    lexicon = en
    use_vader = True
    lexical_weight = 0.55
    vader_weight = 0.45
    human_label = "motor heuristico de ingles com VADER"
