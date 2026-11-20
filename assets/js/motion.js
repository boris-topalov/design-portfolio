/* motion.js — ванильный движок движения портфолио.
   Без зависимостей и модулей: работает по file://, включается по наличию
   разметки, целиком отключается при prefers-reduced-motion: reduce.

   CSS-контракт: --mg-x/--mg-y (px), --tilt-x/--tilt-y (deg), --mx/--my (%),
   --hold-progress (0…1), классы .is-open / .is-visible / .is-done.
   В анимациях только transform и opacity; геометрия читается до записи. */
(function () {
  'use strict';

  var doc = document;
  var root = doc.documentElement;
  var mqReduce = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  var mqFine = window.matchMedia ? window.matchMedia('(pointer: fine)') : null;

  function reduced() { return !!(mqReduce && mqReduce.matches); }
  function fine() { return mqFine ? mqFine.matches : true; }
  function raf(fn) { return window.requestAnimationFrame ? window.requestAnimationFrame(fn) : setTimeout(fn, 16); }
  function stop(id) { if (window.cancelAnimationFrame) { window.cancelAnimationFrame(id); } else { clearTimeout(id); } }
  function all(sel, scope) { return [].slice.call((scope || doc).querySelectorAll(sel)); }
  function clamp(v, min, max) { return v < min ? min : v > max ? max : v; }

  /* 1. Морф-заголовок: фразы лежат в одной ячейке grid, видимую меняет
     пружина. Высота слота фиксируется min-height по замеру. */
  var K = 190;
  var C = 24;

  function initWordRoll(host) {
    var words = all('.word-roll__word', host);
    if (words.length < 2) { return; }

    var index = 0, frame = 0, timer = 0, inView = true;

    function paint(w, y, o) {
      w.style.transform = 'translate3d(0,' + y + '%,0)';
      w.style.opacity = String(o);
    }

    function settle(to) {
      stop(frame);
      for (var i = 0; i < words.length; i++) {
        paint(words[i], i === to ? 0 : -105, i === to ? 1 : 0);
        words[i].setAttribute('aria-hidden', i === to ? 'false' : 'true');
      }
      index = to;
    }

    function measure() {
      var h = 0;
      for (var i = 0; i < words.length; i++) { h = Math.max(h, words[i].offsetHeight); }
      if (h) { host.style.minHeight = h + 'px'; }
    }

    function swap(to) {
      var out = words[index], inc = words[to], p = 0, v = 0, last = 0;
      stop(frame);
      out.setAttribute('aria-hidden', 'true');
      inc.setAttribute('aria-hidden', 'false');
      paint(inc, 105, 0);

      function step(now) {
        if (!last) { last = now; }
        var dt = Math.min((now - last) / 1000, 0.032);
        last = now;
        v += (-K * (p - 1) - C * v) * dt;
        p += v * dt;
        var e = clamp(p, 0, 1.15);
        paint(out, -e * 105, clamp(1 - p * 1.7, 0, 1));
        paint(inc, (1 - e) * 105, clamp(p * 1.9, 0, 1));
        if (Math.abs(1 - p) < 0.002 && Math.abs(v) < 0.02) {
          paint(out, -105, 0);
          paint(inc, 0, 1);
          index = to;
          return;
        }
        frame = raf(step);
      }
      frame = raf(step);
    }

    function schedule() {
      clearTimeout(timer);
      if (reduced() || !inView) { return; }
      timer = setTimeout(function () {
        swap((index + 1) % words.length);
        schedule();
      }, 2600);
    }

    settle(0);
    measure();
    if (reduced()) { return; }
    schedule();

    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (entries) {
        inView = entries[0].isIntersecting;
        if (inView) { schedule(); } else { clearTimeout(timer); }
      }, { threshold: 0.1 }).observe(host);
    }

    doc.addEventListener('visibilitychange', function () {
      if (doc.hidden) { clearTimeout(timer); } else { schedule(); }
    });

    /* После смены языка фразы другой длины — пересчитываем высоту. */
    host.addEventListener('motion:relayout', function () {
      measure();
      settle(index);
    });
  }

  /* 2. Scramble: раскодировка подписи глифами, 200–400 мс. */
  var GLYPHS = 'ABCDEFGHIKLMNOPRSTUVWXYZ0123456789#$%&*+<>/АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЭЮЯ';

  function initScramble(el) {
    var busy = false;

    function run() {
      if (reduced() || busy) { return; }
      var text = el.textContent;
      if (!text || text.length < 2) { return; }
      busy = true;
      el.classList.add('is-scrambling');
      var chars = text.split('');
      var total = chars.length;
      var duration = clamp(200 + total * 8, 200, 400);
      var start = 0;

      function step(now) {
        if (!start) { start = now; }
        var t = clamp((now - start) / duration, 0, 1);
        var shown = Math.floor(t * total);
        var out = '';
        for (var i = 0; i < total; i++) {
          out += (i < shown || chars[i] === ' ')
            ? chars[i]
            : GLYPHS.charAt((Math.random() * GLYPHS.length) | 0);
        }
        el.textContent = out;
        if (t < 1) {
          raf(step);
        } else {
          el.textContent = text;
          el.classList.remove('is-scrambling');
          busy = false;
        }
      }
      raf(step);
    }

    el.addEventListener('pointerenter', run, { passive: true });
    el.addEventListener('focus', run);
    return run;
  }

  /* 3. Морф-остров: пилюля раскрывает панель классом .is-open; раскрытие
     и ширина — в CSS, JS держит состояние, aria и размер индикатора. */
  function initIsland(island) {
    var toggle = island.querySelector('[data-morph-toggle]');
    var panel = island.querySelector('[data-morph-panel]');
    if (!toggle || !panel) { return; }
    var pill = island.querySelector('.morph-island__pill');

    /* Индикатор компонентного слоя живёт в отдельном слое и едет по
       --pill-x/--pill-w. Ставим ему ширину кнопки и сдвиг, при котором
       подсветка стоит ровно под ней (значения считаются, а не зашиты). */
    function sizePill() {
      if (!pill) { return; }
      var tr = toggle.getBoundingClientRect();
      if (!tr.width) { return; }
      island.style.setProperty('--pill-w', tr.width.toFixed(2) + 'px');
      island.style.setProperty('--pill-x', (tr.left - pill.getBoundingClientRect().left).toFixed(2) + 'px');
    }

    function isOpen() { return island.classList.contains('is-open'); }

    function setOpen(open, back) {
      island.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) { panel.removeAttribute('inert'); } else { panel.setAttribute('inert', ''); }
      if (!open && back) { toggle.focus(); }
    }

    setOpen(false, false);
    sizePill();
    window.addEventListener('resize', sizePill, { passive: true });
    if (doc.fonts && doc.fonts.ready && doc.fonts.ready.then) { doc.fonts.ready.then(sizePill); }

    toggle.addEventListener('click', function () { setOpen(!isOpen(), false); });

    doc.addEventListener('keydown', function (event) {
      if ((event.key === 'Escape' || event.key === 'Esc') && isOpen()) { setOpen(false, true); }
    });

    doc.addEventListener('pointerdown', function (event) {
      if (isOpen() && !island.contains(event.target)) { setOpen(false, false); }
    }, { passive: true });

    panel.addEventListener('click', function (event) {
      if (event.target.closest && event.target.closest('a')) { setOpen(false, false); }
    });
  }

  /* 4. Магнитные кнопки: --mg-x/--mg-y тянут элемент к курсору. */
  function initMagnetic(el) {
    var frame = 0, rect = null, active = false;
    var pos = { x: 0, y: 0 };

    function apply() {
      frame = 0;
      if (!rect) { return; }
      var dx = (pos.x - (rect.left + rect.width / 2)) * 0.22;
      var dy = (pos.y - (rect.top + rect.height / 2)) * 0.22;
      el.style.setProperty('--mg-x', clamp(dx, -18, 18).toFixed(2) + 'px');
      el.style.setProperty('--mg-y', clamp(dy, -14, 14).toFixed(2) + 'px');
    }

    el.addEventListener('pointerenter', function () {
      if (reduced() || !fine()) { return; }
      active = true;
      rect = el.getBoundingClientRect();
      el.classList.add('is-magnetic');
    }, { passive: true });

    el.addEventListener('pointermove', function (event) {
      if (!active) { return; }
      pos.x = event.clientX;
      pos.y = event.clientY;
      if (!frame) { frame = raf(apply); }
    }, { passive: true });

    el.addEventListener('pointerleave', function () {
      if (!active) { return; }
      active = false;
      rect = null;
      stop(frame);
      frame = 0;
      el.classList.remove('is-magnetic');
      el.style.setProperty('--mg-x', '0px');
      el.style.setProperty('--mg-y', '0px');
    }, { passive: true });
  }

  /* 5. Tilt карточки: поворот, точка подсветки и сдвиг обложки. */
  function initTilt(card) {
    var frame = 0, rect = null, active = false;
    var pos = { x: 0, y: 0 };

    function apply() {
      frame = 0;
      if (!rect) { return; }
      var nx = (pos.x - (rect.left + rect.width / 2)) / (rect.width / 2);
      var ny = (pos.y - (rect.top + rect.height / 2)) / (rect.height / 2);
      card.style.setProperty('--tilt-x', (nx * 5).toFixed(2) + 'deg');
      card.style.setProperty('--tilt-y', (-ny * 5).toFixed(2) + 'deg');
      card.style.setProperty('--tilt-shift-x', (nx * -7).toFixed(2) + 'px');
      card.style.setProperty('--tilt-shift-y', (ny * -5).toFixed(2) + 'px');
      card.style.setProperty('--mx', (clamp((pos.x - rect.left) / rect.width, 0, 1) * 100).toFixed(1) + '%');
      card.style.setProperty('--my', (clamp((pos.y - rect.top) / rect.height, 0, 1) * 100).toFixed(1) + '%');
    }

    card.addEventListener('pointerenter', function () {
      if (reduced() || !fine()) { return; }
      active = true;
      rect = card.getBoundingClientRect();
      card.classList.add('is-tilting');
    }, { passive: true });

    card.addEventListener('pointermove', function (event) {
      if (!active) { return; }
      pos.x = event.clientX;
      pos.y = event.clientY;
      if (!frame) { frame = raf(apply); }
    }, { passive: true });

    card.addEventListener('pointerleave', function () {
      if (!active) { return; }
      active = false;
      rect = null;
      stop(frame);
      frame = 0;
      card.classList.remove('is-tilting');
      card.style.setProperty('--tilt-x', '0deg');
      card.style.setProperty('--tilt-y', '0deg');
      card.style.setProperty('--tilt-shift-x', '0px');
      card.style.setProperty('--tilt-shift-y', '0px');
      card.style.setProperty('--mx', '50%');
      card.style.setProperty('--my', '45%');
    }, { passive: true });
  }

  /* 6. .card-expand: лист поверх карточки. aria-expanded стоит и на самой
     карточке (контракт CSS), и на кнопке-триггере; при закрытии фокус
     возвращается на триггер. */

  /* .case-grid.has-open — открыта хотя бы одна карточка; считаем по факту,
     а не инкрементом, поэтому классы не разъезжаются. */
  function syncGrids() {
    all('.case-grid').forEach(function (g) {
      g.classList.toggle('has-open', !!g.querySelector('.card-expand.is-open'));
    });
  }

  function initExpand(card) {
    var toggle = card.querySelector('[data-expand-toggle]');
    var body = card.querySelector('.card-expand__body');
    if (!toggle || !body) { return; }
    var closers = all('[data-expand-close]', body);

    function isOpen() { return card.classList.contains('is-open'); }

    function setOpen(open) {
      card.classList.toggle('is-open', open);
      card.setAttribute('aria-expanded', open ? 'true' : 'false');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) { body.removeAttribute('inert'); } else { body.setAttribute('inert', ''); }
      syncGrids();
    }

    setOpen(false);
    toggle.addEventListener('click', function () { setOpen(!isOpen()); });

    closers.forEach(function (button) {
      button.addEventListener('click', function () {
        setOpen(false);
        toggle.focus();
      });
    });

    /* Свободное место карточки раскрывает её; открытый лист не закрываем —
       иначе клик по тексту фактов схлопывал бы карточку. */
    card.addEventListener('click', function (event) {
      if (isOpen() || event.target.closest('a, button')) { return; }
      setOpen(true);
    });

    card.addEventListener('keydown', function (event) {
      if ((event.key === 'Escape' || event.key === 'Esc') && isOpen()) {
        event.stopPropagation();
        setOpen(false);
        toggle.focus();
      }
    });
  }

  /* 7. .hold-btn: удержание 800 мс мышью/тачем и 300 мс с клавиатуры
     (у клавиши нет тактильной обратной связи, 800 мс читаются как сбой).
     Прогресс — одна переменная --hold-progress. */
  function initHold(el) {
    var MOUSE_MS = 800, KEY_MS = 300, RESET_MS = 220;
    var progress = 0, duration = MOUSE_MS, start = 0, frame = 0;
    var active = false, completed = false;

    function paint(v) { el.style.setProperty('--hold-progress', v.toFixed(3)); }

    function complete() {
      completed = true;
      active = false;
      progress = 1;
      paint(1);
      stop(frame);
      el.classList.remove('is-holding');
      el.classList.add('is-complete');
      el.click();
      setTimeout(function () {
        completed = false;
        el.classList.remove('is-complete');
        progress = 0;
        paint(0);
      }, 900);
    }

    function tick(now) {
      if (!start) { start = now; }
      progress = clamp((now - start) / duration, 0, 1);
      paint(progress);
      if (progress >= 1) { complete(); return; }
      frame = raf(tick);
    }

    function begin(ms) {
      if (completed || active) { return; }
      duration = ms;
      start = 0;
      progress = 0;
      active = true;
      stop(frame);
      el.classList.add('is-holding');
      frame = raf(tick);
    }

    function fade() {
      var from = progress, t0 = 0;
      stop(frame);
      if (from <= 0) { paint(0); return; }
      function step(now) {
        if (!t0) { t0 = now; }
        var k = clamp((now - t0) / RESET_MS, 0, 1);
        progress = from * (1 - k);
        paint(progress);
        if (k < 1) { frame = raf(step); } else { progress = 0; paint(0); }
      }
      frame = raf(step);
    }

    function release() {
      if (!active) { return; }
      active = false;
      stop(frame);
      el.classList.remove('is-holding');
      if (!completed) { fade(); }
    }

    paint(0);
    if (reduced()) { return; }

    el.addEventListener('pointerdown', function (event) {
      if (event.pointerType === 'mouse' && event.button !== 0) { return; }
      begin(MOUSE_MS);
    }, { passive: true });
    el.addEventListener('pointerup', release, { passive: true });
    el.addEventListener('pointercancel', release, { passive: true });
    el.addEventListener('pointerleave', release, { passive: true });
    el.addEventListener('blur', release);

    el.addEventListener('keydown', function (event) {
      if (event.key !== ' ' && event.key !== 'Spacebar' && event.key !== 'Enter') { return; }
      if (event.repeat) { return; }
      if (event.key !== 'Enter') { event.preventDefault(); }
      begin(KEY_MS);
    });

    el.addEventListener('keyup', function (event) {
      if (event.key === ' ' || event.key === 'Spacebar' || event.key === 'Enter') { release(); }
    });

    /* Клик без удержания не должен уводить со страницы. */
    el.addEventListener('click', function (event) {
      if (!completed) { event.preventDefault(); }
    });
  }

  /* 8. .stream: печать по буквам один раз при входе в вьюпорт. */
  function buildStream(el, text) {
    el.textContent = '';
    var out = doc.createTextNode('');
    var cursor = doc.createElement('span');
    cursor.className = 'stream__cursor';
    cursor.setAttribute('aria-hidden', 'true');
    el.appendChild(out);
    el.appendChild(cursor);
    el.setAttribute('aria-label', text);
    return out;
  }

  function initStream(el) {
    var text = (el.textContent || '').replace(/\s+/g, ' ').trim();
    if (!text) { return; }
    var out = buildStream(el, text);

    function type() {
      if (reduced()) {
        out.data = text;
        el.classList.add('is-done');
        return;
      }
      var total = text.length, start = 0;
      el.classList.add('is-typing');
      function step(now) {
        if (!start) { start = now; }
        var n = Math.min(total, Math.floor((now - start) / 18));
        out.data = text.slice(0, n);
        if (n < total) {
          raf(step);
        } else {
          el.classList.remove('is-typing');
          el.classList.add('is-done');
        }
      }
      raf(step);
    }

    if (reduced() || !('IntersectionObserver' in window)) { type(); return; }

    var io = new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting) {
        io.disconnect();
        type();
      }
    }, { threshold: 0.35 });
    io.observe(el);
  }

  /* 9. Scroll-reveal: порог 0.15, один раз на элемент. */
  function initReveal() {
    var items = all('.reveal');
    if (!items.length) { return; }
    if (reduced() || !('IntersectionObserver' in window)) {
      items.forEach(function (el) { el.classList.add('is-visible'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15 });
    items.forEach(function (el) { io.observe(el); });
  }

  /* 10. Пятно за указателем: один rAF на движение. */
  function initGlow() {
    if (reduced() || !fine()) { return; }
    var glow = doc.createElement('div');
    glow.className = 'cursor-glow';
    glow.setAttribute('aria-hidden', 'true');
    doc.body.appendChild(glow);

    var x = 0, y = 0, frame = 0;

    function apply() {
      frame = 0;
      glow.style.setProperty('--cursor-x', x + 'px');
      glow.style.setProperty('--cursor-y', y + 'px');
    }

    window.addEventListener('pointermove', function (event) {
      x = event.clientX;
      y = event.clientY;
      glow.classList.add('is-visible');
      if (!frame) { frame = raf(apply); }
    }, { passive: true });

    doc.addEventListener('pointerleave', function () {
      glow.classList.remove('is-visible');
    }, { passive: true });
  }

  /* 11. Бегущая строка: один раз дублируем элементы дорожки. */
  function initMarquee(box) {
    var track = box.querySelector('.marquee__track');
    if (!track || track.getAttribute('data-ready') === '1') { return; }
    all('.marquee__item', track).forEach(function (item) {
      var copy = item.cloneNode(true);
      copy.setAttribute('aria-hidden', 'true');
      track.appendChild(copy);
    });
    track.setAttribute('data-ready', '1');
  }

  /* 12. Шапка и плавающий CTA: после первого экрана, кроме блока контактов. */
  function initHeader() {
    var header = doc.querySelector('.site-header');
    var sticky = doc.querySelector('[data-sticky-cta]');
    var contact = doc.getElementById('contact');
    var bands = all('.cta-band');
    var hits = 0;
    var contactVisible = false, ticking = false;

    /* reduce: без transition */
    function bandHide(on) {
      sticky.style.transition = reduced() ? 'none' : '';
      sticky.classList.toggle('is-hidden', on);
    }

    if (sticky && bands.length && 'IntersectionObserver' in window) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) { hits += e.isIntersecting ? 1 : -1; });
        if (hits < 0) { hits = 0; }
        bandHide(hits > 0);
      }, { threshold: 0.25 });
      bands.forEach(function (b) { io.observe(b); });
    }

    function update() {
      ticking = false;
      var y = window.pageYOffset || 0;
      if (header) { header.classList.toggle('is-stuck', y > 40); }
      if (sticky) {
        sticky.classList.toggle('is-visible', y > window.innerHeight * 0.8 && !contactVisible);
      }
    }

    if (contact && 'IntersectionObserver' in window) {
      new IntersectionObserver(function (entries) {
        contactVisible = entries[0].isIntersecting;
        update();
      }, { threshold: 0.2 }).observe(contact);
    }

    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; raf(update); }
    }, { passive: true });
    update();
  }

  /* Инициализация ------------------------------------------------------- */

  function relayout() {
    all('.word-roll').forEach(function (host) {
      host.dispatchEvent(new CustomEvent('motion:relayout'));
    });
    /* Смена языка переписывает тексты, но не классы; пересчёт страхует
       инвариант «.has-open ⇔ есть открытая карточка». */
    syncGrids();
  }

  function boot() {
    if (!reduced()) { root.classList.add('js-motion'); }

    all('.word-roll').forEach(initWordRoll);

    var scrambles = [];
    all('.scramble').forEach(function (el) {
      var run = initScramble(el);
      if (run) { scrambles.push({ el: el, run: run }); }
    });

    if (scrambles.length && 'IntersectionObserver' in window && !reduced()) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) { return; }
          io.unobserve(entry.target);
          scrambles.forEach(function (item) {
            if (item.el === entry.target) { item.run(); }
          });
        });
      }, { threshold: 0.6 });
      scrambles.forEach(function (item) { io.observe(item.el); });
    }

    all('.morph-island').forEach(initIsland);
    all('.magnetic').forEach(initMagnetic);
    all('.card-tilt').forEach(initTilt);
    all('.card-expand').forEach(initExpand);
    all('[data-hold]').forEach(initHold);
    all('[data-stream]').forEach(initStream);
    all('.marquee').forEach(initMarquee);

    initReveal();
    initGlow();
    initHeader();

    /* Смена языка: другой текст — другой замер и другие строки. */
    doc.addEventListener('langchange', function () {
      relayout();
      all('[data-stream]').forEach(function (el) {
        var text = (el.textContent || '').replace(/\s+/g, ' ').trim();
        if (!text) { return; }
        buildStream(el, text).data = text;
        el.classList.add('is-done');
      });
    });

    if (mqReduce && mqReduce.addEventListener) {
      mqReduce.addEventListener('change', function (event) {
        if (!event.matches) { return; }
        root.classList.remove('js-motion');
        all('.reveal').forEach(function (el) { el.classList.add('is-visible'); });
      });
    }
  }

  if (doc.readyState === 'loading') {
    doc.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
