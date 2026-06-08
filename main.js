/* Stanowisko EGEA — main.js (interakcje dokumentacji) */

(function () {
  'use strict';

  /* ---- Scroll-reveal: pojawianie się elementów przy przewijaniu ---- */
  const revealEls = document.querySelectorAll(
    '.mode-card, .kpi-card, .eq-card, .param-row:not(.header-row), ' +
    '.std-row:not(.std-header), .phase-row:not(.phase-header), ' +
    '.step, .install-step, .biblio-item, .file-row'
  );

  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          e.target.style.opacity = '1';
          e.target.style.transform = 'translateY(0)';
          io.unobserve(e.target);
        }
      });
    },
    { threshold: 0.1, rootMargin: '0px 0px -40px 0px' }
  );

  revealEls.forEach((el, i) => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(16px)';
    el.style.transition = `opacity 0.4s ${i * 0.02}s ease, transform 0.4s ${i * 0.02}s ease`;
    io.observe(el);
  });

  /* ---- Podświetlanie aktywnego linku w nawigacji ---- */
  const sections = document.querySelectorAll('section[id]');
  const navLinks = document.querySelectorAll('.nav-links a');

  const navObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          navLinks.forEach((a) => {
            a.style.color = a.getAttribute('href') === '#' + e.target.id
              ? 'var(--c-text)'
              : '';
          });
        }
      });
    },
    { threshold: 0.4 }
  );

  sections.forEach((s) => navObserver.observe(s));

  /* ---- Kopiowanie poleceń z bloków kodu po kliknięciu ---- */
  document.querySelectorAll('.code-block').forEach((block) => {
    block.style.cursor = 'pointer';
    block.title = 'Kliknij, aby skopiować';

    block.addEventListener('click', () => {
      const text = block.textContent.replace(/^\s*[$→]\s*/, '').trim();
      navigator.clipboard.writeText(text).then(() => {
        const orig = block.innerHTML;
        block.innerHTML = '<span style="color:var(--c-ok);font-family:var(--f-mono)">✓ Skopiowano</span>';
        setTimeout(() => { block.innerHTML = orig; }, 1400);
      });
    });
  });

  /* ---- Smooth scroll z offsetem dla kotwic ---- */
  document.querySelectorAll('a[href^="#"]').forEach((link) => {
    link.addEventListener('click', (e) => {
      const id = link.getAttribute('href').slice(1);
      const target = document.getElementById(id);
      if (target) {
        e.preventDefault();
        const offset = 40;
        const top = target.getBoundingClientRect().top + window.pageYOffset - offset;
        window.scrollTo({ top, behavior: 'smooth' });
      }
    });
  });
})();
