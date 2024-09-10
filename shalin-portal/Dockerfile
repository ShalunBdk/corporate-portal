# Используем базовый образ Python
FROM python:3.9

# Устанавливаем рабочий каталог
WORKDIR /shalin-portal

# Копируем файл зависимостей и устанавливаем их
COPY requirements.txt /shalin-portal/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Копируем все файлы проекта в рабочий каталог
COPY . /shalin-portal/

# Устанавливаем cron
RUN apt-get update && apt-get install -y cron

# Добавляем задание cron для запуска скрипта каждые 6 часов
RUN echo "0 */6 * * * python /shalin-portal/shalin-portal/ADConnect.py >> /var/log/adconnect.log 2>&1" > /etc/cron.d/adconnect-cron

# Настраиваем права для cron и добавляем его задание
RUN chmod 0644 /etc/cron.d/adconnect-cron && crontab /etc/cron.d/adconnect-cron

# Открываем порт 80
EXPOSE 80

# Запускаем cron и Flask приложение
CMD ["sh", "-c", "cron && python /shalin-portal/shalin-portal/app.py"]
