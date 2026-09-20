"""Motor de analise para noticias em portugues brasileiro.

Diferencas em relacao ao motor de ingles:

* usa somente o lexico pt-BR, com pesos por termo;
* NAO usa VADER, que e treinado em ingles e so injetava ruido em texto em
  portugues;
* trata negacao ("nao registrou prejuizo") e intensificadores ("forte alta");
* apoia-se nas frases de ``rules.PHRASE_POLARITY`` para desambiguar termos como
  "juros", que muda de sinal conforme o contexto.
"""

from __future__ import annotations

from .language import PT_BR
from .lexicons import pt_br
from .local import LocalLexicalEngine


class PortugueseAnalysisEngine(LocalLexicalEngine):
    name = "rules-ptbr"
    language = PT_BR
    lexicon = pt_br
    use_vader = False
    lexical_weight = 0.80
    vader_weight = 0.0
    phrase_weight = 0.70
    human_label = "motor heuristico de portugues"
