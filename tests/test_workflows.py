"""Testes end-to-end do MVP contra banco SQLite de teste e contas 100% fictícias."""
import os
import re
import tempfile
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix='conecta_test_')
os.environ['APP_ENV'] = 'development'
os.environ['DEMO_SEED'] = 'true'
os.environ['SESSION_SECRET'] = 'test-only-secret-'*4
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(TMP.name) / 'test.db')
os.environ['UPLOAD_DIR'] = str(Path(TMP.name) / 'uploads')

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import User
from sqlalchemy import select

@pytest.fixture(scope='module')
def context():
    with TestClient(app) as client:
        yield client

def csrf(response):
    return re.search(r'name="_csrf" value="([^"]+)"', response.text).group(1)

def login(client, email, password='Teste@12345'):
    p = client.get('/entrar')
    r = client.post('/entrar', data={'_csrf':csrf(p), 'email':email, 'password':password}, follow_redirects=False)
    return r

def logout(client):
    p = client.get('/perfil')
    return client.post('/sair', data={'_csrf':csrf(p)}, follow_redirects=False)

def test_public_routes(context):
    for path in ['/','/vagas','/cadastrar','/entrar','/privacidade','/saude']:
        r=context.get(path)
        assert r.status_code==200, path
    assert 'Estágio em Administração' in context.get('/vagas').text
    assert context.get('/saude').json()['ok'] is True

def test_student_company_and_admin_complete_flow(context):
    c=context
    assert login(c,'aluna@demo.test').status_code==303
    dash=c.get('/painel')
    assert 'Marina' in dash.text
    assert c.get('/empresa').status_code==200  # redirect followed -> dashboard, not company
    job_page=c.get('/vagas/1')
    assert job_page.status_code==200
    token=csrf(job_page)
    assert c.post('/vagas/1/candidatar', data={'_csrf':'invalid','message':'Olá'},follow_redirects=False).status_code==403
    r=c.post('/vagas/1/candidatar',data={'_csrf':token,'message':'Tenho interesse.'},follow_redirects=False)
    assert r.status_code==303 and r.headers['location']=='/candidaturas'
    assert 'Estágio em Administração' in c.get('/candidaturas').text
    r=c.post('/vagas/1/candidatar',data={'_csrf':token},follow_redirects=False)
    assert r.status_code==303
    assert 'já se candidatou' in c.get('/vagas/1').text
    assert c.get('/media/curriculo/4').status_code==404  # denied / missing file
    logout(c)

    assert login(c,'empresa@demo.test').status_code==303
    page=c.get('/empresa')
    assert 'Minhas vagas' in page.text
    job_form=c.get('/empresa/vagas/nova')
    token=csrf(job_form)
    newjob = {'_csrf':token,'title':'Estágio em Dados','description':'Análise de relatórios e suporte ao time de finanças.','job_type':'Estágio',
              'area':'Dados','city':'São Lourenço','work_mode':'Híbrido','deadline':'2027-08-30','requirements':'Excel','benefits':'Mentoria'}
    res=c.post('/empresa/vagas/nova',data=newjob,follow_redirects=False)
    assert res.status_code==303
    assert 'Estágio em Dados' in c.get('/empresa').text
    candidate_page=c.get('/empresa/vagas/1/candidatos')
    assert 'Marina Oliveira' in candidate_page.text
    r=c.post('/empresa/candidaturas/1/status',data={'_csrf':csrf(candidate_page),'status':'entrevista'},follow_redirects=False)
    assert r.status_code==303
    convo=c.get('/mensagens/1')
    assert convo.status_code==200
    assert c.post('/mensagens/1',data={'_csrf':csrf(convo),'content':'Vamos marcar uma entrevista.'},follow_redirects=False).status_code==303
    assert 'Vamos marcar uma entrevista.' in c.get('/mensagens/1').text
    assert 'Marina Oliveira' in c.get('/empresa/talentos').text
    logout(c)

    assert login(c,'aluna@demo.test').status_code==303
    assert 'entrevista' in c.get('/candidaturas').text
    assert 'Vamos marcar uma entrevista.' in c.get('/mensagens/1').text
    # estudantes não criam vagas
    assert c.get('/empresa/vagas/nova', follow_redirects=False).status_code==303
    logout(c)

    assert login(c,'admin@demo.test').status_code==303
    assert 'Painel da' in c.get('/admin').text
    assert 'Estágio em Administração' in c.get('/admin/vagas').text
    assert 'Total de candidaturas' in c.get('/admin/relatorios').text
    logout(c)

