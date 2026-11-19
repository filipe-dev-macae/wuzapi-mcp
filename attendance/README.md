# Água Viva Attendance

Este diretório contém o backend e o conector OpenBot de referência. Use o [prompt de integração](../PROMPT-WUZAPI-CLI.md) para implementar a execução por Codex CLI ou Antigravity CLI. Os exemplos mantêm o despacho desabilitado.

Backend de atendimento independente, com conta de serviço, banco e implantação
próprios. Conecta WuzAPI e OpenBot por interfaces públicas, sem alterar o backend
do OpenBot. A instalação atual está ativa **somente para o contato de teste do
proprietário**, com avisos ao gerente bloqueados.

## Arquitetura

```text
WuzAPI → backend (fila, histórico, áudio, guard) → conector local → OpenBot
                  ↑              ações estruturadas / artefato ← agente
                  └── valida pausa/destino/ID e envia por MCP → WuzAPI
```

O backend roda como usuário `aguaviva`; o conector roda como usuário do OpenBot.
Só o conector conhece o token local do OpenBot. Ele aceita mensagens e consultas
de execução exclusivamente para o agente configurado; não expõe aprovação de
permissões ou alterações de modelo. Os serviços têm ciclo de vida independente.

### Isolamento com a API disponível

A API de Scripts locais não seleciona threads por cliente. O conector usa um
**agente dedicado e serial**, consulta o recibo anterior e só depois executa
`context/clear` e entrega a nova tarefa. O histórico por cliente fica no backend.
Repetição de tarefa reutiliza seu recibo persistido; falha ambígua bloqueia o
próximo reset. Não use esse mesmo agente para conversas administrativas paralelas.
A limpeza preserva o histórico visível do OpenBot, as instruções e ferramentas.
Memórias globais não devem conter conversas ou dados pessoais de clientes.

Essa estratégia é deliberadamente serial. Para paralelismo do modelo, substituir
o adaptador por sessões nativas por cliente quando houver contrato suportado e
validado. Texto de outro cliente não espera a preparação de uma mídia pendente,
mas toda execução do modelo aguarda a anterior terminar.

## Instalação e teste

