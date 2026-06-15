# 🚀 Vacancy Analyzer Pro

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0-green.svg)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/Docker-✅-blue.svg)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Tests-Pytest-important.svg)](https://pytest.org/)
[![Coverage](https://img.shields.io/badge/Coverage-85%25-brightgreen.svg)](https://coverage.readthedocs.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 🔍 **Умный поиск вакансий на основе искусственного интеллекта** | Анализируй свои навыки и находи релевантные предложения с hh.ru

## ✨ Особенности

- 🧠 **AI-поиск** — использует `SentenceTransformer` для семантического сравнения навыков с вакансиями
- ⚡ **Молниеносная работа** — кэширование данных в SQLite, повторные запросы выполняются за секунды
- 🐳 **Docker-готовность** — разверни приложение одной командой
- 📊 **Визуализация** — график топ-10 востребованных технологий на рынке
- 💰 **Актуальная информация** — парсинг зарплат и требований с hh.ru в реальном времени
- 🧪 **Высокое покрытие тестами** — более 85% кода покрыто юнит-тестами
- 📱 **Адаптивный интерфейс** — работает на ПК, планшете и телефоне

## 🎯 Что умеет

| Функция | Описание |
|---------|----------|
| 🔎 **Поиск по навыкам** | Введи "Python, SQL, Docker" — получи вакансии с похожими требованиями |
| 🎚 **Фильтр по схожести** | Показывать только вакансии с совпадением ≥25% |
| 💵 **Детали зарплат** | Парсинг актуальных зарплат с конвертацией валют (₽/$/€/₸) |
| 📈 **График технологий** | Анализ рынка: какие скиллы сейчас в топе |
| 💾 **Умное кэширование** | Детали вакансий сохраняются, чтобы не парсить дважды |

## 🚀 Быстрый старт

### 📦 Локальный запуск

```bash
# 1. Клонируй репозиторий
git clone https://github.com/ТВОЙ_ЛОГИН/vacancy-analyzer.git
cd vacancy-analyzer

# 2. Установи зависимости
pip install -r requirements.txt

# 3. Запусти приложение
python app.py

# 4. Открой браузер
http://localhost:5000