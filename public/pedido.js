const form = document.querySelector('#pedido');
const file = document.querySelector('#arquivo');

const categoryFields = [...form.querySelectorAll('input[name="categorias"]')];
const [allCategories, ...individualCategories] = categoryFields;
for (const field of categoryFields) {
  field.addEventListener('change', () => {
    if (!field.checked) return;
    if (field === allCategories) {
      individualCategories.forEach(category => { category.checked = false; });
    } else {
      allCategories.checked = false;
    }
  });
}

const heading = document.querySelector('#estado');
const message = document.querySelector('#mensagem');
const error = document.querySelector('#erro');
const download = document.querySelector('#download');
const submit = form.querySelector('button');
const token = location.pathname.split('/').at(-1);
const endpoint = '/api/pedido/' + encodeURIComponent(token);
let pollTimer;
const states = {
  aguardando_fontes: ['Receitas aguardando conferência', 'Os links foram recebidos. Envie o arquivo novamente depois que as fichas dos posts forem revisadas.'],
  sem_fichas: ['Nenhuma ficha de teste corresponde', 'Escolha outra categoria e envie novamente pelo mesmo link.'],
  falha: ['Não foi possível montar o PDF', 'Tente enviar novamente pelo mesmo link.'],
  aguardando: ['Aguardando seus Salvos', 'Comece pelo envio do arquivo.'],
  recebido: ['Arquivo recebido', 'Suas preferências foram salvas. Volte pelo mesmo link para acompanhar seu pedido.'],
  montando: ['Montando seu livro', 'Volte pelo mesmo link para acompanhar seu pedido.'],
  revisao: ['Precisamos de outro arquivo', 'Você pode corrigir o envio usando o mesmo link.'],
  pronto: ['Seu livro está pronto', 'Baixe o PDF para consultar as receitas e os bônus.'],
};
function show(order) {
  [heading.textContent, message.textContent] = states[order.status];
  if (order.status === 'recebido' && order.total === 0) {
    message.textContent = 'O arquivo não trouxe links de publicações. Suas preferências foram salvas para a seleção das receitas.';
  }
  form.hidden = !['aguardando', 'revisao', 'sem_fichas', 'falha', 'aguardando_fontes'].includes(order.status);
  download.hidden = order.status !== 'pronto';
  download.href = endpoint + '/livro';
  clearTimeout(pollTimer);
  if (order.status === 'montando') pollTimer = setTimeout(load, 1000);
}
async function read(response) {
  if (!response.headers.get('content-type')?.includes('application/json')) {
    throw new Error('O servidor de pedidos está indisponível. Confira o link recebido.');
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.erro || 'Tente novamente em instantes.');
  return data;
}
async function load() {
  try {
    show(await read(await fetch(endpoint, {cache:'no-store'})));
  } catch (issue) {
    heading.textContent = 'Não foi possível abrir o pedido';
    message.textContent = issue.message;
    if (pollTimer) pollTimer = setTimeout(load, 3000);
  }
}
file.addEventListener('change', () => {
  document.querySelector('#nome-arquivo').textContent = file.files[0]?.name || 'Escolher ZIP ou JSON';
  error.textContent = '';
});
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (submit.disabled) return;
  const selected = file.files[0];
  if (!selected || !/\.(zip|json)$/i.test(selected.name) || selected.size > 4 * 1024 * 1024) {
    error.textContent = 'Escolha um ZIP ou JSON de até 4 MB.';
    return;
  }
  const fields = new FormData(form);
  const preferences = {categorias:fields.getAll('categorias'), pessoas:Number(fields.get('pessoas')), evitar:fields.get('evitar').trim()};
  submit.disabled = true;
  submit.textContent = 'Enviando…';
  error.textContent = '';
  try {
    const result = await read(await fetch(endpoint, {
      method:'POST',
      headers:{'Content-Type':'application/octet-stream','X-Arquivo':selected.name.toLowerCase().endsWith('.zip') ? 'zip' : 'json','X-Preferencias':encodeURIComponent(JSON.stringify(preferences))},
      body:selected
    }));
    show(result);
  } catch (issue) {
    error.textContent = issue.message;
  } finally {
    submit.disabled = false;
    submit.textContent = 'Enviar Salvos e preferências';
  }
});
load();
