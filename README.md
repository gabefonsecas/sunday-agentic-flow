# Sunday

Sunday transforma pedidos em linguagem natural em tarefas Friday e executa o desenvolvimento até uma pull request auditável.

Depois da instalação e configuração inicial, o fluxo acontece dentro da CLI de IA.
Você não precisa decorar nem digitar comandos Sunday.

Exemplos de pedidos:

```text
Sunday, crie uma tarefa no Friday para corrigir o login.
Sunday, crie três histórias para esta feature.
Sunday, crie a tarefa e já comece a executar.
Sunday, execute a tarefa Friday 1234.
Sunday, acompanhe a execução 8b17...
Sunday, revise esta branch.
```

Se a CLI de IA estiver aberta dentro de `~/src/smb-products`, Sunday assume que a tarefa pertence ao projeto `smb-products`.
Ele usa a raiz Git atual, lê `AGENTS.md` e instruções equivalentes, e só exige o nome do projeto quando existir ambiguidade real.

Ele recebe um pedido ou item Friday e controla todo o fluxo:

1. Assume a tarefa usando o usuário do token.
2. Lê as regras e a arquitetura do projeto.
3. Converte requisitos vagos em histórias verificáveis.
4. Publica as histórias no Friday sem duplicação.
5. Cria uma branch baseada em `main` ou `homolog`.
6. Executa a implementação usando o modelo adequado.
7. Verifica testes e critérios em outro contexto.
8. Faz code review usando um modelo profundo.
9. Cria commit, push e pull request.
10. Vincula a pull request ao item Friday.

Os comandos abaixo são a API interna usada pelas skills e também ficam disponíveis para automação:

```bash
sunday create "corrigir o login"
sunday create "corrigir o login" --execute
sunday run ID_DA_TAREFA --project NOME_DO_PROJETO
```

O watcher opcional inicia tarefas etiquetadas automaticamente.

## Como Sunday funciona

Sunday possui um runtime Python independente dos hosts.
As skills apresentam o produto dentro de cada IA.
O runtime controla estado, efeitos externos e recuperação.

As fases persistidas são:

```text
intake
discovery
stories
publication
implementation
verification
review
pull_request
completed
```

Falhas recuperáveis entram em `paused`.
Falhas finais podem entrar em `failed`.

O banco SQLite fica fora dos projetos:

```text
~/.local/state/sunday/sunday.db
```

No Windows nativo ele usa `%LOCALAPPDATA%\sunday`.

## Roteamento e transições visuais

Sunday inicia uma execução headless separada para cada fase.
O modelo é passado explicitamente ao CLI do host.

| Host | Econômico | Rápido | Intermediário | Avançado | Profundo |
| --- | --- | --- | --- | --- | --- |
| Codex | GPT-5.4 mini | GPT-5.4 | GPT-5.6 Terra | GPT-5.5 | GPT-5.6 Sol |
| Claude | Haiku 4.5 | Sonnet 4.6 | - | Sonnet 5 | Opus 5 |
| Gemini | Flash-Lite | Flash | Gemini 3 Flash | Auto | Pro |
| Antigravity | Flash-Lite | Flash | Gemini 3 Flash | Auto | Pro |

Sunday classifica a tarefa antes de selecionar modelos:

- tarefa simples começa no nível econômico;
- descoberta normal começa no nível rápido;
- implementação normal começa no nível equilibrado;
- tarefa complexa começa no nível avançado;
- risco alto começa no nível avançado;
- falhas avançam até o nível profundo.

Git, GitHub e Friday usam adapters determinísticos.
Criar branch, commit, push e PR não consome modelo.

Durante a execução, Sunday imprime cada troca:

```text
[>>] Discovery: gpt-5.4-mini  pool=1/5  reason=simple complexity
[!!] Discovery: gpt-5.4-mini  duration=8.2s  accepted=False
[>>] Discovery: gpt-5.4  pool=2/5  reason=retry escalation
[OK] Discovery: gpt-5.4  duration=14.1s  accepted=True
[API] github:pull_request: deterministic adapter, no model
```

