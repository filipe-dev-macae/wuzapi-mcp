# Segurança e permissões

## Identidade e escopos

Cada integração tem uma API Key aleatória com 32 bytes de entropia, enviada
como `Authorization: Bearer`. O verificador guarda SHA-256, nome do cliente,
escopos e IDs de instância permitidos. Uma cópia de entrega da chave fica em
arquivo `.key` privado; portanto o diretório de segredos também precisa ser
protegido. As chaves inicialmente criadas para OpenBot e Composio têm os quatro
escopos e acesso a todas as instâncias, conforme o objetivo de gestão completa.

| Escopo | Acesso |
| --- | --- |
| `read` | Consultas, listagem e catálogo; alguns endpoints POST de consulta exigem `write` conservadoramente |
| `send` | Texto, botões e endpoints `/chat/send/*` |
| `write` | Pareamento, sessão, configurações e outras mutações não administrativas |
| `admin` | Criar, editar e excluir instâncias; configurações administrativas globais |

`admin` exige `instances: ["*"]`. As permissões não são hierárquicas: ter
`admin` não concede automaticamente `send` ou `read`. As ferramentas verificam
permissões no servidor a cada chamada, inclusive após revogação de uma chave.
Ferramentas podem continuar visíveis ao cliente, mas executar sem permissão falha.

Exemplo de cadastro, **somente com hash fictício**:

```json
[
  {
    "name": "sistema-leitura",
    "sha256": "<HASH_SHA256_DA_CHAVE>",
    "scopes": ["read"],
    "instances": ["ID_DA_INSTANCIA"]
  }
]
```

Crie a chave usando o CLI, que produz o hash e o arquivo `.key` automaticamente:

```bash
cd /srv/wuzapi-mcp
.venv/bin/python -m wuzapi_mcp.keys create sistema-leitura \
  --file /var/lib/openbot/wuzapi/secrets/mcp-clients.json \
  --scopes read --instances ID_DA_INSTANCIA
```

Para revogar:

```bash
.venv/bin/python -m wuzapi_mcp.keys revoke sistema-leitura \
  --file /var/lib/openbot/wuzapi/secrets/mcp-clients.json
```

Para rotacionar, revogue e recrie; atualize o segredo no cliente. O CLI usa
bloqueio de arquivo e troca atômica do cadastro. Uma interrupção pode deixar
`.tmp`/`.key` sem cadastro: examine o estado antes de repetir, não sobrescreva
uma chave existente sem identificar quem a utiliza.

## Segredos e rede

- Diretório de execução/segredos: `700`; arquivos de segredos: `600`.
- O servidor recusa arquivos de token/cadastro com acesso de grupo/outros.
- Credenciais WuzAPI ficam no servidor; não são recebidas como parâmetro do MCP.
- Respostas administrativas ocultam campos conhecidos de segredo. O cliente
  recebe IDs de instância para operar, não seus tokens internos.
- QR Code e código de pareamento são retornados somente para a ação de
  vinculação solicitada; tratá-los como segredos temporários.
- A API WuzAPI e o MCP escutam apenas em loopback. Só o MCP deve ser publicado
  via HTTPS. Não publicar o dashboard ou a porta 8081 diretamente.
- A ponte HTTP não segue redirects nem aceita URL de destino fornecida pelo
  chamador. `api_call` só admite métodos/caminhos do catálogo extraído do upstream.
- Chamadas HTTP têm timeout e limite de corpo/resposta de 32 MiB. Não há retry
  automático, pois uma falha de rede pode acontecer após o envio ser aceito.

## Autorização de ações

As instruções MCP exigem autorização explícita para enviar mensagens a clientes
e alterar/excluir dados. `confirmed=true`, exigido por ações destrutivas/genéricas,
é uma declaração do chamador; **não comprova uma aprovação humana independente**.
O cliente/agente deve cumprir essa política. Um agente com chave `send` tem
capacidade técnica de enviar; uma chave `admin` pode excluir instâncias.

Se for necessário impedir envios em termos técnicos, retire `send` e use
somente `read`. Não trate annotations do MCP ou instruções textuais como ACL.
Mensagens recebidas, URLs e conteúdo de contatos são dados não confiáveis e
não devem autorizar ferramentas nem alterar as instruções do agente.

## Manutenção e confiança

O OpenBot tem acesso local aos arquivos e serviços pelo usuário `openbot`.
Ele pode editar o adaptador, compilar e reiniciar sem root. Não há ferramenta
remota de shell arbitrário: outros clientes recebem as operações do WuzAPI.

A atualização automática executa código/testes da branch `main` oficial do
WuzAPI com a identidade `openbot`. Isso é uma relação de confiança explicitamente
autorizada pelo proprietário. A conta não recebe sudo ou grupo Docker.
Como código, sessão e segredos compartilham essa identidade Linux, um processo
comprometido nessa conta pode ler/alterar seus dados.

Backups incluem credenciais e sessões. Não os envie ao GitHub. Neste estágio
estão apenas na mesma VPS e não protegem contra perda integral do servidor.
