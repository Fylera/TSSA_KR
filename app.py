import json
import re
import base64
import sqlite3
import os
from io import BytesIO
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask, render_template, request
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# ========== БАЗА ДАННЫХ ==========
DB_FILE = 'vacancies.db'


def init_db():
    """Создаёт таблицу и заполняет из JSON, если база пустая"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Сначала создаём таблицу (если её нет)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vacancies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            category_assigned TEXT,
            employer TEXT,
            url TEXT,
            vacancy_text TEXT,
            similarity REAL DEFAULT 0
        )
    ''')

    # Теперь проверяем, есть ли данные
    cursor.execute("SELECT COUNT(*) FROM vacancies")
    count = cursor.fetchone()[0]

    if count > 0:
        print(f"✅ База уже заполнена: {count} вакансий")
        conn.close()
        return

    print("📦 Загружаю JSON в базу данных...")

    # Загружаем JSON
    with open('filtered_vacancies.json', 'r', encoding='utf-8') as f:
        all_vacancies = json.load(f)

    for v in all_vacancies:
        # Предобработка текста
        parts = [
            v.get('name', ''),
            v.get('description', ''),
            v.get('category_assigned', ''),
            v.get('employer', '')
        ]
        text = ' '.join(parts)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip().lower()

        cursor.execute('''
            INSERT INTO vacancies (name, description, category_assigned, employer, url, vacancy_text)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            v.get('name', ''),
            v.get('description', ''),
            v.get('category_assigned', ''),
            v.get('employer', ''),
            v.get('url', ''),
            text
        ))

    conn.commit()
    print(f"✅ Загружено {len(all_vacancies)} вакансий в базу")
    conn.close()


def get_all_vacancies():
    """Возвращает список всех вакансий из БД"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, description, category_assigned, employer, url, vacancy_text FROM vacancies')
    rows = cursor.fetchall()
    conn.close()

    vacancies = []
    for row in rows:
        vacancies.append({
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'category_assigned': row[3],
            'employer': row[4],
            'url': row[5],
            'vacancy_text': row[6]
        })
    return vacancies


