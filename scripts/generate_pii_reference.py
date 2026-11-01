#!/usr/bin/env python3
"""Еталон для PII-детектора: benchmark-набір, набір-«пастка» і ground_truth.csv.

Запуск:  python scripts/generate_pii_reference.py

Створює (детерміновано, seed 20261031):
  data/pii/benchmark_people.csv  - колонки з PII різних типів (+ кілька не-PII)
  data/pii/traps.csv             - колонки, які ЛИШЕ ВИГЛЯДАЮТЬ як PII («пастки»)
  data/pii/ground_truth.csv      - розмітка колонок усіх чотирьох наборів

Наприкінці перевіряє: розмітку, коректність контрольних сум (ІПН, IBAN, Луна),
що «пастки» не проходять перевірки, і що імена з data/payroll.csv та
data/customers.json є у словниках. Лише стандартна бібліотека Python 3.9+.
"""
import csv
import json
import random
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_datasets as gd  # хелпери ІПН, IBAN, телефонів

SEED = 20261031
ROOT = Path(__file__).resolve().parent.parent
PII = ROOT / "data" / "pii"
DICT = PII / "dictionaries"
N = 80

# Прізвища й імена, яких НЕМАЄ у словниках: детектор не повинен покладатися
# лише на словник (реальні дані містять рідкісні імена).
RARE_SURNAMES = ["Цюпа", "Брусенцов", "Ляшко-Мельник", "Вітрук", "Кернес", "Шпак", "Зубань",
                 "Грицай", "Чепіжко", "Мовчан"]
RARE_FIRST = ["Любослав", "Ярополк", "Ждана", "Зореслава", "Ростик", "Мальва"]

STREETS = ["Шевченка", "Франка", "Лесі Українки", "Грушевського", "Незалежності", "Центральна",
           "Садова", "Лісова", "Миру", "Соборна", "Дорошенка", "Княгині Ольги", "Поштова"]
STREET_TYPES = ["вул.", "вулиця", "просп.", "пров.", "бульв."]
CITIES = gd.CITIES
VILLAGES = ["Гнідин", "Мархалівка", "Чайки", "Вишеньки", "Коцюбинське", "Зазим'я"]
OBLASTS = ["Київська", "Львівська", "Полтавська", "Вінницька", "Одеська", "Харківська"]

# «Пастки»: слова, схожі на імена / прізвища, і числа, схожі на ІПН / картки / IBAN
NAMELIKE_BRANDS = ["Марічка", "Дарина", "Лілея", "Зоряна", "Наталка", "Оксамит", "Ярослава",
                   "Софійка", "Надія", "Любава"]
SURNAMELIKE_WORDS = ["Мороз", "Жук", "Козак", "Гончар", "Швець", "Лис", "Вовк", "Сокіл",
                     "Береза", "Орел"]
NAMELIKE_CITIES = ["Олександрія", "Костянтинівка", "Миколаїв", "Василівка", "Володимир",
                   "Павлоград", "Святогірськ", "Богуслав", "Ромни", "Дружківка", "Маріуполь"]


def luhn_valid(s):
    digits = [int(c) for c in s]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def make_card(rng):
    body = "".join(str(rng.randint(0, 9)) for _ in range(15))
    body = rng.choice(["4", "5"]) + body[1:]            # схоже на Visa / Mastercard
    for check in range(10):
        if luhn_valid(body + str(check)):
            return body + str(check)


def make_non_luhn(rng, n=16):
    while True:
        s = rng.choice(["4", "5"]) + "".join(str(rng.randint(0, 9)) for _ in range(n - 1))
        if not luhn_valid(s):
            return s


def make_non_ipn(rng):
    while True:
        s = f"{rng.randint(10**9, 10**10 - 1)}"
        if not gd.ipn_valid(s):
            return s


def make_non_iban(rng):
    while True:
        s = "UA" + "".join(str(rng.randint(0, 9)) for _ in range(27))
        if not gd.iban_valid(s):
            return s


def read_dict(name):
    return [ln.strip() for ln in (DICT / name).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]


def fmt_card(c, rng):
    return c if rng.random() < 0.5 else " ".join(c[i:i + 4] for i in range(0, 16, 4))


