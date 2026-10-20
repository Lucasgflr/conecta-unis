import os
import re
import secrets
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, or_, and_, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.sessions import SessionMiddleware

from app.database import Base, engine, SessionLocal, get_db
from app.models import User, Job, Application, Message, AuditLog, EmailToken, utcnow
from app.security import hash_password, verify_password, create_token, consume_token, clean_text, valid_url, password_ok
from app.mail import send_mail

ROOT = Path(__file__).resolve().parent
APP_ENV = os.getenv('APP_ENV', 'development').lower()
BASE_URL = os.getenv('APP_BASE_URL', 'http://localhost:8000').rstrip('/')
UPLOAD_DIR = Path(os.getenv('UPLOAD_DIR', './data/uploads')).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
SECRET = os.getenv('SESSION_SECRET', '')
if APP_ENV == 'production' and len(SECRET) < 32:
    raise RuntimeError('Defina SESSION_SECRET com pelo menos 32 caracteres em produção.')
if not SECRET:
    SECRET = secrets.token_urlsafe(48)
    print('AVISO: SESSION_SECRET temporária. Defina a variável para preservar sessões após reinícios.', flush=True)

ACADEMIC_ROLES = ('student', 'alumni', 'teacher')
CANDIDATE_ROLES = ('student', 'alumni')
JOB_TYPES = ('Estágio', 'Trainee', 'CLT', 'PJ', 'Temporário', 'Jovem aprendiz')
WORK_MODES = ('Presencial', 'Híbrido', 'Remoto')
APP_STATUSES = ('enviada', 'visualizada', 'em análise', 'entrevista', 'aprovada', 'não selecionada')
JOB_STATUSES = ('active', 'paused', 'closed', 'filled')
ROLE_NAMES = {'student':'Aluno', 'alumni':'Egresso', 'teacher':'Professor', 'company':'Empresa', 'admin':'Coordenação'}
STATUS_NAMES = {'pending':'Pendente', 'active':'Ativo', 'suspended':'Suspenso', 'paused':'Pausada', 'closed':'Encerrada', 'filled':'Preenchida', 'rejected':'Removida'}

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        bootstrap(db)
    yield

app = FastAPI(title='Conecta Unis', docs_url=None if APP_ENV == 'production' else '/api/docs', lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET, same_site='lax', https_only=APP_ENV == 'production', max_age=60*60*12)
app.mount('/static', StaticFiles(directory=str(ROOT / 'static')), name='static')

@app.middleware('http')
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; form-action 'self'; base-uri 'self'; frame-ancestors 'none'"
    return response
templates = Jinja2Templates(directory=str(ROOT / 'templates'))
templates.env.globals.update(role_names=ROLE_NAMES, status_names=STATUS_NAMES, app_statuses=APP_STATUSES, job_types=JOB_TYPES, work_modes=WORK_MODES, today=date.today, is_candidate=lambda u: bool(u and u.role in CANDIDATE_ROLES))

# Proteção simples contra tentativas excessivas de login; em produção multi-instância usar Redis/WAF.
ATTEMPTS = {}

def bootstrap(db):
    email = os.getenv('ADMIN_EMAIL', '').strip().lower()
    password = os.getenv('ADMIN_PASSWORD', '')
    if email and password:
        if not password_ok(password):
            raise RuntimeError('ADMIN_PASSWORD deve ter ao menos 10 caracteres.')
        if not db.scalar(select(User).where(User.email == email)):
            db.add(User(name='Coordenação Conecta Unis', email=email,
                password_hash=hash_password(password), role='admin', status='active',
                email_verified=True, institutional_verified=True))
            db.commit()
            print(f'Conta administrativa criada: {email}', flush=True)
    demo_enabled = os.getenv('DEMO_SEED', 'false').strip().lower() == 'true'
    demo_password = os.getenv('DEMO_PASSWORD', '')
    if demo_enabled:
        if APP_ENV == 'production':
            if os.getenv('DEMO_ALLOW_PUBLIC', 'false').strip().lower() != 'true':
                raise RuntimeError('Defina DEMO_ALLOW_PUBLIC=true para habilitar dados de teste em produção.')
            if not password_ok(demo_password) or demo_password == 'Teste@12345':
                raise RuntimeError('Defina DEMO_PASSWORD forte (10 a 128 caracteres), diferente da senha padrão.')
            if demo_password == os.getenv('ADMIN_PASSWORD', ''):
                raise RuntimeError('DEMO_PASSWORD deve ser diferente de ADMIN_PASSWORD.')
        seed_demo(db, demo_password or 'Teste@12345')
    elif os.getenv('DEMO_DISABLE_ACCOUNTS', 'false').strip().lower() == 'true':
        # Suspende as contas de demonstração, sem apagar dados históricos.
        demo_emails = ('aluna@demo.test', 'egresso@demo.test', 'professor@demo.test',
                       'empresa@demo.test', 'admin@demo.test')
        for account in db.scalars(select(User).where(User.email.in_(demo_emails))):
            account.status = 'suspended'
        db.commit()

