import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import sqlite3
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
import zipfile
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('PEDIDOS_DADOS', ROOT / 'dados')).resolve()
LIMIT = 20 * 1024 * 1024
CATEGORIES = ('Pães e massas', 'Refeições', 'Lanches', 'Sobremesas')
ALL_CATEGORIES = 'De tudo um pouco'
TOKEN = r'[A-Za-z0-9_-]{43}'
ROUTE = re.compile(r'/api/pedido/(' + TOKEN + r')(/livro)?')
SAVED_NAME = re.compile(r'(saved_posts|saved_collections|publica[cç][oõ]es_salvas)(?:_\d+)?\.json', re.I)
SAVED_ROOTS = {'saved_saved_media', 'saved_saved_collections', 'saved_posts', 'saved_collections'}
MEDIA_PATH = re.compile(r'/(?:p|reel|reels|tv)/([A-Za-z0-9_-]{1,64})/?')


@contextmanager
def database():
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / 'pedidos.sqlite3')
    db.row_factory = sqlite3.Row
    try:
        with db:
            db.execute("""CREATE TABLE IF NOT EXISTS pedidos (
                referencia TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'aguardando', links TEXT,
                preferencias TEXT, livro BLOB)""")
            yield db
    finally:
        db.close()


def token_hash(token):
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def parse_json(raw):
    payload = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(payload, dict):
        raise ValueError('Escolha o JSON de publicações salvas da exportação do Instagram.')
    roots = [payload[key] for key in SAVED_ROOTS.intersection(payload) if isinstance(payload[key], list)]
    if not roots:
        raise ValueError('Escolha o JSON de publicações salvas da exportação do Instagram.')
    links = {}

    def walk(item, collection=None):
        if isinstance(item, list):
            for value in item:
                walk(value, collection)
        elif isinstance(item, dict):
            title = item.get('title')
            if isinstance(title, str) and (item.get('string_list_data') is not None or 'saved_media' in item):
                collection = title.strip()[:120] or collection
            href = item.get('href')
            if isinstance(href, str) and len(href) <= 2048:
                try:
                    url = urlsplit(href)
                    match = MEDIA_PATH.fullmatch(url.path)
                    if url.scheme == 'https' and url.netloc.lower() in {'www.instagram.com', 'instagram.com', 'm.instagram.com'} and match:
                        code = match.group(1)
                        record = links.setdefault(code, {'url': 'https://www.instagram.com' + url.path.rstrip('/') + '/', 'colecoes': []})
                        if collection and collection not in record['colecoes']:
                            record['colecoes'].append(collection)
                except ValueError:
                    pass
            for key, value in item.items():
                if key != 'href':
                    walk(value, collection)

    for root in roots:
        walk(root)
    return links


def import_saved(raw, kind):
    if kind == 'json':
        return list(parse_json(raw).values())
    if kind != 'zip':
        raise ValueError('Envie um ZIP ou JSON de publicações salvas.')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files = [item for item in archive.infolist()
                     if not item.is_dir() and SAVED_NAME.fullmatch(PurePosixPath(item.filename).name)]
            if not files:
                raise ValueError('O ZIP não contém o JSON de publicações salvas. Exporte a seção de Salvos no formato JSON.')
            if len(files) > 50 or sum(item.file_size for item in files) > LIMIT:
                raise ValueError('O conteúdo de Salvos excede o limite de 20 MB.')
            links = {}
            for item in files:
                with archive.open(item) as stream:
                    part = parse_json(stream.read(LIMIT + 1))
                for code, record in part.items():
                    saved = links.setdefault(code, {'url': record['url'], 'colecoes': []})
                    saved['colecoes'] = list(dict.fromkeys(saved['colecoes'] + record['colecoes']))
            return list(links.values())
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError):
        raise ValueError('Não conseguimos abrir esse ZIP. Baixe o arquivo novamente pelo Instagram.') from None


def preferences(header):
    data = json.loads(unquote(header))
    if not isinstance(data, dict):
        raise ValueError('Revise suas preferências.')
    tags, people, avoid = data.get('categorias'), data.get('pessoas'), data.get('evitar')
    if (not isinstance(tags, list) or len(tags) > 4
            or any(not isinstance(tag, str) or tag not in (*CATEGORIES, ALL_CATEGORIES) for tag in tags)
            or type(people) is not int or not 1 <= people <= 12
            or not isinstance(avoid, str) or len(avoid) > 300):
        raise ValueError('Revise suas preferências.')
    selected = list(CATEGORIES) if ALL_CATEGORIES in tags else list(dict.fromkeys(tags))
    return {'categorias': selected, 'pessoas': people, 'evitar': avoid.strip()}


