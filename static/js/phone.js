/* Маска российского номера: «+7 (999) 123-45-67».
 *
 * Правила, которые важнее красоты:
 *  - первая же цифра превращает поле в «+7 (…», как и просили;
 *  - ведущие 8 и 7 считаются кодом страны и не занимают место первой цифры
 *    номера: «8 912…» и «+7 912…» дают один и тот же результат;
 *  - каретка не прыгает в конец при правке середины;
 *  - вставка из буфера разбирается так же, как набор руками;
 *  - если скрипт не загрузился, поле остаётся обычным текстовым — сервер
 *    всё равно нормализует номер (users.utils.normalize_phone).
 */
(function () {
  'use strict';

  var LENGTH = 10; // цифр после кода страны

  /** Цифры самого номера, без кода страны. */
  function nationalDigits(raw) {
    var digits = (raw || '').replace(/\D/g, '');
    if (digits[0] === '8' || digits[0] === '7') {
      digits = digits.slice(1);
    }
    return digits.slice(0, LENGTH);
  }

  function format(digits) {
    var out = '+7 (' + digits.slice(0, 3);
    if (digits.length >= 3) out += ')';
    if (digits.length > 3) out += ' ' + digits.slice(3, 6);
    if (digits.length > 6) out += '-' + digits.slice(6, 8);
    if (digits.length > 8) out += '-' + digits.slice(8, 10);
    return out;
  }

  function render(raw) {
    var digits = nationalDigits(raw);
    if (digits) return format(digits);
    // Человек набрал только «8» или «7» — это код страны. Показываем начало
    // маски, иначе кажется, что поле не реагирует на ввод.
    return /\d/.test(raw || '') ? '+7 (' : '';
  }

  /** Сколько цифр номера стоит левее каретки — по ним и восстановим позицию. */
  function digitsBeforeCaret(value, caret) {
    var open = value.indexOf('(');
    var start = open >= 0 ? open + 1 : 0;
    if (caret <= start) return 0;

    var head = value.slice(start, caret).replace(/\D/g, '');
    // Скобки ещё нет — значит человек печатает в пустое поле и первая 7/8
    // может оказаться кодом страны.
    if (open < 0 && /^[78]/.test(head)) head = head.slice(1);
    return head.length;
  }

  function caretForDigit(formatted, index) {
    if (index <= 0) return formatted.length;
    var seen = 0;
    for (var i = formatted.indexOf('(') + 1; i < formatted.length; i++) {
      if (/\d/.test(formatted[i])) {
        seen++;
        if (seen === index) return i + 1;
      }
    }
    return formatted.length;
  }

  function apply(input, keepCaret) {
    var before = input.value;
    var index = keepCaret ? digitsBeforeCaret(before, input.selectionStart) : 0;

    var formatted = render(before);
    if (formatted === before) return;

    input.value = formatted;
    if (keepCaret && input === document.activeElement) {
      var position = caretForDigit(formatted, index);
      input.setSelectionRange(position, position);
    }
  }

  function attach(input) {
    if (input.dataset.phoneMask === 'on') return;
    input.dataset.phoneMask = 'on';

    input.setAttribute('inputmode', 'tel');
    input.setAttribute('autocomplete', 'tel');
    if (!input.getAttribute('placeholder')) {
      input.setAttribute('placeholder', '+7 (___) ___-__-__');
    }

    input.addEventListener('input', function () { apply(input, true); });
    // Поле, в котором остался только код страны, очищаем: пустое поле
    // честнее показывает, что номер не введён.
    input.addEventListener('blur', function () {
      if (!nationalDigits(input.value)) input.value = '';
    });

    apply(input, false); // номер, пришедший с сервера, тоже приводим к маске
  }

  function init(root) {
    (root || document).querySelectorAll('[data-phone]').forEach(attach);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { init(); });
  } else {
    init();
  }

  window.phoneMask = { init: init, render: render, digits: nationalDigits };
})();
