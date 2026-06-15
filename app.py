import json
import re
import base64
import sqlite3
import os
from io import BytesIO
from collections import Counter
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask, render_template, request, jsonify
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from playwright.sync_api import sync_playwright

# ========== ИНИЦИАЛИЗАЦИЯ FLASK ==========
app = Flask(__name__)

# ========== КОНСТАНТЫ ==========
DB_FILE = 'vacancies.db'
CACHE_FILE = 'vacancy_details_cache.json'

tech_keywords = [
    'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'go', 'rust',
    'sql', 'postgresql', 'mysql', 'mongodb', 'redis', 'kafka', 'docker',
    'kubernetes', 'linux', 'windows', 'git', 'jenkins', 'selenium',
    'pytest', 'junit', 'react', 'angular', 'vue', 'flask', 'django',
    'spring', 'node.js', 'fastapi', 'rest', 'api', 'golang', 'playwright'
]

PROFESSION_KEYWORDS = {
    'QA': ['тестировщик', 'qa', 'quality assurance', 'тестирование', 'test engineer', 'manual', 'automation'],
    'Developer': ['разработчик', 'developer', 'программист', 'programmer', 'backend', 'frontend', 'fullstack'],
    'Analyst': ['аналитик', 'analyst', 'business analyst', 'system analyst'],
    'DevOps': ['devops', 'системный администратор', 'admin', 'инфраструктура'],
    'Manager': ['менеджер', 'manager', 'project manager', 'pm', 'product manager'],
    'Designer': ['дизайнер', 'designer', 'ui/ux', 'графический дизайнер']
}

# ========== ФУНКЦИИ ДЛЯ АНАЛИЗА ==========

def detect_profession(vacancy_text):
    text_lower = vacancy_text.lower()
    for prof, keywords in PROFESSION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return prof
    return 'Other'


def extract_requirements(description):
    requirements = {
        'skills': [],
        'experience': None,
        'education': None,
        'work_format': None,
        'schedule': None
    }
    text = description.lower() if description else ''
    found_skills = []
    for tech in tech_keywords:
        if tech in text:
            found_skills.append(tech)
    requirements['skills'] = found_skills[:5]
    exp_match = re.search(r'опыт\s+от\s+(\d+)', text)
    if exp_match:
        requirements['experience'] = f"от {exp_match.group(1)} лет"
    if 'удален' in text or 'remote' in text:
        requirements['work_format'] = 'Удаленно'
    elif 'гибрид' in text or 'hybrid' in text:
        requirements['work_format'] = 'Гибрид'
    elif 'офис' in text:
        requirements['work_format'] = 'Офис'
    if 'гибкий' in text or 'flexible' in text:
        requirements['schedule'] = 'Гибкий'
    elif '5/2' in text:
        requirements['schedule'] = '5/2'
    elif '2/2' in text:
        requirements['schedule'] = '2/2'
    return requirements


def get_vacancy_statistics(vacancies):
    stats = {
        'total': len(vacancies),
        'companies': {},
        'professions': {},
        'avg_salary': 0,
        'top_skills': {},
        'salary_distribution': {'low': 0, 'medium': 0, 'high': 0}
    }
    salaries = []
    for v in vacancies:
        employer = v.get('employer', 'Не указана')
        stats['companies'][employer] = stats['companies'].get(employer, 0) + 1
        text = v.get('vacancy_text', '')
        prof = detect_profession(text)
        stats['professions'][prof] = stats['professions'].get(prof, 0) + 1
        for tech in tech_keywords:
            if tech in text:
                stats['top_skills'][tech] = stats['top_skills'].get(tech, 0) + 1
        salary_raw = v.get('salary_raw', '')
        salary_match = re.search(r'(\d+)[\s\-]*(\d+)?', salary_raw)
        if salary_match:
            if salary_match.group(2):
                salary = (int(salary_match.group(1)) + int(salary_match.group(2))) / 2
            else:
                salary = int(salary_match.group(1))
            salaries.append(salary)
    if salaries:
        stats['avg_salary'] = int(sum(salaries) / len(salaries))
        for s in salaries:
            if s < 80000:
                stats['salary_distribution']['low'] += 1
            elif s < 150000:
                stats['salary_distribution']['medium'] += 1
            else:
                stats['salary_distribution']['high'] += 1
    stats['top_skills'] = dict(sorted(stats['top_skills'].items(), key=lambda x: x[1], reverse=True)[:5])
    stats['top_companies'] = dict(sorted(stats['companies'].items(), key=lambda x: x[1], reverse=True)[:5])
    return stats


def get_typical_vacancy(vacancies, profession):
    prof_vacancies = [v for v in vacancies if detect_profession(v.get('vacancy_text', '')) == profession]
    if not prof_vacancies:
        return None
    avg_len = sum(len(v.get('description', '')) for v in prof_vacancies) / len(prof_vacancies)
    return min(prof_vacancies, key=lambda v: abs(len(v.get('description', '')) - avg_len))


def get_generalized_requirements(vacancies, profession):
    prof_vacancies = [v for v in vacancies if detect_profession(v.get('vacancy_text', '')) == profession]
    if not prof_vacancies:
        return {}
    all_skills, experiences, formats = [], [], []
    for v in prof_vacancies:
        req = extract_requirements(v.get('description', ''))
        all_skills.extend(req['skills'])
        if req['experience']:
            experiences.append(req['experience'])
        if req['work_format']:
            formats.append(req['work_format'])
    skill_counts = Counter(all_skills)
    return {
        'profession': profession,
        'count': len(prof_vacancies),
        'top_skills': [s for s, c in skill_counts.most_common(5)],
        'typical_experience': Counter(experiences).most_common(1)[0][0] if experiences else 'не указан',
        'common_format': Counter(formats).most_common(1)[0][0] if formats else 'не указан'
    }


