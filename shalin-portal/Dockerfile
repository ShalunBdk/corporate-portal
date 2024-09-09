FROM python:3.9

WORKDIR /shalin-portal

COPY requirements.txt /shalin-portal
RUN pip3 install --upgrade pip -r requirements.txt

COPY . /shalin-portal

# Установка cron
RUN apt-get update && apt-get install -y cron

# Добавить задание в cron для запуска скрипта каждые 6 часов
RUN echo "0 */6 * * * python /shalin-portal/ADconnect.py" > /etc/cron.d/adconnect-cron

# Настройка прав для cron
RUN chmod 0644 /etc/cron.d/adconnect-cron

# Добавление задания cron
RUN crontab /etc/cron.d/adconnect-cron

# Открытие порта 80
EXPOSE 80

# Запуск cron и сервера Flask
CMD cron && python app.py