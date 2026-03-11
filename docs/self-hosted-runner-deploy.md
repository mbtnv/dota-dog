# CI/CD через GitHub Actions и self-hosted runner

Эта схема использует:

- GitHub-hosted runner для `ruff`, `ty` и `pytest`;
- self-hosted runner на домашнем сервере для сборки Docker image и deploy;
- [`docker-compose.prod.yml`](../docker-compose.prod.yml) как production compose-файл;
- `/opt/dota-dog/stack.env` как production env file на сервере.

## Что уже настроено в репозитории

- workflow [`CI/CD`](../.github/workflows/ci-cd.yml);
- deploy на runner с label `prod`;
- production compose-файл с локальной сборкой образа на сервере;
- отдельный пример env-файла [`stack.prod.env.example`](../stack.prod.env.example).

## Что нужно сделать в GitHub

1. Убедиться, что основной production branch называется `main`.
2. В `Settings -> Branches` защитить `main` и требовать успешный job `CI`.
3. В `Settings -> Environments` создать environment `production`.
4. По желанию включить manual approval для `production`, чтобы каждый deploy требовал подтверждения.
5. Убедиться, что self-hosted runner зарегистрирован именно для этого репозитория или для нужной organization.

## Что нужно сделать на сервере

### 1. Подготовить Docker

Установите Docker Engine и Docker Compose plugin.

Проверьте:

```bash
docker --version
docker compose version
```

### 2. Создать отдельного пользователя для runner

Пример:

```bash
sudo useradd --create-home --shell /bin/bash actions-runner
sudo usermod -aG docker actions-runner
```

После добавления в группу `docker` перелогиньтесь этим пользователем или перезапустите сервер.

### 3. Подготовить директорию для production env

```bash
sudo mkdir -p /opt/dota-dog
sudo chown actions-runner:actions-runner /opt/dota-dog
```

Скопируйте пример env-файла:

```bash
cp stack.prod.env.example /opt/dota-dog/stack.env
```

Отредактируйте минимум:

- `BOT_TOKEN`;
- `POSTGRES_PASSWORD`;
- при необходимости остальные настройки.

### 4. Установить self-hosted runner

На GitHub откройте `Settings -> Actions -> Runners -> New self-hosted runner`.

Для Linux GitHub покажет актуальные команды установки. Выполняйте их под пользователем `actions-runner`.

Важно при регистрации:

- добавьте label `prod`;
- оставьте `self-hosted` и `linux`;
- привяжите runner именно к этому репозиторию или к нужной organization.

### 5. Установить runner как systemd service

В каталоге runner выполните команду установки сервиса, которую показывает GitHub, обычно это:

```bash
sudo ./svc.sh install actions-runner
sudo ./svc.sh start
```

Проверьте статус:

```bash
sudo ./svc.sh status
```

### 6. Проверить доступ runner к Docker

Под пользователем `actions-runner` команда должна работать без `sudo`:

```bash
docker ps
```

Если не работает, проверьте membership в группе `docker`.

## Первый deploy

1. Закоммитьте изменения в репозиторий.
2. Запушьте их в ветку `main`.
3. Дождитесь workflow `CI/CD`.
4. После успешного `CI` job `Deploy to production` выполнится на домашнем сервере.

На первом запуске workflow:

- соберет Docker image на сервере;
- поднимет `db`;
- прогонит Alembic миграции;
- запустит `bot` и `worker`.

## Полезные команды на сервере

Проверить сервисы:

```bash
cd /path/to/runner/_work/<repo>/<repo>
docker compose -f docker-compose.prod.yml --env-file /opt/dota-dog/stack.env ps
```

Посмотреть логи:

```bash
cd /path/to/runner/_work/<repo>/<repo>
docker compose -f docker-compose.prod.yml --env-file /opt/dota-dog/stack.env logs -f bot worker
```

Откатить deploy:

1. Откатите или заревертите проблемный коммит в `main`.
2. Дождитесь следующего запуска workflow `CI/CD`.
3. Runner заново соберет образ на сервере уже из предыдущего состояния кода и перезапустит сервисы.

## Ограничения и замечания

- self-hosted runner на production-сервере фактически имеет высокий уровень доступа, потому что через Docker можно управлять контейнерами и volume;
- не запускайте на этом runner недоверенные workflow;
- не используйте этот runner для `pull_request` job;
- все production secrets остаются только на сервере в `/opt/dota-dog/stack.env`.
