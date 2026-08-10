# Agentic Dev Flow

Plugin global para executar todo o fluxo de desenvolvimento.

Ele funciona com Codex, Claude Code, Gemini CLI e Antigravity.
O plugin não precisa ser instalado dentro dos projetos.
Ele usa somente modelos remotos fornecidos pelo host escolhido.

Uma solicitação comum inicia o orquestrador automaticamente.
Não é necessário citar skills, agentes ou modelos.

## O que o fluxo faz

Para qualquer feature, correção, refatoração ou manutenção, ele:

1. Localiza a raiz correta do repositório.
2. Lê `AGENTS.md`, `GEMINI.md` e regras aplicáveis.
3. Descobre arquitetura, convenções, testes e integração Git.
4. Transforma requisitos incompletos em critérios verificáveis.
5. Resolve workspace, board, grupos e colunas no Friday.
6. Escreve e publica as histórias necessárias.
7. Move os cards conforme o trabalho realmente avança.
8. Implementa cada história respeitando o projeto.
9. Executa testes, lint, build e verificações relevantes.
10. Revisa a branch contra sua base correta.
11. Publica a branch e abre uma pull request.
12. Escolhe `main` ou `homolog` usando evidências.
13. Publica o link da PR no item Friday.
14. Mantém falhas e riscos registrados no card.

## Roteamento automático entre modelos

Não existe modelo local neste projeto.
Também não existe servidor Ollama, MLX ou LM Studio.

O orquestrador escolhe modelos remotos por função:

| Função | Nível | Codex | Claude | Gemini CLI | Antigravity |
| --- | --- | --- | --- | --- | --- |
| Descoberta e resumo | Rápido | `gpt-5.6-terra` | `haiku` | Gemini Flash | `flash` |
| Implementação e testes | Balanceado | `gpt-5.6-sol` | `sonnet` | Gemini Pro | `pro` |
| Verificação independente | Rápido e crítico | `gpt-5.6-terra` | `sonnet` | Gemini Pro | `pro` |
| Arquitetura e revisão | Profundo | `gpt-5.6-sol` com `xhigh` | `opus` | Gemini Pro | `pro` |

Os nomes exatos podem depender da conta contratada.
Quando um modelo não estiver disponível, o host herda o modelo ativo.

No Gemini, `kind: local` significa subagente da sessão.
Isso não significa modelo local ou inferência offline.

A interpolação ocorre na camada semântica:

- Um agente descobre e resume evidências.
- Outro agente implementa ou verifica a solução.
- Um agente profundo critica riscos importantes.
- O agente principal confirma tudo no repositório.
- Somente o agente principal altera Friday, Git e PRs.

Não ocorre mistura de pesos entre arquiteturas diferentes.

A transição acontece por delegação entre subagentes.
O modelo da conversa principal não muda silenciosamente.
Cada fase abre um contexto especialista independente.

As quatro transições obrigatórias são:

1. Descoberta com o analista rápido.
2. Implementação com o worker balanceado.
3. Verificação com um agente independente.
4. Revisão final com o agente profundo.

O relatório final apresenta um `route ledger`.
Ele mostra agente, nível, modelo observado e resultado.
Se o host não suportar subagentes, aparece `degraded`.

## Compatibilidade

O tutorial principal usa Windows x64 com WSL 2.
O mesmo pacote também funciona em Linux e macOS.

Requisitos mínimos:

- Windows 10 ou 11 com virtualização habilitada.
- WSL 2 com Ubuntu 22.04 ou superior.
- Python 3.9 ou superior.
- Git.
- Acesso ao Friday.
- Conta para pelo menos um host suportado.
- Acesso ao repositório remoto e provedor de PRs.

Você não precisa instalar todos os quatro hosts.
Instale somente aqueles usados pela sua equipe.

# Tutorial completo para WSL 2

## 1. Instalar WSL 2 no Windows

Abra PowerShell como Administrador.

Execute:

```powershell
wsl --install -d Ubuntu
wsl --update
wsl --set-default-version 2
```

Reinicie o Windows quando solicitado.
Depois abra o aplicativo Ubuntu.

Crie seu usuário e senha Linux.
Confirme que a distribuição usa WSL 2:

```powershell
wsl --list --verbose
```

A coluna `VERSION` deve mostrar `2`.

## 2. Preparar o Ubuntu

