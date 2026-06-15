import pytest
import json
from app import app, parse_salary_range, extract_experience_from_desc

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_home_page(client):
    response = client.get('/')
    assert response.status_code == 200

def test_parse_salary_range():
    assert parse_salary_range("от 100 000 ₽") == "от 100 000 ₽"
    assert "USD" in parse_salary_range("3 000 - 4 000 USD")
    assert parse_salary_range("не указана") == "не указана"

def test_experience_extract():
    assert "от 3 лет" in extract_experience_from_desc("опыт от 3 лет")
    assert extract_experience_from_desc("нет опыта") == "не указан"