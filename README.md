# Conecta Unis — MVP web funcional

Sistema de carreiras e oportunidades acadêmicas, desenvolvido a partir do documento **Conecta Unis — Proposta e Levantamento de Requisitos Iniciais**, de 29/09/2026. Projeto para revisão e aprovação **antes** de qualquer deploy público.

**Importante:** esta entrega contém uma aplicação executável com persistência de dados, não apenas telas ou layout. Ainda é um **MVP de teste**: não foi homologado pela faculdade, não recebeu auditoria completa de segurança/LGPD e não deve operar com dados pessoais reais até que essas etapas sejam concluídas.

## Tecnologias

- **FastAPI + Python 3.11 ou superior:** rotas, formulários, controles de acesso, regras de negócio.
- **SQLAlchemy:** persistência em SQLite para testes, PostgreSQL como opção futura.
- **Jinja2 + HTML + CSS + JavaScript:** interface responsiva sem dependência de build Node.js.
- **Argon2:** hash de senhas; **sessão assinada** e **proteção CSRF** em formulários.
- **SMTP:** confirmação de e-mail e recuperação de senha quando configurado.
- **Pytest/TestClient:** testes automatizados do fluxo principal.

## 1. Executar no computador (Windows PowerShell)

Instale [Python](https://www.python.org/downloads/) 3.11+ e descompacte este projeto. Abra PowerShell na pasta `conecta-unis-mvp` e execute:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload
```

Se o PowerShell bloquear a ativação de scripts, dispense a ativação e execute ` .\.venv\Scripts\python.exe -m pip install -r requirements.txt` e ` .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload` diretamente.

Abra **http://localhost:8000**. Para simular as contas de teste, altere `DEMO_SEED=false` para `DEMO_SEED=true` no arquivo `.env`, **somente em desenvolvimento**, antes de iniciar o aplicativo. Configure `SESSION_SECRET` com uma chave aleatória grande mesmo no ambiente de testes para preservar as sessões após reinicializações. O banco é criado automaticamente na primeira inicialização em `./data/conecta_unis.db`.

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## 2. Acessos fictícios para demonstração

Configure `APP_ENV=development` e `DEMO_SEED=true`. **Estes usuários não representam pessoas ou empresas reais.**

| Perfil | Login | Senha de teste |
|---|---|---|
| Aluna | `aluna@demo.test` | `Teste@12345` |
| Egresso | `egresso@demo.test` | `Teste@12345` |
| Professor | `professor@demo.test` | `Teste@12345` |
| Empresa | `empresa@demo.test` | `Teste@12345` |
| Coordenação | `admin@demo.test` | `Teste@12345` |

Três vagas fictícias são criadas na primeira inicialização com modo de demonstração ativado. Não habilite `DEMO_SEED` em ambiente público. **O código impede esse modo quando `APP_ENV=production`.**

Para configurar um administrador sem usar os dados fictícios, defina `ADMIN_EMAIL` e `ADMIN_PASSWORD` (senha com ao menos 10 caracteres) no `.env` antes de iniciar. A conta é criada apenas se ainda não existir. Não salve senhas reais em repositórios Git.

## 3. O que testar

1. Entre como **aluna**, acesse *Explorar vagas*, abra uma oportunidade, faça uma candidatura e consulte *Minhas candidaturas*.
2. Entre como **empresa**, crie ou edite uma vaga, pause/reabra, consulte candidatos, atualize o status e envie uma mensagem.
3. Entre como **coordenação**, veja indicadores, consulte os cadastros e modere uma vaga.
4. Cadastre um **novo usuário**. No modo de desenvolvimento sem SMTP, o sistema mostra um **link temporário de confirmação** na página após o cadastro. Confirme o e-mail; entre como coordenação para aprovar a conta; só então o usuário poderá entrar.
5. Teste o envio de currículo em PDF no perfil do aluno. O arquivo só pode ser acessado pelo próprio aluno, pela coordenação ou por uma empresa que recebeu uma candidatura dele.

**Segurança da aprovação:** o sistema não consegue comprovar sozinho a matrícula ou a titularidade do CNPJ. O responsável da coordenação precisa conferir essas informações antes de clicar *Aprovar*. A validação formal deve ser definida com a instituição.

## 4. Testes automatizados

```bash
python -m pip install pytest httpx
python -m pytest -q tests/test_workflows.py
```

Os testes validam rotas públicas, proteção CSRF, login e permissões por perfil, candidatura única, publicação/gestão e moderação de vagas, mensagens, mudança de status, cadastro com confirmação por e-mail e aprovação administrativa, privacidade de currículos e exclusão de conta. O teste usa um banco **temporário** e dados fictícios.

## 5. Arquitetura e arquivos

```text
app/
  main.py          Rotas HTML, regras de negócio e verificações de permissão
  database.py      Conexão de banco (SQLite/PostgreSQL)
  models.py        Modelos de usuários, vagas, candidaturas, mensagens e logs
  security.py      Senhas Argon2, tokens, normalização
  mail.py          Envio de e-mail via SMTP
  templates/       Páginas HTML renderizadas pelo Jinja2
  static/          CSS responsivo e JavaScript de interação
requirements.txt   Dependências Python
Dockerfile         Contêiner para deploy
railway.json       Configuração de referência para Railway
.env.example       Configurações de exemplo, sem senhas reais
tests/             Testes de fluxos completos
MATRIZ_REQUISITOS.md Rastreabilidade entre PDF e MVP
```

## 6. Preparar deploy **após aprovação**

**Recomendação para teste inicial:** Railway com repositório GitHub privado, aplicativo Python e volume persistente.

1. Publique o código em um repositório **privado** do GitHub. Não envie `.env`, bancos, arquivos de upload ou currículos reais.
2. Crie um novo serviço no Railway a partir do repositório. O `railway.json` e o `Dockerfile` já estão disponíveis como referência.
3. Configure domínio de teste HTTPS e as variáveis `APP_ENV=production`, `APP_BASE_URL=https://SEU-DOMINIO`, `SESSION_SECRET` aleatório de 64+ caracteres, `ADMIN_EMAIL`, `ADMIN_PASSWORD` e as credenciais SMTP.
4. Para manter os arquivos em SQLite, monte **um volume persistente** no caminho `/data`, configure `DATABASE_URL=sqlite:////data/conecta_unis.db` e `UPLOAD_DIR=/data/uploads`. **Sem volume, arquivos e banco SQLite podem desaparecer a cada nova implantação.**
5. Alternativamente, utilize PostgreSQL gerenciado no `DATABASE_URL`, mas **ainda será necessário armazenamento persistente para currículos e logotipos**.
6. Confira o endpoint `/saude`, registros da aplicação, cadastro/verificação de e-mail, perfis, permissões, upload/download e backups em ambiente isolado antes de compartilhar o link.
7. Configure **backups automáticos diários do banco e dos arquivos**, retenção, restauração testada, monitoramento e notificações de falha. A aplicação **não provisiona esses recursos automaticamente**.

**Notas de implantação:** alguns provedores oferecem planos gratuitos sem disco persistente. Não utilize armazenamento efêmero para dados de usuários. O ambiente gratuito/volume e os preços precisam ser validados na data da implantação. Se utilizar PostgreSQL, o driver `psycopg` já está listado no `requirements.txt`.

## 7. Limitações conhecidas do MVP

- Integração com o sistema acadêmico do UNIS, verificação automática de matrícula/CNPJ, entrevistas por vídeo e pagamentos **não foram implementados**.
- Recomendação de vagas, favoritos, rede social, feed, endossos de professores, eventos, denúncia e notificações push ficam para etapas futuras.
- Perfil acadêmico: o currículo e a foto podem ser anexados, mas não há antivírus de arquivos ou controle refinado de visibilidade de cada campo.
- Mensagens existem dentro das candidaturas; não há notificação de mensagem por e-mail/push nem leitura em tempo real.
- “Aprovada” é uma etapa da candidatura, **não uma contratação formal confirmada**. Os indicadores de contratação exigem integração/validação posterior.
- O texto de privacidade é **provisório**, sem dados de controlador e DPO. Necessita revisão institucional e jurídica antes de uso real.
- Os requisitos de latência (até 3 s e 2 s), disponibilidade 98%, backup diário e acessibilidade integral **ainda precisam ser comprovados em homologação**. Não estão garantidos por esta entrega.
- A proteção básica contra força bruta é em memória (adequada apenas a instância única de testes). Um ambiente público deverá adotar mecanismos de rate limiting distribuído, gestão de logs, retenção, verificação de upload, migrações de banco, revisão de dependências, testes de penetração e monitoramento.
- A identidade visual é uma **proposta inicial**, não um logotipo oficial autorizado pelo UNIS.

## 8. Próximos passos sugeridos

Validar as telas e a navegação com os integrantes, professor e representantes dos cursos; recolher correções; homologar fluxos e privacidade; finalizar as configurações de segurança e armazenamento; **somente depois aprovar e fazer o deploy**.
