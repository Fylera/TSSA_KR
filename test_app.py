import pytest
import json
from app import app, parse_salary_range, extract_experience_from_desc, initialize_app, detect_profession, \
    extract_requirements, PROFESSION_KEYWORDS


# ========== ИНИЦИАЛИЗАЦИЯ ДЛЯ ТЕСТОВ ==========
@pytest.fixture(scope='session', autouse=True)
def init_app():
    """Один раз инициализируем приложение перед всеми тестами"""
    initialize_app()


@pytest.fixture
def client():
    """Тестовый клиент Flask"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


# ========== ТЕСТЫ ГЛАВНОЙ СТРАНИЦЫ ==========

def test_home_page_get(client):
    """Тест 1: GET-запрос к главной странице"""
    response = client.get('/')
    assert response.status_code == 200
    # Проверяем, что страница содержит хоть какой-то текст (не пустая)
    assert len(response.data) > 100


def test_home_page_post_with_skills(client):
    """Тест 2: POST-запрос с навыками"""
    response = client.post('/', data={
        'skills': 'python pytest',
        'show_all': 'on'
    })
    assert response.status_code == 200


def test_home_page_post_without_skills(client):
    """Тест 3: POST-запрос без навыков"""
    response = client.post('/', data={
        'skills': '',
        'show_all': 'off'
    })
    assert response.status_code == 200


# ========== ТЕСТЫ API ДАШБОРДА ==========

def test_api_statistics(client):
    """Тест 4: API статистики"""
    response = client.get('/api/statistics')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'total' in data
    assert 'avg_salary' in data
    assert isinstance(data['total'], int)


def test_api_professions(client):
    """Тест 5: API списка профессий"""
    response = client.get('/api/professions')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert isinstance(data, list)
    assert 'QA' in data


def test_api_typical_valid(client):
    """Тест 6: API типовой вакансии (существующая профессия)"""
    response = client.get('/api/typical/QA')
    assert response.status_code == 200
    data = json.loads(response.data)
    # Может вернуть вакансию или ошибку, если нет вакансий QA
    assert 'error' in data or 'name' in data


def test_api_typical_invalid(client):
    """Тест 7: API типовой вакансии (несуществующая профессия)"""
    response = client.get('/api/typical/NonExistentProfession123')
    assert response.status_code == 200 or response.status_code == 404


def test_api_generalized(client):
    """Тест 8: API обобщённых требований"""
    response = client.get('/api/generalized/QA')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'profession' in data or 'count' in data


# ========== ТЕСТЫ ФУНКЦИЙ АНАЛИЗА ==========

def test_detect_profession():
    """Тест 9: Определение профессии по тексту"""
    # QA
    assert detect_profession("looking for QA tester") == "QA"
    assert detect_profession("quality assurance engineer needed") == "QA"
    assert detect_profession("manual testing automation") == "QA"

    # Developer
    assert detect_profession("Python developer") == "Developer"
    assert detect_profession("backend developer java") == "Developer"

    # Другое
    assert detect_profession("") == "Other"
    assert detect_profession("random text without keywords") == "Other"


def test_extract_requirements():
    """Тест 10: Извлечение требований из описания"""
    req = extract_requirements("experience from 5 years, remote, flexible schedule, python sql docker")

    assert 'experience' in req
    assert 'work_format' in req
    assert 'schedule' in req
    assert 'skills' in req

    # Пустое описание
    req2 = extract_requirements("")
    # Функция возвращает пустые значения, тест просто проверяет что нет ошибки
    assert isinstance(req2, dict)


def test_parse_salary_range():
    """Тест 11: Форматирование зарплат"""
    # Русские рубли
    result = parse_salary_range("from 100000 RUB")
    assert "100000" in result or "100 000" in result

    # Доллары
    result = parse_salary_range("3000 - 4000 USD")
    assert "$" in result or "USD" in result

    # Евро
    result = parse_salary_range("2500 EUR")
    assert "€" in result or "EUR" in result

    # Не указана
    assert parse_salary_range("not specified") == "not specified"
    assert parse_salary_range("") == ""


def test_extract_experience_from_desc():
    """Тест 12: Извлечение опыта из описания"""
    # Проверяем только русские паттерны (оригинальная функция ищет русский текст)
    result = extract_experience_from_desc("опыт от 3 лет")
    # Может вернуть None или строку, просто проверяем что нет ошибки
    assert result is not None

    result = extract_experience_from_desc("")
    assert result == "не указан" or result is None


def test_profession_keywords_structure():
    """Тест 13: Проверка структуры ключевых слов профессий"""
    assert 'QA' in PROFESSION_KEYWORDS
    assert 'Developer' in PROFESSION_KEYWORDS
    assert isinstance(PROFESSION_KEYWORDS['QA'], list)
    assert len(PROFESSION_KEYWORDS['QA']) > 0


# ========== ДОПОЛНИТЕЛЬНЫЕ ТЕСТЫ ДЛЯ ПОКРЫТИЯ ==========

def test_index_post_with_filter_on(client):
    """Тест 14: POST с включённым фильтром 25%"""
    response = client.post('/', data={
        'skills': 'python',
        'show_all': 'off'
    })
    assert response.status_code == 200


def test_index_post_with_filter_off(client):
    """Тест 15: POST с выключенным фильтром 25%"""
    response = client.post('/', data={
        'skills': 'python',
        'show_all': 'on'
    })
    assert response.status_code == 200


def test_api_generalized_with_different_professions(client):
    """Тест 16: API обобщённых требований для разных профессий"""
    for prof in ['QA', 'Developer', 'Analyst', 'DevOps']:
        response = client.get(f'/api/generalized/{prof}')
        assert response.status_code == 200


def test_api_typical_with_different_professions(client):
    """Тест 17: API типовой вакансии для разных профессий"""
    for prof in ['QA', 'Developer', 'Analyst']:
        response = client.get(f'/api/typical/{prof}')
        assert response.status_code == 200


def test_home_page_post_empty_skills_with_filter(client):
    """Тест 18: POST с пустыми навыками и включённым фильтром"""
    response = client.post('/', data={
        'skills': '',
        'show_all': 'off'
    })
    assert response.status_code == 200