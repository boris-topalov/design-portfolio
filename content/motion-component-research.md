# Motion-компоненты для ванильного портфолио: Kokonut UI + SmoothUI

Точные параметры анимации для HTML/CSS/JS без сборки и библиотек. Исходники читал прямо из репозиториев (raw GitHub), поэтому в тексте — конкретные цифры, а не общие рекомендации.

## 1. Лицензии (обе MIT)

| Проект | Автор | LICENSE |
|---|---|---|
| Kokonut UI (v2.0.0) | Dorian Baffier, © 2025 kokonutUI | https://github.com/kokonut-labs/kokonutui/blob/main/LICENSE |
| SmoothUI | Eduardo Calvo, © 2024 | https://github.com/educlopez/smoothui/blob/main/LICENSE |
**Требуется при атрибуции:** сохранять copyright notice (Copyright (c) 2025 kokonutUI / © 2024 Eduardo Calvo) и полный текст условий лицензии (permission notice) во всех копиях и в существенных частях ПО.
**Нельзя:** использовать бренд/логотип/название библиотек для производных работ, подразумевающих аффилированность с владельцем. MIT не даёт прав на торговые знаки.
**Нюанс:** в реестр-json `kokonutui.com/r/hold-button.json` для `hold-button` указан `holdDuration=3000`, в реальном файле (v2.0.0, 2026-10-16) и на docs — `1200`. Доверяй актуальному файлу, а не устаревшему snapshot.

## 2. Правила производительности (6–8 одновременных эффектов без лагов)

1. **Только transform/opacity/clip-path** — width/height/top/left вызывают relayout и тормозят.
2. **Писать стили прямо в DOM** (`el.style.transform`), без перерендера и React-diff'а за кадр.
3. **will-change эластично** — только на элемент, который точно анимируется, и снять после окончания.
4. **rAF + dt clamp** `min((now-last)/1000, 1/30)` — иначе падение фреймов ломает пружину.
5. **cancelAnimationFrame** при выходе; отписка от `matchMedia`, ResizeObserver, сетевых таймеров.
6. **IntersectionObserver/useInView:** анимации только при видимости (typewriter паузится при скрытии).
7. **prefers-reduced-motion** — пропускать или `duration: 0`; на touch отключать оверлейные gestures `touch-pan-y`.

## 3. Hold button (Kokonut UI, buttons)

**Источники:** https://github.com/kokonut-labs/kokonutui/blob/main/components/kokonutui/hold-button.tsx (v2.0.0, 2026-10-16) · docs https://kokонутui.com/docs/buttons/hold-button
**Ключевая логика**
- state machine: idle | holding | complete
- onPointerDown (button 0): release capture → startHold(): progress 0→1 за holdDuration/1000 с, linear; onComplete: complete()
- complete(): phase=complete, onHoldComplete(), после resetAfter ms → progress=0, idle
- оставшаяся доля: remaining=(1-progress)*holdDuration → pick up where drain ended
- onRelease (up/leave/cancel): если phase==holding: drain duration=(progress*DRAIN_MS)/1000 с, ease-out; short tap ≈ 0
- Label: idle "Hold to delete" → holding (150 ms) "Keep holding" → complete (DrawnCheck path 0→1, 0.3 с); data-complete + aria-disabled; AnimatePresence mode="popLayout"
- Keyboard: Space/Enter keydown startHold, keyup endHold, preventDefault
- Reduced motion: MotionConfig reducedMotion="user" → drain 0
**Параметры**
| Параметр | Значение | Примечание |
|---|---|---|
| holdDuration | **1200 ms** | docs + исходник; `3000` в устаревшем registry JSON |
| resetAfter | 1800 ms (0 = держать) | |
| DRAIN_MS | 300 ms | fill спадает обратно за 300 мс после раннего отпускания |
| LABEL_DELAY_MS | 150 ms | задержка показа "Keep holding" |
| EASE_OUT | cubic-bezier(0.23,1,0.32,1) | drain + label |
| Филл | clipPath inset(0 (1-p)*100% 0 0), linear 0→1 | |
| Check | pathLength 0→1, 0.3 с, delay 0.1 | |
**Как воспроизвести на ванильный JS/CSS**

