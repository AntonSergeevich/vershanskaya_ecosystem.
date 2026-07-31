/* Панель форматирования над текстовым полем в студии.
 *
 * Ничего не грузит со стороны и не хранит HTML: кнопки просто расставляют
 * пометки в тексте — те самые, что понимает core/services/markup.py.
 * Без JavaScript поле остаётся обычной textarea, и пометки можно набрать
 * руками — форма от этого не ломается.
 */
(function () {
  'use strict';

  var BUTTONS = [
    {label: 'Ж', title: 'Жирный', wrap: '**', style: 'font-weight:700'},
    {label: 'К', title: 'Курсив', wrap: '*', style: 'font-style:italic'},
    {label: 'H2', title: 'Заголовок', prefix: '## '},
    {label: '•', title: 'Список', prefix: '- '},
    {label: '1.', title: 'Нумерованный список', prefix: '1. '},
    {label: '❝', title: 'Цитата', prefix: '> '},
    {label: '🔗', title: 'Ссылка', link: true}
  ];

  function selectionLines(field) {
    // Границы строк, попавших в выделение: префикс ставится ко всей строке,
    // а не в середину слова, где курсор оказался случайно.
    var start = field.value.lastIndexOf('\n', field.selectionStart - 1) + 1;
    var end = field.value.indexOf('\n', field.selectionEnd);
    return {start: start, end: end === -1 ? field.value.length : end};
  }

  function replace(field, from, to, text) {
    field.setRangeText(text, from, to, 'end');
    field.focus();
    field.dispatchEvent(new Event('input', {bubbles: true}));
  }

  function select(field, from, length) {
    // setRangeText сбрасывает выделение в конец вставленного текста. Без
    // этого повторное нажатие кнопки видит пустое выделение и вместо снятия
    // разметки вставляет ещё одну пару звёздочек.
    field.selectionStart = from;
    field.selectionEnd = from + length;
  }

  function applyWrap(field, marker) {
    var from = field.selectionStart;
    var to = field.selectionEnd;
    var chosen = field.value.slice(from, to);

    if (!chosen) {
      // Ничего не выделено — вставляем заготовку и выделяем слово внутри,
      // чтобы его сразу можно было заменить своим.
      replace(field, from, to, marker + 'текст' + marker);
      select(field, from + marker.length, 'текст'.length);
      return;
    }

    // Пробелы по краям выносим наружу: «** текст **» разметкой не считается.
    var lead = chosen.length - chosen.replace(/^\s+/, '').length;
    var tail = chosen.length - chosen.replace(/\s+$/, '').length;
    from += lead;
    to -= tail;
    chosen = field.value.slice(from, to);
    if (!chosen) { return; }

    // Повторное нажатие снимает разметку — иначе получается ****текст****.
    var outer = field.value.slice(from - marker.length, to + marker.length);
    if (outer === marker + chosen + marker) {
      replace(field, from - marker.length, to + marker.length, chosen);
      select(field, from - marker.length, chosen.length);
      return;
    }

    replace(field, from, to, marker + chosen + marker);
    select(field, from + marker.length, chosen.length);
  }

  function applyPrefix(field, prefix) {
    var span = selectionLines(field);
    var block = field.value.slice(span.start, span.end);
    var lines = block.split('\n');
    var already = lines.every(function (line) { return line.indexOf(prefix) === 0; });

    var result = lines.map(function (line) {
      if (already) { return line.slice(prefix.length); }
      return line ? prefix + line : line;
    }).join('\n');

    replace(field, span.start, span.end, result);
    select(field, span.start, result.length);
  }

  function applyLink(field) {
    var chosen = field.value.slice(field.selectionStart, field.selectionEnd) || 'текст';
    var url = window.prompt('Адрес ссылки', 'https://');
    if (!url) { return; }
    replace(field, field.selectionStart, field.selectionEnd,
            '[' + chosen + '](' + url + ')');
  }

  function build(field) {
    var bar = document.createElement('div');
    bar.className = 'editor-bar';

    BUTTONS.forEach(function (spec) {
      var button = document.createElement('button');
      button.type = 'button';           // иначе кнопка отправит форму
      button.className = 'editor-button';
      button.textContent = spec.label;
      button.title = spec.title;
      if (spec.style) { button.setAttribute('style', spec.style); }

      button.addEventListener('click', function () {
        if (spec.link) { applyLink(field); }
        else if (spec.wrap) { applyWrap(field, spec.wrap); }
        else { applyPrefix(field, spec.prefix); }
      });
      bar.appendChild(button);
    });

    var hint = document.createElement('span');
    hint.className = 'editor-hint';
    hint.textContent = 'Пустая строка — новый абзац';
    bar.appendChild(hint);

    field.parentNode.insertBefore(bar, field);
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('textarea[data-editor]').forEach(build);
  });
})();
