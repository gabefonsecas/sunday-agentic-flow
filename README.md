# Sunday

Sunday executa tarefas de desenvolvimento até uma pull request auditável.

Ele recebe um item Friday e controla todo o fluxo:

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

O usuário não escreve prompts para iniciar o orquestrador.
O comando universal é:

```bash
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

## Roteamento de modelos

Sunday inicia uma execução headless separada para cada fase.
O modelo é passado explicitamente ao CLI do host.

| Fase | Codex | Claude | Gemini | Antigravity |
| --- | --- | --- | --- | --- |
| Descoberta | `gpt-5.6-terra` | `haiku` | `flash` | `flash` |
| Implementação | `gpt-5.6-sol` | `sonnet` | `pro` | `pro` |
| Verificação | `gpt-5.6-terra` | `sonnet` | `pro` | `pro` |
| Review | `gpt-5.6-sol` | `opus` | `pro` | `pro` |

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

# Instalação completa no WSL 2

Este tutorial parte de uma instalação vazia.

## 1. Instalar o WSL 2

Abra o PowerShell como Administrador.

```powershell
wsl --install -d Ubuntu
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
sudo apt install -y ca-certificates curl git jq python3 python3-venv python3-pip unzip build-essential gh
```

Confirme o Python:

```bash
python3 --version
```

Sunday exige Python 3.11 ou superior.
Ubuntu 24.04 já atende esse requisito.

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
SUNDAY_ANTIGRAVITY_COMMAND=agy --model {model} --prompt -
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
python3 scripts/install.py
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

## 8. Descobrir IDs do Friday

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

Guarde os IDs usados pelo seu fluxo.

## 9. Configurar um projeto

Edite:

```bash
nano ~/.config/sunday/config.toml
```

Exemplo completo:

```toml
[runtime]
default_host = "auto"
cross_provider = false
strict_model_verification = true
watcher_interval = 60
minimum_confidence = 0.70
max_phase_attempts = 2

[projects.portal]
repository = "~/src/portal"
workspace_id = 37
board_id = 46
intake_group_id = 101
ready_label = "sunday-ready"
base_branch = "auto"
pr_column = "Pull Request"
people_column = "Responsável"
publish_stories = true

[projects.portal.states]
discovery = 102
stories = 103
publication = 104
implementation = 105
verification = 106
review = 107
pull_request = 108
completed = 109
failed = 110
```

Significado dos campos:

- `repository`: clone local onde Sunday trabalhará;
- `workspace_id`: workspace Friday;
- `board_id`: board da tarefa;
- `intake_group_id`: grupo que receberá histórias derivadas;
- `ready_label`: etiqueta exigida pelo watcher;
- `base_branch`: `auto`, `main` ou `homolog`;
- `pr_column`: coluna de link da pull request;
- `people_column`: coluna de responsável;
- `states`: mapeamento das fases para grupos Friday.

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

Use `--retry-uncertain` somente após verificar o Friday ou GitHub.
Esse sinal permite repetir uma operação cuja resposta foi perdida.

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
```

O modo `--network` também testa o Friday.

## Atualização

```bash
sunday update
```

Esse comando executa atualização Git com fast-forward.
Depois reinstala os arquivos gerenciados.
Falhas de instalação restauram os arquivos gerenciados anteriores.
O checkout Git permanece na revisão baixada.

## Remoção

```bash
sunday uninstall
```

Arquivos modificados depois da instalação são preservados.
O `.env`, `config.toml` e banco permanecem disponíveis.

# Desenvolvimento

Execute todas as verificações:

```bash
python3 -m compileall -q sunday scripts tests
python3 -m unittest discover -s tests -v
python3 scripts/check_model_routing.py
python3 scripts/sync_versions.py
```

A integração contínua testa:

- Python 3.11 e 3.13;
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

# Limitações conhecidas

- O Friday atual não expõe `get_current_user`.
- Contas sem tarefas precisam do e-mail fallback.
- Antigravity precisa expor um comando headless compatível.
- Integrações GitLab, Azure DevOps, Jira e Linear ainda não existem.
- Uma operação interrompida exige reconciliação antes de repetir.

# Licença

MIT. Consulte `LICENSE`.