```css
.btn{position:relative;overflow:hidden;touch-action:manipulation}
.fill{position:absolute;left:0;top:0;width:0%;height:100%;transition:width linear 1.2s}
.btn:active .fill{transition:width cubic-bezier(0.23,1,0.32,1) calc(300ms*(var(--fill)/100))}
.btn.cmp{background:var(--ok);border-color:var(--ok)}.fill{opacity:0}
/* keyboard: Space/Enter preventDefault; labels opacity .2s + transform .2s */
/* linear() не даёт пружины: на drain используй cubic-bezier(0.34,1.56,0.64,1) */
```

Схожие кнопки в том же коллекции: slide-to-confirm (плавный скролл), tear-button, magnet-button — для портфолио можно оставить только hold-кнопку, она показывает pattern "удержание с обратным прогрессом".

## 4. Smooth tab + morph island

### 4.1 Smooth tab (Kokonut UI, navigation)

**Источники:** https://github.com/kokonut-labs/kokonutui/blob/main/components/kokonutui/smooth-tab.tsx · docs https://kokonutui.com/docs/navigation/smooth-tab
**Ключевая логика**
- progress = useMotionValue(selected) (за пределами — rubber-band)
- paint(p): track translate3d(-p*100%/count,0,0); панели opacity 1-d*(1-0.35); indicator = clipPath inset(...) round height/2 — одна полоска без цветового tween
- settle: reducedMotion? 0.15 с ease-out : spring {stiffness 420, damping 38, velocity}
- drag: setPointerCapture; axis = x при |dx|>6 (AXIS_LOCK), иначе скролл; velocity по 100 мс окну (VELOCITY_WINDOW); |v|>0.11 px/ms → соседний таб
- select + suppressClick 0 мс, чтобы тап не съел click; Arrows + Home/End, удержание → instant jump
- indicator: overlay clipPath, labels в activeColor под оверлеем
**Параметры**
| Параметр | Значение |
|---|---|
| Spring stiffness / damping | **420 / 38** (критическое ≈41 → малое перекоса) |
| EASE_OUT | cubic-bezier(0.23,1,0.32,1) |
| Reduced motion | 0.15 с, ease-out |
| RUBBER_BAND / AXIS_LOCK / SWIPE_VELOCITY / VELOCITY_WINDOW | 0.35 / 6 px / 0.11 px/ms / 100 ms |
| NEIGHBOUR_OPACITY | 0.35 |
| Панели | inert + tabIndex -1, min-h 220px, translate3d |
**Как воспроизвести на ванильный JS/CSS**

```css
.tab-track{transform:translate3d(0,0,0);transition:transform .25s cubic-bezier(0.23,1,0.32,1)}
.panel{opacity:.35;transition:opacity .25s cubic-bezier(0.23,1,0.32,1)}.panel.active{opacity:1}
/* indicator: прямоугольник, clip-path inset(...) round; измерить через ResizeObserver */
/* spring vanilla: rAF a=-k*x-c*v; v+=a*dt; x+=v*dt (k=420, c=38, dt<=1/30) */
/* CSS-приближение перекоса: cubic-bezier(0.34,1.56,0.64,1) (easeOutBack) */
```

### 4.2 Morph island (SmoothUI analog — morph-surface)

**Источники:** https://github.com/educlopez/smoothui/blob/main/packages/smoothui/components/morph-surface/index.tsx · docs https://smoothui.dev/docs/components/morph-surface
**Ключевая логика**
- showFeedback: borderRadius 20→14, height 44→200, width 360→auto
- spring: stiffness 550, damping 45, mass 0.7, duration 0.25 с; delay 0 open, 0.08 с close
- Два spring'а: обёртка (borderRadius/height/width) и контент (opacity, blur, translateX)
- AnimatePresence mode="wait": иконка SiriOrb 0.2 с opacity 0→1; Reduced motion: все переходы duration 0
- Контент: форма с textarea + кнопка отправки; при success вспыхивает сообщение 1.5 с
- Закрытие: крест, клик вне компонента или Escape; Focus переходит в панель
**Параметры**
| Параметр | Значение |
|---|---|
| Spring stiffness / damping / mass | 550 / 45 / 0.7 |
| Duration | 0.25 с; close delay 0.08 с |
| Размеры | borderRadius 20→14; height 44→200; width 360 |
**Как воспроизвести на ванильный JS/CSS**

