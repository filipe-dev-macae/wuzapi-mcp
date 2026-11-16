# Evidências de validação

## WuzAPI

Versão usada nos testes reais: commit
`ef36fa4961e10b74b23ffa54d7f9b5c656829fee` do repositório oficial.
Compilada em Linux amd64 com Go 1.26.11 e `CGO_ENABLED=0`.

Antes de criar este adaptador, o titular pareou sua conta por código e confirmou
no WhatsApp que funcionaram:

- Botão de abrir URL.
- Botão de resposta rápida.
- Botão de copiar código fictício.
- Botão de ligação telefônica.
- Combinação de resposta, URL e copiar na mesma mensagem.
- Link preview de um link curto do Mercado Livre, incluindo sua apresentação.

Esses envios foram feitos diretamente pela API WuzAPI. O remetente e o
destinatário eram o mesmo número do titular: a validação foi na conversa consigo
mesmo. Isso não substitui teste de entrega entre contas distintas ou em versões
diferentes de Android, iOS e WhatsApp Web. Não há números, códigos de pareamento,
tokens ou mensagens privadas neste documento.

O relatório local anterior, fora deste repositório, contém os IDs das mensagens
e o procedimento. Não publique bancos, QR Codes ou logs para reproduzir o teste.

## Adaptador MCP

Testes automatizados em `tests/` verificam:

- Mapeamento de botões mistos e `LinkPreview` para os payloads WuzAPI.
- Validação de campos de botão e URLs sem credenciais embutidas.
- Autenticação HTTP: nenhuma chave/chave inválida é rejeitada.
- Handshake MCP `2025-06-18` e descoberta de ferramentas via Streamable HTTP.
- Revogação de chave, escopos e isolamento por ID de instância.
- Ocultação de tokens e segredos nas respostas administrativas.
- Bloqueio de destinos externos, endpoints fora do catálogo e path traversal.
- Ausência de retry automático após timeout e de redirecionamento autenticado.
- Criação, revogação e rotação de chave sem imprimir seu valor.
- Geração do catálogo excluindo rotas comentadas.
- Backup/restauração e rollback preservando o estado da implantação malsucedida.

Na VPS também foram executados:

- Smoke test de um binário candidato com banco e credenciais temporários,
  sem conectar conta WhatsApp.
- Cliente MCP autenticado pela porta real, descoberta de ferramentas e consulta
  de saúde até o backend real.
- Migração da sessão pareada para serviço `systemd --user`.
- Backup consistente real seguido da reinicialização e consulta pelo MCP.
- Consulta de upstream que confirmou a versão já atualizada, sem implantação nova.

Após autorização do titular, foram enviados testes reais pelo Composio/MCP:
link no corpo com botão de URL, resposta citada com preview, reação 👍 e card
com imagem da oferta e botão. As chamadas retornaram sucesso; a confirmação
visual desses novos formatos ainda está pendente. Uma consulta de grupos
também funcionou, sem alterações. Procedimentos em `WHATSAPP.md`.

Nesse teste foi corrigida a extração de schemas legados em `definitions`,
usados pelo OpenAPI do WuzAPI. O catálogo agora contém 57 schemas consultáveis.
Os 19 testes passaram, incluindo regressão desse formato. Os schemas de
mensagem, reação e criação de grupo foram consultados pelo Composio real.

## Ainda não validado

- Chamada partindo da ZapIA; o conector Composio já foi validado.
- Aplicação da configuração MCP dentro do OpenBot.
- Inicialização depois de reboot real da VPS.
- Atualização real para um commit futuro; rollback foi exercitado em testes.
- Todos os demais endpoints do catálogo em contas WhatsApp reais.

## Repetir as verificações

Publicação validada em 16/11/2026: Cloudflare Tunnel saudável com quatro
conexões; HTTPS `/healthz` retornou 200 e `/mcp` sem chave retornou 401.
Um cliente MCP real usando a chave dedicada ao Composio descobriu as 13
ferramentas, consultou saúde e confirmou a sessão conectada/autenticada pelo
endpoint público. Nenhuma mensagem foi enviada nessa validação.

Composio validado em 16/11/2026: conector `Wuzapi MCP - AWS` ativo, ferramentas
de saúde e listagem de instâncias executadas com sucesso pelo conector real.
A sessão retornou conectada e autenticada. Nenhuma mensagem foi enviada.

Os serviços foram ajustados para logs privados, pois a conta de sistema
`openbot` não tem acesso ao journal global. Unidades systemd foram verificadas,
e acesso aos arquivos de log como `openbot` foi conferido.

```bash
cd /srv/wuzapi-mcp
.venv/bin/pytest -q
```

Para a verificação local com cliente real, consulte `CONNECTORS.md`. Para
atualização, backup e consulta de logs, consulte `OPERATIONS.md`.
