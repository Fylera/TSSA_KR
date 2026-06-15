import json
from collections import Counter

# Загружаем файл с "логичными" скиллами
with open('giant_skills_db.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 1. Собираем все навыки в одну корзину
all_skills = []
for entry in data:
    all_skills.extend([s.lower() for s in entry['Skills']])

# 2. Обобщаем (считаем частоту)
# Counter сам сгруппирует похожие строки и посчитает их
counts = Counter(all_skills)

# 3. Выводим результат в удобном виде (Топ требований)
print(f"{'Навык':<20} | {'Количество упоминаний':<20}")
print("-" * 45)
for skill, count in counts.most_common(20):
    print(f"{skill:<20} | {count:<20}")

# 4. Сохраняем итоговую статистику для отчета
summary = dict(counts.most_common())
with open('giant_skills_db.json', 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=4)