```css
#m{border-radius:20px;height:44px;transition:border-radius .25s,height .25s,width .25s cubic-bezier(0.23,1,0.32,1)}

/* open: 14px/200px/360px */
/* Пружины в CSS нет: smooth-curve-out (0.23,1,0.32,1) с долгим хвостом; точная пружина —
   rAF: a=-550x-45v; v+=a*dt; x+=v*dt. linear() только для линейных интерполяций */
```

## 5. Expand card / notification stack

### 5.1 Notification stack (Kokonut UI)

**Источники:** https://github.com/kokonut-labs/kokonutui/blob/main/components/kokonutui/notification-stack.tsx · docs https://kokonutui.com/docs/cards/notification-stack
**Ключевая логика**
- expanded=(hovered||focused||pinned)&&n>1
- height: collapsed=front+min(n-1,2)*PEEK; expanded=sum heights+(n-1)*GAP
- cards: absolute inset-x-0 top-0 origin-top; translateY(y) scale(1-depth*0.05); за expanded — opacity 0
- snapBack rAF: F=-520x-45.6v; v+=F*dt; x+=v*dt; stop |x|<0.5 && |v|<10
- dismiss: flight speed=max(|v|,1400) px/s, accel 4200 px/s², distance=1.1*width; opacity=1-|x|/distance; finish при |x|>=distance
- gesture: axis 6px; velocity по 80 мс окну; |v|>0.11 → направление от знака dx; else snapBack
- focus: Delete/Backspace → focus на соседнюю карточку
- collapse/expand: height 300ms cubic-bezier(0.23,1,0.32,1); за expanded — opacity 0
**Параметры**
| Параметр | Значение |
|---|---|
| PEEK / VISIBLE_BEHIND / GAP | 10px / 2 / 8px |
| FALLBACK_HEIGHT | 76px |
| DISMISS_DISTANCE / VELOCITY | 100px / 0.11 px/ms |
| Spring stiffness / damping | 520 / 45.6 (критическое) |
| FLIGHT: min speed / accel | 1400 px/s / 4200 px/s² |
| VELOCITY_WINDOW_MS | 80 |
| EXIT_MS | 200 (fade при reduced-motion) |
| Height transition | 300ms cubic-bezier(0.23,1,0.32,1) |
| Масштаб карточек | 1 - depth*0.05 |
**Как воспроизвести на ванильный JS/CSS**

```css
.cards{position:relative;overflow:hidden}
.card{position:absolute;inset-x-0;top:0;transform-origin:top;transition:transform .3s ease-out,opacity .2s}
.collapsed .back{transform:translateY(10px) scale(.95);opacity:0}
/* expand: высота + translateY offsets, 300ms */
/* swipe: el.style.transform=translateX(x); opacity=max(1-|x|/d,0) */
/* spring rAF: a=-520x-45.6v; v+=a*dt; x+=v*dt; останов |x|<.5 && |v|<10 */
/* keyboard: Enter/Space toggle expand; Delete dismiss + focus next */
```

### 5.2 Expandable cards (SmoothUI analog)

**Источники:** https://github.com/educlopez/smoothui/blob/main/packages/smoothui/components/expandable-cards/index.tsx · docs https://smoothui.dev/docs/components/expandable-cards
**Ключевая логика**
- scroll: x mandatory + scrollPaddingLeft 20%; карточки 200px, snap по start
- выбранная карточка растягивается в 500px: layout-анимация, ease-out-quint [0.23,1,0.32,1], 0.25 с
- AnimatePresence popLayout: лоток-экспанд blur 5px, opacity 0, width 0, x 20, 0.25 с; exit — карточка возвращается на место
- overlay-кнопка на всю карточку (after inset-0), stopPropagation на play-кнопке, focus переходит в выбранную карточку
- авто-центровка кликнутой карточки: scrollIntoView smooth, block nearest, inline center
- Reduced motion: instant, opacity 1; aria-expanded на заголовке карточки
**Параметры**
| Параметр | Значение |
|---|---|
| Ширина | 200px / 500px |
| Transition | 0.25 с, ease-out-quint |
| Panel exit | blur 5px, opacity 0, width 0, x 20, 0.25 с |
**Как воспроизвести на ванильный JS/CSS**