def update_similarity(vacancy_id, similarity):
    """Обновляет коэффициент схожести в БД"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE vacancies SET similarity = ? WHERE id = ?', (similarity, vacancy_id))
    conn.commit()
    conn.close()


def get_sorted_vacancies(threshold=0.25):
    """Возвращает вакансии, отсортированные по схожести"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, description, category_assigned, employer, url, similarity 
        FROM vacancies 
        WHERE similarity >= ?
        ORDER BY similarity DESC
    ''', (threshold,))
    rows = cursor.fetchall()
    conn.close()

    vacancies = []
    for row in rows:
        vacancies.append({
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'category_assigned': row[3],
            'employer': row[4],
            'url': row[5],
            'similarity': row[6]
        })
    return vacancies


# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ (загружаются 1 раз) ==========
# Используем флаг, чтобы предотвратить двойную загрузку при debug=True
_initialized = False


def initialize_app():
    global _initialized, all_vacancies, vacancy_texts, model, vacancy_embeddings

    if _initialized:
        return

    print("🚀 Инициализация приложения...")

    # База данных
    init_db()
    all_vacancies = get_all_vacancies()
    vacancy_texts = [v['vacancy_text'] for v in all_vacancies]

    # Модель
    print("Загрузка модели для схожести текстов...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    vacancy_embeddings = model.encode(vacancy_texts, show_progress_bar=False)

    _initialized = True
    print("✅ Инициализация завершена!")


# ---------- кэш для деталей вакансий ----------
CACHE_FILE = 'vacancy_details_cache.json'


def load_cache():
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_cache(cache):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


cache = load_cache()


# ---------- парсинг страницы через Playwright ----------
def fetch_vacancy_details_playwright(url, cache):
    if url in cache:
        return cache[url]['salary'], cache[url]['experience']
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until='networkidle')
            try:
                page.wait_for_selector('[data-qa="vacancy-salary-compensation-type-net"]', timeout=10000)
            except:
                page.wait_for_selector('[data-qa="vacancy-salary"]', timeout=10000)
            salary_elem = page.query_selector('[data-qa="vacancy-salary-compensation-type-net"]')
            if not salary_elem:
                salary_elem = page.query_selector('[data-qa="vacancy-salary"]')
            salary_text = salary_elem.inner_text().strip() if salary_elem else "не указана"
            exp_elem = page.query_selector('[data-qa="vacancy-experience"]')
            experience_text = exp_elem.inner_text().strip() if exp_elem else "не указан"
            browser.close()
            cache[url] = {'salary': salary_text, 'experience': experience_text}
            return salary_text, experience_text
    except Exception as e:
        print(f"Ошибка парсинга {url}: {e}")
        cache[url] = {'salary': 'ошибка парсинга', 'experience': 'ошибка парсинга'}
        return cache[url]['salary'], cache[url]['experience']


# ---------- форматирование зарплаты + валюта ----------
def parse_salary_range(salary_str: str) -> str:
    if not salary_str or salary_str == "не указана" or "ошибка" in salary_str.lower():
        return salary_str
    currency = "₽"
    lower = salary_str.lower()
    if "usd" in lower or "$" in salary_str:
        currency = "$"
    elif "eur" in lower or "€" in salary_str:
        currency = "€"
    elif "kzt" in lower or "тг" in lower:
        currency = "₸"
    clean = salary_str.replace('\xa0', ' ').replace(' ', ' ')
    numbers = re.findall(r'(\d[\d\s]*\d)', clean)
    if not numbers:
        return salary_str
    nums = [int(n.replace(' ', '')) for n in numbers]
    if len(nums) == 1:
        if re.search(r'от\s*\d', clean, re.IGNORECASE):
            return f"от {nums[0]:,} {currency}".replace(',', ' ')
        elif re.search(r'до\s*\d', clean, re.IGNORECASE):
            return f"до {nums[0]:,} {currency}".replace(',', ' ')
        else:
            return f"{nums[0]:,} {currency}".replace(',', ' ')
    elif len(nums) >= 2:
        return f"{nums[0]:,} – {nums[1]:,} {currency}".replace(',', ' ')
    return salary_str


def extract_experience_from_desc(text):
    pat = r'опыт(?: работы)?\s+от\s+(\d+(?:\.\d+)?)\s*лет'
    match = re.search(pat, text, re.IGNORECASE)
    if match:
        return f"от {match.group(1)} лет"
    return "не указан"


# ---------- подсчёт топ-10 технологий ----------
tech_keywords = [
    'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'go', 'rust',
    'sql', 'postgresql', 'mysql', 'mongodb', 'redis', 'kafka', 'docker',
    'kubernetes', 'linux', 'windows', 'git', 'jenkins', 'selenium',
    'pytest', 'junit', 'react', 'angular', 'vue', 'flask', 'django',
    'spring', 'node.js', 'fastapi', 'rest', 'api', 'golang', 'playwright'
]


def get_tech_stats():
    """Считает топ технологий из БД"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT vacancy_text FROM vacancies')
    rows = cursor.fetchall()
    conn.close()

    tech_counts = {tech: 0 for tech in tech_keywords}
    for row in rows:
        text_low = row[0].lower()
        for tech in tech_keywords:
            if tech in text_low:
                tech_counts[tech] += 1
    return sorted(tech_counts.items(), key=lambda x: x[1], reverse=True)[:10]


# ---------- основной маршрут ----------
@app.route('/', methods=['GET', 'POST'])
def index():
    global all_vacancies, model, vacancy_embeddings

    user_skills = ""
    show_all = False
    candidate_vacancies = []

    if request.method == 'POST':
        user_skills = request.form.get('skills', '')
        show_all = request.form.get('show_all') == 'on'

        if user_skills.strip():
            user_emb = model.encode([user_skills])
            similarities = cosine_similarity(user_emb, vacancy_embeddings)[0]

            # Обновляем схожесть в БД
            for i, v in enumerate(all_vacancies):
                update_similarity(v['id'], float(similarities[i]))

            # Получаем отфильтрованные вакансии
            threshold = 0 if show_all else 0.25
            candidate_vacancies = get_sorted_vacancies(threshold)
        else:
            candidate_vacancies = get_all_vacancies()
            for v in candidate_vacancies:
                v['similarity'] = 0
    else:
        candidate_vacancies = get_all_vacancies()
        for v in candidate_vacancies:
            v['similarity'] = 0

    # Парсим детали и фильтруем ошибки
    valid_vacancies = []
    for v in candidate_vacancies:
        url = v.get('url')
        if url:
            salary, experience = fetch_vacancy_details_playwright(url, cache)
            v['salary_raw'] = salary
            v['exp_display'] = experience
        else:
            v['salary_raw'] = "не указана"
            v['exp_display'] = extract_experience_from_desc(v.get('description', ''))

        error_phrases = ['ошибка парсинга', 'не удалось загрузить', '403', '404']
        if any(phrase in v['salary_raw'].lower() for phrase in error_phrases):
            continue
        if any(phrase in v['exp_display'].lower() for phrase in error_phrases):
            continue

        v['salary_range'] = parse_salary_range(v['salary_raw'])
        valid_vacancies.append(v)

    save_cache(cache)

    # График
    sorted_tech = get_tech_stats()
    fig, ax = plt.subplots(figsize=(8, 5))
    techs, counts = zip(*sorted_tech)
    ax.barh(techs, counts, color='skyblue')
    ax.set_xlabel('Количество вакансий')
    ax.set_title('Топ-10 востребованных технологий')
    ax.invert_yaxis()
    buf = BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plot_url = base64.b64encode(buf.getvalue()).decode('utf8')
    plt.close(fig)

    return render_template(
        'index.html',
        vacancies=valid_vacancies,
        plot_url=plot_url,
        user_skills=user_skills,
        show_all=show_all,
        total_count=len(all_vacancies),
        filtered_count=len(valid_vacancies)
    )


if __name__ == '__main__':
    # Инициализация ТОЛЬКО при первом запуске (даже при debug=True)
    initialize_app()

    print("=" * 50)
    print(f"💾 База данных: {DB_FILE}")
    print("🌐 Сервер запущен: http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)