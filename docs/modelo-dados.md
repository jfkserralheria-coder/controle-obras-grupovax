# Modelo de dados

SQLite local em `data/grupovax.sqlite3`. O servidor cria as tabelas ausentes na inicialização e habilita chaves estrangeiras em cada conexão. Não há integração externa nem dados de demonstração inseridos automaticamente.

## Entidades persistidas

### `demands` — planejamento e estado atual

| Coluna | Tipo SQLite | Regra |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Identificador gerado pelo SQLite |
| `payload` | TEXT NOT NULL | Objeto JSON com os campos abaixo, validado pela aplicação |
| `created_at` | TEXT NOT NULL | Data e hora de criação em ISO 8601, UTC |
| `updated_at` | TEXT NOT NULL | Data e hora da última alteração ou foto, em ISO 8601, UTC |

| Campo do `payload` | Tipo JSON | Regra |
|---|---|---|
| `title` | string | Título obrigatório |
| `type` | string | `Manutenção` ou `Obra`; padrão `Manutenção` |
| `priority` | string | `Baixa`, `Média` ou `Alta`; padrão `Média` |
| `urgency` | string | `Normal`, `Urgente` ou `Imediata`; padrão `Normal` |
| `what` | string | O que será feito; obrigatório |
| `why` | string | Por que será feito; obrigatório |
| `where` | string | Local; obrigatório |
| `when` | string | Prazo obrigatório, data válida `AAAA-MM-DD`, sem horário |
| `who` | string | Pessoas envolvidas no 5W2H; obrigatório |
| `how` | string | Forma de execução; obrigatório |
| `cost` | number | Custo previsto em reais, finito e não negativo; padrão `0` |
| `team` | string | Nome da equipe; obrigatório |
| `responsible` | string | Nome do responsável; obrigatório |
| `status` | string | `Aberta`, `Em andamento`, `Bloqueada` ou `Concluída`; padrão `Aberta` |
| `progress` | number | Percentual inteiro de 0 a 100; padrão `0` |
| `pending` | string | Texto das pendências atuais; padrão vazio |

Os campos textuais são aparados nas extremidades e aceitam até 5.000 caracteres na API; os obrigatórios não aceitam somente espaços. O formulário limita o título a 200 caracteres. Prioridade e urgência são independentes. A validação rejeita campos desconhecidos, números booleanos e valores não finitos. O custo é um número JSON, não um livro contábil nem um valor em centavos inteiros; a interface apresenta reais com duas casas decimais.

Não há entidades separadas de equipes ou pessoas: `who`, `team` e `responsible` são textos. O estado `Concluída` exige `progress = 100` e `pending` vazio. Os demais estados podem ter qualquer percentual válido. Não há uma máquina de transições que impeça reabrir uma demanda.

### `updates` — histórico

| Coluna | Tipo SQLite | Regra |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Identificador do registro |
| `demand_id` | INTEGER NOT NULL | Referência a `demands.id` |
| `author` | TEXT NOT NULL | Conta `admin` ou `operacao` |
| `note` | TEXT NOT NULL | Relato e/ou descrição automática da alteração |
| `created_at` | TEXT NOT NULL | ISO 8601, UTC |

O servidor gera registros ao cadastrar, alterar campos e adicionar fotos. Relatos enviados aceitam até 5.000 caracteres. O histórico é apresentado do mais recente ao mais antigo. Não existe rota de edição ou exclusão desses registros. A tabela não é um mecanismo externo de auditoria imutável: quem acessa diretamente o arquivo SQLite pode modificá-la.

### `photos` — evidências

| Coluna | Tipo SQLite | Regra |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Identificador da foto |
| `demand_id` | INTEGER NOT NULL | Referência a `demands.id` |
| `name` | TEXT NOT NULL | Nome informado, não vazio, até 200 caracteres |
| `mime` | TEXT NOT NULL | `image/jpeg`, `image/png` ou `image/webp` |
| `content` | BLOB NOT NULL | Conteúdo binário de até 5 MB |
| `author` | TEXT NOT NULL | Conta que enviou a foto |
| `created_at` | TEXT NOT NULL | ISO 8601, UTC |

O envio usa JSON com uma data URL base64. O servidor confere formato declarado, base64 e assinatura inicial do arquivo; não realiza decodificação completa da imagem. Cada corpo HTTP aceita até 7 MB para acomodar a codificação. As fotos só são servidas por uma rota autenticada. Não há exclusão de evidências pela interface.

## Autenticação e autorização

As contas e sessões não são tabelas. As senhas vêm de variáveis de ambiente, são derivadas com PBKDF2-HMAC-SHA256 e sal aleatório na memória do processo. As sessões usam tokens aleatórios em cookie `HttpOnly` e `SameSite=Strict`, expiram após oito horas e são perdidas ao reiniciar.

| Ação | `admin` | `operacao` |
|---|---|---|
| Consultar demandas e fotos | Sim | Sim |
| Criar demanda | Sim | Não |
| Alterar planejamento 5W2H, equipe, responsável, prioridade e urgência | Sim | Não |
| Atualizar status, progresso e pendências | Sim | Sim |
| Registrar relato e foto | Sim | Sim |

Não há exclusão de demandas, gestão de contas, atribuição de acesso por equipe ou hospedagem nesta base. O banco armazena o estado atual e o histórico de trabalho; o diretório `data/` deve permanecer fora do repositório público.