# ========== БАЗА ДАННЫХ ==========

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
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
    cursor.execute("SELECT COUNT(*) FROM vacancies")
    count = cursor.fetchone()[0]
    if count > 0:
        print(f"✅ База уже заполнена: {count} вакансий")
        conn.close()
        return
    print("📦 Загружаю JSON в базу данных...")
    with open('filtered_vacancies.json', 'r', encoding='utf-8') as f:
        all_vacancies = json.load(f)
    for v in all_vacancies:
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
        ''', (v.get('name', ''), v.get('description', ''), v.get('category_assigned', ''),
              v.get('employer', ''), v.get('url', ''), text))
    conn.commit()
    print(f"✅ Загружено {len(all_vacancies)} вакансий в базу")
    conn.close()


def get_all_vacancies():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, description, category_assigned, employer, url, vacancy_text FROM vacancies')
    rows = cursor.fetchall()
    conn.close()
    return [{'id': r[0], 'name': r[1], 'description': r[2], 'category_assigned': r[3],
             'employer': r[4], 'url': r[5], 'vacancy_text': r[6]} for r in rows]


def update_similarity(vacancy_id, similarity):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE vacancies SET similarity = ? WHERE id = ?', (similarity, vacancy_id))
    conn.commit()
    conn.close()


def get_sorted_vacancies(threshold=0.25):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, description, category_assigned, employer, url, similarity 
        FROM vacancies WHERE similarity >= ? ORDER BY similarity DESC
    ''', (threshold,))
    rows = cursor.fetchall()
    conn.close()
    return [{'id': r[0], 'name': r[1], 'description': r[2], 'category_assigned': r[3],
             'employer': r[4], 'url': r[5], 'similarity': r[6]} for r in rows]


def get_tech_stats():
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


# ========== КЭШ И ПАРСИНГ ==========

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


def fetch_vacancy_details_playwright(url):
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


# ========== API МАРШРУТЫ ==========

@app.route('/api/statistics')
def api_statistics():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, description, employer, vacancy_text FROM vacancies')
    rows = cursor.fetchall()
    conn.close()
    vacancies = [{'id': r[0], 'name': r[1], 'description': r[2], 'employer': r[3],
                  'vacancy_text': r[4], 'salary_raw': ''} for r in rows]
    return jsonify(get_vacancy_statistics(vacancies))


@app.route('/api/professions')
def api_professions():
    return jsonify(list(PROFESSION_KEYWORDS.keys()))


@app.route('/api/typical/<profession>')
def api_typical(profession):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, description, employer, vacancy_text FROM vacancies')
    rows = cursor.fetchall()
    conn.close()
    vacancies = [{'id': r[0], 'name': r[1], 'description': r[2], 'employer': r[3], 'vacancy_text': r[4]} for r in rows]
    typical = get_typical_vacancy(vacancies, profession)
    if typical:
        return jsonify(typical)
    return jsonify({'error': 'No vacancies found'}), 404


@app.route('/api/generalized/<profession>')
def api_generalized(profession):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, description, employer, vacancy_text FROM vacancies')
    rows = cursor.fetchall()
    conn.close()
    vacancies = [{'id': r[0], 'name': r[1], 'description': r[2], 'employer': r[3], 'vacancy_text': r[4]} for r in rows]
    return jsonify(get_generalized_requirements(vacancies, profession))


# ========== ОСНОВНОЙ МАРШРУТ ==========

@app.route('/', methods=['GET', 'POST'])
def index():
    global all_vacancies, model, vacancy_embeddings
    user_skills = ""
    show_all = False
    if request.method == 'POST':
        user_skills = request.form.get('skills', '')
        show_all = request.form.get('show_all') == 'on'
        if user_skills.strip():
            user_emb = model.encode([user_skills])
            similarities = cosine_similarity(user_emb, vacancy_embeddings)[0]
            for i, v in enumerate(all_vacancies):
                update_similarity(v['id'], float(similarities[i]))
            candidate_vacancies = get_sorted_vacancies(0 if show_all else 0.25)
        else:
            candidate_vacancies = get_all_vacancies()
            for v in candidate_vacancies:
                v['similarity'] = 0
    else:
        candidate_vacancies = get_all_vacancies()
        for v in candidate_vacancies:
            v['similarity'] = 0
    valid_vacancies = []
    for v in candidate_vacancies:
        url = v.get('url')
        if url:
            salary, experience = fetch_vacancy_details_playwright(url)
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
    return render_template('index.html', vacancies=valid_vacancies, plot_url=plot_url,
                          user_skills=user_skills, show_all=show_all,
                          total_count=len(all_vacancies), filtered_count=len(valid_vacancies))


# ========== ЗАПУСК ==========

_initialized = False


def initialize_app():
    global _initialized, all_vacancies, vacancy_texts, model, vacancy_embeddings
    if _initialized:
        return
    print("🚀 Инициализация приложения...")
    init_db()
    all_vacancies = get_all_vacancies()
    vacancy_texts = [v['vacancy_text'] for v in all_vacancies]
    print("Загрузка модели для схожести текстов...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    vacancy_embeddings = model.encode(vacancy_texts, show_progress_bar=False)
    _initialized = True
    print("✅ Инициализация завершена!")


if __name__ == '__main__':
    initialize_app()
    print("=" * 50)
    print(f"💾 База данных: {DB_FILE}")
    print("🌐 Сервер запущен: http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)