Python 3.12+. Não é preciso uma segunda VPS.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install --no-deps -e .
.venv/bin/python -m pytest -q
```

`deploy/config.example.json` e `deploy/POLICY.md` são pontos de partida, não
credenciais ou catálogo fixo. Configurações e chaves devem ter permissão 600.
O exemplo começa com despacho bloqueado. Libere `context_isolation_verified`
somente após a prova de reset serial com o agente dedicado.

Provisione HMAC do webhook, chave MCP restrita à instância, chave de ações e chave
do conector. Cada backend aceita uma instância. Configure aliases verificados,
contatos permitidos, exclusões e o gerente; LID não é convertido em telefone.

```sh
.venv/bin/python -m aguaviva.attendance_bridge --config /etc/aguaviva/config.json --data /var/lib/aguaviva
```

Exemplos systemd em `deploy/`. O backend global roda em conta própria; o conector
é um serviço do usuário do OpenBot. Para o conector, configure agente, diretório
de automação, estado próprio, chaves, URL do backend e diretório de fotos do agente.
O conector não acessa tabelas internas do OpenBot.

Compose e Dockerfile são alternativas de empacotamento. O exemplo publica a porta
somente em loopback do host; UID 10001 precisa ler `runtime/` sem tornar chaves
públicas. Endpoints dentro do container precisam ser alcançáveis: `127.0.0.1`
dentro dele não é o host. Para máquinas distintas, usar HTTPS autenticado e alterar
endpoints na configuração; não expor o token ou a API local do OpenBot.

## Contrato do agente

O agente recebe evento, histórico e estado autenticados e usa a política estável
em AGENTS.md. Não precisa reler cinco documentos nem consultar status para uma
resposta simples. Dados comerciais continuam exigindo Stoqui/vitrine atuais.

Na implantação Água Viva, `require_link_preview=true` força `LinkPreview=true`
em texto no guard, antes de registrar a ação. Não altera botões/carrosséis e não
garante a aparência no aplicativo. A opção é falsa por padrão para outras
implantações. A política de voz está em `deploy/VOICE-AGUAVIVA.md`.

Confira as regras de horário e catálogo desta empresa antes de reutilizar o backend em outro atendimento.

Para respostas pequenas, devolver exclusivamente:

```json
{"actions":[{"operation":"text","body":{"Body":"Olá! Posso ajudar?"}}]}
```

Operações: text, buttons, carousel, react e handoff. Destinatário e IDs de envio
são resolvidos pelo backend. handoff aceita Body com o resumo e só executa as ações
seguintes após aceite ao gerente; em teste esse recurso está bloqueado.
`{"actions":[]}` encerra sem resposta quando não há pendência.

Para carrosséis, scripts Python devem construir o JSON e codificar fotos, sem
copiar base64 pela saída do modelo. Enviar o JSON ao comando abaixo, com
`ATTENDANCE_RESULTS_DIR` igual a `<estado-do-conector>/results`:

```sh
.venv/bin/python -m aguaviva.result < acoes.json
```

O helper valida operações/schema e retorna `{"actions_ref":"referencia_hex"}`;
o agente devolve esse objeto curto. O backend busca o artefato autenticado e
valida de novo antes de executar. Snapshot do schema vigente em `schemas.json`.
Atualizações de WuzAPI exigem conferir o catálogo/schema e testar compatibilidade.

### Fotos e áudio

Para foto pronta, o agente consulta status pelo cliente protegido. Configure:

```text
ATTENDANCE_URL=<endpoint-do-backend>
ATTENDANCE_KEY_FILE=<arquivo-privado-da-chave-de-acoes>
ATTENDANCE_CONNECTOR_URL=<endpoint-do-conector>
```

`python -m aguaviva.client` recebe JSON no stdin. Para status:
`{"chat_jid":"JID_AUTENTICADO","operation":"status"}`.
A foto é obtida por HTTP autenticado e materializada no host do OpenBot. Somente
IDs hexadecimais e arquivos JPEG locais no diretório autorizado são aceitos;
limites, expiração e rejeição de symlinks impedem caminhos arbitrários.

O áudio é transcrito antes do modelo. Instale o extra `media`, provisione o cache
do modelo multilíngue small e configure `ATTENDANCE_MODELS`. O worker reaproveita
o modelo, usa uma thread de CPU e nasce por spawn, evitando herdar sockets e
sinais do servidor. Originais são preservados se o processamento for interrompido
pelo encerramento do serviço. Áudio: até cinco minutos. Fotos expiram em 24 horas.

## Controles do envio

Recepção autenticada e fila são gravadas atomicamente. Mensagem humana pausa seu
chat por 300 segundos; recepção não aguarda chamadas de rede. Envio exige evento
atual e execução ativa. Mensagem nova invalida a resposta antiga. IDs estáveis por
evento/ação impedem repetição após timeout; resultados incertos não são repetidos.
O guard também restringe links/cartões pelo horário aprovado. Leitura e presença
são executadas pelo backend, sem rodadas adicionais de raciocínio do agente.

Aceite da API não prova entrega ou aparência no celular. O registro `effects`
guarda tipo e quantidade de cards; `outgoing` guarda o estado da tentativa.
JSON inválido ou schema inventado é rejeitado. Uma operação ambígua deve ser
reconciliada, nunca repetida cegamente ou trocada silenciosamente por texto.

## Backup, mudança de diretório e retorno

Antes do corte, bloquear novas execuções e aguardar agente/mídia. O receptor deve
continuar durável, ou a retenção/reentrega de webhooks precisa estar validada.
Nunca executar duas cópias do mesmo consumidor durante a troca.

```sh
.venv/bin/python -m aguaviva.backup snapshot /var/lib/aguaviva /backup/novo
.venv/bin/python -m aguaviva.backup restore /backup/novo /destino/vazio
```

O snapshot só começa com o serviço parado: lock impede consumidor concorrente no
mesmo volume. Usa SQLite Backup API, inclui mídias e manifesto SHA256, sem segredos.
A restauração checa integridade e remapeia referências locais. Cache de modelos e
segredos são provisionados separadamente. O destino não deve existir.

O ensaio A → B com dados fictícios roda na suíte em diretórios distintos nesta VPS.
Quando o backend mudar de máquina, o conector pode continuar no host OpenBot:
altere a URL do backend nele e a URL do conector no backend. Não há volume de mídia
compartilhado. Se mover também o conector, preserve sua fila `sessions.sqlite` e
reconcilie os recibos antes de iniciar. WuzAPI e suas sessões têm migração própria.

Rollback após novos envios exige preservar os registros de saída; um banco antigo
pode repetir mensagens. Backup local não protege contra perda da VPS. Outra
arquitetura de CPU, firewall e latência externa serão verificados no destino real.