```css
.card{width:200px;transition:width .25s ease-[cubic-bezier(0.23,1,0.32,1)]}
.card.active{width:500px}
/* panel: opacity+x+blur 0.25с; scroll-snap x mandatory */
```

## 6. Word roll / scramble / typewriter

### 6.1 Typewriter (Kokonut UI)

**Источники:** https://github.com/kokonut-labs/kokonutui/blob/main/components/kokonutui/type-writer.tsx · docs https://kokonutui.com/docs/texts/type-writer
**Ключевая логика**
- typing: setTimeout: text.slice(0,char+1) каждые 50 ms
- naturalVariance: ±40%, 10% пауза 2×, 10% burst 0.5×
- delete: 30 ms/char backspace или select (sweep 120 ms/символ, hold 220 ms, очистка); TYPO_NOTICE_MS=250: опечатка видна 250 мс, потом затерта + 1.5× wait
- caret: CSS-анимация blink (свой тайминг, не main thread); solid пока идёт typing; мигает после CARET_IDLE_MS=500
- loop: pauseBeforeDelete 1000 мс → next phrase (100 ms); loopDelay 1000; last phrase удаляется при autoLoop
- Локация: пауза/отступ от вью → текст не сбрасывается; isRunning=!paused&&inView
- Reduced motion: финальная фраза сразу
- Layout trick: все фразы в невидимом grid-контейнере одного шрифта → ширина wrap = ширина самой широкой фразы; текст слева, leading 1.2, cursor min-h 1.2em — одна высота строки, скролл не прыгает; aria-live polite; seed=7 (Park-Miller)
**Параметры**
| Параметр | Значение |
|---|---|
| typingSpeed / deleteSpeed | 50 / 30 ms/символ |
| startDelay / loopDelay / pauseBeforeDelete | 200 / 1000 / 1000 ms |
| naturalVariance | ±40%, 10%×2, 10%×0.5 |
| deleteMode | backspace \| select (sweep 120 ms, hold 220 ms) |
| typos | 0.04 (4%) |
| seed / CARET_IDLE_MS / NEXT_SEQUENCE_DELAY | 7 / 500 / 100 мс |
**Как воспроизвести на ванильный JS/CSS**

```css
.wrap{position:relative;white-space:nowrap;line-height:1.2}
.caret{display:inline-block;width:2px;height:1.05em;background:currentColor; animation: ktm 1s steps(2,end) infinite}
@keyframes ktm{0%,33.33%{opacity:1}66.67%,100%{opacity:0}}
/* JS: setTimeout-цепочка с jitter; reduced-motion → сразу весь текст */
```

**Почему не скачет высота:** все варианты фраз помещены в невидимый grid-контейнер одного шрифта, который "замеряет" ширину; в видимом элементе текст слева, одна строка, фиксированная line-height. При этом нет отдельного помещения курсора, который бы менял высоту.

### 6.2 Split-flap text (Kokonut UI)

**Источники:** https://github.com/kokonut-labs/kokonutui/blob/main/components/kokonutui/split-flap-text.tsx · docs https://kokonutui.com/docs/texts/split-flap-text
**Ключевая логика**
- FLIP=56ms: верхняя половинка rotateX 0→-90 (28 мс, cubic-bezier(0.5,0,0.9,0.6)); нижняя 90→0 со сдвигом 28 мс (cubic-bezier(0.2,0.6,0.3,1)); shade 0→1→0 linear 56 мс
- STAGGER=40 ms: tiles начинают флипнуты сзади вперёд; interval=3800 мс — переключение слова
- length = длина самого длинного слова по умолчанию → ширина доски фиксирована; reduceMotion: без анимации, единообразная целевая буква
- Tile постоянно держит своё положение при смене слова (front/back клип); tiles aria-hidden, а текст объявляется в sr-only
**Параметры**
| Параметр | Значение |
|---|---|
| FLIP | 56 ms |
| STAGGER | 40 ms |
| interval | 3800 ms |
| rotateX | 0→-90 (верх), 90→0 (низ, delay half) |
| easing | 0.5/0/0.9/0.6 · 0.2/0.6/0.3/1 |
| shade | opacity 0→1→0 linear |
**Как воспроизвести на ванильный JS/CSS**

```css
.tile{perspective:5em}.half{backface-hidden}
@keyframes t{to{transform:rotateX(-90deg)}}@keyframes b{to{transform:rotateX(0deg)}}
/* tile: top 0→28ms; bottom 28→56ms; shade 0→56ms linear; stagger i*40ms */
```