def seed_demo(db, demo_password: str = 'Teste@12345'):
    demo = [
        dict(name='Marina Oliveira', email='aluna@demo.test', role='student', course='Administração',
             city='São Lourenço', period='6º período', skills='Excel, Finanças, Atendimento, Power BI',
             summary='Estudante de Administração interessada em gestão e análise de dados.'),
        dict(name='Gabriel Ribeiro', email='egresso@demo.test', role='alumni', course='Ciências Contábeis',
             city='Caxambu', period='Concluído', skills='Contabilidade, Excel, Fiscal',
             summary='Profissional de contabilidade em busca de novos desafios.'),
        dict(name='Beatriz Ferreira', email='professor@demo.test', role='teacher', course='Administração',
             city='São Lourenço'),
        dict(name='Empresa Horizonte RH', email='empresa@demo.test', role='company', company_name='Horizonte Consultoria',
             cnpj='11222333000181', industry='Consultoria', city='São Lourenço',
             summary='Consultoria fictícia para testes de usabilidade da plataforma.'),
        dict(name='Coordenação de Carreiras', email='admin@demo.test', role='admin'),
    ]
    for record in demo:
        existing = db.scalar(select(User).where(User.email == record['email']))
        if existing:
            # Reativa somente contas fictícias e sincroniza a senha temporária.
            existing.status = 'active'
            existing.email_verified = True
            existing.institutional_verified = True
            if not verify_password(existing.password_hash, demo_password):
                existing.password_hash = hash_password(demo_password)
        else:
            db.add(User(**record, password_hash=hash_password(demo_password),
                status='active', email_verified=True, institutional_verified=True))
    db.commit()
    company = db.scalar(select(User).where(User.email == 'empresa@demo.test'))
    if company and not db.scalar(select(Job).where(Job.company_id == company.id)):
        from datetime import timedelta
        jobs = [
            dict(title='Estágio em Administração', job_type='Estágio', area='Administração', city='São Lourenço', work_mode='Híbrido', compensation='Bolsa a combinar', description='Auxiliar na organização de processos, relatórios e atendimento aos clientes.', requirements='Estar cursando Administração e ter domínio básico do Excel.', benefits='Vale-transporte e mentoria'),
            dict(title='Assistente de Departamento Pessoal', job_type='CLT', area='Recursos Humanos', city='Caxambu', work_mode='Presencial', compensation='A combinar', description='Apoiar admissões, controles de ponto e rotinas de departamento pessoal.', requirements='Conhecimento básico de folha de pagamento.', benefits='Vale-alimentação'),
            dict(title='Analista Financeiro Júnior', job_type='Trainee', area='Finanças', city='Remoto', work_mode='Remoto', compensation='A combinar', description='Auxiliar análises financeiras e indicadores gerenciais.', requirements='Excel intermediário e interesse em planejamento.', benefits='Treinamentos e horário flexível'),
        ]
        for data in jobs:
            db.add(Job(company_id=company.id, deadline=date.today()+timedelta(days=30), **data))
        db.commit()

def log(db, user, action, target=''):
    db.add(AuditLog(actor_id=user.id if user else None, action=action, target=str(target)[:140]))

def current_user(request, db):
    uid = request.session.get('user_id')
    if not uid:
        return None
    user = db.get(User, uid)
    return user if user and user.status == 'active' and user.email_verified else None

def flash(request, msg, kind='info'):
    request.session['flash'] = {'msg': msg, 'kind': kind}

def render(request, name, db=None, **ctx):
    user = current_user(request, db) if db is not None else None
    if 'csrf' not in request.session:
        request.session['csrf'] = secrets.token_urlsafe(24)
    msg = request.session.pop('flash', None)
    return templates.TemplateResponse(request, name, {'user': user, 'csrf': request.session['csrf'], 'flash': msg, **ctx})

def go(to='/painel'):
    return RedirectResponse(to, status_code=303)

def guard(request, db, roles=None):
    user = current_user(request, db)
    if not user:
        raise HTTPException(303, headers={'Location': '/entrar'})
    if roles and user.role not in roles:
        raise HTTPException(303, headers={'Location': '/painel'})
    return user

async def form_data(request):
    data = await request.form()
    token = str(data.get('_csrf', ''))
    expected = request.session.get('csrf', 'not-set')
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(403, detail='Sessão expirada ou token de formulário inválido. Atualize a página.')
    return data

def can_view_job(job):
    return job.status == 'active' and job.deadline >= date.today() and job.company.status == 'active'

def readable_job_status(job):
    return 'Expirada' if job.status == 'active' and job.deadline < date.today() else STATUS_NAMES.get(job.status, job.status)
templates.env.globals['readable_job_status'] = readable_job_status

def is_valid_cnpj(value):
    digits = re.sub(r'\D', '', value)
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    for length in (12, 13):
        weights = ([5,4,3,2,9,8,7,6,5,4,3,2] if length == 12 else [6,5,4,3,2,9,8,7,6,5,4,3,2])
        check = (11 - sum(int(a)*b for a,b in zip(digits[:length], weights)) % 11) % 11
        if check != int(digits[length]):
            return False
    return True

