import io
import json
from pathlib import Path
import re
import unicodedata
from xml.sax.saxutils import escape

from PIL import Image, ImageOps
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph


ROOT = Path(__file__).parent
IVORY = colors.HexColor('#FAF6EB')
GREEN = colors.HexColor('#18372D')
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
    return [recipe for recipe in recipes if not categories or recipe['category'] in categories]


def ingredient_note(recipe, ingredient, preferences):
    name = normalize(ingredient)
    terms = [normalize(value) for value in re.split(r'[,;\n]', preferences) if value.strip()]
    if not any(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', name) for term in terms):
        return ''
    if recipe['title'] == 'Cuscuz marroquino com grão-de-bico' and name in {'coentro fresco', 'salsinha'}:
        alternative = 'salsinha' if name == 'coentro fresco' else 'coentro fresco'
        if not any(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', normalize(alternative)) for term in terms):
            return f'{ingredient.capitalize()} pode ser substituído por {alternative} ou omitido. Ajuste também a etapa de temperar.'
        return f'{ingredient.capitalize()} pode ser omitido. Ajuste também a etapa de temperar.'
    return f'{ingredient.capitalize()} consta na receita original. Esta ficha ainda não tem uma substituição validada.'


def reviewed_recipes(path, links):
    if not path.exists():
        return []
    catalog = json.loads(path.read_text(encoding='utf-8'))
    recipes = []
    for link in links:
        source = link['url']
        code = source.rstrip('/').rsplit('/', 1)[-1]
        if code not in catalog:
            continue
        record = catalog[code]
        title, category, yield_text = (record[key].strip() for key in ('title', 'category', 'yield'))
        ingredients = [item.strip() for item in record['ingredients']]
        steps = [item.strip() for item in record['steps']]
        if not (title and category and yield_text and ingredients and all(ingredients) and steps and all(steps)):
            raise ValueError('Ficha revisada incompleta: ' + code)
        recipes.append(dict(title=title, category=category, yield_text=yield_text,
                            ingredients=ingredients, steps=steps, source=source,
                            photo=record.get('photo'), details=record.get('details', []),
                            stage_titles=record.get('stage_titles', []), stage_icons=record.get('stage_icons', [])))
    return recipes


def generate_demo(options, links, reviewed=None, *, bonuses=None):
    recipes = select_recipes(options) if reviewed is None else reviewed
    if not recipes:
        return None
    portions = options['pessoas']
    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=A4, pageCompression=1)
    pdf.setTitle('Dos Salvos para a Mesa | Homologação')
    gold = colors.HexColor('#C7A473')
    terra = colors.HexColor('#8D482D')
    pale = colors.HexColor('#EFE6D5')

    def rect(x, y, w, h, color):
        pdf.setFillColor(color)
        pdf.rect(x, H-y-h, w, h, fill=1, stroke=0)

    def text(x, y, value, font='Helvetica', size=11, color=INK, align='left'):
        pdf.setFont(font, size)
        pdf.setFillColor(color)
        draw = {'left': pdf.drawString, 'center': pdf.drawCentredString, 'right': pdf.drawRightString}[align]
        draw(x, H-y, value)

    def paragraph(value, width, size=11, leading=14, font='Helvetica', color=INK):
        para = Paragraph(escape(value), ParagraphStyle('body', fontName=font, fontSize=size, leading=leading, textColor=color))
        height = para.wrap(width, H)[1]
        return para, height

    def block(x, y, width, value, **kwargs):
        para, height = paragraph(value, width, **kwargs)
        para.drawOn(pdf, x, H-y-height)
        return y+height

    def line(x, y, end, color=LINE):
        pdf.setStrokeColor(color)
        pdf.setLineWidth(.65)
        pdf.line(x, H-y, end, H-y)

    def bookmark(key):
        pdf.bookmarkPage(key, fit='XYZ', left=0, top=H, zoom=0)

    def link(key, x, y, end, bottom):
        pdf.linkRect('', key, (x, H-bottom, end, H-y), relative=0, thickness=0)

    def footer(number, back=False):
        line(M, 792, W-M)
        text(M, 811, 'Dos Salvos para a Mesa · Homologação', 'Times-Italic', 11, GREEN)
        text(W-M, 811, f'{number:02d}', 'Helvetica-Bold', 9, GREEN, 'right')
        if back:
            text(W-M-25, 811, 'Voltar ao índice', 'Helvetica', 9, GREEN, 'right')
            link('indice', W-M-105, 798, W-M-23, 817)

    def picture(path, x, y, width, height, crop=False):
        with Image.open(path) as original:
            if crop:
                img = ImageOps.fit(original.convert('RGB'), (round(width*1.45), round(height*1.45)))
                encoded = io.BytesIO()
                img.save(encoded, format='JPEG', quality=83, optimize=True)
                encoded.seek(0)
                picture_data = ImageReader(encoded)
            else:
                picture_data = ImageReader(original)
            pdf.drawImage(picture_data, x, H-y-height, width, height, preserveAspectRatio=not crop,
                          anchor='c', mask='auto')

    def recipe_photo(recipe):
        if recipe.get('photo') in ('brownie.jpg', 'mousse.jpg'):
            return ROOT / 'referencia' / recipe['photo']
        if not recipe.get('source') and recipe['title'] == 'Focaccia de alecrim':
            return ROOT / 'referencia' / 'focaccia.webp'
        return None

    def utensil(kind, x, y):
        pdf.saveState()
        pdf.translate(x,H-y-26)
        pdf.setStrokeColor(GREEN)
        pdf.setLineWidth(1.3)
        if kind == 'tigela':
            p = pdf.beginPath()
            p.moveTo(0,17)
            p.curveTo(3,-2,25,-2,28,17)
            p.close()
            pdf.drawPath(p)
        elif kind == 'forno':
            pdf.roundRect(0,0,27,21,2)
            pdf.rect(4,4,19,10)
            pdf.line(2,16,25,16)
        elif kind == 'geladeira':
            pdf.roundRect(6,0,15,23,2)
            pdf.line(6,15,21,15)
            pdf.line(10,17,10,20)
            pdf.line(10,5,10,12)
        elif kind == 'liquidificador':
            path = pdf.beginPath()
            path.moveTo(5,22)
            path.lineTo(23,22)
            path.lineTo(19,7)
            path.lineTo(9,7)
            path.close()
            pdf.drawPath(path)
            pdf.rect(7,1,14,5)
            pdf.line(4,24,24,24)
        pdf.restoreState()

    rect(0, 0, W, H, GREEN)
    line(M, 68, W-M, gold)
    text(W/2, 171, 'Dos Salvos', 'Times-Roman', 71, IVORY, 'center')
    text(W/2, 239, 'para a Mesa', 'Times-Italic', 71, IVORY, 'center')
    rect(0, 291, W, 383, IVORY)
    picture(ROOT / 'mockup-campanha.webp', 12, 299, W-24, 362)
    text(W/2, 742, 'Seu livro de receitas', 'Times-Italic', 20, IVORY, 'center')
    line(M, 782, W-M, gold)
    pdf.showPage()

    index_size = 6
    index_pages = (len(recipes)+index_size-1)//index_size
    recipe_start = 2 + index_pages
    card_width = (W-2*M-12)/2
    for offset in range(0, len(recipes), index_size):
        if not offset:
            bookmark('indice')
        rect(0, 0, W, H, IVORY)
        rect(0, 0, W, 126, GREEN)
        text(M, 82, 'Índice', 'Times-Roman', 56, IVORY)
        for position, recipe in enumerate(recipes[offset:offset+index_size]):
            index = offset+position
            x = M+(position%2)*(card_width+12)
            y = 149+(position//2)*207
            rect(x, y, card_width,183,pale)
            photo = recipe_photo(recipe)
            if photo:
                picture(photo,x,y,card_width,108,True)
                text(x+card_width-9,y+120,'Foto ilustrativa','Helvetica',7,terra,'right')
            text(x+10,y+133,recipe['category'].upper(),'Helvetica-Bold',8,terra)
            end = block(x+10,y+139,card_width-20,recipe['title'],size=16,leading=17,font='Times-Roman')
            text(x+10,max(y+174,end+10),f'Página {recipe_start+index:02d}','Helvetica-Bold',9,GREEN)
            link(f'receita-{index}',x,y,x+card_width,y+190)
        if bonuses:
            for i, label in enumerate(('Cardápio e compras', 'Guia do freezer', 'Índice por ingrediente')):
                x = M+i*167
                text(x,768,label,'Helvetica-Bold',9,GREEN)
                link(f'bonus-{i}',x,755,x+157,777)
        footer(2+offset//index_size)
        pdf.showPage()

    for index, recipe in enumerate(recipes):
        bookmark(f'receita-{index}')
        rect(0, 0, W, H, IVORY)
        rect(0, 0, W, 128, GREEN)
        text(M, 30, 'ATLAS VISUAL DE RECEITAS  /  '+recipe['category'].upper(), 'Helvetica-Bold', 8.5, gold)
        title = recipe['title']
        title_size = min(40, 40*(W-2*M)/max(W-2*M,pdf.stringWidth(title,'Times-Roman',40)))
        text(M, 77, title, 'Times-Roman', title_size, IVORY)
        yield_text = recipe.get('yield_text') or f'{portions} ' + ('porção' if portions == 1 else 'porções')
        text(M, 102, 'Rendimento: '+yield_text, 'Helvetica', 10, IVORY)
        photo = recipe_photo(recipe)
        ingredients_heading = 152
        if photo:
            picture(photo,0,128,W-171,199,True)
            rect(W-171,128,171,199,pale)
            text(W-154,156,'CONSULTA RÁPIDA','Helvetica-Bold',8,terra)
            for row, (label,value) in enumerate(recipe.get('details',())[:3]):
                y = 178+row*47
                text(W-154,y,label.upper(),'Helvetica-Bold',8,terra)
                block(W-154,y+5,143,value,size=16,leading=16,font='Times-Roman')
            if not recipe.get('details'):
                block(W-154,180,124,yield_text,size=20,leading=23,font='Times-Roman')
            rect(W-261,308,90,19,GREEN)
            text(W-177,321,'Foto ilustrativa','Helvetica',7,IVORY,'right')
            ingredients_heading = 358

        text(M, ingredients_heading, 'Ingredientes', 'Times-Roman', 26, GREEN)
        heights = [ingredients_heading+12]*2
        cols = (len(recipe['ingredients'])+1)//2
        for number, item in enumerate(recipe['ingredients']):
            if recipe.get('source') or recipe.get('fixed_yield'):
                ingredient = display = item
            else:
                amount, unit, ingredient = item
                display = f'{amount*portions:g}'.replace('.',',')+' '+unit+' '+ingredient
            note = ingredient_note(recipe,ingredient,options['evitar'])
            column = int(number>=cols)
            x = M+column*(card_width+12)
            y = heights[column]
            _, h = paragraph(display,card_width-16)
            rect(x,y,card_width,h+8,pale)
            y = block(x+8,y+4,card_width-16,display+('*' if note else ''))+8
            if note:
                y = block(x+8,y,card_width-16,'* '+note,size=9.4,leading=12,color=terra)+5
            heights[column]=y
        top = max(heights)+30
        text(M,top,'Preparo em etapas','Times-Roman',26,GREEN)
        width=(W-2*M-20)/3
        y=top+15
        row_bottom=y
        stages=recipe.get('stage_titles',())
        icons=recipe.get('stage_icons',())
        for i,step in enumerate(recipe['steps']):
            if i and i%3==0:
                y=row_bottom+10
            x=M+(i%3)*(width+10)
            headline=stages[i] if i<len(stages) else ''
            _, hh=paragraph(headline,width-20,size=15,leading=17,font='Times-Roman') if headline else (None,0)
            _, sh=paragraph(step,width-20,size=11,leading=14)
            if y+45+hh+sh>781:
                raise ValueError('Ficha longa demais para o modelo de homologação: '+title)
            rect(x,y,width,45+hh+sh,pale)
            rect(x+10,y+10,23,19,GREEN)
            text(x+21.5,y+23,f'{i+1:02d}','Helvetica-Bold',8,IVORY,'center')
            if i<len(icons):
                utensil(icons[i],x+width-37,y+5)
            text_top=y+34
            if headline:
                text_top=block(x+10,text_top,width-20,headline,size=15,leading=17,font='Times-Roman')+4
            end=block(x+10,text_top,width-20,step)
            row_bottom=max(row_bottom,end+11)
        footer(recipe_start+index,back=True)
        pdf.showPage()
    if bonuses:
        number = recipe_start + len(recipes)
        for bonus_index, (title, rows) in enumerate(bonuses):
            bookmark(f'bonus-{bonus_index}')
            y = 800
            for label, recipe_index in rows:
                content = label if recipe_index is None else f'{label} · pág. {recipe_start+recipe_index:02d}'
                _, height = paragraph(content,W-2*M)
                if y+height > 775:
                    if y != 800:
                        footer(number,back=True)
                        pdf.showPage()
                        number += 1
                    rect(0,0,W,H,IVORY)
                    rect(0,0,W,120,GREEN)
                    text(M,41,f'BÔNUS {bonus_index+1}','Helvetica-Bold',9,gold)
                    block(M,57,W-2*M,title,size=30,leading=31,font='Times-Roman',color=IVORY)
                    y = 148
                top = y
                y = block(M,y,W-2*M,content,color=GREEN if recipe_index is not None else INK)+8
                if recipe_index is not None:
                    link(f'receita-{recipe_index}',M,top,W-M,y-2)
            footer(number,back=True)
            pdf.showPage()
            number += 1
    pdf.save()
    return stream.getvalue()

