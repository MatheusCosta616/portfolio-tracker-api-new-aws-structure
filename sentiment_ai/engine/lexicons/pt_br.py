"""Lexico financeiro em portugues brasileiro.

Os termos sao gravados sem acento porque ``text_processing.normalize_text``
remove diacriticos antes da tokenizacao. Cada termo carrega um peso: termos
inequivocos valem 1.0 e termos mais fracos ou ambiguos valem menos.

Termos ambiguos isolados NAO entram aqui. "juros", por exemplo, e negativo em
"alta de juros" e positivo em "juros sobre capital proprio"; quem decide isso e
``rules.SECTOR_RULES`` / ``rules.PHRASE_POLARITY``, que enxergam a frase inteira.
"""

POSITIVE_WEIGHTS: dict[str, float] = {
    "acordo": 0.5,
    "alta": 0.8,
    "altas": 0.8,
    "amplia": 0.6,
    "ampliacao": 0.6,
    "aprovacao": 0.6,
    "aprovado": 0.6,
    "aumenta": 0.8,
    "aumento": 0.8,
    "avanca": 0.7,
    "avanco": 0.7,
    "bate": 0.7,
    "beneficio": 0.6,
    "bonificacao": 0.8,
    "captacao": 0.5,
    "cresce": 0.9,
    "crescimento": 0.9,
    "disparam": 0.8,
    "dispara": 0.8,
    "dividendo": 0.9,
    "dividendos": 0.9,
    "elevacao": 0.6,
    "expande": 0.7,
    "expansao": 0.7,
    "forte": 0.5,
    "ganho": 0.8,
    "ganhos": 0.8,
    "lucra": 1.0,
    "lucratividade": 0.9,
    "lucro": 1.0,
    "lucros": 1.0,
    "melhora": 0.7,
    "otimista": 0.7,
    "positivo": 0.8,
    "proventos": 0.9,
    "rali": 0.7,
    "recompra": 0.8,
    "recorde": 1.0,
    "recuperacao": 0.7,
    "rentabilidade": 0.7,
    "sobe": 0.8,
    "subiu": 0.8,
    "sucesso": 0.6,
    "supera": 0.9,
    "superavit": 0.9,
    "valorizacao": 0.9,
    "vantagem": 0.5,
}

NEGATIVE_WEIGHTS: dict[str, float] = {
    "acidente": 0.9,
    "adiamento": 0.6,
    "baixa": 0.7,
    "cai": 0.8,
    "caiu": 0.8,
    "calote": 1.0,
    "colapso": 1.0,
    "crise": 0.9,
    "declinio": 0.8,
    "deficit": 0.9,
    "demissao": 0.7,
    "demissoes": 0.7,
    "derrete": 0.9,
    "desaba": 1.0,
    "desabou": 1.0,
    "desacelera": 0.7,
    "desaceleracao": 0.7,
    "despenca": 1.0,
    "despencou": 1.0,
    "desvalorizacao": 0.9,
    "escandalo": 1.0,
    "falencia": 1.0,
    "fraco": 0.7,
    "fraude": 1.0,
    "greve": 0.8,
    "inadimplencia": 0.9,
    "investigacao": 0.8,
    "multa": 0.8,
    "paralisacao": 0.8,
    "perda": 0.9,
    "perdas": 0.9,
    "pessimista": 0.7,
    "prejuizo": 1.0,
    "prejuizos": 1.0,
    "queda": 0.8,
    "rebaixa": 0.9,
    "rebaixamento": 0.9,
    "recua": 0.7,
    "recuo": 0.7,
    "risco": 0.6,
    "rombo": 1.0,
    "sancao": 0.8,
    "tomba": 0.9,
}

# Compatibilidade com o codigo anterior, que importava conjuntos.
POSITIVE_TERMS = frozenset(POSITIVE_WEIGHTS)
NEGATIVE_TERMS = frozenset(NEGATIVE_WEIGHTS)

# Invertem a polaridade do termo seguinte dentro da janela de negacao.
NEGATORS = frozenset({
    "nao", "nem", "sem", "nunca", "jamais", "nenhum", "nenhuma", "tampouco",
})

# Multiplicam a intensidade do termo seguinte.
INTENSIFIERS: dict[str, float] = {
    "forte": 1.35,
    "fortes": 1.35,
    "recorde": 1.45,
    "expressivo": 1.30,
    "expressiva": 1.30,
    "significativo": 1.25,
    "significativa": 1.25,
    "historico": 1.30,
    "historica": 1.30,
    "leve": 0.70,
    "leves": 0.70,
    "ligeira": 0.70,
    "ligeiro": 0.70,
    "pequena": 0.70,
    "pequeno": 0.70,
    "moderada": 0.80,
    "moderado": 0.80,
}

STOPWORDS = frozenset({
    "ainda", "alem", "apos", "como", "companhia", "contra", "depois",
    "empresa", "entre", "foram", "mais", "mercado", "para", "pela", "pelo",
    "pode", "servicos", "sobre", "tambem", "teve", "uma", "com", "dos",
    "das", "que", "seu", "sua", "nesta", "neste", "nessa", "desse", "pelas",
    "pelos", "seus", "suas", "ser", "sao", "tem", "ter", "foi", "isso",
})

# Palavras funcionais usadas so para identificar o idioma.
FUNCTION_WORDS = frozenset({
    "de", "da", "do", "das", "dos", "para", "com", "que", "nao", "em", "no",
    "na", "nos", "nas", "ao", "aos", "pela", "pelo", "uma", "um", "sobre",
    "apos", "ate", "entre", "como", "mais", "mas", "por", "seu", "sua", "se",
    "ja", "foi", "sao", "ser", "ter", "tem", "esta", "este", "essa", "isso",
    "acoes", "acao", "empresa", "bilhoes", "milhoes", "trimestre", "ano",
})
