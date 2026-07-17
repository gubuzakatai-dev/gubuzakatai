# SecondBrain

Персональный Telegram-бот для фиксации мыслей и задач. Поведение первой версии описано в `docs/`, а порядок реализации — в `SecondBrain_Development_Checklist.md`.

## Подготовка Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

В `.env` нужно указать токен, полученный у BotFather, и числовой Telegram ID единственного разрешённого пользователя.

Для распознавания Telegram voice-сообщений укажите `DEEPGRAM_API_KEY`. Если ключ не задан или
Deepgram недоступен, бот продолжит принимать текст, а на voice-сообщения ответит просьбой
отправить текстом.

## Запуск

```powershell
python -m secondbrain
```

Рабочие данные и секреты хранятся только локально и исключены из Git.
