"""Load the bundled confectionery supplement for the full edition."""

import gzip
import json
from functools import lru_cache
from pathlib import Path


CATEGORIAS = {
    'pães doces': 'Pães e massas',
    'cookies e biscoitos': 'Lanches',
    'salgados doces de festa': 'Lanches',
}
COMPONENTES = {'recheios', 'coberturas e massas base'}


@lru_cache(maxsize=1)
def carregar_confeitaria():
    arquivo = Path(__file__).with_name('acervo_confeiteiras.json.gz')
    with gzip.open(arquivo, 'rt', encoding='utf-8') as entrada:
        registros = json.load(entrada)
    return tuple({
        'title': receita['titulo'],
        'category': CATEGORIAS.get(receita['categoria'], 'Sobremesas'),
        'yield_text': receita['rendimento'],
        'ingredients': [
            f"{item['quantidade']} {item['unidade']} {item['item']}"
            for item in receita['ingredientes']
        ],
        'ingredient_index': [item['item'] for item in receita['ingredientes']],
        'steps': receita['modo_de_preparo'],
        'fixed_yield': True,
        'freezer': {},
    } for receita in registros if receita['categoria'] not in COMPONENTES)
