/* Кнопки «поделиться» на странице результата.
 *
 * Ссылки на Telegram и WhatsApp работают без JavaScript — они и есть
 * основной способ. Здесь только две надстройки: копирование в буфер и
 * системное окно «Поделиться» на телефонах, где оно есть.
 */
(function () {
  'use strict';

  function copy(text) {
    if (navigator.clipboard) {
      return navigator.clipboard.writeText(text);
    }
    // Старые браузеры и любой http без TLS: clipboard там недоступен.
    return new Promise(function (resolve, reject) {
      var helper = document.createElement('textarea');
      helper.value = text;
      helper.setAttribute('readonly', '');
      helper.style.position = 'fixed';
      helper.style.opacity = '0';
      document.body.appendChild(helper);
      helper.select();
      var ok = document.execCommand('copy');
      document.body.removeChild(helper);
      ok ? resolve() : reject();
    });
  }

  function setup(card) {
    var url = card.dataset.shareUrl;
    var text = card.dataset.shareText;

    var button = card.querySelector('[data-copy]');
    if (button) {
      button.addEventListener('click', function () {
        var label = button.textContent;
        copy(url).then(function () {
          button.textContent = 'Скопировано';
        }).catch(function () {
          button.textContent = 'Не вышло — скопируйте из адресной строки';
        }).then(function () {
          setTimeout(function () { button.textContent = label; }, 2200);
        });
      });
    }

    // На телефонах системное окно удобнее списка кнопок: там сразу видны
    // те чаты, куда человек пишет чаще всего.
    if (!navigator.share) { return; }
    var native = document.createElement('button');
    native.type = 'button';
    native.className = 'btn btn-small';
    native.textContent = 'Поделиться';
    native.addEventListener('click', function () {
      navigator.share({title: text, text: text, url: url}).catch(function () {
        // Человек закрыл окно — это не ошибка, показывать нечего.
      });
    });
    var row = card.querySelector('.share-buttons');
    row.insertBefore(native, row.firstChild);
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.share-card').forEach(setup);
  });
})();
