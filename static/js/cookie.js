/* Закрытие уведомления о куках.
 *
 * Согласие храним в самой куке, а не в localStorage: сервер должен знать,
 * показывать баннер или нет, иначе он мелькает при каждой загрузке страницы,
 * пока не отработает JavaScript.
 */
(function () {
  'use strict';

  var banner = document.getElementById('cookie-banner');
  var button = document.getElementById('cookie-accept');
  if (!banner || !button) return;

  button.addEventListener('click', function () {
    var year = 365 * 24 * 60 * 60;
    // SameSite=Lax: кука не нужна сторонним сайтам, и незачем её им отдавать.
    var flags = 'path=/; max-age=' + year + '; SameSite=Lax';
    if (location.protocol === 'https:') flags += '; Secure';
    document.cookie = 'cookie_consent=yes; ' + flags;
    banner.remove();
  });
})();
