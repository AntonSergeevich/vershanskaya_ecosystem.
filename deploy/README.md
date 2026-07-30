# Деплой

Два пути. Выберите по вашему тарифу на Beget.

| | Обычный хостинг | VPS |
|---|---|---|
| Python-приложение | панель Beget, Passenger | gunicorn + systemd |
| Точка входа | `deploy/passenger_wsgi.py` | `deploy/gunicorn.service` |
| nginx | настраивает Beget | `deploy/nginx.conf` — ваш |
| Защита видео через nginx | недоступна, работает отдача через Django | `X-Accel-Redirect`, полноценно |
| PostgreSQL | если есть в тарифе, иначе SQLite | ставится сами |
| Перезапуск | `touch tmp/restart.txt` | `systemctl restart vershanskaya` |

На обычном хостинге проект работает, но видео уроков отдаёт сам Python — при
нескольких одновременных просмотрах это заметно. Если планируются видеокурсы
с потоком людей, VPS оправдан.

---

## Что нужно на сервере в любом случае

1. Python 3.11 или новее.
2. Каталоги рядом с проектом: `media/`, `protected_media/`, `staticfiles/`.
   Первые два должны быть доступны на запись пользователю приложения.
3. Файл `.env` — не из репозитория, создаётся на сервере. Обязательно:

   ```
   DEBUG=False
   SECRET_KEY=<50+ случайных символов>
   ALLOWED_HOSTS=vershanskaya.ru,www.vershanskaya.ru
   CSRF_TRUSTED_ORIGINS=https://vershanskaya.ru,https://www.vershanskaya.ru
   ```

   Ключ сгенерировать:
   `python -c "import secrets; print(secrets.token_urlsafe(50))"`

   Остальные переменные — в `.env.example` в корне проекта.

4. `protected_media/` **не должен** быть доступен по прямой ссылке из
   интернета. Проверьте после деплоя: откройте
   `https://ваш-домен/protected_media/` — должно быть 403 или 404.

---

## Обычный хостинг Beget

```bash
# по SSH
cd ~
git clone https://github.com/AntonSergeevich/vershanskaya_ecosystem. site
cd site

python3 -m venv venv
venv/bin/pip install -r requirements.txt

cp deploy/passenger_wsgi.py ./passenger_wsgi.py
nano .env                      # см. выше
mkdir -p media protected_media tmp

venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput
venv/bin/python manage.py createsuperuser
venv/bin/python manage.py seed_demo --with-slots

touch tmp/restart.txt
```

В панели Beget: **Сайты → ваш домен → Python** — указать каталог `~/site`,
версию Python и файл `passenger_wsgi.py`.

Статику Beget отдаёт сам, если в панели указать `staticfiles` как каталог
статики. Если такой настройки нет — оставьте как есть, WhiteNoise отдаст
статику из Python (в `MIDDLEWARE` он уже подключён).

---

## VPS

```bash
sudo apt update && sudo apt install -y python3-venv nginx postgresql

sudo mkdir -p /srv/vershanskaya && sudo chown $USER /srv/vershanskaya
git clone https://github.com/AntonSergeevich/vershanskaya_ecosystem. /srv/vershanskaya
cd /srv/vershanskaya

python3 -m venv venv
venv/bin/pip install -r requirements.txt

sudo -u postgres createuser vershanskaya --pwprompt
sudo -u postgres createdb vershanskaya --owner=vershanskaya

nano .env                      # + POSTGRES_* и PROTECTED_MEDIA_USE_NGINX=True
mkdir -p media protected_media

venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput
venv/bin/python manage.py createsuperuser

sudo cp deploy/gunicorn.service /etc/systemd/system/vershanskaya.service
sudo systemctl daemon-reload && sudo systemctl enable --now vershanskaya

sudo cp deploy/nginx.conf /etc/nginx/sites-available/vershanskaya
sudo ln -s /etc/nginx/sites-available/vershanskaya /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx -d vershanskaya.ru -d www.vershanskaya.ru

sudo chown -R www-data:www-data /srv/vershanskaya
```

---

## Регулярные задачи (cron)

Подписки не закрываются сами — за этим следит команда. Без неё человек,
переставший платить, останется в клубе навсегда.

```cron
0 3 * * * cd /srv/vershanskaya && venv/bin/python manage.py expire_subscriptions >> /var/log/vershanskaya-cron.log 2>&1

# Раз в неделю добавлять окна для записи на две недели вперёд
0 4 * * 1 cd /srv/vershanskaya && venv/bin/python manage.py generate_slots --days 14
```

На обычном хостинге Beget cron настраивается в панели, путь к Python свой:
`~/site/venv/bin/python ~/site/manage.py expire_subscriptions`.

---

## Что настроить после первого запуска

1. **Админка → Профиль сайта** — портрет и тексты первого экрана.
2. **Админка → Отзывы, Частые вопросы** — заменить демо-контент на реальный.
3. **`.env`** — ключи эквайринга (`YOOKASSA_*`) и Telegram-бота. Пока их нет,
   оплата подтверждается вручную в админке, а уведомления пишутся в лог.
4. **Вебхук в личном кабинете ЮKassa** — адрес `https://ваш-домен/webhook/`.
5. Проверить, что `https://ваш-домен/protected_media/` недоступен.

---

## Обновление

```bash
cd /srv/vershanskaya && ./deploy/update.sh
```

Скрипт забирает изменения, ставит зависимости, применяет миграции, собирает
статику, прогоняет `check --deploy` и перезапускает приложение. Останавливается
на первой ошибке.