async def save_upload(upload, user_id: int, kind: str):
    if not upload or not getattr(upload, 'filename', ''):
        return ''
    max_size = 5 * 1024 * 1024 if kind == 'resume' else 2 * 1024 * 1024
    raw = await upload.read(max_size+1)
    if len(raw) > max_size:
        raise ValueError(f'Arquivo muito grande. Limite de {max_size//1048576} MB.')
    if kind == 'resume':
        if not raw.startswith(b'%PDF-'):
            raise ValueError('O currículo deve ser um arquivo PDF válido.')
        ext = 'pdf'
    else:
        if raw.startswith(b'\xff\xd8\xff'):
            ext = 'jpg'
        elif raw.startswith(b'\x89PNG\r\n\x1a\n'):
            ext = 'png'
        else:
            raise ValueError('A foto deve estar em JPG ou PNG.')
    name = f'{kind}_{user_id}_{secrets.token_hex(12)}.{ext}'
    (UPLOAD_DIR / name).write_bytes(raw)
    return name

def remove_upload(name):
    if name:
        (UPLOAD_DIR / Path(name).name).unlink(missing_ok=True)

def send_link(email, route, token, subject):
    link = f'{BASE_URL}{route}/{token}'
    sent = send_mail(email, subject, f'Conecta Unis\n\nAcesse o link:\n{link}\n\nSe não solicitou, ignore este e-mail.')
    return link if APP_ENV == 'development' and not sent else None

@app.get('/', response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).options(joinedload(Job.company)).where(Job.status == 'active', Job.deadline >= date.today()).order_by(Job.created_at.desc()).limit(3)).all()
    return render(request, 'home.html', db, jobs=[j for j in jobs if j.company.status=='active'])

@app.get('/saude')
def health():
    return {'ok': True, 'service': 'conecta-unis'}

