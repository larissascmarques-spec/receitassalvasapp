# Área do pedido | Dos Salvos para a Mesa

Protótipo funcional para homologar o fluxo pós-compra. Requer Python 3.10 ou superior. Usa SQLite e roda sem instalar pacotes.

## Teste local

Em um terminal, rode `python3 servidor.py servir`. Em outro, rode `python3 servidor.py criar DEMO` e abra o endereço exibido. Trate o link como uma senha. Cada pedido usa um token aleatório próprio e o banco guarda somente o hash do token.

Envie o JSON de publicações salvas ou um ZIP com os JSONs de Salvos. Os ZIPs são lidos em memória, sem extrair arquivos no servidor. Só as referências de publicações e as preferências são guardadas. O arquivo original é descartado após a análise. Quando o PDF é anexado, as referências e preferências são removidas do pedido.

## Operação de teste

- `python3 servidor.py ver DEMO` mostra as referências e preferências para a montagem.
- `python3 servidor.py montando DEMO` atualiza o status.
- `python3 servidor.py revisao DEMO` libera novo envio no mesmo link.
- `python3 servidor.py entregar DEMO livro.pdf` disponibiliza um PDF preparado externamente no link privado.

## Antes de receber pedidos reais

O checkout no material da página de vendas recebido ainda está vazio. Este protótipo usa criação e entrega manuais. A implantação precisa de servidor HTTPS com armazenamento persistente, publicação aprovada e política de retenção para os pedidos e PDFs. Para automatizar, conecte aprovação da Hotmart e e-mail ao fluxo privado, valide formatos com uma exportação real e integre a recuperação autorizada, o acervo e o gerador do livro. O PDF pode ser anexado no teste de entrega. A importação do ZIP ou JSON apenas registra referências aos posts.

## Simular como cliente

Extraia o ZIP inteiro. No Windows com Python 3.10+ e o comando `py`, dê dois cliques em `ABRIR-TESTE-WINDOWS.bat`. Na primeira execução ele instala a biblioteca gratuita de PDF em um ambiente local. A janela deve continuar aberta enquanto você testa. Alternativa: em um ambiente com ReportLab instalado, rode `python servidor.py servir --teste --abrir`.

1. Clique em **Simular compra aprovada** para receber um link privado naquele navegador.
2. Envie `saved_posts.json`, indique as preferências e clique em **Enviar Salvos e preferências**.
3. O servidor importa e deduplica os links, seleciona as fichas de teste, gera o PDF e libera **Baixar meu livro** no mesmo link. O navegador acompanha o estado automaticamente.
4. Compare a ficha com `referencia/pagina-aprovada.png`, a página original da venda. A amostra usa o fundo marfim, títulos verdes, ingredientes à esquerda e preparo à direita. A focaccia inclui a foto ilustrativa da referência fornecida.

Neste modo, o pagamento é simulado, a geração de PDF é real e só usa as quatro receitas ilustrativas do acervo incluído. A compra de teste abre diretamente o pedido, sem envio de e-mail. Os dados de teste ficam separados dos pedidos comuns. A montagem fica bloqueada se os filtros eliminarem todas as fichas. A geração de 200 fichas e dos bônus exige o acervo validado e a recuperação dos Salvos reais. O checkout, o e-mail e a operação hospedada ainda precisam de integração.