Todos os comandos seguintes rodam dentro do Ubuntu.

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y ca-certificates curl git jq python3 python3-venv python3-pip unzip build-essential
```

Configure sua identidade Git:

```bash
git config --global user.name "Seu Nome"
git config --global user.email "voce@empresa.com"
```

Mantenha repositórios dentro do sistema Linux.
Isso oferece desempenho melhor que `/mnt/c`.

Exemplo:

```bash
mkdir -p ~/src ~/plugins
```

## 3. Instalar Node.js no WSL

Codex e Gemini CLI precisam de Node.js atual.
O Gemini CLI exige Node.js 20 ou superior.

Instale Node.js 22 pelo repositório NodeSource:

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x -o /tmp/nodesource_setup.sh
sudo -E bash /tmp/nodesource_setup.sh
sudo apt install -y nodejs
```

Confirme:

```bash
node --version
npm --version
```

O comando `node --version` deve mostrar versão 20 ou superior.

## 4. Instalar o GitHub CLI

Este passo permite autenticação, push e criação de PRs.

```bash
sudo apt install -y gh
gh auth login
gh auth status
```

Escolha GitHub.com ou seu servidor corporativo.
Escolha HTTPS ou SSH conforme sua organização.

Se outro provedor hospeda o repositório, instale seu cliente.
O plugin também pode usar ferramentas MCP disponíveis no host.

## 5. Instalar os hosts desejados

### Codex

```bash
npm install --global @openai/codex
codex --version
codex
```

Na primeira execução, conclua a autenticação apresentada.
O Codex requer WSL 2 nas versões atuais.

### Claude Code

Use o instalador oficial para Linux e WSL:

```bash
curl -fsSL https://claude.ai/install.sh | bash
claude --version
claude doctor
claude
```

Conclua a autenticação no navegador.

### Gemini CLI

```bash
npm install --global @google/gemini-cli
gemini --version
gemini
```

Conclua a autenticação solicitada.

### Antigravity CLI

Esta é a opção otimizada para Antigravity dentro do WSL.

```bash
curl -fsSL https://antigravity.google/cli/install.sh | bash
agy --version
agy
```

Conclua a autenticação no navegador.
O binário fica em `~/.local/bin/agy`.

Garanta que os binários locais estejam no `PATH`:

```bash
printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> ~/.bashrc
source ~/.bashrc
```

## 6. Colocar o plugin no WSL

O diretório global esperado é:

```text
~/plugins/agentic-dev-flow
```

Se recebeu um arquivo compactado no Windows, extraia ou copie assim:

```bash
cp -a /mnt/c/Users/SEU_USUARIO/Downloads/agentic-dev-flow ~/plugins/
cd ~/plugins/agentic-dev-flow
```

Substitua `SEU_USUARIO` pelo usuário do Windows.

Se o plugin estiver em um repositório Git, clone-o diretamente:

```bash
git clone https://github.com/gabefonsecas/agentic-dev-flow.git ~/plugins/agentic-dev-flow
cd ~/plugins/agentic-dev-flow
```

Não coloque este plugin dentro do projeto trabalhado.

## 7. Criar o arquivo `.env`

Todas as chaves externas devem ficar neste arquivo:

```text
~/.config/agentic-dev-flow/.env
```

Crie o diretório:

```bash
mkdir -p ~/.config/agentic-dev-flow
cp .env.example ~/.config/agentic-dev-flow/.env
chmod 600 ~/.config/agentic-dev-flow/.env
```

Edite o arquivo:

```bash
nano ~/.config/agentic-dev-flow/.env
```

Conteúdo esperado:

```dotenv
FRIDAY_MCP_BASE_URL=https://friday.eletromidia.com.br/api/mcp_sse.php
FRIDAY_MCP_API_TOKEN=seu_token_friday
```

O responsável é descoberto usando somente esse token.
Nenhum e-mail ou ID precisa ser configurado.

O bridge chama `list_my_tasks`, filtrado pelo token.
Ele encontra a identidade comum aos cards retornados.
Depois valida o usuário no workspace escolhido.

Boards com várias colunas de pessoas exigem:

```dotenv
FRIDAY_ASSIGNEE_COLUMN=Responsável
```

Salve usando `Ctrl+O`, Enter e `Ctrl+X`.

Nunca coloque o token em manifests ou regras.
Nunca faça commit do arquivo `.env`.

Outro arquivo pode ser usado assim:

```bash
export AGENTIC_DEV_FLOW_ENV_FILE=/caminho/seguro/.env
```

## 8. Executar o instalador do plugin

Dentro do diretório do plugin, execute:

```bash
cd ~/plugins/agentic-dev-flow
python3 scripts/install.py
```

O instalador cria:

- O comando global `agentic-friday-mcp`.
- A configuração privada no perfil Linux.
- A entrada do marketplace pessoal do Codex.
- O plugin global do Antigravity.
- Agentes remotos específicos para cada host.

Os agentes ficam nestes diretórios:

```text
~/.codex/agents
~/.claude/agents
~/.gemini/agents
~/.gemini/config/agents
```

O instalador nunca altera o repositório do projeto.

## 9. Ativar o plugin em cada host

Ative somente os hosts instalados.

### Codex

```bash
codex plugin add agentic-dev-flow@personal
codex plugin list
codex mcp list
```

O MCP esperado chama-se `friday`.
Abra uma sessão nova após instalar ou atualizar.

### Claude Code

```bash
claude plugin marketplace add ~/plugins/agentic-dev-flow
claude plugin install agentic-dev-flow@agentic-dev-flow-local --scope user
claude plugin list
```

Feche e abra novamente o Claude Code.

### Gemini CLI

```bash
gemini extensions link ~/plugins/agentic-dev-flow
gemini extensions list
```

Feche e abra novamente o Gemini CLI.

Os subagentes do Gemini usam o recurso preview atual.
Eles são instalados no perfil do usuário.

### Antigravity CLI

O instalador cria este vínculo global:

```text
~/.gemini/config/plugins/agentic-dev-flow
```

Feche e abra novamente o Antigravity CLI.
Depois confirme o plugin nas customizações disponíveis.

Os agentes do Antigravity usam níveis `flash` e `pro`.
Essa configuração evita modelos locais e escolhas manuais.

## 10. Validar a instalação

Execute:

```bash
cd ~/plugins/agentic-dev-flow
python3 scripts/check_environment.py
python3 scripts/check_model_routing.py
```

Confirme os seguintes campos:

- `python` possui um caminho válido.
- Seu host aparece com um caminho válido.
- `friday_configured` mostra `true`.
- `friday_identity.source` menciona o token Friday.
- Os quatro diretórios de agentes são exibidos.
- `check_model_routing.py` mostra `valid: true`.

Confira o bridge Friday:

```bash
command -v agentic-friday-mcp
```

Confira cada host instalado:

```bash
codex plugin list
claude plugin list
gemini extensions list
agy --version
```

# Uso diário

## Executar uma tarefa completa

Entre no projeto:

```bash
cd ~/src/meu-projeto
```

Abra qualquer host instalado:

```bash
codex
```

Ou:

```bash
claude
gemini
agy
```

Descreva somente a necessidade real:

```text
Corrija a recuperação de senha que expira antes do prazo.
```

Isso basta.

Não escreva `Use orchestrate-development-task`.
Não selecione agentes ou modelos manualmente.
Não repita o processo operacional no pedido.

O plugin detecta a solicitação de desenvolvimento automaticamente.
Ele inicia descoberta, histórias, execução, revisão e entrega.

Quando a execução começa, o plugin também:

1. Resolve o usuário autenticado pelo token.
2. Descobre a coluna Friday do tipo `people`.
3. Atualiza essa coluna com o ID correto.
4. Exige confirmação `assigned: true`.
5. Somente depois inicia mudanças no código.

## Solicitações incompletas

Uma demanda curta também deve funcionar:

```text
O checkout está duplicando pedidos em tentativas simultâneas.
```

O orquestrador deve descobrir o contexto do projeto.
Ele transforma evidências em critérios de aceitação.
Ele pergunta somente quando uma escolha muda o produto.

## Criar histórias sem implementar

Descreva o limite desejado naturalmente:

```text
Planeje essa demanda e publique as histórias no Friday. Não implemente ainda.
```

## Executar um item Friday existente

```text
Implemente o item Friday 1234 até uma PR revisada.
```

## Revisar uma branch

Abra o host dentro do repositório.
Depois escreva:

```text
Revise a branch feature/pagamentos contra homolog.
```

O revisor deve:

1. Encontrar a base e o merge-base.
2. Ler todas as regras aplicáveis.
3. Inspecionar o diff completo.
4. Verificar caminhos afetados e testes.
5. Priorizar erros concretos e regressões.
6. Evitar comentários puramente estéticos.
7. Não modificar código durante revisão somente leitura.

Para corrigir depois:

```text
Corrija os achados confirmados e atualize o Friday.
```

## Escolha entre `main` e `homolog`

O plugin usa evidências do pedido e repositório.

Ele prefere `homolog` quando:

- A tarefa pede homologação ou staging.
- O fluxo exige validação antes de produção.
- As regras do projeto determinam essa base.

Ele prefere `main` quando:

- A entrega vai diretamente para produção.
- Um hotfix exige essa base.
- `homolog` não existe.
- As regras definem `main` como integração.

O agente pergunta quando a decisão continuar ambígua.

## Estado dos cards Friday

O fluxo semântico é:

