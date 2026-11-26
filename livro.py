import io
import json
from pathlib import Path
import re
import unicodedata
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph


ROOT = Path(__file__).parent
IVORY = colors.HexColor('#FAF6EB')
GREEN = colors.HexColor('#203D32')
INK = colors.HexColor('#262D27')
LINE = colors.HexColor('#CEC8B7')
W, H = A4
M = 45


def normalize(text):
    return ''.join(letter for letter in unicodedata.normalize('NFD', text.casefold())
                   if not unicodedata.combining(letter)).strip()


def select_recipes(options):
    recipes = json.loads((ROOT / 'acervo-teste.json').read_text(encoding='utf-8'))
    categories = options['categorias']
    exclusions = [normalize(value) for value in re.split(r'[,;\n]', options['evitar']) if value.strip()]
    return [recipe for recipe in recipes
            if (not categories or recipe['category'] in categories)
            and not any(term in normalize(name) for _, _, name in recipe['ingredients'] for term in exclusions)]


def generate_demo(options, links):
    recipes = select_recipes(options)
    if not recipes:
        return None
    portions = options['pessoas']
    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=A4, pageCompression=1)
    pdf.setTitle('Dos Salvos para a Mesa | Pedido de teste')

    def text(x, y, value, font='Helvetica', size=11, color=INK):
        pdf.setFont(font, size)
        pdf.setFillColor(color)
        pdf.drawString(x, H - y, value)

    def block(x, y, width, value):
        style = ParagraphStyle('text', fontName='Helvetica', fontSize=11, leading=15, textColor=INK)
        paragraph = Paragraph(escape(value), style)
        _, height = paragraph.wrap(width, H)
        paragraph.drawOn(pdf, x, H - y - height)
        return y + height + 7

    def line(x, y, end):
        pdf.setStrokeColor(LINE)
        pdf.line(x, H - y, end, H - y)

    def page(section, number):
        pdf.setFillColor(IVORY)
        pdf.rect(0, 0, W, H, fill=1, stroke=0)
        text(M, 44, 'DOS SALVOS PARA A MESA', 'Helvetica-Bold', 9, GREEN)
        pdf.setFillColor(GREEN)
        pdf.drawRightString(W - M, H - 44, section)
        line(M, 55, W - M)
        line(M, 790, W - M)
        text(M, 807, 'Pedido de teste · Receitas ilustrativas', 'Helvetica', 9, GREEN)
        text(W - M - 15, 807, f'{number:02d}', 'Helvetica-Bold', 9, GREEN)

    page('Amostra', 1)
    text(M, 146, 'Dos Salvos para a Mesa', 'Times-Roman', 44, GREEN)
    block(M, 170, W - 2*M, f'{len(links)} links importados · {len(recipes)} receitas ilustrativas do acervo de teste · {portions} porções por ficha.')
    block(M, 215, W - 2*M, 'Os links do pedido foram usados para testar a importação. As fichas desta amostra foram selecionadas pelas preferências.')
    pdf.drawImage(str(ROOT / 'mockup-campanha.webp'), M, H - 550, W - 2*M, (W - 2*M)*805/1320)
    text(M, 600, 'Índice', 'Times-Roman', 24, GREEN)
    for i, recipe in enumerate(recipes):
        y = 629 + i*27
        text(M, y, f'{i+2:02d}  {recipe["title"]}')
        pdf.linkRect('', f'receita-{i}', (M, H-y-5, W-M, H-y+15), relative=0, thickness=0)
    pdf.showPage()

    for i, recipe in enumerate(recipes):
        pdf.bookmarkPage(f'receita-{i}', fit='XYZ', left=0, top=H, zoom=0)
        page(recipe['category'], i+2)
        text(M, 115, recipe['title'], 'Times-Roman', 32, GREEN)
        text(M, 144, f'Rendimento: {portions} ' + ('porção' if portions == 1 else 'porções'))
        column_top = 206
        photo = ROOT / 'referencia' / 'focaccia.webp'
        if recipe['title'] == 'Focaccia de alecrim':
            pdf.drawImage(str(photo), M, H - 435, W - 2*M, 270)
            text(M, 450, 'Imagem ilustrativa', 'Helvetica', 8, GREEN)
            column_top = 492
        line(M, column_top - 25, W - M)
        right = M + 200
        text(M, column_top, 'Ingredientes', 'Times-Roman', 22, GREEN)
        text(right, column_top, 'Modo de preparo', 'Times-Roman', 22, GREEN)
        y = column_top + 17
        for amount, unit, ingredient in recipe['ingredients']:
            quantity = f'{amount * portions:g}'.replace('.', ',')
            y = block(M, y, 175, f'{quantity} {unit} {ingredient}')
        y = column_top + 17
        for step, instruction in enumerate(recipe['steps'], 1):
            y = block(right, y, W - M - right, f'{step:02d}  {instruction}')
        pdf.showPage()
    pdf.save()
    return stream.getvalue()
