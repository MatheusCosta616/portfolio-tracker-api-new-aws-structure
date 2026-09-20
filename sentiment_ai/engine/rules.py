from __future__ import annotations

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "oil": (
        "oil", "brent", "crude", "barrel", "opec", "opep", "fuel", "diesel",
        "gasoline", "refining", "petroleo", "barril", "combustivel", "gasolina",
        "refino",
    ),
    "mining": (
        "iron ore", "ore", "mining", "steel", "nickel", "copper", "pellet",
        "minerio de ferro", "mineracao", "aco", "niquel", "cobre",
    ),
    "aviation": (
        "airline", "aviation", "jet fuel", "flights", "passengers", "airfare",
        "companhia aerea", "aviacao", "querosene", "voos", "passageiros",
    ),
    "banking": (
        "interest rate", "credit", "loan", "default", "bank", "banking", "spread",
        "taxa de juros", "credito", "emprestimo", "inadimplencia", "banco",
    ),
    "technology": (
        "cloud", "artificial intelligence", "semiconductor", "software", "data center",
        "chip", "nuvem", "inteligencia artificial", "semicondutor",
    ),
    "retail": (
        "consumer", "retail", "e-commerce", "sales", "store", "shopping",
        "consumidor", "varejo", "comercio eletronico", "vendas", "loja",
    ),
    "macro": (
        "inflation", "gdp", "recession", "rate cut", "rate hike", "unemployment",
        "inflacao", "pib", "recessao", "corte de juros", "alta de juros", "desemprego",
    ),
    "government": (
        "government", "regulation", "tax", "tariff", "sanction", "minister", "president",
        "governo", "regulacao", "imposto", "tarifa", "sancao", "ministro", "presidente",
    ),
    "dividends": (
        "dividend", "payout", "yield", "buyback", "jcp", "dividendo", "dividendos",
        "recompra", "juros sobre capital proprio",
    ),
    "earnings": (
        "earnings", "profit", "loss", "ebitda", "revenue", "guidance", "results",
        "resultado", "resultados", "lucro", "prejuizo", "receita",
    ),
    "geopolitics": (
        "war", "conflict", "tension", "attack", "middle east", "supply disruption",
        "guerra", "conflito", "tensao", "ataque", "oriente medio", "interrupcao de oferta",
    ),
}

SECTOR_RULES: dict[str, dict[str, object]] = {
    "energy": {
        "topic_weights": {"oil": 0.16, "dividends": 0.10, "earnings": 0.10, "geopolitics": 0.05, "government": -0.10},
        "phrase_weights": {
            "oil prices rise": 0.18, "crude prices rise": 0.18, "petroleo sobe": 0.18,
            "alta do petroleo": 0.18, "dividend": 0.08, "dividendo": 0.08,
            "government intervention": -0.18, "intervencao do governo": -0.18,
            "price controls": -0.20, "controle de precos": -0.20,
            "oil prices fall": -0.18, "queda do petroleo": -0.18,
        },
    },
    "basic materials": {
        "topic_weights": {"mining": 0.14, "earnings": 0.10, "macro": 0.03, "government": -0.06},
        "phrase_weights": {
            "iron ore rises": 0.18, "minerio de ferro sobe": 0.18,
            "china stimulus": 0.15, "estimulo da china": 0.15,
            "iron ore falls": -0.18, "minerio de ferro cai": -0.18,
        },
    },
    "financial services": {
        "topic_weights": {"banking": 0.10, "earnings": 0.10, "macro": 0.02, "government": -0.04},
        "phrase_weights": {
            "lower defaults": 0.12, "queda da inadimplencia": 0.12,
            "higher defaults": -0.14, "alta da inadimplencia": -0.14,
            "rate hike": 0.03, "alta de juros": 0.03,
            "rate cut": -0.03, "corte de juros": -0.03,
        },
    },
    "airlines": {
        "topic_weights": {"aviation": 0.10, "earnings": 0.10, "macro": 0.02, "oil": -0.16, "geopolitics": -0.06},
        "phrase_weights": {
            "oil prices rise": -0.20, "alta do petroleo": -0.20,
            "oil prices fall": 0.17, "queda do petroleo": 0.17,
        },
    },
    "technology": {
        "topic_weights": {"technology": 0.12, "earnings": 0.10, "government": -0.04, "macro": -0.02},
        "phrase_weights": {},
    },
    "consumer cyclicals": {
        "topic_weights": {"retail": 0.09, "macro": 0.04, "earnings": 0.10, "government": -0.03},
        "phrase_weights": {},
    },
    "industrials": {
        "topic_weights": {"macro": 0.04, "earnings": 0.10, "government": -0.04},
        "phrase_weights": {},
    },
    "default": {
        "topic_weights": {"earnings": 0.08, "dividends": 0.06, "government": -0.04},
        "phrase_weights": {},
    },
}


# Frases cuja polaridade independe do setor. Existem para resolver termos que,
# sozinhos, seriam ambiguos demais para entrar no lexico. O caso classico e
# "juros": negativo em "alta de juros", positivo em "juros sobre capital
# proprio". A frase mais longa vence a mais curta.
PHRASE_POLARITY: dict[str, float] = {
    # Proventos
    "juros sobre capital proprio": 0.55,
    "jcp": 0.45,
    "pagamento de dividendos": 0.50,
    "distribuicao de proventos": 0.50,
    "aumento de dividendos": 0.60,
    "dividend increase": 0.60,
    "special dividend": 0.55,
    # Resultado
    "lucro recorde": 0.75,
    "lucro liquido": 0.35,
    "record profit": 0.75,
    "acima do esperado": 0.55,
    "abaixo do esperado": -0.55,
    "above expectations": 0.55,
    "below expectations": -0.55,
    "reversao de prejuizo": 0.60,
    "prejuizo liquido": -0.70,
    # Macro / juros
    "alta de juros": -0.35,
    "aumento dos juros": -0.35,
    "elevacao dos juros": -0.35,
    "corte de juros": 0.35,
    "reducao dos juros": 0.35,
    "rate hike": -0.35,
    "rate cut": 0.35,
    # Governanca / risco
    "acao judicial": -0.45,
    "processo judicial": -0.45,
    "investigacao da cvm": -0.65,
    "pedido de recuperacao judicial": -0.95,
    "fato relevante": 0.0,
}
