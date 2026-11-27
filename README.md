# Dos Salvos para a Mesa na Vercel

Versão de homologação. A raiz orienta a abrir o link do pedido. O FastAPI oferece as rotas de pedido e download. O armazenamento deve ser um Vercel Blob **privado** conectado a este projeto. O PDF é produzido na própria requisição e o serviço guarda apenas o PDF e a existência do pedido. Arquivos de entrada reais ficam bloqueados nesta versão.

Defina no ambiente privado de homologação a variável `PEDIDOS_HOMOLOGACAO_CHAVE` com um valor longo e aleatório. Com ela, faça POST em `/api/homologacao/pedidos` com o cabeçalho Authorization no formato Bearer. Abra o link retornado e envie o `saved_posts.json`. O limite do upload é 4 MB. Não publique a chave nem compartilhe o link com terceiros.

Pendências de operação comercial: plano ou hospedagem comercial, integração da aprovação Hotmart, emissão e envio confiável dos links, política de exclusão, obtenção autorizada e verificação das receitas reais, acervo completo e testes de entrega.

## WhatsApp e domínio

Configure `PEDIDOS_WHATSAPP` no ambiente com o número de atendimento no formato internacional (DDI + DDD + número). A área do pedido então apresenta **Falar pelo WhatsApp**, com uma mensagem inicial que não contém o token privado, dados do pedido ou receitas. O contato abre uma conversa para a cliente enviar quando desejar. Enquanto a configuração estiver ausente, nenhum link de atendimento é exibido.

As rotas de pedido e API usam o mesmo domínio da página. Cadastre na hospedagem o domínio escolhido para a área privada. A integração de pagamento deve emitir os links daquele domínio após verificar o pagamento.

## Modelo editorial do PDF

O gerador usa `mockup-campanha.webp` na primeira página, seguido do índice clicável e de uma página por receita. O acervo pode informar foto, dados rápidos, títulos de etapas e utensílios conferidos. As fotos e os desenhos ficam vinculados à receita. O PDF não inclui links externos para posts. As fotos de brownie e mousse usadas na amostra vêm do Pexels (imagens 6095744 e 30616908).