@app.get('/entrar', response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if current_user(request, db):
        return go()
    return render(request, 'login.html', db)

@app.post('/entrar')
async def login(request: Request, db: Session = Depends(get_db)):
    f = await form_data(request)
    email = clean_text(f.get('email'), 254).lower()
    password = str(f.get('password') or '')
    ip = request.client.host if request.client else 'unknown'
    key = (ip, email)
    times = [t for t in ATTEMPTS.get(key, []) if time.monotonic()-t < 900]
    if len(times) >= 8:
        return render(request, 'login.html', db, error='Muitas tentativas. Tente novamente em 15 minutos.')
    u = db.scalar(select(User).where(User.email == email))
    if not u or not verify_password(u.password_hash, password):
        times.append(time.monotonic()); ATTEMPTS[key] = times
        log(db, None, 'login_failed', email); db.commit()
        return render(request, 'login.html', db, error='E-mail ou senha incorretos.')
    if not u.email_verified:
        return render(request, 'login.html', db, error='Confirme seu e-mail antes de entrar.')
    if u.status != 'active':
        return render(request, 'login.html', db, error=('Seu cadastro ainda aguarda aprovação da coordenação.' if u.status=='pending' else 'Esta conta está suspensa.'))
    ATTEMPTS.pop(key, None)
    request.session.clear()
    request.session['user_id'] = u.id
    request.session['csrf'] = secrets.token_urlsafe(24)
    log(db, u, 'login', u.email); db.commit()
    return go()

@app.post('/sair')
async def logout(request: Request, db: Session = Depends(get_db)):
    await form_data(request)
    u = current_user(request, db)
    log(db, u, 'logout'); db.commit()
    request.session.clear()
    return go('/')

@app.get('/cadastrar', response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    return render(request, 'register.html', db)

@app.post('/cadastrar')
async def register(request: Request, db: Session = Depends(get_db)):
    f = await form_data(request)
    role = clean_text(f.get('role'), 20)
    name = clean_text(f.get('name'), 130)
    email = clean_text(f.get('email'), 254).lower()
    password = str(f.get('password') or '')
    company_name = clean_text(f.get('company_name'), 160)
    cnpj = clean_text(f.get('cnpj'), 20)
    course = clean_text(f.get('course'), 120)
    if role not in (*ACADEMIC_ROLES, 'company') or len(name) < 3 or not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return render(request, 'register.html', db, error='Preencha nome, e-mail válido e tipo de conta.')
    if not password_ok(password):
        return render(request, 'register.html', db, error='A senha precisa ter entre 10 e 128 caracteres.')
    if str(f.get('consent', '')) != 'yes':
        return render(request, 'register.html', db, error='Leia e aceite os termos de uso e privacidade.')
    if role == 'company' and (not company_name or not is_valid_cnpj(cnpj)):
        return render(request, 'register.html', db, error='Informe a razão social e um CNPJ válido.')
    if role in ACADEMIC_ROLES and not course:
        return render(request, 'register.html', db, error='Informe o curso/vínculo acadêmico para análise da coordenação.')
    if db.scalar(select(User).where(User.email == email)):
        return render(request, 'register.html', db, error='Este e-mail já está cadastrado.')
    user = User(name=name, email=email, password_hash=hash_password(password), role=role,
        course=course, company_name=company_name if role=='company' else '',
        cnpj=re.sub(r'\D', '', cnpj) if role=='company' else '',
        status='pending', email_verified=False, institutional_verified=False)
    db.add(user)
    db.flush()
    token = create_token(db, user.id, 'verify', hours=48)
    log(db, user, 'register', role)
    db.commit()
    try:
        dev_link = send_link(user.email, '/verificar', token, 'Confirme seu e-mail no Conecta Unis')
    except Exception as exc:
        print('Falha ao enviar email de verificação:', type(exc).__name__, flush=True)
        dev_link = None
    return render(request, 'notice.html', db, title='Cadastro enviado', message='Confirme seu e-mail e aguarde a aprovação da coordenação antes de utilizar a plataforma.', dev_link=dev_link)

@app.get('/verificar/{token}')
def verify_email(request: Request, token: str, db: Session = Depends(get_db)):
    uid = consume_token(db, token, 'verify')
    if not uid:
        return render(request, 'notice.html', db, title='Link inválido', message='O link expirou ou já foi utilizado. Contate a coordenação para reenviar a confirmação.')
    user = db.get(User, uid)
    user.email_verified = True
    log(db, user, 'email_verified')
    db.commit()
    return render(request, 'notice.html', db, title='E-mail confirmado!', message='Seu cadastro foi confirmado por e-mail e segue aguardando a validação da coordenação.')

@app.get('/recuperar')
def forgot_page(request: Request, db: Session = Depends(get_db)):
    return render(request, 'forgot.html', db)

@app.post('/recuperar')
async def forgot(request: Request, db: Session = Depends(get_db)):
    f = await form_data(request)
    email = clean_text(f.get('email'), 254).lower()
    user = db.scalar(select(User).where(User.email == email))
    link = None
    if user:
        token = create_token(db, user.id, 'reset', hours=1)
        db.commit()
        try:
            link = send_link(email, '/redefinir', token, 'Recuperação de senha do Conecta Unis')
        except Exception:
            pass
    return render(request, 'notice.html', db, title='Solicitação recebida', message='Se o e-mail estiver cadastrado, as instruções de redefinição foram enviadas.', dev_link=link)

@app.get('/redefinir/{token}')
def reset_page(request: Request, token: str, db: Session = Depends(get_db)):
    return render(request, 'reset.html', db, token=token)

@app.post('/redefinir/{token}')
async def reset_password(request: Request, token: str, db: Session = Depends(get_db)):
    f = await form_data(request)
    password = str(f.get('password') or '')
    if not password_ok(password):
        return render(request, 'reset.html', db, token=token, error='A senha deve ter entre 10 e 128 caracteres.')
    uid = consume_token(db, token, 'reset')
    if not uid:
        return render(request, 'notice.html', db, title='Link inválido', message='Este link expirou ou já foi utilizado.')
    u = db.get(User, uid)
    u.password_hash = hash_password(password)
    log(db, u, 'password_reset')
    db.commit()
    request.session.clear()
    return render(request, 'notice.html', db, title='Senha atualizada', message='Sua senha foi redefinida. Entre com as novas credenciais.')

@app.get('/painel')
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = guard(request, db)
    if user.role == 'company':
        return go('/empresa')
    if user.role == 'admin':
        return go('/admin')
    jobs = db.scalars(select(Job).options(joinedload(Job.company)).where(Job.status=='active', Job.deadline >= date.today()).order_by(Job.created_at.desc()).limit(5)).all()
    applications = db.scalars(select(Application).options(joinedload(Application.job)).where(Application.applicant_id==user.id).order_by(Application.created_at.desc()).limit(5)).all()
    return render(request, 'dashboard.html', db, jobs=[j for j in jobs if j.company.status=='active'], applications=applications, count=db.scalar(select(func.count(Application.id)).where(Application.applicant_id==user.id)) or 0)

@app.get('/perfil')
def profile(request: Request, db: Session = Depends(get_db)):
    user = guard(request, db)
    return render(request, 'profile.html', db)

@app.post('/perfil')
async def save_profile(request: Request, db: Session = Depends(get_db)):
    user = guard(request, db)
    f = await form_data(request)
    user.name = clean_text(f.get('name'), 130) or user.name
    user.city = clean_text(f.get('city'), 120)
    user.summary = clean_text(f.get('summary'), 2000)
    user.website = valid_url(clean_text(f.get('website'), 400))
    if user.role == 'company':
        user.company_name = clean_text(f.get('company_name'), 160) or user.company_name
        user.industry = clean_text(f.get('industry'), 120)
    else:
        user.course = clean_text(f.get('course'), 120)
        user.period = clean_text(f.get('period'), 30)
        user.skills = clean_text(f.get('skills'), 1000)
        user.experience = clean_text(f.get('experience'), 2000)
        user.education = clean_text(f.get('education'), 1500)
        user.languages = clean_text(f.get('languages'), 500)
        user.certificates = clean_text(f.get('certificates'), 1000)
        user.linkedin = valid_url(clean_text(f.get('linkedin'), 400))
        user.portfolio = valid_url(clean_text(f.get('portfolio'), 400))
        user.contact_public = str(f.get('contact_public', '')) == 'yes'
    for kind, field in ((('avatar','avatar_file'),) if user.role == 'company' else (('resume','resume_file'), ('avatar','avatar_file'))):
        upload = f.get(kind)
        try:
            new_name = await save_upload(upload, user.id, kind)
        except ValueError as err:
            db.rollback()
            return render(request, 'profile.html', db, error=str(err))
        if new_name:
            remove_upload(getattr(user, field))
            setattr(user, field, new_name)
    log(db, user, 'profile_updated')
    db.commit()
    flash(request, 'Perfil atualizado com sucesso!', 'success')
    return go('/perfil')

@app.get('/media/avatar/{user_id}')
def avatar(user_id: int, db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u or not u.avatar_file:
        raise HTTPException(404)
    path = UPLOAD_DIR / Path(u.avatar_file).name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type='image/png' if path.suffix=='.png' else 'image/jpeg', headers={'X-Content-Type-Options':'nosniff', 'Cache-Control':'private, max-age=3600'})

@app.get('/media/curriculo/{user_id}')
def resume(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = guard(request, db)
    owner = db.get(User, user_id)
    if not owner or not owner.resume_file:
        raise HTTPException(404)
    allowed = user.id == user_id or user.role == 'admin'
    if user.role == 'company' and not allowed:
        allowed = bool(db.scalar(select(Application.id).join(Job, Job.id == Application.job_id).where(Job.company_id==user.id, Application.applicant_id==user_id)))
    if not allowed:
        raise HTTPException(403)
    path = UPLOAD_DIR / Path(owner.resume_file).name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type='application/pdf', filename='curriculo.pdf', headers={'X-Content-Type-Options':'nosniff', 'Cache-Control':'private, no-store'})

def purge_user(db, person):
    """Remove os dados de conta, vagas, candidaturas, arquivos e mensagens."""
    if person.role == 'company':
        jobs = db.scalars(select(Job).where(Job.company_id == person.id)).all()
        for job in jobs:
            for application in db.scalars(select(Application).where(Application.job_id == job.id)).all():
                db.execute(delete(Message).where(Message.application_id == application.id))
                db.delete(application)
            db.delete(job)
    else:
        for application in db.scalars(select(Application).where(Application.applicant_id == person.id)).all():
            db.execute(delete(Message).where(Message.application_id == application.id))
            db.delete(application)
    db.execute(delete(EmailToken).where(EmailToken.user_id == person.id))
    db.execute(delete(Message).where(Message.sender_id == person.id))
    remove_upload(person.avatar_file)
    remove_upload(person.resume_file)
    db.delete(person)

@app.post('/conta/excluir')
async def delete_account(request: Request, db: Session = Depends(get_db)):
    user = guard(request, db)
    f = await form_data(request)
    if str(f.get('confirm')) != 'EXCLUIR' or not verify_password(user.password_hash, str(f.get('password') or '')):
        flash(request, 'Confirmação inválida. Digite EXCLUIR e informe sua senha.', 'error')
        return go('/perfil')
    if user.role == 'admin':
        flash(request, 'A conta administrativa deve ser desativada por outro administrador.', 'error')
        return go('/perfil')
    log(db, user, 'account_deleted', f'id={user.id}')
    purge_user(db, user)
    db.commit()
    request.session.clear()
    return go('/')

@app.get('/vagas')
def jobs_page(request: Request, q: str='', tipo: str='', cidade: str='', modalidade: str='', area: str='', db: Session = Depends(get_db)):
    query = select(Job).options(joinedload(Job.company)).join(User, Job.company_id==User.id).where(Job.status=='active', Job.deadline>=date.today(), User.status=='active')
    if q: query=query.where(or_(Job.title.ilike(f'%{q[:80]}%'), Job.description.ilike(f'%{q[:80]}%'), Job.area.ilike(f'%{q[:80]}%')))
    if tipo: query=query.where(Job.job_type==tipo)
    if modalidade: query=query.where(Job.work_mode==modalidade)
    if cidade: query=query.where(Job.city.ilike(f'%{cidade[:80]}%'))
    if area: query=query.where(Job.area.ilike(f'%{area[:80]}%'))
    jobs = db.scalars(query.order_by(Job.created_at.desc()).limit(100)).all()
    return render(request, 'jobs.html', db, jobs=jobs, filters={'q':q,'tipo':tipo,'cidade':cidade,'modalidade':modalidade,'area':area})

@app.get('/vagas/{job_id}')
def job_detail(request: Request, job_id: int, db: Session = Depends(get_db)):
    job = db.scalar(select(Job).options(joinedload(Job.company)).where(Job.id==job_id))
    if not job: raise HTTPException(404)
    u = current_user(request, db)
    if not can_view_job(job) and not (u and (u.role=='admin' or u.id==job.company_id)):
        raise HTTPException(404)
    applied = bool(u and db.scalar(select(Application.id).where(Application.job_id==job.id, Application.applicant_id==u.id)))
    return render(request, 'job_detail.html', db, job=job, applied=applied, available=can_view_job(job))

@app.post('/vagas/{job_id}/candidatar')
async def apply_job(request: Request, job_id: int, db: Session = Depends(get_db)):
    user = guard(request, db, CANDIDATE_ROLES)
    f = await form_data(request)
    job = db.scalar(select(Job).options(joinedload(Job.company)).where(Job.id==job_id))
    if not job or not can_view_job(job):
        flash(request, 'Esta vaga não está disponível para candidatura.', 'error')
        return go('/vagas')
    if db.scalar(select(Application.id).where(Application.job_id==job_id, Application.applicant_id==user.id)):
        flash(request, 'Você já se candidatou a esta vaga.', 'error')
        return go(f'/vagas/{job_id}')
    item = Application(job_id=job_id, applicant_id=user.id, message=clean_text(f.get('message'), 1200))
    db.add(item)
    try:
        log(db, user, 'application_created', f'job={job_id}')
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, 'Esta candidatura já existe.', 'error')
        return go(f'/vagas/{job_id}')
    flash(request, 'Candidatura enviada com sucesso!', 'success')
    return go('/candidaturas')

@app.get('/candidaturas')
def applications_page(request: Request, db: Session = Depends(get_db)):
    user = guard(request, db, CANDIDATE_ROLES)
    items = db.scalars(select(Application).options(joinedload(Application.job).joinedload(Job.company)).where(Application.applicant_id==user.id).order_by(Application.created_at.desc())).all()
    return render(request, 'applications.html', db, items=items)

@app.get('/empresa')
def company_dashboard(request: Request, db: Session = Depends(get_db)):
    user = guard(request, db, ('company',))
    jobs = db.scalars(select(Job).where(Job.company_id==user.id).order_by(Job.created_at.desc())).all()
    apps = db.scalars(select(Application).join(Job).options(joinedload(Application.job), joinedload(Application.applicant)).where(Job.company_id==user.id).order_by(Application.created_at.desc()).limit(8)).all()
    return render(request, 'company.html', db, jobs=jobs, applications=apps)

@app.get('/empresa/vagas/nova')
def new_job_page(request: Request, db: Session = Depends(get_db)):
    guard(request, db, ('company',))
    return render(request, 'job_form.html', db, job=None)

@app.post('/empresa/vagas/nova')
async def new_job(request: Request, db: Session = Depends(get_db)):
    user = guard(request, db, ('company',))
    f = await form_data(request)
    data, error = parse_job(f)
    if error:
        return render(request, 'job_form.html', db, job=None, error=error)
    item = Job(company_id=user.id, status='active', **data)
    db.add(item)
    db.flush()
    log(db, user, 'job_created', f'job={item.id}')
    db.commit()
    flash(request, 'Vaga publicada com sucesso!', 'success')
    return go('/empresa')

def parse_job(f):
    title=clean_text(f.get('title'),160)
    description=clean_text(f.get('description'),4000)
    job_type=clean_text(f.get('job_type'),35)
    mode=clean_text(f.get('work_mode'),20)
    city=clean_text(f.get('city'),120)
    try: deadline=date.fromisoformat(str(f.get('deadline')))
    except ValueError: deadline=None
    if len(title)<5 or len(description)<20 or job_type not in JOB_TYPES or mode not in WORK_MODES or not city or not deadline or deadline<date.today():
        return None, 'Preencha título, descrição (20 caracteres), tipo, modalidade, cidade e prazo futuro válidos.'
    content=(title + ' ' + description).lower()
    if any(term in content for term in ('taxa de candidatura','pague para se candidatar','taxa de inscrição obrigatória')):
        return None, 'Vagas que cobram taxas dos candidatos não são permitidas.'
    return dict(title=title,description=description,job_type=job_type,area=clean_text(f.get('area'),90),
        requirements=clean_text(f.get('requirements'),2200),benefits=clean_text(f.get('benefits'),1600),
        compensation=clean_text(f.get('compensation'),100),city=city,work_mode=mode,deadline=deadline), None

@app.get('/empresa/vagas/{job_id}/editar')
def edit_job_page(request: Request, job_id: int, db: Session = Depends(get_db)):
    user=guard(request, db, ('company',))
    job=db.get(Job, job_id)
    if not job or job.company_id!=user.id: raise HTTPException(404)
    return render(request, 'job_form.html', db, job=job)

@app.post('/empresa/vagas/{job_id}/editar')
async def edit_job(request: Request, job_id: int, db: Session = Depends(get_db)):
    user=guard(request, db, ('company',))
    job=db.get(Job, job_id)
    if not job or job.company_id!=user.id: raise HTTPException(404)
    f=await form_data(request)
    data,error=parse_job(f)
    if error: return render(request, 'job_form.html', db, job=job, error=error)
    for k,v in data.items(): setattr(job,k,v)
    log(db,user,'job_updated',f'job={job_id}'); db.commit()
    flash(request, 'Vaga atualizada.', 'success'); return go('/empresa')

@app.post('/empresa/vagas/{job_id}/status')
async def change_job_status(request: Request, job_id: int, db: Session = Depends(get_db)):
    user=guard(request, db, ('company',))
    f=await form_data(request)
    job=db.get(Job,job_id)
    if not job or job.company_id!=user.id: raise HTTPException(404)
    status=clean_text(f.get('status'),20)
    if status not in JOB_STATUSES: raise HTTPException(400)
    if status=='active' and job.deadline<date.today():
        flash(request,'Atualize o prazo da vaga antes de reabri-la.','error')
    elif job.status=='rejected':
        flash(request,'Uma vaga removida pela coordenação não pode ser reaberta.','error')
    else:
        job.status=status
        log(db,user,'job_status_changed',f'job={job_id};status={status}');db.commit()
        flash(request,'Status da vaga atualizado.','success')
    return go('/empresa')

@app.get('/empresa/vagas/{job_id}/candidatos')
def candidates_page(request: Request, job_id: int, db: Session = Depends(get_db)):
    user=guard(request,db,('company',))
    job=db.get(Job,job_id)
    if not job or job.company_id!=user.id: raise HTTPException(404)
    items=db.scalars(select(Application).options(joinedload(Application.applicant)).where(Application.job_id==job_id).order_by(Application.created_at.desc())).all()
    return render(request,'candidates.html',db,job=job,items=items)

@app.post('/empresa/candidaturas/{app_id}/status')
async def change_application_status(request:Request, app_id:int, db:Session=Depends(get_db)):
    user=guard(request,db,('company',))
    f=await form_data(request)
    item=db.scalar(select(Application).options(joinedload(Application.job)).where(Application.id==app_id))
    if not item or item.job.company_id!=user.id: raise HTTPException(404)
    status=clean_text(f.get('status'),30)
    if status not in APP_STATUSES: raise HTTPException(400)
    item.status=status
    log(db,user,'application_status_changed',f'application={item.id};status={status}')
    db.commit()
    flash(request,'Status da candidatura atualizado.','success')
    return go(f'/empresa/vagas/{item.job_id}/candidatos')

@app.get('/empresa/talentos')
def search_talent(request: Request, curso: str='', habilidade: str='', cidade: str='', db:Session=Depends(get_db)):
    user=guard(request,db,('company',))
    query=select(User).where(User.role.in_(CANDIDATE_ROLES), User.status=='active',User.email_verified==True)
    if curso: query=query.where(User.course.ilike(f'%{curso[:80]}%'))
    if habilidade: query=query.where(User.skills.ilike(f'%{habilidade[:80]}%'))
    if cidade: query=query.where(User.city.ilike(f'%{cidade[:80]}%'))
    talents=db.scalars(query.limit(50)).all()
    # Dados de contato e currículos não são expostos antes de candidatura.
    return render(request,'talents.html',db,talents=talents,filters={'curso':curso,'habilidade':habilidade,'cidade':cidade})

@app.get('/mensagens')
def conversations(request:Request,db:Session=Depends(get_db)):
    user=guard(request,db,('student','alumni','company'))
    query=select(Application).options(joinedload(Application.job).joinedload(Job.company), joinedload(Application.applicant))
    if user.role=='company': query=query.join(Job).where(Job.company_id==user.id)
    else: query=query.where(Application.applicant_id==user.id)
    apps=db.scalars(query.order_by(Application.created_at.desc())).all()
    return render(request,'conversations.html',db,items=apps)

@app.get('/mensagens/{app_id}')
def conversation(request:Request,app_id:int,db:Session=Depends(get_db)):
    user=guard(request,db,('student','alumni','company'))
    item=db.scalar(select(Application).options(joinedload(Application.job).joinedload(Job.company),joinedload(Application.applicant)).where(Application.id==app_id))
    if not item or user.id not in (item.applicant_id,item.job.company_id): raise HTTPException(404)
    items=db.scalars(select(Message).options(joinedload(Message.sender)).where(Message.application_id==app_id).order_by(Message.created_at)).all()
    return render(request,'conversation.html',db,item=item,items=items)

@app.post('/mensagens/{app_id}')
async def post_message(request:Request,app_id:int,db:Session=Depends(get_db)):
    user=guard(request,db,('student','alumni','company'))
    f=await form_data(request)
    item=db.scalar(select(Application).options(joinedload(Application.job)).where(Application.id==app_id))
    if not item or user.id not in (item.applicant_id,item.job.company_id): raise HTTPException(404)
    content=clean_text(f.get('content'),1500)
    if not content: flash(request,'Escreva uma mensagem.','error');return go(f'/mensagens/{app_id}')
    db.add(Message(application_id=app_id,sender_id=user.id,content=content))
    log(db,user,'message_sent',f'application={app_id}');db.commit()
    return go(f'/mensagens/{app_id}')

@app.get('/admin')
def admin_dashboard(request:Request,db:Session=Depends(get_db)):
    guard(request,db,('admin',))
    stats={
        'pending': db.scalar(select(func.count(User.id)).where(User.status=='pending')) or 0,
        'users':db.scalar(select(func.count(User.id)).where(User.status=='active')) or 0,
        'jobs':db.scalar(select(func.count(Job.id)).where(Job.status=='active')) or 0,
        'applications':db.scalar(select(func.count(Application.id))) or 0,
        'hires':db.scalar(select(func.count(Application.id)).where(Application.status=='aprovada')) or 0,
    }
    pending=db.scalars(select(User).where(User.status=='pending').order_by(User.created_at).limit(15)).all()
    latest_jobs=db.scalars(select(Job).options(joinedload(Job.company)).order_by(Job.created_at.desc()).limit(8)).all()
    return render(request,'admin.html',db,stats=stats,pending=pending,jobs=latest_jobs)

@app.get('/admin/usuarios')
def admin_users(request:Request,db:Session=Depends(get_db)):
    guard(request,db,('admin',))
    users=db.scalars(select(User).order_by(User.created_at.desc()).limit(250)).all()
    return render(request,'admin_users.html',db,users=users)

@app.post('/admin/usuarios/{user_id}/acao')
async def admin_user_action(request:Request,user_id:int,db:Session=Depends(get_db)):
    admin=guard(request,db,('admin',))
    f=await form_data(request)
    user=db.get(User,user_id)
    action=clean_text(f.get('action'),30)
    if not user or user.id==admin.id or action not in ('approve','suspend','activate'):
        raise HTTPException(400)
    if action=='approve':
        if not user.email_verified:
            flash(request,'O usuário ainda não confirmou seu e-mail.','error');return go('/admin/usuarios')
        # Aprovação exige conferência documental/institucional efetuada pelo responsável.
        user.status='active'; user.institutional_verified=True
    elif action=='suspend': user.status='suspended'
    else:
        if not user.email_verified: raise HTTPException(400)
        user.status='active'
    log(db,admin,'user_'+action,f'user={user_id};role={user.role}');db.commit()
    flash(request,'Cadastro atualizado.','success')
    return go('/admin/usuarios')

@app.post('/admin/usuarios/{user_id}/excluir')
async def admin_delete_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    admin = guard(request, db, ('admin',))
    f = await form_data(request)
    person = db.get(User, user_id)
    if not person or person.role == 'admin' or f.get('confirm') != 'EXCLUIR':
        raise HTTPException(400)
    log(db, admin, 'user_deleted_by_admin', f'user={person.id};role={person.role}')
    purge_user(db, person)
    db.commit()
    flash(request, 'Usuário e seus dados relacionados foram excluídos.', 'success')
    return go('/admin/usuarios')

@app.get('/admin/vagas')
def admin_jobs(request:Request,db:Session=Depends(get_db)):
    guard(request,db,('admin',))
    jobs=db.scalars(select(Job).options(joinedload(Job.company)).order_by(Job.created_at.desc()).limit(200)).all()
    return render(request,'admin_jobs.html',db,jobs=jobs)

@app.post('/admin/vagas/{job_id}/acao')
async def admin_job_action(request:Request,job_id:int,db:Session=Depends(get_db)):
    admin=guard(request,db,('admin',))
    f=await form_data(request)
    action=clean_text(f.get('action'),30)
    job=db.get(Job,job_id)
    if not job or action not in ('rejected','active'):
        raise HTTPException(400)
    if action=='active' and job.deadline<date.today():
        flash(request,'O prazo desta vaga está vencido.','error');return go('/admin/vagas')
    job.status=action
    log(db,admin,'job_moderated',f'job={job.id};status={action}');db.commit()
    flash(request,'Vaga moderada.','success');return go('/admin/vagas')

@app.get('/admin/relatorios')
def admin_reports(request:Request,db:Session=Depends(get_db)):
    guard(request,db,('admin',))
    courses=db.execute(select(User.course,func.count(Application.id)).join(Application,Application.applicant_id==User.id).where(Application.status=='aprovada').group_by(User.course)).all()
    companies=db.scalar(select(func.count(User.id)).where(User.role=='company',User.status=='active')) or 0
    types=db.execute(select(Job.job_type,func.count(Job.id)).group_by(Job.job_type)).all()
    return render(request,'reports.html',db,courses=courses,companies=companies,types=types,
        jobs_count=db.scalar(select(func.count(Job.id))) or 0, app_count=db.scalar(select(func.count(Application.id))) or 0,
        hired=db.scalar(select(func.count(Application.id)).where(Application.status=='aprovada')) or 0)

@app.get('/privacidade')
def privacy(request:Request,db:Session=Depends(get_db)):
    return render(request,'privacy.html',db)

@app.exception_handler(404)
async def not_found(request, exc):
    return HTMLResponse('<h1>Página não encontrada</h1><p><a href="/">Voltar ao início</a></p>', status_code=404)
