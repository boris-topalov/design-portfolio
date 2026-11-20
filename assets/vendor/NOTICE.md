# NOTICE — внешние идеи и атрибуция

## Код

Весь код сайта написан для этого проекта: HTML, CSS и ванильный JavaScript
(`assets/js/*.js`). Сборщиков, пакетных менеджеров и сторонних библиотек нет;
сайт открывается по `file://` без сети.

## Идеи и параметры движения

Часть приёмов и значений движения адаптирована по мотивам открытых
UI-библиотек. **Прямая копия кода не использовалась** — реализации в
`assets/js/motion.js` написаны с нуля на ванильном JS и переработаны под
статический сайт без React и без сборки.

| Источник | Лицензия | Что взято как ориентир |
| --- | --- | --- |
| [Kokonut UI](https://kokonutui.com) | MIT | идея «морф-острова» (компактная пилюля → панель), поведение магнитных кнопок, приём со стримингом текста |
| [SmoothUI](https://smoothui.dev) | MIT | параметры пружин (жёсткость/демпфирование подъёма слова), hold-to-confirm с кольцом прогресса, мягкое пятно за указателем |

### MIT License (текст лицензии обоих проектов)

```
MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Шрифт

Manrope — SIL Open Font License 1.1, файл и текст лицензии лежат рядом:
`assets/fonts/Manrope-Variable.woff2`, `assets/fonts/OFL.txt`.
