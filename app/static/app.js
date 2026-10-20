(() => {
  const menuToggle = document.getElementById('menu-toggle');
  const nav = document.getElementById('main-nav');
  if (menuToggle && nav) {
    menuToggle.addEventListener('click', () => {
      const opened = nav.classList.toggle('nav-open');
      menuToggle.setAttribute('aria-expanded', String(opened));
      menuToggle.setAttribute('aria-label', opened ? 'Fechar menu' : 'Abrir menu');
    });
  }
  const role = document.getElementById('role');
  if (role) {
    const update = () => {
      const company = role.value === 'company';
      const cf = document.getElementById('company-fields');
      const af = document.getElementById('academic-fields');
      cf.classList.toggle('is-hidden', !company);
      af.classList.toggle('is-hidden', company);
      for (const element of cf.querySelectorAll('input')) element.required = company;
      for (const element of af.querySelectorAll('input')) element.required = !company;
    };
    role.addEventListener('change', update);
    update();
  }
  for (const button of document.querySelectorAll('[data-confirm]')) {
    button.addEventListener('click', (event) => {
      if (!confirm(button.dataset.confirm)) event.preventDefault();
    });
  }
})();
