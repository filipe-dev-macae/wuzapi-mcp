# Prompt de implementação — WuzAPI com Codex CLI e Antigravity CLI

Copie o conteúdo a partir da próxima seção para o agente que fará a implantação.

## Objetivo

Reproduza a instalação de WuzAPI desta VPS em um ambiente independente. Mantenha a API de WhatsApp, o adaptador MCP e o backend de atendimento. Substitua o conector OpenBot por execução local não interativa com **Codex CLI** (`codex`) e **Google Antigravity CLI** (`agy`). Entregue os dois modos de execução e permita usar apenas um CLI instalado. Quando ambos existirem, selecione exatamente um por empresa/instância. Numa instalação que atende uma única empresa, um único processo de atendimento basta.

Use `codex` como padrão no exemplo de configuração. Configure `engine=codex` ou `engine=antigravity`, com modelo opcional sujeito aos modelos disponíveis para a conta. Uma falha do provedor deve aparecer como falha dessa execução. Troque o provedor de forma explícita após drenar o trabalho ou reconciliar o estado da fila. O CLI tem o papel de interpretar a conversa e propor ações, e o backend continua responsável por autorizar e executá-las.

Este pedido cobre implementação, configuração de exemplo e validação isolada no destino autorizado. Preserve a instalação que está rodando na VPS de origem. Caso só tenha acesso à origem, trabalhe em diretórios isolados e use banco vazio, fixtures, portas livres e processos de teste. Pare antes de publicar endpoint, vincular WhatsApp real, trocar webhook ativo, migrar estado, habilitar respostas reais ou contratar um plano. Esses passos exigem autorização explícita.

## Fonte e inventário

| Componente | Referência na VPS de origem |
| --- | --- |
| WuzAPI | Upstream oficial `asternic/wuzapi`. O runtime documentado fica em `/var/lib/openbot/wuzapi` com `source/`, `releases/<commit>/`, symlink `current`, `data/`, `secrets/`, `logs/` e `backups/`. A API responde em `127.0.0.1:8081`, com saúde em `/health`. |
| Adaptador MCP | `/srv/wuzapi-mcp`, repositório `filipe-dev-macae/wuzapi-mcp`. FastMCP por HTTP Streamable em `127.0.0.1:8082/mcp` com Bearer. Saúde em `/healthz`. |
| Atendimento | Fonte em `/home/ubuntu/Projects/aguaviva-attendance` e instalação em `/opt/aguaviva-attendance`. O backend usa webhook `POST /webhook`, SQLite e um worker. `8090` é a porta de exemplo. Use a configuração sanitizada para confirmar a porta no destino. |
| Conector a substituir | `aguaviva/connector.py` e o trecho de despacho em `aguaviva/bridge.py`. O conector atual responde em loopback na porta `8091`, recebe chamadas em `/invoke` e consulta recibos da API de Scripts locais do OpenBot. |
| Implantação atual | WuzAPI e MCP rodam como serviços de usuário. O serviço `aguaviva-attendance` roda como conta própria. A instalação foi configurada para atender somente no contato de teste do Água Viva. |

Use este repositório como ponto de partida. O adaptador MCP está na raiz e o código-base do atendimento está em [attendance/](attendance/). Os caminhos da VPS na tabela descrevem a instalação de referência. Em outro host, siga os caminhos e as permissões do destino.

Leia os `AGENTS.md` aplicáveis. No MCP, leia `docs/INSTALL.md`, `docs/OPERATIONS.md`, `docs/SECURITY.md`, `docs/CONNECTORS.md`, `docs/VALIDATION.md` e `docs/WHATSAPP.md`. Em `attendance/`, leia `README.md`, `deploy/config.example.json`, `deploy/attendance.service`, `deploy/POLICY.md`, os módulos `bridge.py`, `attendance_bridge.py`, `connector.py`, `result.py`, `attendance_media.py`, `backup.py` e os testes de segurança e migração.

Use o conteúdo versionado deste repositório para levar o MCP e o atendimento a outra VPS. A pasta `attendance/` inclui código, testes, dependências e exemplos. Crie a configuração e os diretórios privados no destino.

