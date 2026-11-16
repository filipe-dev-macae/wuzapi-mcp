# Skill e orientação automática dos clientes

A skill `wuzapi-mcp` é mantida em
[`wuzapi_mcp/skills/wuzapi-mcp/SKILL.md`](../wuzapi_mcp/skills/wuzapi-mcp/SKILL.md).
As três referências cobrem mensagens, administração e operação da VPS. Essa
é a fonte única: o servidor carrega os arquivos do pacote na inicialização,
e a ferramenta de consulta devolve o mesmo conteúdo servido como recursos.
Não há cópia de credenciais, números reais ou sessões dentro da skill.

## Como o agente recebe a orientação

| Caminho | O que acontece | Dependência do cliente |
| --- | --- | --- |
| Instruções de conexão | O guia principal inteiro é enviado em `initialize.result.instructions` no protocolo legado | O host precisa apresentar essas instruções ao modelo |
| Skill nativa | FastMCP publica descoberta e manifesto pela extensão Skills (SEP-2640) | Cliente precisa negociar a extensão; suporte ainda experimental |
| Recursos MCP | Arquivos disponíveis em `skill://wuzapi-mcp/...` | Cliente precisa oferecer leitura de resources ao agente |
| Ferramenta de consulta | `get_usage_guide` lê o guia ou uma referência | Funciona em clientes que só repassam tools, após sincronizar a ferramenta |

As descrições de envio e descoberta também apontam para `get_usage_guide`.
O guia orienta o agente a consultá-lo antes da primeira operação na sessão,
ou carregar apenas a referência necessária se já recebeu o guia na conexão.

**O servidor disponibiliza a orientação automaticamente, mas não controla o
prompt de todo cliente.** Um host pode ignorar instructions, recursos ou a
extensão. Nenhum mecanismo aqui força uma LLM a obedecer ou instala arquivos
na máquina do usuário sem que o host escolha isso. A skill também não substitui
autenticação, escopos, isolamento de instância ou autorização do proprietário.

## Consultar pelo MCP

```text
get_usage_guide()
get_usage_guide(section="messages")
get_usage_guide(section="administration")
get_usage_guide(section="operations")
```

As quatro opções são fechadas; o chamador não pode fornecer caminho de arquivo.
A ferramenta exige escopo `read`, não chama WuzAPI e não envia mensagens.
O transporte autenticado também protege os recursos. Não foi criada rota HTTP
pública de download da documentação.

URIs dos arquivos:

```text
skill://wuzapi-mcp/SKILL.md
skill://wuzapi-mcp/references/messages.md
skill://wuzapi-mcp/references/administration.md
skill://wuzapi-mcp/references/operations.md
```

Clientes FastMCP 4.2 podem usar `read_skill` para obter o pacote e verificar os
digests/tamanhos do manifesto. Clientes antigos continuam usando resources ou
a ferramenta; o teste de handshake `2025-06-18` cobre essa compatibilidade.

## Composio, ZapIA e OpenBot

No Composio, sincronize as ferramentas do Custom MCP após esta implantação.
A lista do servidor passa de 13 para 14 ferramentas. Confirme que a ferramenta
equivalente a `get_usage_guide` aparece no toolkit e execute uma leitura.
O prefixo `CUSTOM_*` é atribuído pelo Composio; não copie um slug presumido.
As descrições das ferramentas já existentes também mudaram e podem ser cacheadas.

Em 16/11/2026, após sincronização pelo titular, `get_usage_guide` foi descoberto
e executado pelo Composio com sucesso. A conexão retorna o guia atualizado.