```text
entrada -> entendida -> planejada -> publicada -> em andamento
-> validada -> PR aberta -> revisada
```

Esses estados são mapeados aos grupos existentes.
O plugin não cria grupos administrativos implicitamente.
Uma falha nunca é movida para concluída.

## Ferramentas Friday utilizadas

O plugin pode usar:

- `list_workspaces`
- `list_boards`
- `list_groups`
- `list_items`
- `list_columns`
- `create_item`
- `move_item`
- `update_cell_value`
- `assign_authenticated_user`
- `add_comment`
- `list_ia_tasks`

IDs, colunas e URLs nunca devem ser inventados.

# Atualização

Atualize os arquivos do plugin primeiro.
Depois reinstale os adaptadores:

```bash
cd ~/plugins/agentic-dev-flow
python3 scripts/install.py
```

Atualize cada host utilizado:

```bash
codex plugin add agentic-dev-flow@personal
claude plugin update agentic-dev-flow@agentic-dev-flow-local
gemini extensions link ~/plugins/agentic-dev-flow
```

Reinicie as sessões abertas.

# Solução de problemas

## `agentic-friday-mcp` não foi encontrado

```bash
export PATH="$HOME/.local/bin:$PATH"
python3 ~/plugins/agentic-dev-flow/scripts/install.py
command -v agentic-friday-mcp
```

## Friday não conecta

```bash
chmod 600 ~/.config/agentic-dev-flow/.env
python3 ~/plugins/agentic-dev-flow/scripts/check_environment.py
```

Confirme `FRIDAY_MCP_BASE_URL` e `FRIDAY_MCP_API_TOKEN`.
Depois reinicie o host para recarregar o MCP.

## Token de uma conta sem tarefas

O Friday atual não expõe `get_current_user`.
Nesse caso, `list_my_tasks` não fornece identidade.
O plugin interrompe a atribuição com segurança.
Ele nunca usa e-mail fixo como fallback.

Para suportar contas totalmente novas, o servidor Friday
deve expor `get_current_user` usando o mesmo token.

## O host não inicia o fluxo automaticamente

Confirme que o plugin está habilitado.
Depois abra uma sessão completamente nova.

Também confirme os arquivos instalados:

```bash
find ~/.codex/agents ~/.claude/agents ~/.gemini/agents ~/.gemini/config/agents \
  -maxdepth 1 -name 'agentic-*' -print
```

## Claude não encontra atualizações

```bash
claude plugin update agentic-dev-flow@agentic-dev-flow-local
```

Reinicie a sessão depois da atualização.

## Gemini não encontra agentes

Confirme se o recurso de agentes está habilitado.
Use `/agents` dentro do Gemini CLI para verificar.

## Antigravity não encontra o plugin

```bash
ls -la ~/.gemini/config/plugins/agentic-dev-flow
```

Execute novamente `scripts/install.py` quando necessário.
Depois reinicie completamente o Antigravity.

## Node do Windows apareceu dentro do WSL

Confira:

```bash
which node
which npm
```

Os caminhos não devem começar com `/mnt/c`.
Reinstale Node.js dentro do Ubuntu se necessário.

# Segurança operacional

- Mantenha qualquer token somente no `.env`.
- Use permissão `600` no arquivo privado.
- Autorize somente ferramentas necessárias.
- Revise mudanças antes do primeiro push.
- Não marque validações falhas como concluídas.
- Não permita exclusões administrativas automáticas.
- O agente principal controla mudanças externas.

# Estrutura do pacote

```text
agentic-dev-flow/
├── .codex-plugin/          Manifesto Codex
├── .claude-plugin/         Manifesto Claude Code
├── adapters/               Agentes específicos por host
├── rules/                  Regras automáticas do Antigravity
├── scripts/                Instalador e bridge Friday
├── skills/                 Fluxos reutilizáveis
├── .env.example            Modelo de configuração
├── gemini-extension.json   Manifesto Gemini CLI
├── mcp_config.json         MCP do Antigravity
└── plugin.json             Manifesto Antigravity
```

# Referências oficiais

- [Codex CLI](https://learn.chatgpt.com/docs/codex/cli)
- [Codex no WSL](https://learn.chatgpt.com/docs/windows/wsl)
- [Claude Code no WSL](https://code.claude.com/docs/en/installation)
- [Gemini CLI](https://geminicli.com/docs/get-started/installation/)
- [Subagentes do Gemini CLI](https://geminicli.com/docs/core/subagents/)
- [Antigravity CLI](https://antigravity.google/docs/cli/install)
- [Plugins do Antigravity](https://antigravity.google/docs/plugins)
- [Subagentes do Antigravity](https://antigravity.google/docs/subagents)
