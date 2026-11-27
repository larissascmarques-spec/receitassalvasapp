from base64 import urlsafe_b64encode
from html import escape
import hmac
import json
import os
import re
from pathlib import Path
import secrets
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool
from vercel import blob

from livro import generate_demo
from servidor import TOKEN, import_saved, preferences, token_hash

ROOT = Path(__file__).resolve().parent
MAX_BODY = 4 * 1024 * 1024
PRIVATE = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
           'X-Robots-Tag': 'noindex, nofollow', 'X-Content-Type-Options': 'nosniff'}
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
sample = import_saved((ROOT / 'saved_posts.json').read_bytes(), 'json')
sample_urls = {item['url'] for item in sample}


def problem(message, status):
    return JSONResponse({'erro': message}, status_code=status, headers=PRIVATE)


def order_path(token):
    return f'homologacao/{token_hash(token)}'


async def read_blob(path):
    try:
        item = await blob.get_blob(path, access='private')
    except blob.BlobNotFoundError:
        return None
    return None if item is None else item.body


async def save_blob(path, payload, mime, overwrite=False):
    await blob.put_blob(path, payload, access='private', content_type=mime,
                        allow_overwrite=overwrite, cache_control_max_age=0)


async def order_exists(token):
    return await read_blob(order_path(token) + '/pedido.json') is not None


@app.get('/')
async def home():
    return HTMLResponse('<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
                        '<title>Dos Salvos para a Mesa</title><h1>Dos Salvos para a Mesa</h1>'
                        '<p>Abra o link privado recebido para consultar seu pedido.</p></html>', headers=PRIVATE)


@app.get('/teste')
async def test_page():
    if os.getenv('VERCEL_ENV') != 'preview':
        return problem('Teste disponível apenas na prévia protegida.', 404)
    return FileResponse(ROOT / 'checkout-teste.html', headers=PRIVATE)


@app.get('/saved_posts.json')
async def sample_file():
    if os.getenv('VERCEL_ENV') != 'preview':
        return problem('Arquivo indisponível.', 404)
    return FileResponse(ROOT / 'saved_posts.json', filename='saved_posts.json', headers=PRIVATE)


@app.post('/teste')
async def browser_test_order(request: Request):
    if os.getenv('VERCEL_ENV') != 'preview':
        return problem('Teste disponível apenas na prévia protegida.', 404)
    if request.headers.get('sec-fetch-site') != 'same-origin':
        return problem('Abra a página de teste e tente novamente.', 403)
    token = secrets.token_urlsafe(32)
    try:
        await save_blob(order_path(token) + '/pedido.json', b'{}', 'application/json')
    except blob.BlobError:
        return problem('O armazenamento de teste está indisponível.', 503)
    return RedirectResponse('/pedido/' + token, status_code=303, headers=PRIVATE)



def purchase_config():
    return (os.getenv('HOTMART_HOTTOK'), os.getenv('HOTMART_PRODUCT_ID'),
            os.getenv('PEDIDOS_ATIVACAO_CHAVE'))


def purchase_digest(secret, purpose, transaction, email=''):
    return hmac.digest(secret.encode(), json.dumps([purpose, transaction, email]).encode(), 'sha256')


def purchase_details(transaction, email):
    transaction = transaction.strip().upper() if isinstance(transaction, str) else ''
    email = email.strip().casefold() if isinstance(email, str) else ''
    if not re.fullmatch(r'HP[A-Z0-9]{5,60}', transaction) or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email) or len(email) > 254:
        raise ValueError('Confira o e-mail da compra e o código da transação.')
    return transaction, email


def activation_page(message='', status=200):
    info = f'<p role="status">{escape(message)}</p>' if message else ''
    return HTMLResponse(
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Ativar meu livro | Dos Salvos para a Mesa</title>'
        '<link rel="stylesheet" href="/estilo.css"></head><body>'
        '<main class="frame"><section class="card"><p class="eyebrow">DOS SALVOS PARA A MESA</p>'
        '<h1>Ativar meu livro</h1><p>Use os dados do comprovante enviado pela Hotmart.</p>'
        '<form method="post" action="/ativar"><p><label for="email">E-mail da compra</label><br>'
        '<input id="email" name="email" type="email" autocomplete="email" maxlength="254" required></p>'
        '<p><label for="transacao">Código da transação</label><br>'
        '<input id="transacao" name="transacao" type="text" placeholder="HP…" maxlength="62" required></p>'
        '<p><button class="button" type="submit">Ativar meu livro</button></p></form>'
        + info + '</section></main></body></html>', status_code=status, headers=PRIVATE)


