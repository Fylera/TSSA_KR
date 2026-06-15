FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем JSON с вакансиями
COPY filtered_vacancies.json .

# Копируем всё остальное
COPY . .

EXPOSE 5000

CMD ["python", "app.py"]