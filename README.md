# WuzAPI MCP

Servidor MCP em Python para gerenciar o WuzAPI pelo OpenBot, Composio e outros
clientes. Inclui botões interativos, link preview, gestão de instâncias e
pareamento por código ou QR Code.

```text
ZapIA → Composio ── HTTPS + Bearer API Key ──┐
                                          ├─ MCP → WuzAPI privado → WhatsApp
OpenBot ─────────── HTTP local + chave ─────┘
```

O servidor utiliza [FastMCP](https://github.com/PrefectHQ/fastmcp). O WuzAPI
continua sendo um projeto independente, instalado a partir do
[repositório oficial](https://github.com/asternic/wuzapi).

## Estado da implantação

- Serviços locais instalados e executados como `openbot`, sem sudo nessa conta.
- WuzAPI em `127.0.0.1:8081`; MCP em `http://127.0.0.1:8082/mcp`.
- Sessão originalmente pareada para o teste preservada na migração.
- Endereço público: `https://wuzapi-mcp.filipesantosdev.pro/mcp`, publicado
  por Cloudflare Tunnel após autorização explícita do proprietário.
- HTTPS autenticado validado: descoberta das ferramentas, consulta de saúde
  até o WuzAPI e status da sessão. Sem chave, o endpoint retorna HTTP 401.
- Conector `Wuzapi MCP - AWS` ativo no Composio; saúde e instâncias consultadas
  com sucesso por ele. O titular confirmou uso bem-sucedido pelo OpenBot;
  relatou dificuldade da ZapIA ao executar o formato de carrossel solicitado.
- Atualização automática aplicada em 16/11/2026: commit WuzAPI
  `3ee4ecddd4c935f492fc54cde81923fc0938b36b`, com 114 operações no catálogo ativo.
- Nenhum segredo, sessão, banco, backup ou número real faz parte deste repositório.

## Recursos

| Ferramenta | Uso | Escopo |
| --- | --- | --- |
| `get_usage_guide` | Skill e referências por seção | `read` |
| `health` | Saúde do WuzAPI | `read` |
| `list_instances` | Instâncias e estados, com tokens ocultados | `read` |
| `create_instance` | Nova instância com token forte interno | `admin` |
| `session` | Status, conectar, desconectar ou logout | `read` / `write` |
| `pairing_code` | Código para vincular telefone | `write` |
| `pairing_qr` | Imagem de QR Code | `write` |
| `delete_instance` | Remoção completa ou preservando dispositivos | `admin` |
| `send_text` | Texto, com preview opcional | `send` |
| `send_buttons` | Resposta, URL, copiar, ligação e combinações | `send` |
| `configure_webhook` | Destino e assinaturas de eventos | `write` |
| `api_operations` | Descobrir outros endpoints e seus parâmetros | `read` |
| `api_schema` | Consultar schemas referenciados pelo catálogo | `read` |
| `api_call` | Usar endpoints JSON do catálogo | Conforme operação |

O catálogo inicial tem 113 operações extraídas das rotas **ativas** do WuzAPI.
O catálogo da release ativa pode incluir operações posteriores; a atualização
citada acima adicionou `/chat/send/raw`, um envio avançado de protobuf JSON.
Há acesso genérico a envio de mídias, grupos, contatos, enquetes, listas,
carrosséis, histórico e configurações. Esses recursos dependem das capacidades
e dos requisitos da versão instalada; não foram todos testados em celulares.

A gravação de voz por upload `multipart/form-data` não passa pelo adaptador JSON.
Para áudio, use os endpoints JSON `/chat/send/audio` ou outros que constarem do
catálogo. Histórico exige habilitar retenção na instância; não é ativado por
padrão pelo MCP. Webhooks são configurados no WuzAPI, não recebidos pelo MCP.

## Exemplos de chamadas

Antes da primeira operação, consulte `get_usage_guide`. O guia principal também
é enviado nas instruções da conexão e como skill/recursos MCP; detalhes em
[Skill e orientação automática](docs/SKILLS.md). Clientes decidem o que carregar
no contexto da LLM; ferramentas de WhatsApp continuam exigindo autorização.

Obtenha primeiro o `instance_id` com `list_instances`.

Texto com preview:

```json
{
  "instance_id": "ID_DA_INSTANCIA",
  "phone": "5511999999999",
  "text": "Veja esta oferta: https://example.com/oferta",
  "link_preview": true
}
```

Botões mistos com `send_buttons`:

```json
{
  "instance_id": "ID_DA_INSTANCIA",
  "phone": "5511999999999",
  "text": "Como você quer continuar?",
  "buttons": [
    {"type": "reply", "title": "Quero saber mais", "id": "interesse"},
    {"type": "cta_url", "title": "Abrir oferta", "url": "https://example.com/oferta"},
    {"type": "copy", "title": "Copiar código", "copy_code": "TESTE123"},
    {"type": "cta_call", "title": "Ligar", "phone_number": "+5511999999999"}
  ]
}
```

Os títulos têm até 20 caracteres. Os campos `image`, `footer`, `envelope` e
`message_id` são opcionais. O envelope padrão `original` foi validado no teste
real. `fork`, `viewonce`, imagens nos botões e `voice_call` não foram validados
nesse teste e continuam experimentais. Quantidade aceita pelo adaptador não é
garantia de exibição pelo WhatsApp.

Para parear: `session(action="connect")`, aguarde o início da conexão e use
`pairing_code` com DDI/DDD, sem pontuação. O titular confirma no WhatsApp.
Consulte `session(action="status")` até `loggedIn` ser verdadeiro. O retorno de
`connect` indica que o processo foi iniciado, não que o pareamento terminou.

## Instalação, conexão e manutenção

- [Instalar em uma VPS / ambiente local](docs/INSTALL.md)
- [Conectar Composio, ZapIA e OpenBot](docs/CONNECTORS.md)
- [Skill, descoberta e instruções aos agentes](docs/SKILLS.md)
- [Serviços, backups, atualização e recuperação](docs/OPERATIONS.md)
- [Autenticação, permissões e limites](docs/SECURITY.md)
- [Rotação manual de chaves, somente quando solicitada](docs/ROTATION.md)
- [Validação e resultados](docs/VALIDATION.md)
- [Grupos, reações, respostas citadas e cards com botões](docs/WHATSAPP.md)

Desenvolvimento:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install -e . --no-deps
.venv/bin/pytest -q
```

Os testes não usam contas reais e não enviam mensagens. Para iniciar, configure
os caminhos dos arquivos privados conforme `.env.example` e execute:

```bash
.venv/bin/python -m wuzapi_mcp.server
```

## Atualização automática

O timer consulta a branch `main` oficial a cada 15 minutos, com até 60 segundos
de dispersão. Quando há commit novo, compila e testa o WuzAPI, gera um catálogo
novo, testa o MCP, faz uma verificação isolada de API e, se tudo passar, cria
backup consistente e implanta a versão. Falhas de implantação acionam rollback.
Não há pedido de autorização por atualização: isso foi autorizado pelo titular.

As ferramentas MCP mantêm seus nomes. Endpoints novos aparecem no catálogo
atualizado, sem exigir implementar uma ferramenta por endpoint. Mudanças
incompatíveis nos contratos usados podem bloquear a implantação. O processo
não escreve correções de código por inteligência artificial nem garante
compatibilidade com qualquer mudança futura.

## Publicar este projeto no GitHub

O Git local está preparado; envie somente os arquivos do repositório. Confira
`git status --short` e o diff antes de criar o remoto. A pasta de execução é
separada do código. Nunca adicione `.env`, `*.key`, bancos, logs, QR Codes ou
backups com `git add -f`.

O workflow em `.github/workflows/ci.yml` executa os testes sem credenciais reais.
Criar o repositório remoto e fazer push exige autorização do proprietário.

## Licenças e limites

Adaptador sob [MIT](LICENSE). O catálogo contém material derivado do WuzAPI,
com atribuição e licença em [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Dependências conservam suas próprias licenças.

O WuzAPI usa uma integração não oficial com o WhatsApp. Mudanças no protocolo
podem interromper funcionalidades, e o uso pode acarretar bloqueio de contas.
Um retorno `Sent` não comprova entrega, leitura ou renderização do botão.
