from collections import defaultdict
from decimal import Decimal

from livro import generate_demo, normalize

DIAS = ('Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo')
TOTAL = 200


def selecionar(recovered, catalog, categories):
    selected = []
    names = set()
    ordered = [*recovered, *(item for item in catalog if not categories or item['category'] in categories)]
    for item in ordered:
        name = normalize(item['title'])
        if not name or name in names:
            continue
        if not item['ingredients'] or not item['steps']:
            raise ValueError('Receita incompleta no catálogo.')
        selected.append(item)
        names.add(name)
        if len(selected) == TOTAL:
            return selected
    raise ValueError(f'Acervo insuficiente para estas preferências: {len(selected)} de {TOTAL} receitas.')


def montar_bonus(recipes, portions):
    meals = [(i, r) for i, r in enumerate(recipes) if r.get('meal') and r.get('shopping')][:7]
    frozen = [(i, r) for i, r in enumerate(recipes)
              if r.get('photo') and all(r.get('freezer', {}).get(key)
                    for key in ('congelar', 'acondicionar', 'servir', 'fonte'))]
    if len(meals) < 7 or not frozen:
        raise ValueError('O acervo ainda não cobre sete refeições ou o guia verificado de freezer.')
    shopping = defaultdict(Decimal)
    for _, recipe in meals:
        for row in recipe['shopping']:
            amount = Decimal(str(row['por_pessoa']))
            if not amount.is_finite() or amount <= 0:
                raise ValueError('Quantidade inválida na lista de compras.')
            key = (row['secao'], row['ingrediente'], row['unidade'])
            shopping[key] += amount * portions
    if portions < 1:
        raise ValueError('Informe o tamanho da porção.')
    plan = [(f'{day} · {recipe["title"]}', index) for day, (index, recipe) in zip(DIAS, meals)]
    plan += [('', None), (f'Lista de compras para {portions} pessoa(s)', None)]
    plan += [(f'{section} · {name}: {quantity.normalize():f} {unit}'.replace(f'{quantity.normalize():f}', f'{quantity.normalize():f}'.replace('.', ','), 1), None)
             for (section, name, unit), quantity in sorted(shopping.items())]
    freezer = []
    for index, recipe in frozen:
        data = recipe['freezer']
        freezer.extend([(recipe['title'], index),
                        ('Congelar · ' + data['congelar'], None),
                        ('Acondicionar · ' + data['acondicionar'], None),
                        ('Servir · ' + data['servir'], None),
                        ('Fonte · ' + data['fonte'], None), ('', None)])
    ingredient_index = defaultdict(list)
    for index, recipe in enumerate(recipes):
        for ingredient in dict.fromkeys(normalize(name) for name in recipe.get('ingredient_index', [])):
            if ingredient and ingredient not in {'água', 'agua', 'sal', 'azeite'}:
                ingredient_index[ingredient].append((recipe['title'], index))
    if not ingredient_index:
        raise ValueError('Faltam ingredientes catalogados para o índice.')
    lookup = []
    for ingredient, entries in sorted(ingredient_index.items()):
        lookup.extend([(ingredient.capitalize(), None), *entries, ('', None)])
    return [('Seu cardápio com lista de compras', plan),
            ('Do livro para o freezer', freezer),
            ('Índice por ingrediente', lookup)]


def gerar_edicao(options, links, recovered, catalog):
    """Build the full edition or report a catalog gap before rendering."""
    recipes = selecionar(recovered, catalog, options['categorias'])
    bonuses = montar_bonus(recipes, options['pessoas'])
    return generate_demo(options, links, recipes, bonuses=bonuses)