def fmt_phone(p, rng):
    local = p[4:]  # 9 цифр після +380
    return rng.choice([
        p,                                            # +380501234567
        "380" + local,                                # 380501234567
        "0" + local,                                  # 0501234567
        f"+38 (0{local[:2]}) {local[2:5]}-{local[5:7]}-{local[7:]}",
        f"+380 {local[:2]} {local[2:5]} {local[5:7]} {local[7:]}",
    ])


def gen_address(rng):
    if rng.random() < 0.8:
        return (f"м. {rng.choice(CITIES)}, {rng.choice(STREET_TYPES)} {rng.choice(STREETS)}, "
                f"{rng.randint(1, 150)}, кв. {rng.randint(1, 200)}")
    return (f"с. {rng.choice(VILLAGES)}, {rng.choice(OBLASTS)} обл., "
            f"вул. {rng.choice(STREETS)}, {rng.randint(1, 80)}")


def maybe_empty(v, rng, p=0.05):
    return "" if rng.random() < p else v


BENCH_FIELDS = ["record_id", "surname", "first_name", "patronymic", "name_initials", "ipn",
                "passport_id", "passport_book", "iban", "card_number", "email", "phone",
                "address", "birth_date", "department", "amount_uah", "status"]


def build_benchmark(rng):
    males, females = read_dict("first_names_male_uk.txt"), read_dict("first_names_female_uk.txt")
    surnames = read_dict("surnames_uk.txt")
    rows = []
    for i in range(1, N + 1):
        male = rng.random() < 0.5
        surname = rng.choice(RARE_SURNAMES if rng.random() < 0.1 else surnames)
        first = rng.choice(RARE_FIRST if rng.random() < 0.08 else (males if male else females))
        patr = rng.choice(gd.MALE_PATRONYMICS if male else gd.FEMALE_PATRONYMICS)
        birth = gd.rand_date(rng, date(1960, 1, 1), date(2004, 12, 31))
        slug = gd.translit(first)[:6] + "." + gd.translit(surname)[:8]
        rows.append({
            "record_id": f"R{i:04d}",
            "surname": maybe_empty(surname, rng),
            "first_name": maybe_empty(first, rng),
            "patronymic": maybe_empty(patr, rng),
            "name_initials": f"{surname} {first[0]}. {patr[0]}.",
            "ipn": maybe_empty(gd.make_ipn(rng, birth, male), rng),
            "passport_id": maybe_empty(f"{rng.randint(0, 999999999):09d}", rng),
            "passport_book": maybe_empty(
                rng.choice(["АА", "АВ", "ВК", "КН", "МЕ", "СО", "ТТ"]) + f" {rng.randint(0, 999999):06d}", rng),
            "iban": maybe_empty(gd.make_iban(rng), rng),
            "card_number": maybe_empty(fmt_card(make_card(rng), rng), rng),
            "email": maybe_empty(f"{slug}{rng.randint(1, 99)}@{rng.choice(gd.EMAIL_DOMAINS)}", rng),
            "phone": maybe_empty(fmt_phone(gd.make_phone(rng), rng), rng),
            "address": maybe_empty(gen_address(rng), rng),
            "birth_date": birth.isoformat(),
            "department": rng.choice(["Фінансовий відділ", "IT", "HR", "Юридичний відділ", "Склад"]),
            "amount_uah": f"{rng.uniform(5000, 90000):.2f}",
            "status": rng.choice(["активний", "відпустка", "звільнений"]),
        })
    return rows


TRAP_FIELDS = ["order_id", "order_number", "invoice_no", "transaction_id", "contract_ref",
               "part_number", "postal_code", "brand_name", "product_line", "city_name",
               "price_uah", "quantity"]


