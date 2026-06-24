/* index.js — Post-Pilot landing page interactive behaviour */

// ---------------------------------------------------------------------------
// Navbar: add background on scroll
// ---------------------------------------------------------------------------
(function () {
  const navbar = document.getElementById('navbar');
  if (!navbar) return;
  const onScroll = () => {
    if (window.scrollY > 20) {
      navbar.style.background = 'rgba(7,7,26,0.92)';
      navbar.style.backdropFilter = 'blur(16px)';
      navbar.style.borderBottom = '1px solid rgba(255,255,255,0.06)';
    } else {
      navbar.style.background = '';
      navbar.style.backdropFilter = '';
      navbar.style.borderBottom = '';
    }
  };
  window.addEventListener('scroll', onScroll, { passive: true });
})();

// ---------------------------------------------------------------------------
// Mobile nav drawer
// ---------------------------------------------------------------------------
function toggleMobileNav() {
  const menu     = document.getElementById('mobile-menu');
  const backdrop = document.getElementById('mobile-backdrop');
  if (!menu) return;
  const isOpen = menu.classList.toggle('open');
  if (backdrop) {
    backdrop.classList.toggle('hidden', !isOpen);
  }
  document.body.style.overflow = isOpen ? 'hidden' : '';
}

// Close drawer on Escape key
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') {
    const menu = document.getElementById('mobile-menu');
    if (menu && menu.classList.contains('open')) toggleMobileNav();
  }
});

// ---------------------------------------------------------------------------
// FAQ accordion
// ---------------------------------------------------------------------------
function toggleFaq(el) {
  const isOpen = el.classList.contains('faq-open');
  // Close all open items first
  document.querySelectorAll('.faq-item.faq-open').forEach(function (item) {
    item.classList.remove('faq-open');
  });
  // Open clicked item unless it was already open
  if (!isOpen) el.classList.add('faq-open');
}
