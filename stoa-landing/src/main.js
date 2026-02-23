import './style.css';

/* ========== Scroll-Triggered Reveals ========== */
function initReveals() {
  const els = document.querySelectorAll('[data-reveal]');
  const obs = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const el = entry.target;
        const delay = parseInt(el.dataset.revealDelay || '0', 10);
        setTimeout(() => el.classList.add('visible'), delay);
        obs.unobserve(el);
      });
    },
    { threshold: 0.15, rootMargin: '0px 0px -40px 0px' }
  );
  els.forEach((el) => obs.observe(el));
}

/* ========== Staggered Children (Mock UI) ========== */
function initStagger() {
  const mockUI = document.querySelector('.mock-ui');
  if (!mockUI) return;
  const obs = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.querySelectorAll('.stagger-child').forEach((child) => {
          const idx = parseInt(child.dataset.stagger || '0', 10);
          setTimeout(() => child.classList.add('visible'), 200 + idx * 150);
        });
        obs.unobserve(entry.target);
      });
    },
    { threshold: 0.1 }
  );
  obs.observe(mockUI);
}

/* ========== Parallax ========== */
function initParallax() {
  const els = document.querySelectorAll('[data-parallax]');
  if (!els.length) return;
  let ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      const scrollY = window.scrollY;
      els.forEach((el) => {
        const factor = parseFloat(el.dataset.parallax);
        el.style.transform = `translateY(${scrollY * factor}px)`;
      });
      ticking = false;
    });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
}

/* ========== Nav Scroll ========== */
function initNav() {
  const nav = document.getElementById('nav');
  if (!nav) return;
  function update() {
    nav.classList.toggle('scrolled', window.scrollY > 50);
  }
  window.addEventListener('scroll', update, { passive: true });
  update();
}

/* ========== Counter Animation ========== */
function initCounters() {
  const els = document.querySelectorAll('[data-counter]');
  els.forEach((el) => {
    const revealParent = el.closest('.reveal');
    if (revealParent) {
      // Wait for parent reveal to become visible before animating
      const mo = new MutationObserver(() => {
        if (revealParent.classList.contains('visible')) {
          mo.disconnect();
          const target = parseInt(el.dataset.counter, 10);
          setTimeout(() => animateCounter(el, target), 300);
        }
      });
      mo.observe(revealParent, { attributes: true, attributeFilter: ['class'] });
    } else {
      // No reveal parent — use IntersectionObserver
      const obs = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            const target = parseInt(el.dataset.counter, 10);
            animateCounter(el, target);
            obs.unobserve(el);
          });
        },
        { threshold: 0.5 }
      );
      obs.observe(el);
    }
  });
}

function animateCounter(el, target) {
  const start = performance.now();
  function easeOutExpo(x) {
    return x === 1 ? 1 : 1 - Math.pow(2, -10 * x);
  }
  function step(now) {
    const elapsed = now - start;
    const progress = Math.min(elapsed / 1800, 1);
    const value = Math.round(easeOutExpo(progress) * target);
    el.textContent = value.toLocaleString();
    if (progress < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

/* ========== Typewriter Effect ========== */
function initTypewriter() {
  document.querySelectorAll('[data-typewriter]').forEach((el) => {
    const text = el.dataset.typewriter;
    let i = 0;
    function type() {
      if (i <= text.length) {
        el.textContent = text.slice(0, i);
        i++;
        const delay = text[i - 1] === ' ' ? 20 : 30 + Math.random() * 30;
        setTimeout(type, delay);
      }
    }
    const revealParent = el.closest('.reveal');
    if (revealParent) {
      const mo = new MutationObserver(() => {
        if (revealParent.classList.contains('visible')) {
          mo.disconnect();
          setTimeout(() => type(), 400);
        }
      });
      mo.observe(revealParent, { attributes: true, attributeFilter: ['class'] });
    } else {
      const obs = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              obs.unobserve(entry.target);
              setTimeout(() => type(), 600);
            }
          });
        },
        { threshold: 0.5 }
      );
      obs.observe(el);
    }
  });
}

/* ========== 3D Tilt Cards ========== */
function initTilt() {
  document.querySelectorAll('[data-tilt]').forEach((el) => {
    el.addEventListener('mousemove', (e) => {
      const rect = el.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const rotateX = ((y - cy) / cy) * -5;
      const rotateY = ((x - cx) / cx) * 5;
      el.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale(1.02)`;
    });
    el.addEventListener('mouseleave', () => {
      el.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) scale(1)';
      el.style.transition = 'transform 0.5s var(--ease-apple)';
      setTimeout(() => (el.style.transition = ''), 500);
    });
    el.addEventListener('mouseenter', () => {
      el.style.transition = 'none';
    });
  });
}

/* ========== Smooth Scroll ========== */
function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach((a) => {
    a.addEventListener('click', (e) => {
      const target = document.querySelector(a.getAttribute('href'));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });
}

/* ========== Init ========== */
document.addEventListener('DOMContentLoaded', () => {
  initNav();
  initReveals();
  initStagger();
  initParallax();
  initCounters();
  initTypewriter();
  initTilt();
  initSmoothScroll();
});
