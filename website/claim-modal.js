/* claim-modal.js — wire up [data-claim="..."] elements to open the
 * claim detail modal populated from window.LOOM_CLAIMS.
 *
 * No framework; vanilla DOM. Targets browsers from ~2020.
 */
(() => {
  const claims = window.LOOM_CLAIMS || {};
  const modal = document.getElementById('claim-modal');
  if (!modal) return;

  const $phase    = modal.querySelector('#claim-modal-phase');
  const $title    = modal.querySelector('#claim-modal-title');
  const $status   = modal.querySelector('#claim-modal-status');
  const $headline = modal.querySelector('#claim-modal-headline');
  const $what     = modal.querySelector('#claim-modal-what');
  const $numbers  = modal.querySelector('#claim-modal-numbers');
  const $calc     = modal.querySelector('#claim-modal-calculations');
  const $constr   = modal.querySelector('#claim-modal-constraints');
  const $limits   = modal.querySelector('#claim-modal-limitations');
  const $repo     = modal.querySelector('#claim-modal-repo');

  function setBullets(ul, items) {
    ul.innerHTML = '';
    if (!items || !items.length) {
      const li = document.createElement('li');
      li.className = 'muted';
      li.textContent = '(none recorded)';
      ul.appendChild(li);
      return;
    }
    for (const text of items) {
      const li = document.createElement('li');
      li.textContent = text;
      ul.appendChild(li);
    }
  }

  function open(id) {
    const c = claims[id];
    if (!c) {
      console.warn('claim id not found:', id);
      return;
    }
    $phase.textContent    = c.phase || '—';
    $title.textContent    = id;
    $status.textContent   = c.status || '';
    $headline.textContent = c.headline || '';
    setBullets($what,   c.what);
    setBullets($numbers,c.numbers);
    setBullets($calc,   c.calculations);
    setBullets($constr, c.constraints);
    setBullets($limits, c.limitations);
    $repo.href = c.repo || '#';
    modal.hidden = false;
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    // focus the close button so Esc/Enter work immediately
    const close = modal.querySelector('.claim-modal-close');
    if (close) close.focus();
  }

  function close() {
    modal.hidden = true;
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }

  // Click handler for any element with [data-claim].
  document.addEventListener('click', (e) => {
    const target = e.target.closest('[data-claim]');
    if (target) {
      e.preventDefault();
      open(target.dataset.claim);
      return;
    }
    // Click backdrop or close button.
    if (e.target.matches('[data-modal-close]') ||
        e.target.closest('[data-modal-close]')) {
      e.preventDefault();
      close();
    }
  });

  // Close on Esc.
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.hidden) close();
  });
})();
