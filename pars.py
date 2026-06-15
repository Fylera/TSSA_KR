import json
import requests
import re
from bs4 import BeautifulSoup
import time
from tqdm import tqdm


# 1. СНАЧАЛА объявляем функцию
def parse_vacancy(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Зарплата
        salary_span = soup.find('span', {
            'data-qa': ['vacancy-salary-compensation-type-gross', 'vacancy-salary-compensation-type-net']})
        salary = 0
        if salary_span:
            nums = re.findall(r'\d+', salary_span.text.replace('\xa0', '').replace(' ', ''))
            if nums: salary = sum(map(int, nums)) / len(nums)

        if salary == 0: return None

        name = soup.find('h1', {'data-qa': 'vacancy-title'}).text
        skills = [skill.text for skill in soup.find_all('span', {'data-qa': 'bloko-tag__text'})]

        return {"Name": name, "Salary": salary, "Skills": skills}
    except:
        return None


# 2. ПОТОМ пишем основной цикл
with open('filtered_vacancies.json', 'r', encoding='utf-8') as f:
    vacancies = json.load(f)

cleaned_data = []

# Теперь Python знает, что такое parse_vacancy, потому что она выше
for v in tqdm(vacancies, desc="Парсинг вакансий", unit="вак"):
    url = v.get('url')
    if url:
        result = parse_vacancy(url)
        if result:
            cleaned_data.append(result)
        time.sleep(0.5)

with open('processed_vacancies.json', 'w', encoding='utf-8') as f:
    json.dump(cleaned_data, f, ensure_ascii=False, indent=4)