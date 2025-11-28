# 🤖 Telegram Media Downloader Bot (Stable)

Бот для скачивания видео и аудио с YouTube, TikTok, Instagram, SoundCloud и Twitch.
Поддерживает Inline-режим, Last.fm, куки пользователей и локальный сервер Telegram API.

## 📋 Требования
- OS: Windows 10/11 или Linux (Ubuntu/Debian)
- Python 3.14.0
- Docker Desktop (для загрузки файлов > 50 МБ)
- Git
- FFmpeg

---

## 🚀 Установка с нуля

### 1. Подготовка системы (Windows)
1.  Установи **Python 3.x**: [python.org](https://www.python.org/) (Не забудь галочку "Add to PATH").
2.  Установи **Git**: [git-scm.com](https://git-scm.com/).
3.  Установи **Docker Desktop**: [docker.com](https://www.docker.com/) (Потребуется WSL 2).
4.  Установи **FFmpeg**:
    * Скачай архив с [gyan.dev](https://www.gyan.dev/ffmpeg/builds/).
    * Распакуй, добавь путь к папке `bin` в переменные среды Windows (PATH).
    * Проверка: в терминале `ffmpeg -version`.

### 2. Скачивание проекта
Открой терминал (PowerShell/CMD) в папке, где будет жить бот:
```bash
git clone [https://github.com/ch4rov/TelegramBot.git](https://github.com/ch4rov/TelegramBot.git)
cd ch4rov/TelegramBot