Para reproduzir a versão da VPS, use o commit da release ativa em `current/UPSTREAM_COMMIT`, obtido por acesso autorizado. A versão retornada por `/health` e o checkout `/home/ubuntu/Projects/wuzapi-test` servem como referências de diagnóstico. Em instalação nova sem acesso ao commit ativo, escolha e registre um commit oficial validado. Use a versão de Go exigida pelo `go.mod` e Python 3.12+ conforme os projetos. Reaproveite os locks, o build Go, os assets e a geração de `mcp-operations.json` a partir da mesma revisão de WuzAPI. Preserve o pin de whatsmeow.

## Fluxo de atendimento

```text
WhatsApp → WuzAPI → webhook assinado → backend de atendimento → fila SQLite
                                          ↓
                                   CLI escolhido por empresa
                                          ↓
                                     ações em JSON
                                          ↓
                              validação e autorização no backend
                                          ↓
                                   MCP → WuzAPI → WhatsApp
```

Use `POST /webhook` do backend como receptor. Preserve a validação HMAC-SHA256 do corpo bruto em `x-hmac-signature`, os limites de entrada, as inscrições necessárias e a deduplicação antes de devolver 2xx. Preserve os formatos de webhook e de mídia que a versão implantada realmente entrega. O processamento do modelo ocorre depois que a fila foi gravada.

Integre os CLIs no ponto onde o backend despacha e coleta a resposta do agente. Reutilize a fila, a máquina de estados e o tratamento de mídia, pausas e envios do código atual. Implemente a execução pela menor interface local compartilhada entre os dois CLIs. Elimine, no novo caminho, as chamadas `/v1/agents/...`, o reset de contexto via API e a dependência da conta, do serviço e do token local do OpenBot. O fluxo local pode chamar o executor diretamente. Mantenha um processo separado quando necessário para isolar permissões e credenciais.

Inicie uma execução nova por trabalho, inicialmente com uma execução por empresa de cada vez. O histórico e o estado do atendimento vêm do backend e são limitados à empresa, instância e conversa corretas. Preserve PN, LID e JID e use somente aliases validados. Monte a entrada com a política da empresa, o evento, o histórico relevante e dados operacionais necessários e verificados. Inclua pedidos anteriores ainda pendentes dentro do contexto permitido. Trate mensagens, transcrições, imagens e dados externos como conteúdo de entrada. Nenhum deles pode alterar as instruções do agente, o destinatário ou o escopo autorizado.

Persistir o ID estável do trabalho e identificar estados como pendente, em execução, concluído, falho e incerto deve permitir reinício sem perder fila ou repetir saída. Grave o resultado validável antes da etapa de envio, preservando o progresso das ações já aceitas. Use timeout, limite de entrada e saída e encerramento de subprocessos. Uma falha comprovadamente anterior a qualquer envio pode ser reprocessada de forma controlada. Se a execução ou um envio ficar incerto, siga as regras de reconciliação e evite replay cego.

## Comandos dos CLIs e contrato de execução

Valide as flags com `--version` e `--help` no destino. Use o binário por caminho absoluto e invoque com lista de argumentos, sem interpolação por shell, com diretório de trabalho isolado e configuração dedicada. Autentique cada provedor com a conta de serviço correspondente pelo método oficial disponível no destino. Faça o teste inicial com dados fictícios sob o mesmo usuário do systemd. Confira acesso ao modo não interativo, cota, latência e adequação do plano ao uso pretendido. Trate expiração, login ausente e limite do provedor como falhas observáveis.

### Codex CLI

Use a interface verificada no `codex-cli 0.170.0` da origem como referência:

```bash
codex -a never exec -s read-only --ephemeral --ignore-user-config --skip-git-repo-check --output-schema /caminho/schema.json -o /diretorio-privado-da-execucao/resultado.json -
```