Nesta sessão, a busca do conector ainda retornou as 13 ferramentas e descrições
antigas. A integração Composio disponível não oferece sincronização de Custom
MCP, e não há credencial administrativa de projeto configurada na VPS. Não foi
recriada a conexão nem pedida uma nova autorização desnecessária. A operação
oficial é [Sync a custom toolkit](https://docs.composio.dev/reference/api-reference/toolkits/postCustomToolkitsSync),
que usa API key do projeto Composio (diferente da chave deste MCP). Execute-a
por uma integração administrativa autorizada, informando o slug do seu toolkit
e, quando necessário, o ID da conta conectada. Não cole essa chave no chat.

No fluxo ZapIA → Composio, não presuma que as instructions do servidor original
sejam repassadas. Se o cliente permitir instruções próprias, use:

```text
Ao usar WuzAPI, consulte get_usage_guide do conector antes da primeira operação
e carregue a seção pertinente. Siga o guia e as autorizações do usuário.
```

Esse texto é uma opção para hosts que descartam instructions, não um novo
requisito do protocolo. No OpenBot conectado diretamente, reconectar ao MCP
atualiza a descoberta; a aplicação das instruções depende da implementação dele.

Para um agente com suporte local a Agent Skills, copie a pasta inteira
`wuzapi_mcp/skills/wuzapi-mcp` para o diretório de skills que ele documentar.
Não copie somente o SKILL.md, pois ele referencia três arquivos. Em instalações
na mesma máquina, um link para essa pasta evita cópias divergentes. Instalação
local é opcional: o servidor já oferece os mesmos arquivos remotamente.

A skill operacional opcional `skills/rotacionar-wuzapi`, na raiz do projeto,
orienta a rotação local de chave somente a pedido explícito. Não é servida como
ferramenta remota e tem invocação implícita desativada nos hosts que respeitam
`agents/openai.yaml`. Detalhes e limites em `ROTATION.md`.
Nesta VPS foi criado um link em `/home/ubuntu/.codex/skills/wuzapi-mcp` para a
fonte do projeto; o conteúdo pode ser descoberto pelo Codex em sessões futuras.
Isso não modifica a configuração interna de skills do OpenBot.

## Manutenção e validação

Inclua os arquivos Markdown no pacote Python ao publicar/buildar. Alterar o
guia requer reiniciar apenas `wuzapi-mcp.service`; não exige reconectar o
WhatsApp. Após mudar descrições ou adicionar ferramentas, sincronize o cliente.
O catálogo de operações segue a atualização automática do WuzAPI; a skill é
documentação versionada do adaptador e não é reescrita automaticamente.

Validações usadas:

- Validador Agent Skills: frontmatter, nome e integridade do conteúdo.
- Testes: descoberta nativa, leitura do manifesto e recursos, igualdade com
  retorno da ferramenta, rejeição de seção arbitrária, escopo e revogação de chave.
- Handshake legado: instructions e resources disponíveis, com ferramenta extra.
- Build de wheel: skill e referências presentes fora do checkout de desenvolvimento.
- Consulta real autenticada após reiniciar o MCP, sem enviar WhatsApp.

O validador e os testes não garantem obediência de uma LLM. Para avaliar um
cliente, peça que consulte o guia e descreva como enviaria um carrossel com
botão, sem executar o envio. A resposta deve usar a URL no botão, evitar
`LinkPreview` no card e diferenciar GIF como documento de GIF em loop.

## Referências pesquisadas

Repositórios oficiais consultados em 16/11/2026, com contagens de estrelas
obtidas na API pública GitHub (contagens variam):

- [PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp), cerca de 28,6 mil:
  biblioteca já instalada; [documentação de skills da versão 4.2.0](https://github.com/PrefectHQ/fastmcp/blob/v4.2.0/docs/servers/skills.mdx)
  orientou o uso de SkillCatalogProvider, arquivos e descoberta nativa.
- [anthropics/skills](https://github.com/anthropics/skills), cerca de 195,8 mil:
  estrutura SKILL.md e referências carregadas conforme a tarefa.
- [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk),
  cerca de 24,9 mil: implementação oficial e compatibilidade de protocolo.
- [Agent Skills Specification](https://agentskills.io/specification): formato
  portátil de nome, descrição e arquivos de referência.
- [MCP Lifecycle 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle):
  campo `instructions` na inicialização e negociação de capacidades.

Nenhum código externo desses repositórios foi copiado. A integração reutiliza
a dependência FastMCP existente, sem adicionar protocolo ou biblioteca nova.