def process_demo(key, options, links):
    try:
        from livro import generate_demo
        pdf = generate_demo(options, links)
    except Exception:
        with database() as db:
            db.execute("UPDATE pedidos SET status='falha' WHERE token_hash=? AND status='montando'", (key,))
        return
    with database() as db:
        db.execute("""UPDATE pedidos SET status=?, livro=?, links=NULL, preferencias=NULL
            WHERE token_hash=? AND status='montando'""", ('pronto' if pdf else 'sem_fichas', pdf, key))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def reply(self, code, data, content_type, attachment=False):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Robots-Tag', 'noindex, nofollow')
        self.send_header('Content-Security-Policy', "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if attachment:
            filename = 'Dos-Salvos-Para-a-Mesa.pdf' if attachment is True else attachment
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def json(self, code, data):
        self.reply(code, json.dumps(data, ensure_ascii=False).encode(), 'application/json; charset=utf-8')

    def do_GET(self):
        route = urlsplit(self.path).path
        if self.server.test_mode and route in {'/teste', '/saved_posts.json'}:
            name, kind = ('checkout-teste.html', 'text/html; charset=utf-8') if route == '/teste' else ('saved_posts.json', 'application/json')
            self.reply(200, (ROOT / name).read_bytes(), kind, attachment='saved_posts.json' if route.endswith('.json') else False)
            return
        assets = {
            '/estilo.css': ('estilo.css', 'text/css; charset=utf-8'),
            '/pedido.js': ('pedido.js', 'text/javascript; charset=utf-8'),
            '/mockup-campanha.webp': ('mockup-campanha.webp', 'image/webp'),
        }
        if route in assets:
            name, kind = assets[route]
            self.reply(200, (ROOT / name).read_bytes(), kind)
            return
        if re.fullmatch(r'/pedido/' + TOKEN, route):
            self.reply(200, (ROOT / 'index.html').read_bytes(), 'text/html; charset=utf-8')
            return
        match = ROUTE.fullmatch(route)
        if not match:
            self.json(404, {'erro': 'Abra o link privado do seu pedido.'})
            return
        with database() as db:
            fields = 'status, livro' if match[2] else 'status, links'
            order = db.execute('SELECT ' + fields + ' FROM pedidos WHERE token_hash = ?', (token_hash(match[1]),)).fetchone()
        if not order:
            self.json(404, {'erro': 'Confira o link privado que você recebeu.'})
        elif not match[2]:
            self.json(200, {'status': order['status'], 'total': len(json.loads(order['links'] or '[]'))})
        elif order['status'] == 'pronto' and order['livro']:
            self.reply(200, order['livro'], 'application/pdf', attachment=True)
        else:
            self.json(409, {'erro': 'Seu livro ainda não está disponível.'})

    def do_POST(self):
        route = urlsplit(self.path).path
        if self.server.test_mode and route == '/teste':
            token = secrets.token_urlsafe(32)
            with database() as db:
                db.execute('INSERT INTO pedidos(referencia,token_hash) VALUES (?,?)',
                           ('teste-' + secrets.token_hex(12), token_hash(token)))
            self.send_response(303)
            self.send_header('Location', '/pedido/' + token)
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            return
        match = ROUTE.fullmatch(route)
        if not match or match[2]:
            self.json(404, {'erro': 'Confira o link privado que você recebeu.'})
            return
        key = token_hash(match[1])
        with database() as db:
            order = db.execute('SELECT status FROM pedidos WHERE token_hash = ?', (key,)).fetchone()
        if not order:
            self.json(404, {'erro': 'Confira o link privado que você recebeu.'})
            return
        if order['status'] not in {'aguardando', 'revisao', 'sem_fichas', 'falha'}:
            self.json(409, {'erro': 'Este pedido já recebeu um arquivo. Atualize a página para acompanhar.'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= LIMIT:
                raise ValueError('Escolha um ZIP ou JSON de até 20 MB.')
            options = preferences(self.headers.get('X-Preferencias', '{}'))
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('O envio foi interrompido. Tente novamente.')
            links = import_saved(raw, self.headers.get('X-Arquivo'))
        except (UnicodeError, json.JSONDecodeError, RecursionError):
            self.json(400, {'erro': 'Não conseguimos ler esse JSON. Confira o arquivo de publicações salvas.'})
            return
        except (TimeoutError, OSError):
            self.json(400, {'erro': 'O envio foi interrompido. Tente novamente.'})
            return
        except ValueError as issue:
            self.json(400, {'erro': str(issue)})
            return
        status = 'montando' if self.server.test_mode else 'recebido'
        with database() as db:
            changed = db.execute("""UPDATE pedidos SET status=?, links=?, preferencias=?, livro=NULL
                WHERE token_hash=? AND status IN ('aguardando','revisao','sem_fichas','falha')""",
                (status, json.dumps(links, ensure_ascii=False), json.dumps(options, ensure_ascii=False), key)).rowcount
        if changed:
            if self.server.test_mode:
                self.server.generation.submit(process_demo, key, options, links)
            self.json(200, {'status': status, 'total': len(links)})
        else:
            self.json(409, {'erro': 'Este pedido já recebeu um arquivo. Atualize a página para acompanhar.'})


def main():
    global DATA
    parser = argparse.ArgumentParser(description='Área de pedidos Dos Salvos para a Mesa')
    commands = parser.add_subparsers(dest='command', required=True)
    serve = commands.add_parser('servir')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--porta', type=int, default=8000)
    serve.add_argument('--teste', action='store_true')
    serve.add_argument('--abrir', action='store_true')
    create = commands.add_parser('criar')
    create.add_argument('referencia')
    create.add_argument('--base', default='http://localhost:8000')
    for name in ('ver', 'montando', 'revisao', 'entregar'):
        command = commands.add_parser(name)
        command.add_argument('referencia')
        if name == 'entregar':
            command.add_argument('pdf', type=Path)
    args = parser.parse_args()
    with database() as db:
        if args.command == 'criar':
            token = secrets.token_urlsafe(32)
            try:
                db.execute('INSERT INTO pedidos(referencia,token_hash) VALUES (?,?)', (args.referencia, token_hash(token)))
            except sqlite3.IntegrityError:
                parser.error('Já existe um pedido com essa referência.')
            print(args.base.rstrip('/') + '/pedido/' + token)
        elif args.command != 'servir':
            order = db.execute('SELECT status,links,preferencias FROM pedidos WHERE referencia=?', (args.referencia,)).fetchone()
            if not order:
                parser.error('Pedido não encontrado.')
            if args.command == 'ver':
                print(json.dumps({'status':order['status'], 'links':json.loads(order['links'] or '[]'),
                                  'preferencias':json.loads(order['preferencias'] or 'null')}, ensure_ascii=False, indent=2))
            elif order['status'] not in {'recebido', 'montando', 'revisao'}:
                parser.error('É preciso receber um arquivo antes de atualizar o pedido.')
            elif args.command == 'entregar':
                if args.pdf.stat().st_size > 50 * 1024 * 1024:
                    parser.error('O PDF deve ter até 50 MB.')
                pdf = args.pdf.read_bytes()
                if not pdf.startswith(b'%PDF-'):
                    parser.error('Informe um arquivo PDF.')
                db.execute("UPDATE pedidos SET status='pronto', livro=?, links=NULL, preferencias=NULL WHERE referencia=?", (pdf, args.referencia))
            else:
                db.execute('UPDATE pedidos SET status=? WHERE referencia=?', (args.command, args.referencia))
    if args.command == 'servir':
        if args.teste and args.host != '127.0.0.1':
            parser.error('O pedido de teste roda somente neste computador.')
        if args.teste:
            DATA = DATA / 'homologacao'
            with database() as db:
                db.execute("UPDATE pedidos SET status='falha' WHERE status='montando'")
        with ThreadingHTTPServer((args.host, args.porta), Handler) as server:
            server.test_mode = args.teste
            if args.abrir and args.teste:
                url = f'http://127.0.0.1:{server.server_port}/teste'
                print(url, flush=True)
                threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
            with ThreadPoolExecutor(max_workers=1) as executor:
                server.generation = executor
                server.serve_forever()


if __name__ == '__main__':
    main()
