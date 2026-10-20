# Rastreabilidade dos requisitos ao MVP

Base: **Conecta Unis — Proposta e Levantamento de Requisitos Iniciais** (2026), seção 4 e seção 7. As implementações abaixo descrevem funcionalidades efetivamente presentes no código, não garantias de homologação.

| Requisito | Prioridade PDF | Situação no MVP | Evidência / ressalva |
|---|---|---|---|
| RF01 Cadastro e validação por e-mail | Essencial | Implementado | `/cadastrar`, `/verificar/{token}`. SMTP configurável |
| RF02 Login/logout/recuperação | Essencial | Implementado | `/entrar`, `/sair`, `/recuperar`, `/redefinir/{token}` |
| RF03 Vínculo acadêmico | Essencial | Validação manual | Coordenação precisa verificar vínculo antes de aprovar; não há integração acadêmica |
| RF04 Empresa aprovada antes de operar | Importante | Implementado, com conferência manual | CNPJ tem validação matemática e coordenação autoriza conta |
| RF05 Perfil profissional | Essencial | Implementado (básico) | `/perfil`: formação, foto, habilidades, experiências, idiomas, cursos, resumo |
| RF06 Currículo PDF e links | Essencial | Implementado | Upload e acesso controlado a PDF; links de portfólio e LinkedIn |
| RF07 Controle de privacidade | Importante | Parcial | Opt-in para contato público; PDF só para empresas com candidatura |
| RF08 Perfil empresa | Essencial | Implementado (básico) | Razão social, CNPJ, segmento, descrição, cidade, site e logotipo |
| RF09 Professor recomenda alunos | Desejável | Pendente | Professor tem cadastro e perfil, sem endossos |
| RF10 Publicação completa de vagas | Essencial | Implementado | `/empresa/vagas/nova`: campos do levantamento |
| RF11 Gerenciar vagas | Essencial | Implementado | Editar, pausar, encerrar, reabrir e preencher |
| RF12 Busca e filtros | Importante | Parcial | Palavra-chave, cidade, tipo e modalidade; área por parâmetro HTTP |
| RF13 Favoritar vagas | Desejável | Pendente | Fora do MVP essencial |
| RF14 Compatibilidade automática | Desejável | Pendente | Fora do MVP essencial |
| RF15 Moderação de vagas | Importante | Implementado | `/admin/vagas` |
| RF16 Candidatura com currículo e mensagem | Essencial | Implementado | `/vagas/{id}/candidatar`; única por aluno e vaga |
| RF17 Status da candidatura | Importante | Implementado | `/candidaturas` |
| RF18 Empresas analisam candidaturas | Essencial | Implementado | `/empresa/vagas/{id}/candidatos` e mudança de status |
| RF19 Busca de talentos | Importante | Implementado (básico) | `/empresa/talentos`: curso, habilidade e cidade |
| RF20 Favoritar candidatos | Desejável | Pendente | Fora do MVP essencial |
| RF21 Mensagens candidato/empresa | Importante | Implementado | `/mensagens`, vinculado a candidatura |
| RF22 Notificações | Desejável | Pendente | SMTP limitado ao cadastro e recuperação |
| RF23 Conexões/feed | Desejável | Pendente | Fora do MVP essencial |
| RF24 Divulgação de eventos | Desejável | Pendente | Fora do MVP essencial |
| RF25 Gerenciar usuários | Essencial | Implementado | Aprovação, suspensão, reativação e exclusão administrativa |
| RF26 Denúncias | Importante | Pendente | Não implementado |
| RF27 Indicadores | Importante | Parcial | `/admin/relatorios`, com limitações nos dados de contratação |
| RF28 Informar contratação | Importante | Parcial | Status “aprovada”; não é confirmação formal de contratação |

**Regras RN01 a RN08:** RN01 validação do vínculo manual por coordenação; RN02 bloqueio de empresas pendentes; RN03 unicidade via restrição no banco; RN04 aviso sobre a lei do estágio; RN05 prazo validado nas buscas e candidaturas; RN06 aviso e bloqueio de algumas expressões de cobrança de taxa (moderação humana continua necessária); RN07 PDF restrito e contato configurável; RN08 suspensão manual de contas e moderação de vagas (sem denúncias/reincidência automatizadas).

**RNF01–RNF11:** foram consideradas usabilidade e adaptação móvel, hash Argon2, HTTPS a configurar no host, autorização de rotas, CSRF, escape em templates, exclusão voluntária, logs essenciais, separação de camadas e identidade visual preliminar. Desempenho, uptime, backup, auditoria LGPD integral, acessibilidade formal e escalabilidade devem ser validados antes da publicação.