def test_register_email_verification_and_coordination_approval(context):
    c=context
    page=c.get('/cadastrar')
    r=c.post('/cadastrar',data={'_csrf':csrf(page),'role':'student','name':'Ana Teste','email':'ana@exemplo.test','password':'SenhaForte@123',
        'course':'Administração','consent':'yes'})
    assert r.status_code==200
    assert 'Cadastro enviado' in r.text
    match=re.search(r'href="(http://localhost:8000/verificar/[^\"]+)"',r.text)
    assert match, r.text
    assert login(c,'ana@exemplo.test','SenhaForte@123').status_code==200  # not verified
    assert 'Entre na sua conta' in c.get('/entrar').text
    link=match.group(1).replace('http://localhost:8000','')
    assert 'E-mail confirmado!' in c.get(link).text
    assert login(c,'ana@exemplo.test','SenhaForte@123').status_code==200  # awaiting approval
    assert login(c,'admin@demo.test').status_code==303
    adminpage=c.get('/admin/usuarios')
    assert 'ana@exemplo.test' in adminpage.text
    with SessionLocal() as db:
        person=db.scalar(select(User).where(User.email=='ana@exemplo.test'))
        uid=person.id
    res=c.post(f'/admin/usuarios/{uid}/acao',data={'_csrf':csrf(adminpage),'action':'approve'},follow_redirects=False)
    assert res.status_code==303
    logout(c)
    assert login(c,'ana@exemplo.test','SenhaForte@123').status_code==303
    assert 'Ana' in c.get('/painel').text
    logout(c)

def test_job_moderation(context):
    c=context
    assert login(c,'admin@demo.test').status_code==303
    page=c.get('/admin/vagas')
    res=c.post('/admin/vagas/2/acao',data={'_csrf':csrf(page),'action':'rejected'},follow_redirects=False)
    assert res.status_code==303
    logout(c)
    assert 'Assistente de Departamento Pessoal' not in c.get('/vagas').text
    assert c.get('/vagas/2').status_code==404

def test_resume_access_controls(context):
    c=context
    assert login(c,'aluna@demo.test').status_code==303
    page=c.get('/perfil')
    r=c.post('/perfil',data={'_csrf':csrf(page),'name':'Marina Oliveira','course':'Administração','city':'São Lourenço','skills':'Excel'},
             files={'resume':('curriculo.pdf',b'%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF', 'application/pdf')},follow_redirects=False)
    assert r.status_code==303
    assert c.get('/media/curriculo/1').status_code==200
    logout(c)
    # outro aluno não pode ler currículo
    assert login(c,'egresso@demo.test').status_code==303
    assert c.get('/media/curriculo/1').status_code==403
    logout(c)
    # empresa que recebeu candidatura pode ler
    assert login(c,'empresa@demo.test').status_code==303
    assert c.get('/media/curriculo/1').status_code==200
    logout(c)

def test_delete_account(context):
    c=context
    assert login(c,'ana@exemplo.test','SenhaForte@123').status_code==303
    page=c.get('/perfil')
    r=c.post('/conta/excluir', data={'_csrf':csrf(page),'confirm':'EXCLUIR','password':'SenhaForte@123'},follow_redirects=False)
    assert r.status_code==303
    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.email=='ana@exemplo.test')) is None

def test_admin_can_delete_non_admin_user(context):
    c=context
    assert login(c,'admin@demo.test').status_code==303
    page=c.get('/admin/usuarios')
    with SessionLocal() as db:
        person=db.scalar(select(User).where(User.email=='egresso@demo.test'))
        uid=person.id
    res=c.post(f'/admin/usuarios/{uid}/excluir',data={'_csrf':csrf(page),'confirm':'EXCLUIR'},follow_redirects=False)
    assert res.status_code==303
    with SessionLocal() as db:
        assert db.get(User,uid) is None
    logout(c)
