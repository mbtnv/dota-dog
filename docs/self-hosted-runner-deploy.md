# CI/CD через GitHub Actions и self-hosted runner

Эта схема использует:

- GitHub-hosted runner для `ruff`, `ty` и `pytest`;
- self-hosted runner на домашнем сервере для запуска того же deploy-процесса, который уже работает вручную;
- существующий git checkout приложения на сервере;
- существующий compose-файл этого checkout;
- `/opt/dota-dog/deploy.env` как небольшой файл с настройками runner.

## Что уже настроено в репозитории

- workflow [`CI/CD`](../.github/workflows/ci-cd.yml);
- deploy на runner с label `prod`;
- использование существующего server-side checkout вместо второй копии репозитория;
- отдельный пример env-файла [`deploy.env.example`](../deploy.env.example).

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

Скопируйте пример файла с настройками deploy:

```bash
cp deploy.env.example /opt/dota-dog/deploy.env
```

Отредактируйте значения:

- `DEPLOY_DIR` как абсолютный путь к существующему checkout, из которого вы уже делаете `git pull`;
- `DEPLOY_BRANCH`, если production идет не из `main`;
- `DEPLOY_COMPOSE_FILE`, если сейчас вы используете не `docker-compose.yml`.

Важно:

- workflow не хранит production secrets и не подменяет ваш рабочий `.env`;
- runner будет использовать тот же каталог проекта и тот же compose-файл, что и текущий ручной деплой.

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

- зайдет в существующий checkout на сервере;
- выполнит `git pull --ff-only`;
- затем выполнит тот же `docker compose up -d --build`, который вы уже используете вручную.

## Полезные команды на сервере

Проверить сервисы:

```bash
cd /path/to/existing/dota-dog
docker compose ps
```

Посмотреть логи:

```bash
cd /path/to/existing/dota-dog
docker compose logs -f bot worker
```

Откатить deploy:

1. Откатите или заревертите проблемный коммит в `main`.
2. Дождитесь следующего запуска workflow `CI/CD`.
3. Runner снова выполнит `git pull` и `docker compose up -d --build` уже из откатанного состояния репозитория.

## Ограничения и замечания

- self-hosted runner на production-сервере фактически имеет высокий уровень доступа, потому что через Docker можно управлять контейнерами и volume;
- не запускайте на этом runner недоверенные workflow;
- не используйте этот runner для `pull_request` job;
- если в server-side checkout есть незакоммиченные изменения, workflow остановится и не будет пытаться их перетереть;
- все production secrets остаются в существующем `.env` вашего server-side checkout.
