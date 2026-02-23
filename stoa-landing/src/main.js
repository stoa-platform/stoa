/* ============================================================
   STOA Landing V4 — Animation Engine
   ============================================================ */
import './style.css';

// ---------- Scroll-Triggered Reveals ----------
function initRevealObserver() {
  const reveals = document.querySelectorAll('[data-reveal]');
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const el = entry.target;
        const delay = parseInt(el.dataset.revealDelay || '0', 10);
        setTimeout(() => el.classList.add('visible'), delay);
        observer.unobserve(el);
      });
    },
    { threshold: 0.15, rootMargin: '0px 0px -40px 0px' }
  );
  reveals.forEach((el) => observer.observe(el));
}

// ---------- Stagger Children (Mock UI) ----------
function initStaggerObserver() {
  const mockUI = document.querySelector('.mock-ui');
  if (!mockUI) return;

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const children = entry.target.querySelectorAll('.stagger-child');
        children.forEach((child) => {
          const idx = parseInt(child.dataset.stagger || '0', 10);
          setTimeout(() => child.classList.add('visible'), 200 + idx * 150);
        });
        observer.unobserve(entry.target);
      });
    },
    { threshold: 0.1 }
  );
  observer.observe(mockUI);
}

// ---------- Parallax Orbs ----------
function initParallax() {
  const orbs = document.querySelectorAll('[data-parallax]');
  if (!orbs.length) return;

  let ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      const scrollY = window.scrollY;
      orbs.forEach((orb) => {
        const speed = parseFloat(orb.dataset.parallax);
        orb.style.transform = `translateY(${scrollY * speed}px)`;
      });
      ticking = false;
    });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
}

// ---------- Nav Scroll Background ----------
function initNavScroll() {
  const nav = document.getElementById('nav');
  if (!nav) return;

  function check() {
    nav.classList.toggle('scrolled', window.scrollY > 50);
  }
  window.addEventListener('scroll', check, { passive: true });
  check();
}

// ---------- Counter Animation ----------
function initCounters() {
  const counters = document.querySelectorAll('[data-counter]');
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const el = entry.target;
        const target = parseInt(el.dataset.counter, 10);
        animateCounter(el, target);
        observer.unobserve(el);
      });
    },
    { threshold: 0.5 }
  );
  counters.forEach((el) => observer.observe(el));
}

function animateCounter(el, target) {
  const duration = 1800;
  const start = performance.now();

  function easeOutExpo(t) {
    return t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
  }

  function tick(now) {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    const current = Math.round(easeOutExpo(progress) * target);
    el.textContent = current.toLocaleString();
    if (progress < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// ---------- Typewriter Effect ----------
function initTypewriter() {
  const elements = document.querySelectorAll('[data-typewriter]');
  elements.forEach((el) => {
    const text = el.dataset.typewriter;
    let i = 0;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          observer.unobserve(entry.target);
          // Delay slightly for the reveal animation to start
          setTimeout(() => typeChar(), 600);
        });
      },
      { threshold: 0.5 }
    );

    function typeChar() {
      if (i <= text.length) {
        el.textContent = text.slice(0, i);
        i++;
        const speed = text[i - 1] === ' ' ? 20 : 30 + Math.random() * 30;
        setTimeout(typeChar, speed);
      }
    }

    observer.observe(el);
  });
}

// ---------- 3D Tilt Cards ----------
function initTilt() {
  const cards = document.querySelectorAll('[data-tilt]');
  cards.forEach((card) => {
    card.addEventListener('mousemove', (e) => {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      const rotateX = ((y - centerY) / centerY) * -5;
      const rotateY = ((x - centerX) / centerX) * 5;
      card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale(1.02)`;
    });

    card.addEventListener('mouseleave', () => {
      card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) scale(1)';
      card.style.transition = 'transform 0.5s var(--ease-apple)';
      setTimeout(() => (card.style.transition = ''), 500);
    });

    card.addEventListener('mouseenter', () => {
      card.style.transition = 'none';
    });
  });
}

// ---------- Smooth Anchor Scroll ----------
function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener('click', (e) => {
      const target = document.querySelector(anchor.getAttribute('href'));
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
}

// ---------- Init ----------
document.addEventListener('DOMContentLoaded', () => {
  initNavScroll();
  initRevealObserver();
  initStaggerObserver();
  initParallax();
  initCounters();
  initTypewriter();
  initTilt();
  initSmoothScroll();
});