Consulte o painel da execução mais recente:

```bash
sunday routes
```

Consulte uma execução específica:

```bash
sunday routes RUN_ID
sunday status RUN_ID --visual
sunday routes RUN_ID --format markdown
sunday routes RUN_ID --format mermaid
sunday routes RUN_ID --format json
```

O formato Mermaid permite renderização em clientes compatíveis.
No Codex, peça: `Sunday, mostre as transições dos modelos`.

Cada execução registra:

- modelo solicitado;
- modelo observado;
- mecanismo de verificação;
- duração;
- confiança declarada;
- resultado da fase;
- tentativas e escalonamentos.

O padrão usa somente o fornecedor do host escolhido.
O modo entre fornecedores é opcional.

Não existe modelo local neste projeto.
Não existe Ollama, MLX ou mistura de pesos.
Interpolação significa roteamento, escalonamento e consenso.

Referências oficiais: [modelos OpenAI](https://developers.openai.com/api/docs/models),
[modelos Claude](https://platform.claude.com/docs/en/about-claude/models/overview) e
[seleção do Gemini CLI](https://geminicli.com/docs/cli/model/).

# Instalação completa no WSL 2

Este tutorial parte de uma instalação vazia.

## 1. Instalar o WSL 2

Abra o PowerShell como Administrador.

```powershell
wsl --install -d Ubuntu-24.04
wsl --update
wsl --set-default-version 2
```

Reinicie o Windows quando solicitado.
Abra o aplicativo Ubuntu.
Crie seu usuário e senha Linux.

Confirme a versão no PowerShell:

```powershell
wsl --list --verbose
```

A distribuição Ubuntu deve mostrar `VERSION 2`.

## 2. Preparar o Ubuntu

Execute dentro do Ubuntu:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y ca-certificates curl wget git jq unzip build-essential
```

### Instalar Python 3.11 sem alterar `python3`

Sunday usa Python 3.11 explicitamente.
O `python3` do sistema pode continuar apontando para Python 3.10.
Não altere `update-alternatives` e não substitua o Python do Ubuntu.

Instale o gerenciador `uv` e uma versão isolada do Python 3.11:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.11
```

Persista o diretório dos executáveis no shell:

```bash
grep -qxF 'export PATH="$HOME/.local/bin:$PATH"' ~/.bashrc || \
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Confirme os dois comandos separadamente:

```bash
python3 --version
python3.11 --version
```

O primeiro pode mostrar `Python 3.10.x`.
O segundo deve mostrar `Python 3.11.x`.
O `uv` instala apenas o executável versionado por padrão.

### Instalar GitHub CLI 2.49.0 ou superior

Sunday usa `gh attestation verify` durante atualizações.
Esse comando existe a partir do GitHub CLI 2.49.0.
Use o repositório oficial, evitando versões antigas do Ubuntu:

```bash
sudo mkdir -p -m 755 /etc/apt/keyrings
wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null
sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
  | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
sudo apt update
sudo apt install -y gh
```

Confirme a versão e o comando de proveniência:

```bash
gh --version
gh attestation --help
```

`gh --version` deve mostrar 2.49.0 ou superior.

Configure sua identidade Git:

```bash
git config --global user.name "Seu Nome"
git config --global user.email "voce@empresa.com"
```

Autentique o GitHub CLI:

```bash
gh auth login
gh auth status
```

Mantenha repositórios dentro do filesystem Linux.
Evite trabalhar diretamente em `/mnt/c`.

```bash
mkdir -p ~/src ~/plugins
```

## 3. Instalar Node.js

Codex e Gemini CLI usam Node.js.

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x -o /tmp/nodesource_setup.sh
sudo -E bash /tmp/nodesource_setup.sh
sudo apt install -y nodejs
node --version
npm --version
```

## 4. Instalar pelo menos um host

Não é necessário instalar todos.

### Codex

```bash
npm install --global @openai/codex
codex --version
codex
```

Conclua a autenticação apresentada.

### Claude Code

```bash
curl -fsSL https://claude.ai/install.sh | bash
claude --version
claude doctor
claude
```

Conclua a autenticação apresentada.

### Gemini CLI

```bash
npm install --global @google/gemini-cli
gemini --version
gemini
```

Conclua a autenticação apresentada.

### Antigravity

Instale o Antigravity fornecido pela sua organização.
Garanta que o executável `agy` esteja disponível no WSL.

```bash
agy --version
```

Quando `agy` não existe, Sunday usa Gemini CLI como executor headless.
Os agentes instalados continuam otimizados para Antigravity.

Quando a instalação usa outro comando, configure um template:

```dotenv
SUNDAY_ANTIGRAVITY_COMMAND=agy --model {model} -p
```

Os agentes específicos ficam em `adapters/antigravity`.
Sunday seleciona `flash` e `pro` automaticamente.

## 5. Clonar Sunday

```bash
git clone https://github.com/gabefonsecas/sunday-agentic-flow.git ~/plugins/sunday-agentic-flow
cd ~/plugins/sunday-agentic-flow
```

Sunday fica fora dos projetos trabalhados.

## 6. Criar o arquivo de segredos

```bash
mkdir -p ~/.config/sunday
cp .env.example ~/.config/sunday/.env
chmod 600 ~/.config/sunday/.env
nano ~/.config/sunday/.env
```

Conteúdo mínimo:

```dotenv
FRIDAY_MCP_BASE_URL=sua_url_friday_mcp
FRIDAY_MCP_API_TOKEN=seu_token_friday
```

Sunday tenta identificar o usuário nesta ordem:

1. ferramenta Friday `get_current_user`, quando disponível;
2. identidade comum nas tarefas filtradas pelo token;
3. e-mail fallback validado nos membros do workspace.

O fallback é necessário somente para contas sem tarefas.

```dotenv
FRIDAY_FALLBACK_ASSIGNEE_EMAIL=voce@empresa.com
```

Boards com várias colunas de pessoas exigem:

```dotenv
FRIDAY_ASSIGNEE_COLUMN=Responsável
```

Nenhum ID de usuário fica fixo no código.
Cada token resolve seu próprio usuário.

Chaves opcionais entre fornecedores também ficam no `.env`:

```dotenv
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
```

Nunca coloque segredos no `config.toml`.

## 7. Instalar Sunday

```bash
cd ~/plugins/sunday-agentic-flow
python3.11 scripts/install.py
```

Garanta os comandos locais no `PATH`:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Confirme:

```bash
sunday --help
sunday doctor
```

O instalador cria:

- `sunday`;
- `sunday-friday-mcp`;
- `~/.config/sunday/config.toml`;
- `~/.config/sunday/.env` quando ausente;
- agentes globais para os quatro hosts;
- plugin Sunday no marketplace pessoal do Codex;
- plugin global do Antigravity.

O instalador usa backup e rollback automático.
Ele nunca instala arquivos dentro dos projetos.
O código ativo fica numa release imutável em `~/.local/share/sunday/releases`.
Cada release usa sua própria `.venv` criada pelo Python 3.11.
Os launchers gravam caminhos absolutos para esse runtime.
Após instalar, nenhum comando Sunday depende do `python3` do sistema.
O clone usado na instalação pode ser removido depois.

## Instalação no Windows x64 nativo

Abra o PowerShell comum. Não é necessário alterar o Python do sistema.

Instale Python 3.11 e GitHub CLI pelo `winget`:

```powershell
winget install --id Python.Python.3.11 -e
winget install --id GitHub.cli -e
```

Feche e reabra o PowerShell. Depois confirme:

```powershell
py -3.11 --version
gh --version
gh attestation --help
```

O GitHub CLI deve ser 2.49.0 ou superior.
Autentique e clone o Sunday:

```powershell
gh auth login
gh auth status
mkdir "$HOME\plugins" -Force
git clone https://github.com/gabefonsecas/sunday-agentic-flow.git "$HOME\plugins\sunday-agentic-flow"
cd "$HOME\plugins\sunday-agentic-flow"
py -3.11 scripts\install.py
```

Os comandos ficam em `%LOCALAPPDATA%\sunday\bin`.
Adicione essa pasta ao `PATH` do usuário uma única vez:

```powershell
$SundayBin = "$env:LOCALAPPDATA\sunday\bin"
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($null -eq $UserPath) { $UserPath = "" }
if (($UserPath -split ';') -notcontains $SundayBin) {
  [Environment]::SetEnvironmentVariable(
    "Path",
    (($UserPath.TrimEnd(';') + ";" + $SundayBin).TrimStart(';')),
    "User"
  )
}
$env:Path = "$SundayBin;$env:Path"
```

```powershell
sunday --help
sunday doctor
```

## Instalação no macOS

Instale as dependências pelo Homebrew:

```bash
brew install python@3.11 gh git
python3.11 --version
gh --version
gh attestation --help
```

O GitHub CLI deve ser 2.49.0 ou superior.
Autentique, clone e instale:

```bash
gh auth login
gh auth status
mkdir -p ~/plugins
git clone https://github.com/gabefonsecas/sunday-agentic-flow.git ~/plugins/sunday-agentic-flow
cd ~/plugins/sunday-agentic-flow
python3.11 scripts/install.py
grep -qxF 'export PATH="$HOME/.local/bin:$PATH"' ~/.zshrc || \
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
sunday --help
sunday doctor
```

## 8. Configuração automática do Friday

Você não precisa descobrir nem preencher IDs manualmente.
Depois de colocar o token no `.env`, abra um host dentro do repositório e faça o primeiro pedido:

```text
Sunday, crie uma tarefa no Friday para corrigir o login.
```

Na primeira execução, Sunday:

1. consulta workspaces, boards, grupos, colunas e opções usando o token;
2. envia o catálogo e o contexto do repositório ao modelo de descoberta;
3. escolhe o board e o workflow mais adequados;
4. valida todos os IDs escolhidos contra a resposta real do Friday;
5. grava `~/.config/sunday/config.toml` atomicamente;
6. continua o pedido original sem exigir um segundo comando.

Se dois boards forem realmente indistinguíveis, Sunday interrompe antes de gravar e pede uma decisão.
Ele nunca aceita IDs inventados pelo modelo.

### Inspeção manual opcional

Os comandos abaixo servem apenas para diagnóstico:

Liste workspaces:

```bash
sunday friday
```

Liste boards de um workspace:

```bash
sunday friday --workspace 37
```

Liste grupos e colunas de um board:

```bash
sunday friday --workspace 37 --board 46
```

## 9. Arquivo gerado automaticamente

Para o board Squad Mustafar consultado durante o desenvolvimento, Sunday produz um arquivo equivalente a:

```toml
[runtime]
default_host = "auto"
default_project = "mustafar"
cross_provider = false
strict_model_verification = true
watcher_interval = 60
minimum_confidence = 0.70
max_phase_attempts = 3
lease_ttl_seconds = 300
lease_heartbeat_seconds = 60
completed_worktree_retention_days = 0 # limpeza de worktrees legados

[projects.mustafar]
repository = "~/src/smb-products"
workspace_id = 37
board_id = 46
intake_group_id = 90
base_branch = "auto"
pr_column = ""
people_column = "200"
status_column = "201"
ai_column = "298"
publish_stories = true

[projects.mustafar.states]
discovery = "none"
stories = "none"
publication = "opt_1783359207831"
implementation = "working"
verification = "opt_1783359320107"
review = "opt_1783359350625"
pull_request = "opt_1783359331060"
completed = "opt_1783359370171"
failed = "stuck"
```

Essa configuração é feita automaticamente uma vez por mapeamento Friday. No uso normal, abra Codex, Claude, Gemini ou Antigravity dentro do repositório e converse com Sunday.
`default_project` define qual mapeamento de board e estados será reutilizado em novas pastas Git.
O nome e o caminho do projeto sempre vêm da pasta atual. Se houver apenas um projeto configurado, ele já funciona como padrão mesmo sem esse campo.

Significado dos campos:

- `repository`: clone local onde Sunday trabalhará;
- `default_project`: mapeamento Friday padrão para repositórios ainda não cadastrados;
- `workspace_id`: workspace Friday;
- `board_id`: board da tarefa;
- `intake_group_id`: grupo que receberá histórias derivadas;
- `ready_label`: etiqueta exigida pelo watcher;
- `base_branch`: `auto`, `main` ou `homolog`;
- `pr_column`: coluna de link da pull request;
- `people_column`: coluna de responsável;
- `status_column`: coluna de status atualizada durante a execução;
- `ai_column`: checkbox usado somente para identificar trabalho realizado pelo Sunday;
- `states`: mapeamento opcional das fases para opções da coluna de status.

Quando `status_column` está configurada, os valores de `states` são IDs das opções de status.
Sunday chama `update_cell_value` e mantém o card no grupo original.

Em boards legados onde os próprios grupos representam o workflow, omita `status_column` e use
IDs numéricos de grupos em `states`. Nesse modo, Sunday movimenta o card com `move_item`.

Se `states` for omitido manualmente, todo o fluxo continua funcionando, mas o status visual do card não é sincronizado.
O watcher considera tarefas atribuídas ao usuário do token em todos os grupos do board configurado,
independentemente do valor da coluna `ai_column`. Ele ignora o status configurado como `completed`.
`ready_label` continua disponível como filtro opcional; vazio significa não filtrar por etiqueta.

Quando `base_branch = "auto"`, Sunday usa `homolog` para demandas de homologação.
Nos demais casos, ele usa `main` quando disponível.

## 10. Ativar em cada host

### Codex

```bash
codex plugin add sunday-agentic-flow@personal
codex plugin list
codex mcp list
```

Abra uma tarefa nova no Codex após instalar.

### Claude Code

```bash
claude plugin marketplace add ~/plugins/sunday-agentic-flow
claude plugin install sunday-agentic-flow@sunday-local --scope user
claude plugin list
```

Abra uma sessão nova após instalar.

### Gemini CLI

```bash
gemini extensions link ~/plugins/sunday-agentic-flow
gemini extensions list
```

Abra uma sessão nova após instalar.

### Antigravity

O instalador cria:

```text
~/.gemini/config/plugins/sunday-agentic-flow
~/.gemini/config/agents/sunday-task-analyst.md
~/.gemini/config/agents/sunday-implementation-worker.md
~/.gemini/config/agents/sunday-implementation-verifier.md
~/.gemini/config/agents/sunday-branch-reviewer.md
```

Reinicie o Antigravity depois da instalação.

# Uso

## Uso normal pela CLI de IA

Abra o host na pasta do projeto:

```bash
cd ~/src/smb-products
codex
```

Também pode ser `claude`, `gemini` ou Antigravity. Depois, faça pedidos naturais:

```text
Sunday, crie uma tarefa no Friday para adicionar paginação ao catálogo.
```

Sunday irá:

1. identificar `smb-products` pela raiz Git atual;
2. ler as regras e o contexto relevante do repositório;
3. usar o modelo de descoberta adequado para completar requisitos vagos;
4. criar a tarefa no grupo de entrada configurado;
5. atribuí-la ao usuário identificado pelo token Friday;
6. devolver o ID e o título do card.

Para criar e executar em seguida:

```text
Sunday, crie uma tarefa para adicionar paginação ao catálogo e já comece a executar.
```

Para decompor sem iniciar a implementação:

```text
Sunday, crie três histórias no Friday para migrar o catálogo para a nova API.
```

Os hosts invocam as skills e a CLI interna. Não copie comandos `sunday` durante o uso cotidiano.

## API de linha de comando para automação

Esta seção é opcional. Ela documenta o motor chamado pelas skills.

### Criar tarefas

```bash
sunday create "adicionar paginação ao catálogo"
sunday create "migrar o catálogo" --count 3
sunday create "corrigir o login" --execute
```

Por padrão, a tarefa é atribuída ao usuário derivado do token Friday.
Use `--no-assign` apenas para criar um card sem responsável.
Repetir o mesmo pedido retorna o resultado anterior sem duplicar cards.
`--allow-duplicate` exige uma intenção explícita de criar outra cópia.

## Executar uma tarefa

```bash
sunday run 1234 --project portal
```

Também aceita uma URL cujo último segmento seja o ID:

```bash
sunday run https://friday.exemplo/tarefas/1234 --project portal
```

Escolha um host explicitamente quando necessário:

```bash
sunday run 1234 --project portal --host codex
sunday run 1234 --project portal --host claude
sunday run 1234 --project portal --host gemini
sunday run 1234 --project portal --host antigravity
```

Com `--host auto`, Sunday usa o primeiro host disponível.

## Executar pelo watcher

Adicione a etiqueta `sunday-ready` ao item Friday.
O item também precisa estar atribuído ao usuário do token.

Teste uma consulta única:

```bash
sunday watch --project portal --once
```

Mantenha o watcher ativo:

```bash
sunday watch --project portal
```

Use systemd de usuário quando quiser execução contínua.

```ini
[Unit]
Description=Sunday Friday watcher
After=network-online.target

[Service]
ExecStart=%h/.local/bin/sunday watch --project portal
Restart=on-failure
RestartSec=15

[Install]
WantedBy=default.target
```

Salve como `~/.config/systemd/user/sunday.service`.

```bash
systemctl --user daemon-reload
systemctl --user enable --now sunday.service
systemctl --user status sunday.service
```

## Consultar execução

```bash
sunday status
sunday status RUN_ID
```

## Retomar uma execução

Resolva primeiro o erro apresentado.

```bash
sunday resume RUN_ID
```

Uma operação de alto risco exige aprovação explícita:

```bash
sunday resume RUN_ID --approve
```

Use `--retry-uncertain` para solicitar reconciliação imediata.
Sunday preserva o efeito iniciado e consulta o sistema remoto.
Ele repete somente quando o probe confirma sua ausência.

```bash
sunday resume RUN_ID --retry-uncertain
```

Encerre definitivamente uma execução pausada quando necessário:

```bash
sunday fail RUN_ID --reason "demanda cancelada"
```

## Fazer code review

```bash
cd ~/src/portal
sunday review minha-branch --project portal
sunday review 123 --project portal
sunday review https://github.com/empresa/portal/pull/123 --project portal
```

O review é independente e não altera arquivos.

## Gerar relatório

```bash
sunday report RUN_ID
sunday report RUN_ID --format json
sunday report RUN_ID --output ~/relatorios/sunday.md
```

O relatório contém timeline e route ledger.
Também inclui recomendações de roteamento.
Sunday nunca altera a política automaticamente.

Para enxergar somente modelos e escalonamentos:

```bash
sunday routes RUN_ID
```

# Modo entre fornecedores

Ative no `config.toml`:

```toml
[runtime]
cross_provider = true
max_phase_attempts = 3
```

Instale e autentique os fornecedores desejados.
Sunday começa no host selecionado.
Uma nova tentativa pode usar outro fornecedor disponível.

O escalonamento acontece quando:

- o processo retorna erro;
- o modelo informa falha;
- a confiança fica abaixo do mínimo;
- a troca obrigatória não é verificada;
- testes ou review não aprovam a fase.

# Segurança e autonomia

Sunday automatiza:

- atribuição no Friday;
- criação e movimentação de histórias;
- branch;
- implementação;
- testes;
- review;
- commit;
- push;
- pull request;
- vínculo da pull request no Friday.

Sunday pausa antes de:

- produção;
- deploy;
- migração destrutiva;
- exclusão em massa;
- manipulação de segredos;
- ações que exigem reconciliação.

Sunday não executa merge nem deploy automaticamente.

Tokens são removidos dos eventos e relatórios.
URLs autenticadas também são redigidas.

# Manutenção

## Diagnóstico

```bash
sunday doctor
sunday doctor --network
sunday doctor --models
```

O modo `--network` também testa o Friday.
O modo `--models` executa probes mínimos e somente leitura.
Ele confirma o modelo observado por cada host.

## Atualização

```bash
sunday update
sunday update --check
sunday update --rollback
sunday update --rollback 1.0.0
```

O update consulta a release oficial no GitHub.
Ele baixa o ZIP e valida checksum e proveniência.
A nova versão passa por smoke test antes da ativação.
Falhas mantêm a versão anterior ativa.
O comando não depende do clone usado na instalação.
O update continua usando o runtime Python 3.11 já instalado.
Ele não chama nem altera o comando `python3` do sistema.

Se `gh attestation --help` falhar, atualize o GitHub CLI primeiro.
Sunday requer GitHub CLI 2.49.0 ou superior para verificar proveniência.

## Branch e checkout de trabalho

Sunday cria uma branch `sunday/...` no próprio repositório aberto.
Todo trabalho acontece diretamente nesse checkout.
Nenhum worktree e nenhuma pasta paralela são criados.
O repositório precisa estar limpo antes da execução.
Sunday recusa iniciar quando encontra alterações locais.
Somente uma execução pode controlar o checkout por vez.

Reviews fazem checkout destacado do commit exato.
Ao terminar, Sunday restaura a branch original.

O comando abaixo existe apenas para instalações antigas.
Ele remove worktrees legados registrados antes desta versão.

```bash
sunday cleanup
sunday cleanup --older-than 14
sunday cleanup --run-id RUN_ID
```

Sunday remove somente worktrees legados registrados e limpos.

## Remoção

```bash
sunday uninstall
```

Arquivos modificados depois da instalação são preservados.
O `.env`, `config.toml` e banco permanecem disponíveis.

# Desenvolvimento

Os comandos abaixo são para WSL, Linux e macOS.
No Windows nativo, substitua `python3.11` por `py -3.11`.

Execute todas as verificações:

```bash
python3.11 -m compileall -q sunday scripts tests
python3.11 -m unittest discover -s tests -v
python3.11 scripts/check_model_routing.py
python3.11 scripts/sync_versions.py
```

A integração contínua testa:

- Python 3.11, 3.12 e 3.13;
- Ubuntu;
- contrato WSL;
- Windows x64;
- macOS;
- manifests;
- roteamento;
- estado e retomada;
- Friday e GitHub falsos;
- segurança e redaction.

Releases geram ZIP portátil, checksum SHA-256 e atestado de proveniência.
O gate WSL 2 roda numa VM Windows descartável hospedada pelo GitHub e não
depende de máquinas ou permissões locais.

# Limitações conhecidas

- O Friday atual não expõe `get_current_user`.
- Contas sem tarefas precisam do e-mail fallback.
- Antigravity precisa expor um comando headless compatível.
- Integrações GitLab, Azure DevOps, Jira e Linear ainda não existem.
- Efeitos sem evidência remota permanecem pausados.

# Licença

MIT. Consulte `LICENSE`.
