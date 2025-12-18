# 🚀 Инструкция по загрузке проекта на GitHub

## Предварительные требования

1. Установите Git: https://git-scm.com/download/win
2. Создайте аккаунт на GitHub: https://github.com
3. Настройте SSH ключ или Personal Access Token

## Шаг 1: Установка Git

После установки Git откройте новый терминал и проверьте:

```bash
git --version
```

## Шаг 2: Настройка Git

```bash
git config --global user.name "Ваше Имя"
git config --global user.email "your.email@example.com"
```

## Шаг 3: Создание репозитория на GitHub

1. Перейдите на https://github.com/new
2. Введите название репозитория: `cupguide`
3. Выберите "Private" или "Public"
4. НЕ добавляйте README, .gitignore или LICENSE (они уже есть)
5. Нажмите "Create repository"

## Шаг 4: Инициализация локального репозитория

Откройте терминал в папке проекта и выполните:

```bash
# Инициализация git
git init

# Добавление файлов
git add .

# Первый коммит
git commit -m "Initial commit: CupGuide - Telegram Bot для поиска футбольных турниров"

# Переименование ветки в main
git branch -M main

# Добавление удаленного репозитория (замените YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/cupguide.git

# Отправка на GitHub
git push -u origin main
```

## Шаг 5: Проверка

После выполнения команд:
1. Перейдите на страницу вашего репозитория на GitHub
2. Убедитесь, что все файлы загружены
3. Проверьте, что .env файлы НЕ загружены (они в .gitignore)

## Структура репозитория

После загрузки репозиторий будет содержать:

```
cupguide/
├── app/                      # FastAPI Backend
├── telegram_bot/             # Telegram Bot
├── tests/                    # Тесты
├── .env.example              # Пример конфигурации
├── .gitignore                # Игнорируемые файлы
├── ARCHITECTURE.md           # Архитектура проекта
├── CONTRIBUTING.md           # Руководство для контрибьюторов
├── LICENSE                   # MIT лицензия
├── README.md                 # Главная документация
└── requirements.txt          # Python зависимости
```

## Важные замечания

⚠️ **Безопасность:**
- Файлы `.env` НЕ загружаются на GitHub
- Используйте `.env.example` как шаблон
- Никогда не коммитьте API ключи и токены

⚠️ **Данные:**
- Папка `data/` содержит только `.gitkeep`
- JSON файлы с данными игнорируются
- Сессии Telegram также игнорируются

## Обновление репозитория

После внесения изменений:

```bash
git add .
git commit -m "описание изменений"
git push
```

## Клонирование на другой машине

```bash
git clone https://github.com/YOUR_USERNAME/cupguide.git
cd cupguide
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Отредактируйте .env файл
```

## Полезные команды Git

```bash
# Статус изменений
git status

# История коммитов
git log --oneline

# Отмена изменений в файле
git checkout -- filename

# Создание ветки
git checkout -b feature/new-feature

# Слияние ветки
git merge feature/new-feature
```

---

После загрузки на GitHub, удалите этот файл или добавьте его в .gitignore.
