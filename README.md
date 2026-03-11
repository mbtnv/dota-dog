# Dota Dog v2

Telegram-бот и `worker` для отслеживания матчей Dota 2 в группах и forum topics.

Сервис хранит конфигурацию и историю матчей в Postgres, отправляет realtime-уведомления о новых играх и собирает отчеты за день, неделю и месяц.

## Что умеет бот

- отслеживать игроков по `account_id` или ссылке на профиль;
- вести отдельный список игроков для каждого `chat_id` + `message_thread_id`;
- отправлять уведомления о новых матчах в тот же topic;
- строить отчеты по всем игрокам topic или по одному игроку;
- показывать последние матчи и мини-лидерборд;
- делать ручной `resync` истории матчей;
- импортировать legacy-список игроков из `old_code/players.json`.

## Как это работает

В проекте два процесса:

- `dota_dog.app` обрабатывает Telegram-команды.
- `dota_dog.worker` по расписанию опрашивает OpenDota, сохраняет матчи в БД и отправляет сообщения.

Логика `worker`:

1. Раз в `POLL_INTERVAL_MINUTES` забирает `recentMatches` для отслеживаемых игроков.
2. Сохраняет новые матчи в Postgres.
3. Отправляет realtime-уведомления по новым матчам в нужный topic.
4. Проверяет, завершился ли предыдущий день, неделя или месяц в таймзоне topic, и при необходимости отправляет автоотчет.

Важно:

- при первом опросе после `/track` бот только фиксирует текущую точку `last_seen_match_id`, чтобы не заспамить старыми матчами;
- для добора истории за прошлые дни используется `/resync`;
- команды изменения состояния доступны только админам чата или пользователям из `ALLOWED_TELEGRAM_USER_IDS`;
- команды работают только в группе, супергруппе или forum topic, не в личке.

## Как пользоваться ботом

1. Создайте Telegram-бота через BotFather и получите `BOT_TOKEN`.
2. Заполните `.env`.
3. Запустите `bot`, `worker` и Postgres.
4. Добавьте бота в нужную группу или forum supergroup.
5. Выполняйте команды прямо в нужном topic.

Типовой сценарий:

```text
/help
/limits
/track 123456789 mid
/track https://www.dotabuff.com/players/987654321 carry
/players
/status
/report week
/last 5 mid
```

## Основные команды

| Команда | Что делает |
| --- | --- |
| `/help` | Показывает список доступных команд и краткую справку по ним. |
| `/limits` | Показывает текущие лимиты запросов к OpenDota API. |
| `/track <account_id\|profile_url> [alias]` | Добавляет игрока в текущий chat/topic. |
| `/untrack <account_id\|alias>` | Удаляет игрока из текущего chat/topic. |
| `/players` | Показывает список отслеживаемых игроков в текущем topic. |
| `/status` | Показывает расширенный статус topic: идентификаторы чата/topic, конфиг опроса, runtime последнего прохода, сводку по матчам в БД, последние отчеты и список игроков. |
| `/report <day\|week\|month> [account_id\|alias]` | Строит отчет по всем игрокам topic или по одному игроку. |

## Дополнительные команды

| Команда | Что делает |
| --- | --- |
| `/last [n] [account_id\|alias]` | Показывает последние матчи из БД. По умолчанию `n = 5`, максимум `10`. |
| `/leaders <day\|week\|month>` | Показывает мини-лидерборд по винрейту и победам за период. |
| `/set_timezone <TZ>` | Меняет таймзону topic, например `Europe/Moscow`. |
| `/pause` | Ставит realtime-уведомления topic на паузу. |
| `/resume` | Возобновляет realtime-уведомления topic. |
| `/resync [days] [account_id\|alias]` | Добирает историю матчей из OpenDota за последние `N` дней. По умолчанию `7`, максимум `365`. |

## Быстрый старт

### Docker Compose

1. Скопируйте пример окружения:

```bash
cp .env.example .env
```

2. Заполните минимум:

- `BOT_TOKEN`
- `DATABASE_URL`

Для `docker compose` можно оставить значение из примера:

```env
DATABASE_URL=postgresql+asyncpg://dota_dog:dota_dog@db:5432/dota_dog
```

3. Поднимите сервисы:

```bash
docker compose up --build
```

Будут запущены:

- `db` - Postgres;
- `migrate` - применение миграций;
- `bot` - Telegram bot;
- `worker` - фоновые задачи.

### Portainer

Для деплоя через Portainer используйте:

- [`docker-compose.portainer.yml`](docker-compose.portainer.yml) как stack file;
- [`stack.env`](stack.env) как набор переменных окружения для stack.

Что нужно отредактировать в `stack.env` перед деплоем:

- `BOT_TOKEN`
- `POSTGRES_PASSWORD`
- при необходимости `DEFAULT_TIMEZONE`, `POLL_INTERVAL_MINUTES`, `ALLOWED_TELEGRAM_USER_IDS`

Важно:

- `DATABASE_URL` в `stack.env` не нужен, в `docker-compose.portainer.yml` он собирается автоматически из `POSTGRES_DB`, `POSTGRES_USER` и `POSTGRES_PASSWORD`;
- `OPENDOTA_API_KEY` можно оставить пустым, если ключ не используется.

### GitHub Actions + self-hosted runner

Для автоматического деплоя на домашний сервер используйте:

- workflow [`CI/CD`](.github/workflows/ci-cd.yml) для проверок на GitHub и deploy через self-hosted runner;
- [`deploy.env.example`](deploy.env.example) как шаблон файла с путями к существующему checkout на сервере.

Подробная инструкция по настройке GitHub, runner и сервера есть в [`docs/self-hosted-runner-deploy.md`](docs/self-hosted-runner-deploy.md).

### Локальный запуск без Docker

Если Postgres работает локально, поменяйте `DATABASE_URL`, например:

```env
DATABASE_URL=postgresql+asyncpg://dota_dog:dota_dog@localhost:5432/dota_dog
```

Дальше:

```bash
uv sync
uv run alembic upgrade head
uv run python -m dota_dog.app
uv run python -m dota_dog.worker
```

## Переменные окружения

Обязательные:

- `BOT_TOKEN` - токен Telegram-бота.
- `DATABASE_URL` - строка подключения к Postgres.

Основные опции:

- `POLL_INTERVAL_MINUTES` - интервал опроса OpenDota.
- `DEFAULT_TIMEZONE` - таймзона для новых topic.
- `ALLOWED_TELEGRAM_USER_IDS` - список Telegram user id через запятую, которым разрешено управлять ботом.
- `TELEGRAM_ADMIN_CHECK_ENABLED` - если `true`, управляющие команды доступны администраторам чата.
- `OPENDOTA_API_KEY` - optional API key для OpenDota.
- `LOG_LEVEL` - уровень логирования.

Полный пример есть в [.env.example](.env.example).

## Импорт legacy-данных

Чтобы перенести список игроков из `old_code/players.json`:

```bash
uv run python -m dota_dog.import_legacy --chat-id -100123 --thread-id 42
```

Опции:

- `--path` - путь к legacy JSON, по умолчанию `old_code/players.json`;
- `--chat-id` - Telegram chat id, обязателен;
- `--thread-id` - id topic, если используется forum topic;
- `--title` - заголовок topic.

## Команды разработки

```bash
uv sync
uv run alembic upgrade head
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
```
