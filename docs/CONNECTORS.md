# Conexão dos clientes

## Composio e ZapIA

O caminho escolhido é **ZapIA → Composio → nosso MCP**. A ZapIA já consegue
acessar conectores personalizados do Composio, conforme teste prévio do titular.
Isso dispensa OAuth/DCR no nosso MCP: o Composio usa API Key no cabeçalho.

O HTTPS já está publicado. Use como URL final, sem redirecionamentos:

```text
https://wuzapi-mcp.filipesantosdev.pro/mcp
```

Cadastre um Custom MCP no projeto Composio com estes valores:

```json
{
  "name": "WuzAPI",
  "mcp_url": "https://wuzapi-mcp.filipesantosdev.pro/mcp",
  "auth_schemes": [
    {"mode": "API_KEY", "headers": {"Authorization": "Bearer {{generic_api_key}}"}}
  ],
  "user_id": "all"
}
```

`user_id: "all"` compartilha a definição do conector com o projeto. Se precisar
de definição privada por usuário, use o ID correto e verifique o plano do
Composio. A disponibilidade de cada ferramenta nas sessões depende da inclusão
do toolkit `CUSTOM_*` retornado pelo cadastro e da conta conectada correta.

Conecte a conta fornecendo a chave dedicada ao Composio, armazenada na VPS em
`/var/lib/openbot/wuzapi/secrets/composio.key`. Transfira-a por um meio privado,
nunca em URL, README, issue ou commit. Não use o token administrativo do WuzAPI.

As ferramentas sincronizam após a conexão. Teste `health` e `list_instances`
antes de autorizar envios. Depois, selecione esse conector na conexão da ZapIA
com o Composio. O primeiro teste com mensagens deve ter destinatário e conteúdo
explicitamente autorizados.

O recurso Custom MCP do Composio é experimental. Consulte os passos atuais em:
https://docs.composio.dev/docs/extending-sessions/custom-mcp

O titular cadastrou o conector **Wuzapi MCP - AWS**, toolkit
`custom_wuzapi_mcp_aws`. Em 16/11/2026, a conexão foi encontrada como ativa e
as ferramentas `CUSTOM_WUZAPI_MCP_AWS_HEALTH` e
`CUSTOM_WUZAPI_MCP_AWS_LIST_INSTANCES` executaram com sucesso pelo Composio,
confirmando uma instância conectada e autenticada. O envio de botões também
foi descoberto; nenhuma mensagem foi enviada nessa validação. A chamada
partindo da ZapIA não foi acompanhada diretamente nessa validação. Depois, o
titular relatou que ela conseguiu enviar pelo conector, mas substituiu um
carrossel solicitado por uma mensagem com três botões. A conexão funcionar
não comprova que o agente executou corretamente o formato pedido. A skill
agora descreve o fluxo de carrossel e os bloqueios de imagem sem substituição.

Se mudar somente o catálogo de endpoints, os nomes das ferramentas MCP
permanecem iguais. Se o código adicionar ferramentas MCP, sincronize o toolkit
novamente conforme a documentação do Composio.

A skill adicionou `get_usage_guide` (14 ferramentas no servidor). Sincronize a
lista e leia o guia pelo conector antes de operar. Como o Composio pode repassar
somente ferramentas, não presuma propagação automática das instructions nem
da extensão Skills até a ZapIA. Veja [mecanismos e limites](SKILLS.md).

## OpenBot

O usuário Linux `openbot` pode acessar diretamente:

```text
http://127.0.0.1:8082/mcp
Authorization: Bearer <conteúdo de openbot.key>
```

A chave está em `/var/lib/openbot/wuzapi/secrets/openbot.key`. O campo `type`
exato depende do cliente. Um exemplo comum de configuração é:

```json
{
  "mcpServers": {
    "wuzapi": {
      "type": "http",
      "url": "http://127.0.0.1:8082/mcp",
      "headers": {"Authorization": "Bearer <CHAVE_PRIVADA_DO_OPENBOT>"}
    }
  }
}
```

Esse é um modelo, não um arquivo aplicado por este instalador à configuração
interna do OpenBot. O titular confirmou posteriormente que o acesso pelo
OpenBot funcionou; o arquivo exato que ele configurou não foi inspecionado aqui.
O arquivo que receber a chave deve ter permissão `600`. Para outro sistema
externo, use HTTPS público e uma chave exclusiva.

Também é possível testar localmente sem imprimir o segredo:

```python
import asyncio
from pathlib import Path
from fastmcp import Client

async def main():
    key = Path('/var/lib/openbot/wuzapi/secrets/openbot.key').read_text().strip()
    async with Client('http://127.0.0.1:8082/mcp', auth=key) as client:
        print([tool.name for tool in await client.list_tools()])
        result = await client.call_tool('health', {})
        print(result.data)

asyncio.run(main())
```

## Outros sistemas

Crie uma chave nova por sistema com o CLI documentado em `SECURITY.md`.
Clientes externos precisam aceitar Streamable HTTP e Bearer em cabeçalho.
Conexão direta da ZapIA a este MCP não está implementada: ela exige OAuth/DCR;
o caminho escolhido passa pelo Composio.