async def bounded_body(request, limit):
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > limit:
            raise ValueError('Dados acima do limite.')
        data.extend(chunk)
    return bytes(data)


@app.get('/ativar')
async def activate_screen():
    return activation_page()


@app.post('/ativar')
async def activate_purchase(request: Request):
    hot_token, product, secret = purchase_config()
    if not all((hot_token, product, secret)):
        return activation_page('A ativação ainda está em configuração. Tente novamente mais tarde.', 503)
    try:
        fields = parse_qs((await bounded_body(request, 4096)).decode(), max_num_fields=4)
        transaction, email = purchase_details(fields.get('transacao', [''])[0], fields.get('email', [''])[0])
        key = purchase_digest(secret, 'aprovacao', transaction, email).hex()
        approved = await read_blob(f'hotmart/aprovacoes/{key}.json')
        if approved is None:
            return activation_page('Compra aprovada não localizada. Confira os dados do comprovante.', 404)
        token = urlsafe_b64encode(purchase_digest(secret, 'pedido', transaction, email)).decode().rstrip('=')
        path = order_path(token) + '/pedido.json'
        if await read_blob(path) is None:
            try:
                await save_blob(path, b'{"origem":"hotmart"}', 'application/json')
            except blob.BlobError:
                if await read_blob(path) is None:
                    raise
        return RedirectResponse('/pedido/' + token, status_code=303, headers=PRIVATE)
    except ValueError:
        return activation_page('Confira o e-mail e o código da transação no comprovante.', 400)
    except blob.BlobError:
        return activation_page('O armazenamento está temporariamente indisponível.', 503)


@app.post('/api/hotmart/webhook')
async def hotmart_purchase(request: Request):
    hot_token, product, secret = purchase_config()
    if not all((hot_token, product, secret)):
        return problem('Integração ainda não configurada.', 503)
    if not hmac.compare_digest(request.headers.get('x-hotmart-hottok', '').encode(), hot_token.encode()):
        return problem('Notificação não autorizada.', 401)
    try:
        body = json.loads(await bounded_body(request, 64 * 1024))
        if body['event'] != 'PURCHASE_APPROVED':
            return Response(status_code=204, headers=PRIVATE)
        data = body['data']
        if str(data['product']['id']) != product or data['purchase']['status'] != 'APPROVED':
            return Response(status_code=204, headers=PRIVATE)
        transaction, email = purchase_details(data['purchase']['transaction'], data['buyer']['email'])
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        return problem('Notificação inválida.', 400)
    key = purchase_digest(secret, 'aprovacao', transaction, email).hex()
    path = f'hotmart/aprovacoes/{key}.json'
    try:
        if await read_blob(path) is None:
            try:
                await save_blob(path, b'{}', 'application/json')
            except blob.BlobError:
                if await read_blob(path) is None:
                    raise
    except blob.BlobError:
        return problem('Tente reenviar a notificação.', 503)
    return Response(status_code=204, headers=PRIVATE)


@app.get('/api/saude')
async def health():
    return JSONResponse({'api': 'ok', 'modo': 'homologacao',
                         'armazenamento_configurado': bool(os.getenv('BLOB_STORE_ID') or os.getenv('BLOB_READ_WRITE_TOKEN'))},
                        headers=PRIVATE)


@app.post('/api/homologacao/pedidos')
async def create_test_order(request: Request):
    secret = os.getenv('PEDIDOS_HOMOLOGACAO_CHAVE')
    if not secret or not hmac.compare_digest(request.headers.get('authorization', '').encode(),
                                            ('Bearer ' + secret).encode()):
        return problem('Pedido indisponível.', 404)
    token = secrets.token_urlsafe(32)
    await save_blob(order_path(token) + '/pedido.json', b'{}', 'application/json')
    return JSONResponse({'link': '/pedido/' + token}, status_code=201, headers=PRIVATE)


def support_link():
    phone = re.sub(r'[+() .-]', '', os.getenv('PEDIDOS_WHATSAPP', ''))
    if not re.fullmatch(r'[1-9][0-9]{7,14}', phone):
        return ''
    query = urlencode({'text': 'Olá! Preciso de ajuda para gerar meu livro Dos Salvos para a Mesa.'})
    return f'https://wa.me/{phone}?{query}'