Passe a entrada por stdin. Leia apenas o arquivo de resposta final em diretório privado por execução e trate código de saída diferente de zero, ausência de arquivo e conteúdo inválido como falhas. Carregue somente as instruções da empresa e os dados necessários. Para foto, use a entrada de imagem do CLI, como `--image`, a partir de arquivo temporário validado e pertencente ao trabalho.

### Google Antigravity CLI

Use o modo `stream-json` para colocar a mensagem em stdin e manter o conteúdo de clientes fora da linha de comando:

```bash
agy --input-format stream-json --output-format stream-json --json-schema /caminho/schema.json --print-timeout 90s --sandbox
```

Escreva uma linha no formato `{"event":"user","message":{"content":"..."}}` construída por serializador JSON. Feche stdin após o evento e consuma stdout/stderr de forma limitada. Exija saída do processo com código zero, um único evento terminal `result` com `result.status == "SUCCESS"` e leia `result.structured_output`. Valide a operação combinada de stdin e schema com a versão instalada. Verifique o isolamento e as permissões reais do CLI na conta de serviço, inclusive quando a flag de sandbox não estiver disponível no host. Preserve foto com entrada multimodal comprovada no destino. Se o modo instalado não aceitar a imagem, use o tratamento de mídia indisponível do atendimento e documente essa limitação.

### Validação compartilhada

Configure um diretório de trabalho e credenciais do provedor dedicados a cada serviço. Bloqueie acesso do agente às credenciais WuzAPI/MCP, aos bancos, aos dados de outras empresas, a endpoints internos de envio e a arquivos fora do trabalho. Aplique a separação no sistema Linux e nas permissões do CLI. Desabilite ferramentas de escrita, execução desnecessária e integrações MCP herdadas. Redija dados pessoais e detalhes de autenticação dos logs. Retenha apenas os dados necessários e limpe artefatos temporários com segurança.

Resposta normal esperada:

```json
{"actions":[{"operation":"text","body":{"Body":"Olá! Como posso ajudar?"}}]}
```

`{"actions":[]}` encerra a tarefa sem resposta ao cliente. Preserve `text`, `buttons`, `carousel`, `react` e `handoff` conforme os contratos existentes. Use um schema de saída compatível com os dois CLIs, mantenha a validação estrita de cada operação no backend e rejeite campos extras, destinos, IDs impostos pelo modelo, operações desconhecidas e payloads fora dos limites. O backend resolve o destinatário, IDs e conta remetente a partir do evento original. Se precisar de `actions_ref`, reaproveite o fluxo autenticado e valide caminho, tamanho, expiração e vínculo com a execução. Monte imagens/carrosséis com os helpers existentes, sem base64 no prompt ou JSON do modelo.

## Políticas comerciais, mídia e envio

- Mantenha regras e dados por empresa. Preserve as regras vigentes do Água Viva quando estiver reproduzindo esse atendimento, inclusive Stoqui/vitrine como fonte atual, horário comercial configurado em `America/Sao_Paulo` e a política de prévia de links. Em outra empresa, configure sua fonte, fuso, horário e gestão de exceções. Confira as regras executáveis em `Attendance.action`, além do texto em `deploy/POLICY.md`.
- Preserve imagem como mídia real quando suportada, áudio transcrito antes do CLI, limites e expiração do fluxo atual. Reaproveite Pillow, o worker de mídia e a configuração do faster-whisper/FFmpeg aplicável. Para catálogo, injete dados verificados pela integração existente ou por consulta restrita de leitura. Sem dado atual, siga a política de dúvida/encaminhamento da empresa.
- Preserve a pausa humana de 300 segundos, a distinção entre saída do bot e intervenção humana, a invalidação por mensagem mais recente, grupos somente quando autorizados, limites por contato e checagem final do evento. Leitura e presença também passam pela política de efeitos externos do backend. Para `handoff`, o gerente precisa estar habilitado e a confirmação ao cliente depende do aceite do encaminhamento.
- Comece com `dispatch_enabled=false`, `policy_approved=false`, `context_isolation_verified=false`, `allow_all_private=false`, `allow_manager=false`, listas vazias e efeito externo desligado em testes. Valide ações pelo guard existente, com chave MCP dedicada e limitada à instância e operações necessárias. Use mocks ou transporte simulado para provar o fluxo sem enviar WhatsApp.