def build_traps(rng):
    rows = []
    for i in range(1, N + 1):
        rows.append({
            "order_id": f"ORD-{i:05d}",
            "order_number": make_non_ipn(rng),           # 10 цифр, але не ІПН
            "invoice_no": make_non_ipn(rng),
            "transaction_id": make_non_luhn(rng),         # 16 цифр, але не картка
            "contract_ref": make_non_iban(rng),           # UA + 27 цифр, але не IBAN
            "part_number": f"{rng.randint(10**8, 10**9 - 1)}",   # 9 цифр, схоже на ID-картку
            "postal_code": f"{rng.randint(1000, 99999):05d}",
            "brand_name": rng.choice(NAMELIKE_BRANDS),    # слова зі словника імен
            "product_line": rng.choice(SURNAMELIKE_WORDS),  # слова зі словника прізвищ
            "city_name": rng.choice(NAMELIKE_CITIES),     # міста, схожі на імена
            "price_uah": f"{rng.uniform(10, 5000):.2f}",
            "quantity": rng.randint(1, 50),
        })
    return rows


def write_csv(path, fields, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


# ground truth
# (dataset, column, expected_class, pii_type, trap, note)
GT = []


def gt(dataset, column, cls, ptype="", trap="no", note=""):
    GT.append((dataset, column, cls, ptype, trap, note))


for c, cls, t, note in [
    ("employee_id", "none", "", "Внутрішній ідентифікатор працівника"),
    ("full_name", "pii", "person_name", "ПІБ"),
    ("ipn", "pii", "ipn", "10 цифр, контрольна цифра"),
    ("iban", "pii", "iban", "UA + 27 цифр, mod 97"),
    ("position", "none", "", ""), ("department", "none", "", ""),
    ("amount_uah", "none", "", ""), ("payment_date", "none", "", "")]:
    gt("payroll.csv", c, cls, t, note=note)
for c, cls, t, note in [
    ("customer_id", "none", "", "Технічний ідентифікатор"),
    ("full_name", "pii", "person_name", "Ім'я та прізвище"),
    ("email", "pii", "email", ""), ("phone", "pii", "phone", "+380XXXXXXXXX"),
    ("birth_date", "quasi", "birth_date", "Квазіідентифікатор, у метриках не враховується"),
    ("age", "none", "", ""), ("city", "none", "", "Назви міст не є PII"),
    ("registration_date", "none", "", "")]:
    gt("customers.json", c, cls, t, note=note)
for c, cls, t, note in [
    ("record_id", "none", "", ""),
    ("surname", "pii", "person_name", "Містить рідкісні прізвища поза словником"),
    ("first_name", "pii", "person_name", "Містить рідкісні імена поза словником"),
    ("patronymic", "pii", "person_name", "По батькові"),
    ("name_initials", "pii", "person_name", "Формат «Прізвище І. П.»"),
    ("ipn", "pii", "ipn", "Є порожні значення (5%)"),
    ("passport_id", "pii", "passport", "ID-картка: 9 цифр, без контрольної суми"),
    ("passport_book", "pii", "passport", "Книжечка: 2 літери + 6 цифр"),
    ("iban", "pii", "iban", ""), ("card_number", "pii", "card", "16 цифр, Луна; з пробілами й без"),
    ("email", "pii", "email", ""), ("phone", "pii", "phone", "П'ять форматів запису"),
    ("address", "pii", "address", "м./с., вулиця, будинок, квартира"),
    ("birth_date", "quasi", "birth_date", "Квазіідентифікатор, у метриках не враховується"),
    ("department", "none", "", ""), ("amount_uah", "none", "", ""), ("status", "none", "", "")]:
    gt("benchmark_people.csv", c, cls, t, note=note)
for c, note in [
    ("order_id", ""), ("order_number", "10 цифр, але контрольна цифра ІПН не збігається"),
    ("invoice_no", "10 цифр, але не ІПН"), ("transaction_id", "16 цифр, але не проходить перевірку Луна"),
    ("contract_ref", "UA + 27 цифр, але не проходить mod 97"),
    ("part_number", "9 цифр, схоже на ID-картку, але це номер деталі"),
    ("postal_code", ""), ("brand_name", "Слова збігаються зі словником імен"),
    ("product_line", "Слова збігаються зі словником прізвищ"),
    ("city_name", "Міста, назви яких схожі на імена"),
    ("price_uah", ""), ("quantity", "")]:
    gt("traps.csv", c, "none", "", "yes" if note else "no", note)


def write_ground_truth():
    with open(PII / "ground_truth.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["dataset", "column", "expected_class", "pii_type", "trap", "note"])
        w.writerows(GT)


# - перевірки
def verify():
    errors = []

    def check(cond, msg):
        if not cond:
            errors.append(msg)

    # 1. розмітка збігається зі справжніми колонками файлів
    with open(ROOT / "data/payroll.csv", encoding="utf-8", newline="") as f:
        payroll_cols = next(csv.reader(f))
    customers = json.loads((ROOT / "data/customers.json").read_text(encoding="utf-8"))
    actual = {
        "payroll.csv": payroll_cols,
        "customers.json": list(customers[0].keys()),
        "benchmark_people.csv": BENCH_FIELDS,
        "traps.csv": TRAP_FIELDS,
    }
    for ds, cols in actual.items():
        labeled = [r[1] for r in GT if r[0] == ds]
        check(labeled == cols, f"{ds}: розмітка не збігається з колонками {cols}")

    # 2. словники покривають імена з готових датасетів
    names = set(read_dict("first_names_male_uk.txt")) | set(read_dict("first_names_female_uk.txt"))
    surn = set(read_dict("surnames_uk.txt"))
    check(not (set(RARE_SURNAMES) & surn), "RARE_SURNAMES не мають бути у словнику")
    check(not (set(RARE_FIRST) & names), "RARE_FIRST не мають бути у словнику")
    with open(ROOT / "data/payroll.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            s, n, _ = r["full_name"].split(" ")
            check(s in surn and n in names, f"payroll: {r['full_name']} не у словниках")
    for r in customers:
        n, s = r["full_name"].split(" ")
        check(s in surn and n in names, f"customers: {r['full_name']} не у словниках")

    # 3. benchmark: значення коректні там, де мають бути, а «пастки» ні
    with open(PII / "benchmark_people.csv", encoding="utf-8", newline="") as f:
        b = list(csv.DictReader(f))
    with open(PII / "traps.csv", encoding="utf-8", newline="") as f:
        t = list(csv.DictReader(f))
    check(all(gd.ipn_valid(r["ipn"]) for r in b if r["ipn"]), "benchmark: невалідний ІПН")
    check(all(gd.iban_valid(r["iban"]) for r in b if r["iban"]), "benchmark: невалідний IBAN")
    check(all(luhn_valid(r["card_number"].replace(" ", "")) for r in b if r["card_number"]),
          "benchmark: картка не проходить Луна")
    check(all(re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", r["email"]) for r in b if r["email"]),
          "benchmark: невалідний email")
    check(not any(gd.ipn_valid(r["order_number"]) or gd.ipn_valid(r["invoice_no"]) for r in t),
          "traps: числове поле проходить перевірку ІПН")
    check(not any(luhn_valid(r["transaction_id"]) for r in t), "traps: transaction_id проходить Луна")
    check(not any(gd.iban_valid(r["contract_ref"]) for r in t), "traps: contract_ref проходить IBAN")
    for r in t:
        check(r["brand_name"] in NAMELIKE_BRANDS and r["city_name"] in NAMELIKE_CITIES, "traps: сторонні значення")
    check(len(b) == N and len(t) == N, "неочікувана кількість рядків")

    # 4. кількості для README/метрик
    pos = sum(1 for r in GT if r[2] == "pii")
    neg = sum(1 for r in GT if r[2] == "none")
    check(pos == 18 and neg == 25, f"кількості колонок: pii={pos}, none={neg} (очікувалось 18 і 25)")
    if errors:
        print("ПОМИЛКИ ПЕРЕВІРКИ:")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print(f"OK: колонок pii={pos}, none={neg}, quasi={sum(1 for r in GT if r[2]=='quasi')}; "
          f"benchmark={len(b)} рядків, traps={len(t)} рядків")


def main():
    rng = random.Random(SEED)
    write_csv(PII / "benchmark_people.csv", BENCH_FIELDS, build_benchmark(rng))
    write_csv(PII / "traps.csv", TRAP_FIELDS, build_traps(rng))
    write_ground_truth()
    verify()


if __name__ == "__main__":
    main()
