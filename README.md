# Controle Obras GrupoVax

Base funcional local para cadastrar e acompanhar demandas de manutenção e obras com planejamento 5W2H, prioridade, urgência, equipe, responsável, andamento, pendências e fotos.

O conteúdo inicial foi conferido em 31/10/2026: a branch `main` continha somente este README com o título do projeto, no commit `b4aaccc` (`Add project title to README.md`). Esta entrega acrescenta aplicação e banco local, sem integrações externas.

## Executar

Requer Python 3.12 ou superior, com SQLite disponível na biblioteca padrão. Não há pacotes para instalar nem etapa de build.

Na pasta do projeto, execute:

```sh
python -c "import getpass, os, runpy; os.environ['ADMIN_PASSWORD']=getpass.getpass('Senha da administração: '); os.environ['OPERATOR_PASSWORD']=getpass.getpass('Senha da operação: '); runpy.run_path('server.py', run_name='__main__')"
```

Escolha senhas diferentes, cada uma com pelo menos 10 caracteres. Elas são solicitadas sem aparecer na tela e não devem ser gravadas no repositório. O servidor também aceita as variáveis de ambiente `ADMIN_PASSWORD` e `OPERATOR_PASSWORD`, caso já estejam definidas, usando `python server.py`.

Abra [http://localhost:8000](http://localhost:8000) no navegador do mesmo computador. Entre com o usuário `admin` ou `operacao` e a senha correspondente. Use `Ctrl+C` no terminal para encerrar.

Esta versão escuta somente em `127.0.0.1`. Não está hospedada e não permite acesso por outro computador ou celular. A interface se adapta a telas menores, mas acesso remoto exige uma etapa própria de implantação.

## Primeiro fluxo

1. Entre como `admin` e clique em **Administração • nova demanda**.
2. Informe título e tipo, escolha prioridade e urgência separadamente e preencha os sete elementos do 5W2H: o que, por quê, onde, quando, quem, como e custo previsto. Defina equipe e responsável.
3. Salve. A demanda aparece no acompanhamento com status **Aberta** e progresso de **0%**.
4. Use a busca por título, local ou responsável e o filtro de status. Clique em **Acompanhar** para abrir o planejamento completo.
5. Registre o relato da execução, status, percentual e pendências atuais. Anexe fotos JPEG, PNG ou WebP de até 5 MB por arquivo.
6. Para concluir, informe **Concluída**, **100%** e deixe as pendências vazias após resolvê-las.
7. Saia e entre como `operacao`: o acompanhamento, os relatos e as fotos continuam disponíveis, enquanto cadastro e alteração do planejamento são bloqueados pelo servidor.

O administrador pode usar **Editar planejamento** nos detalhes. A operação pode alterar status, progresso e pendências, registrar relatos e anexar fotos. Ambos consultam todas as demandas, incluindo custos; não há divisão de visibilidade por equipe nesta base.

## Acessos e limites

As permissões são verificadas na API, além dos controles da interface. Existem duas contas, uma por perfil, sem cadastro individual de pessoas: `admin` e `operacao`. Equipe, responsável e envolvidos são textos do planejamento, não contas de acesso. O histórico identifica a conta utilizada, sem comprovar qual pessoa usou uma conta compartilhada.

As sessões duram oito horas e ficam na memória do servidor. **Sair** invalida a sessão; reiniciar o servidor encerra todas as sessões e exige informar as senhas novamente. A base foi feita para uso local inicial, sem envio de mensagens, autenticação externa ou serviços em nuvem.

## Arquitetura

| Caminho | Responsabilidade |
|---|---|
| `server.py` | Servidor HTTP local, autenticação, autorização, validações, API e persistência SQLite |
| `web/index.html` | Estrutura dos formulários e das visões |
| `web/app.js` | Cadastro, consulta, edição, andamento e envio de fotos pela API |
| `web/style.css` | Apresentação e adaptação para telas menores |
| `docs/modelo-dados.md` | Entidades, campos e regras do modelo |
| `tests/test_server.py` | Verificações automatizadas do fluxo e das permissões |
| `data/grupovax.sqlite3` | Banco criado ao iniciar; inclui demandas, histórico e fotos |

Os dados ficam no servidor local, não no armazenamento do navegador. O diretório `data/`, arquivos `.env` e caches Python são ignorados pelo Git. Nenhuma demanda ou foto real deve ser adicionada ao repositório público.

## Preservar os dados

Encerre o servidor antes de copiar `data/grupovax.sqlite3` para um local protegido. Essa cópia inclui as fotos. Para restaurar, com o servidor desligado, reponha o arquivo no mesmo caminho e inicie novamente. Não há backup automático nesta entrega; perder o arquivo significa perder os registros.

## Verificar

Na pasta do projeto:

```sh
python -m unittest discover -s tests -v
```

Os testes usam um banco temporário e verificam login, permissões, cadastro, atualização, conclusão, foto autenticada, persistência, validações e rejeição de origem externa. Não usam nem alteram `data/grupovax.sqlite3`.

Para conferir a interface, execute o primeiro fluxo acima no navegador e recarregue a página após salvar. Não abra `web/index.html` diretamente: o servidor é necessário para autenticação e persistência.