## Instalação e migração

Reaproveite o systemd e os templates dos projetos. Use contas dedicadas sem sudo para rodar os serviços e substitua caminhos legados por diretórios sob o novo usuário de serviço. Parametrize portas, caminhos, instância, empresa, executor e configuração por unidade apenas onde houver necessidade real. Mantenha WuzAPI, MCP e webhook em loopback na implantação de host único. Para clientes MCP remotos autorizados, use o modelo de publicação HTTPS autenticada do projeto com hostname próprio e publicação explícita. Mantenha a API WuzAPI e o dashboard privados. Preserve a skill `wuzapi-mcp`, os escopos e o catálogo associado à release.

Em instalação limpa, gere chaves próprias em arquivos privados com permissão 600 e diretórios restritos. Pareamento de um número de teste só mediante autorização do titular. Em migração de estado já autorizada, faça snapshots consistentes separados para WuzAPI e atendimento pelos procedimentos dos projetos. Preserve a chave de criptografia correspondente aos dados WuzAPI existentes. Transfira dados e chaves autorizados por canal privado. Restaure em destino vazio, confira integridade e reconcilie os recibos pendentes do conector antigo e os envios incertos antes do corte. Documente a troca de webhook, o rollback que preserva o registro de saída e a prevenção de duas cópias ativas para a mesma identidade de WhatsApp. Na mesma VPS, uma réplica em paralelo usa sessão nova, portas e diretórios próprios e fixtures.

Reaproveite os comandos de backup e as unidades de manutenção do MCP, ajustados ao usuário novo. Entregue as etapas de build, testes, geração de catálogo, troca de release e rollback. A habilitação do timer de atualização e do túnel depende da configuração autorizada para o destino.

## Validação e entrega

1. Execute as suítes existentes. Rode `go test ./...` e build no WuzAPI e `pytest -q` nos ambientes do MCP e do atendimento.
2. Com execução falsa/injetável, teste seleção de ambos os provedores, parsing de saída, schema inválido, erro de autenticação, quota, timeout, interrupção e resultado ausente. Verifique isolamento entre chats e empresas, ausência de credenciais do backend no processo do CLI e rejeição de instruções recebidas pelo WhatsApp que tentem mudar destino ou executar ferramentas.
3. Faça um teste de ponta a ponta com webhook assinado fictício e MCP simulado. Mostre uma única ação para webhook duplicado. Cubra assinatura inválida, reinício antes e durante processamento, pausa humana, evento substituído, destinatário indevido, envio incerto e troca de executor com fila pendente. Teste mídia, links, horário e encaminhamento nos casos habilitados.
4. Quando disponível e autorizado, faça um smoke test real com cada CLI usando apenas conteúdo fictício. Confira autenticação, schema, latência e execução na conta do serviço. Valide saúde e autenticação do MCP sem enviar mensagens. Só faça teste real de WhatsApp para destinatário e formato expressamente autorizados. Registre aceite da API, entrega e aparência no telefone como evidências distintas.
5. Entregue o código reaproveitado e as mudanças do executor, exemplos sanitizados, unidades systemd, instruções de instalação e operação, roteiro de migração/rollback e resultados dos testes. Informe versões e commits, qual CLI foi exercitado de verdade, limites encontrados e o que depende de acesso ao destino. Considere concluída a réplica isolada quando o fluxo teste passar do webhook até o envio simulado e o backend iniciar sem qualquer componente do OpenBot.

## Documentação de referência

- [Upstream oficial do WuzAPI](https://github.com/asternic/wuzapi)
- [Modo headless do Google Antigravity CLI](https://antigravity.google/docs/cli/headless/)
- [Sandbox do Google Antigravity CLI](https://antigravity.google/docs/cli/sandbox/)
- Codex CLI. Consulte `codex --help` e `codex exec --help` da versão instalada.