### 6.3 TypewriterText (SmoothUI)

**Источники:** https://github.com/educlopez/smoothui/blob/main/packages/smoothui/components/typewriter-text/index.tsx · docs https://smoothui.dev/docs/components/typewriter-text
**Ключевая логика**
- type() заполняет display через slice(0,idx+1) каждые 50 ms; recursion через setTimeout, index — ref
- loop: при достижении конца текста — очистка, сброс index, задержка LOOP_RESTART_DELAY_MS=1000 мс, новый цикл
- loop=false → останов после полного ввода; Reduced motion: сразу children (полный текст)
- cleanup: clearTimeout в return функции эффекта; визуально только текущий символ растёт
**Параметры**
| Параметр | Значение |
|---|---|
| speed | 50 ms/символ |
| loop | false |
| LOOP_RESTART_DELAY_MS | 1000 |
**Как воспроизвести на ванильный JS/CSS**

```css
/* как 6.1 с loop=false, speed=50, prefers-reduced-motion → полный текст */
```

## 7. Чек-лист приёма движения (8 пунктов)

- [ ] **Нет скачков** — высота/ширина/положение контента не меняются "соскоками"; отступы не вызывают reflow-скачков.
- [ ] **Все входы** — mouse down/up, touch start/end/cancel, pointer, Enter/Space, focus; pointer capture; Enter не генерирует лишний click.
- [ ] **Рабочая отмена** — ранний отпуск без завершения; fill возвращается (drain); label держится 150 мс.
- [ ] **Аксессibles** — focus-visible ring, aria-live (polite), aria-disabled в active-состоянии, label для иконок, tabindex, Escape dismiss.
- [ ] **prefers-reduced-motion** — анимации отключены/мгновенные; показывается конечное состояние, скрыты blink и счётчики.
- [ ] **Нет layout-скачков при рендере** — размеры рассчитываются заранее (ResizeObserver + широкий вариант текста).
- [ ] **Производительность** — 6–8 эффектов: только transform/opacity, rAF с dt clamp, will-change только на целевых элементах, cancelAnimationFrame, IntersectionObserver.
- [ ] **Чистота** — нет утечек: отписка от ResizeObserver/pointerup/matchMedia, очистка таймеров, кадры остановлены.

## 8. Источники

**Библиотеки:** Kokonut UI https://kokонутui.com · GitHub https://github.com/kokonut-labs/kokonutui (MIT LICENSE) · SmoothUI https://smoothui.dev · GitHub https://github.com/educlopez/smoothui (MIT LICENSE)
**Компоненты**
- Hold Button: https://github.com/kokonut-labs/kokonutui/blob/main/components/kokonutui/hold-button.tsx · docs https://kokonutui.com/docs/buttons/hold-button
- Smooth Tab: https://github.com/kokonut-labs/kokonutui/blob/main/components/kokonutui/smooth-tab.tsx · docs https://kokonutui.com/docs/navigation/smooth-tab
- Status Island: https://github.com/kokonut-labs/kokonutui/blob/main/components/kokonutui/status-island.tsx
- Notification Stack: https://github.com/kokonut-labs/kokonutui/blob/main/components/kokonutui/notification-stack.tsx · docs https://kokonutui.com/docs/cards/notification-stack
- Split Flap Text: https://github.com/kokonut-labs/kokonutui/blob/main/components/kokonutui/split-flap-text.tsx · docs https://kokonutui.com/docs/texts/split-flap-text
- Typewriter: https://github.com/kokonut-labs/kokonutui/blob/main/components/kokonutui/type-writer.tsx · docs https://kokonutui.com/docs/texts/type-writer
- Morph Surface: https://github.com/educlopez/smoothui/blob/main/packages/smoothui/components/morph-surface/index.tsx · docs https://smoothui.dev/docs/components/morph-surface
- Expandable Cards: https://github.com/educlopez/smoothui/blob/main/packages/smoothui/components/expandable-cards/index.tsx · docs https://smoothui.dev/docs/components/expandable-cards
- TypewriterText: https://github.com/educlopez/smoothui/blob/main/packages/smoothui/components/typewriter-text/index.tsx · docs https://smoothui.dev/docs/components/typewriter-text