@app.get('/pedido/{token}')
async def order_page(token: str):
    if not re.fullmatch(TOKEN, token):
        return problem('Confira o link privado que você recebeu.', 404)
    page = (ROOT / 'pedido.html').read_text(encoding='utf-8')
    contact = support_link()
    if contact:
        from html import escape
        markup = ('<aside class="card suporte"><h2>Precisa de ajuda?</h2>'
                  '<p>Se você não conseguiu gerar seu livro, fale com o suporte.</p>'
                  f'<a class="button" href="{escape(contact, quote=True)}" '
                  'target="_blank" rel="noopener noreferrer">Falar pelo WhatsApp</a></aside>')
        page = page.replace('<!-- suporte-whatsapp -->', markup)
    return HTMLResponse(page, headers=PRIVATE)


@app.get('/api/pedido/{token}')
@app.post('/api/pedido/{token}')
async def order(token: str, request: Request):
    if not re.fullmatch(TOKEN, token):
        return problem('Confira o link privado que você recebeu.', 404)
    try:
        if not await order_exists(token):
            return problem('Confira o link privado que você recebeu.', 404)
        path = order_path(token)
        if await read_blob(path + '/livro.pdf') is not None:
            if request.method == 'POST':
                return problem('Seu livro já está pronto. Reabra o link para baixar.', 409)
            return JSONResponse({'status': 'pronto'}, headers=PRIVATE)
        if request.method == 'GET':
            return JSONResponse({'status': 'aguardando'}, headers=PRIVATE)
        record = await read_blob(path + '/pedido.json')
        if record == b'{"origem":"hotmart"}':
            return problem('Seu acesso foi ativado. A produção do livro personalizado ainda está indisponível.', 503)
        raw = bytearray()
        async for data in request.stream():
            if len(raw) + len(data) > MAX_BODY:
                return problem('Envie um JSON ou ZIP de até 4 MB.', 413)
            raw.extend(data)
        options = preferences(request.headers.get('x-preferencias', '{}'))
        links = import_saved(bytes(raw), request.headers.get('x-arquivo'))
        if not links or any(item['url'] not in sample_urls for item in links):
            return problem('Nesta homologação, use o JSON fictício fornecido. Solicitações com dados reais ainda não estão disponíveis.', 422)
        pdf = await run_in_threadpool(generate_demo, options, links)
        if pdf is None:
            return JSONResponse({'status': 'sem_fichas'}, headers=PRIVATE)
        if len(pdf) > MAX_BODY:
            return problem('O livro ultrapassou o limite de download deste ambiente.', 422)
        try:
            await save_blob(path + '/livro.pdf', pdf, 'application/pdf')
        except blob.BlobError:
            if await read_blob(path + '/livro.pdf') is None:
                raise
        return JSONResponse({'status': 'pronto', 'total': len(links)}, headers=PRIVATE)
    except (ValueError, RecursionError):
        return problem('Não foi possível ler o arquivo de Salvos ou as preferências.', 400)
    except blob.BlobError:
        return problem('O armazenamento do pedido está indisponível. Tente novamente em instantes.', 503)


@app.get('/api/pedido/{token}/livro')
async def download(token: str):
    if not re.fullmatch(TOKEN, token):
        return problem('Confira o link privado que você recebeu.', 404)
    try:
        if not await order_exists(token):
            return problem('Confira o link privado que você recebeu.', 404)
        pdf = await read_blob(order_path(token) + '/livro.pdf')
    except blob.BlobError:
        return problem('O armazenamento do pedido está indisponível.', 503)
    if pdf is None:
        return problem('Seu livro ainda não está pronto.', 409)
    return Response(pdf, media_type='application/pdf', headers={
        **PRIVATE, 'Content-Disposition': 'attachment; filename="Dos-Salvos-Para-a-Mesa.pdf"'})


@app.get('/{asset}')
def asset_file(asset: str):
    if asset not in {'estilo.css', 'pedido.js', 'mockup-campanha.webp'}:
        return problem('Página não encontrada.', 404)
    path = ROOT / (asset if asset.endswith('.webp') else 'public/' + asset)
    return FileResponse(path, headers=PRIVATE)
