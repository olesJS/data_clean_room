#!/usr/bin/env python3
"""Генератор синтетичних датасетів для проєкту Data Clean Room.

Створює два демонстраційні набори із заздалегідь закладеними дефектами:
  * data/payroll.csv    - кейс 1: зарплатні відомості (HR -> зовнішній аудитор)
  * data/customers.json - кейс 2: база клієнтів ритейлу (ритейл -> рекламне агентство)
а також допоміжні файли для негативних тестів і маніфест дефектів.

Усі дані ВИГАДАНІ. ІПН і IBAN мають коректні контрольні цифри (щоб PII-детектор
міг їх перевіряти), але збіги з реальними значеннями випадкові.

Запуск (лише стандартна бібліотека, Python 3.9+):
    python scripts/generate_datasets.py            # створює data/
    python scripts/generate_datasets.py --large    # додатково файл > 50 МБ (не комітити)

Результат детермінований: SEED фіксований. Якщо змінюєте SEED або кількості дефектів,
перерахуйте data/defects.md.
"""
import argparse
import csv
import json
import re
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path
import random

SEED = 20261024
# «Сьогодні» для перевірок віку та «дат з майбутнього». Нормальні дати лежать до
# 2026-09-30, дати-дефекти - у 2027-2028 рр., тож лишаються «майбутніми» весь семестр.
REF_DATE = date(2026, 10, 24)

# Кількість записів (унікальних + повних дублікатів = «близько 500» і «близько 1000»)
PAYROLL_UNIQUE, PAYROLL_DUPLICATES = 490, 10
CUSTOMERS_UNIQUE, CUSTOMERS_DUPLICATES = 985, 15

# Кількості дефектів - з плану (розділ 11.3)
PAYROLL_DEFECTS = {
    "missing_ipn": 15,
    "amount_outlier": 5,
    "amount_zero": 4,       # разом з від'ємними: 8 «нульових чи від'ємних сум»
    "amount_negative": 4,
    "future_payment_date": 8,
}
CUSTOMERS_DEFECTS = {
    "age_out_of_range": 20,       # 10 від'ємних + 10 понад 120
    "invalid_email": 25,
    "future_registration_date": 30,
    "missing_city": 40,           # 25 null + 15 порожніх рядків
}

# ----------------------------------------------------------------- словники

MALE_NAMES = ["Олександр", "Андрій", "Богдан", "Василь", "Віктор", "Дмитро", "Іван", "Ігор",
              "Максим", "Микола", "Назар", "Олег", "Петро", "Роман", "Сергій", "Тарас",
              "Юрій", "Ярослав", "Степан", "Володимир", "Артем", "Денис", "Євген", "Захар",
              "Орест", "Остап", "Святослав", "Тимофій", "Данило", "Олексій"]
FEMALE_NAMES = ["Анна", "Оксана", "Олена", "Марія", "Наталія", "Ірина", "Катерина", "Софія",
                "Юлія", "Тетяна", "Вікторія", "Людмила", "Галина", "Дарина", "Ангеліна",
                "Христина", "Мар'яна", "Надія", "Уляна", "Яна", "Світлана", "Лілія",
                "Олександра", "Аліна", "Вероніка", "Ольга", "Злата", "Соломія", "Орися", "Діана"]
# Прізвища однакові для обох статей
SURNAMES = ["Коваленко", "Бондаренко", "Ткаченко", "Кравченко", "Олійник", "Шевчук", "Поліщук",
            "Савчук", "Мороз", "Лисенко", "Руденко", "Бойко", "Мартинюк", "Гончар", "Кушнір",
            "Павленко", "Петренко", "Тимошенко", "Романюк", "Василенко", "Яремчук", "Левчук",
            "Маслюк", "Назарук", "Панчишин", "Костюк", "Гнатюк", "Мельник", "Ковальчук",
            "Іваненко", "Федоренко", "Сидоренко", "Ярмоленко", "Гриценко", "Волошин",
            "Данилюк", "Жук", "Козак", "Литвин", "Пономаренко"]
MALE_PATRONYMICS = ["Олександрович", "Андрійович", "Богданович", "Васильович", "Вікторович",
                    "Дмитрович", "Іванович", "Ігорович", "Максимович", "Миколайович",
                    "Олегович", "Петрович", "Романович", "Сергійович", "Тарасович",
                    "Юрійович", "Ярославович", "Степанович", "Володимирович"]
FEMALE_PATRONYMICS = ["Олександрівна", "Андріївна", "Богданівна", "Василівна", "Вікторівна",
                      "Дмитрівна", "Іванівна", "Ігорівна", "Максимівна", "Миколаївна",
                      "Олегівна", "Петрівна", "Романівна", "Сергіївна", "Тарасівна",
                      "Юріївна", "Ярославівна", "Степанівна", "Володимирівна"]
CITIES = ["Київ", "Львів", "Одеса", "Харків", "Дніпро", "Запоріжжя", "Вінниця", "Полтава",
          "Чернівці", "Івано-Франківськ", "Тернопіль", "Луцьк", "Рівне", "Житомир", "Суми",
          "Черкаси", "Чернігів", "Хмельницький", "Ужгород", "Миколаїв", "Кропивницький"]
EMAIL_DOMAINS = ["gmail.com", "ukr.net", "i.ua", "meta.ua", "outlook.com", "icloud.com"]
MOBILE_CODES = ["50", "63", "66", "67", "68", "73", "91", "93", "95", "96", "97", "98", "99"]
# (посада, відділ, діапазон місячної виплати, грн)
POSITIONS = [
    ("Бухгалтер", "Бухгалтерія", (24000, 40000)),
    ("Старший бухгалтер", "Бухгалтерія", (38000, 55000)),
    ("Економіст", "Фінансовий відділ", (30000, 50000)),
    ("Фінансовий аналітик", "Фінансовий відділ", (42000, 65000)),
    ("Менеджер з персоналу", "HR", (28000, 45000)),
    ("Розробник", "IT", (55000, 80000)),
    ("Тестувальник", "IT", (40000, 62000)),
    ("Аналітик даних", "IT", (50000, 75000)),
    ("Юрист", "Юридичний відділ", (35000, 60000)),
    ("Адміністратор", "Адміністрація", (22000, 34000)),
    ("Керівник відділу", "Керівництво", (60000, 80000)),
]

TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'ґ': 'g', 'д': 'd', 'е': 'e', 'є': 'ye', 'ж': 'zh',
    'з': 'z', 'и': 'y', 'і': 'i', 'ї': 'yi', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
    'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ь': '', 'ю': 'yu', 'я': 'ya', "'": '', '’': '',
}

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")


def translit(s):
    return "".join(TRANSLIT.get(ch, ch) for ch in s.lower())


# ------------------------------------------------- ІПН, IBAN, дати, телефони

IPN_WEIGHTS = [-1, 5, 7, 9, 4, 6, 10, 5, 7]


def ipn_check_digit(first9):
    return sum(int(d) * w for d, w in zip(first9, IPN_WEIGHTS)) % 11 % 10


def make_ipn(rng, birth, male):
    """10 цифр: кількість днів від 31.12.1899 (5), випадкові (3), стать (1: непарна - чол.), контрольна."""
    days = (birth - date(1899, 12, 31)).days
    sex_digit = rng.choice([1, 3, 5, 7, 9]) if male else rng.choice([0, 2, 4, 6, 8])
    first9 = f"{days:05d}{rng.randint(0, 999):03d}{sex_digit}"
    return first9 + str(ipn_check_digit(first9))


def ipn_valid(s):
    return bool(re.fullmatch(r"\d{10}", s)) and ipn_check_digit(s[:9]) == int(s[9])


def make_iban(rng):
    """UA + 2 контрольні + 6 (МФО) + 19 (рахунок) = 29 символів, перевірка mod 97."""
    bban = f"{rng.randint(300000, 399999)}{rng.randint(0, 10**19 - 1):019d}"
    check = 98 - int(bban + "3010" + "00") % 97   # U=30, A=10
    return f"UA{check:02d}{bban}"


def iban_valid(s):
    if not re.fullmatch(r"UA\d{27}", s):
        return False
    return int(s[4:] + "3010" + s[2:4]) % 97 == 1


def rand_date(rng, start, end):
    return start + timedelta(days=rng.randint(0, (end - start).days))


def full_years(birth, today):
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def make_phone(rng):
    return f"+380{rng.choice(MOBILE_CODES)}{rng.randint(0, 9999999):07d}"


def person(rng):
    male = rng.random() < 0.5
    first = rng.choice(MALE_NAMES if male else FEMALE_NAMES)
    patr = rng.choice(MALE_PATRONYMICS if male else FEMALE_PATRONYMICS)
    return male, first, rng.choice(SURNAMES), patr


# -------------------------------------------------------------- payroll.csv

PAYROLL_FIELDS = ["employee_id", "full_name", "ipn", "iban", "position", "department",
                  "amount_uah", "payment_date"]


def build_payroll(rng, manifest):
    rows = []
    for i in range(PAYROLL_UNIQUE):
        male, first, last, patr = person(rng)
        birth = rand_date(rng, date(1960, 1, 1), date(2004, 12, 31))
        position, department, (lo, hi) = rng.choice(POSITIONS)
        rows.append({
            "employee_id": f"E{i + 1:05d}",
            "full_name": f"{last} {first} {patr}",
            "ipn": make_ipn(rng, birth, male),
            "iban": make_iban(rng),
            "position": position,
            "department": department,
            "amount_uah": round(rng.uniform(lo, hi), 2),
            "payment_date": rand_date(rng, date(2026, 1, 1), date(2026, 9, 30)).isoformat(),
        })

    order = list(range(PAYROLL_UNIQUE))
    rng.shuffle(order)
    pos = 0

    def take(n):
        nonlocal pos
        chunk = order[pos:pos + n]
        pos += n
        return chunk

    for i in take(PAYROLL_DEFECTS["missing_ipn"]):
        rows[i]["ipn"] = ""
        manifest.append(("payroll.csv", rows[i]["employee_id"], "missing_ipn"))
    for i in take(PAYROLL_DEFECTS["amount_outlier"]):
        rows[i]["amount_uah"] = round(rows[i]["amount_uah"] * 10, 2)
        manifest.append(("payroll.csv", rows[i]["employee_id"], "amount_outlier"))
    for i in take(PAYROLL_DEFECTS["amount_zero"]):
        rows[i]["amount_uah"] = 0.0
        manifest.append(("payroll.csv", rows[i]["employee_id"], "amount_zero"))
    for i in take(PAYROLL_DEFECTS["amount_negative"]):
        rows[i]["amount_uah"] = -rows[i]["amount_uah"]
        manifest.append(("payroll.csv", rows[i]["employee_id"], "amount_negative"))
    for i in take(PAYROLL_DEFECTS["future_payment_date"]):
        rows[i]["payment_date"] = rand_date(rng, date(2027, 1, 1), date(2028, 12, 31)).isoformat()
        manifest.append(("payroll.csv", rows[i]["employee_id"], "future_payment_date"))

    # Повні дублікати беруться лише з «чистих» рядків, щоб не подвоювати інші дефекти
    for i in take(PAYROLL_DUPLICATES):
        rows.insert(rng.randint(0, len(rows)), dict(rows[i]))
        manifest.append(("payroll.csv", rows[i]["employee_id"], "duplicate_row"))
    return rows


def write_payroll(path, rows, delimiter=",", encoding="utf-8"):
    with open(path, "w", newline="", encoding=encoding) as f:
        w = csv.DictWriter(f, fieldnames=PAYROLL_FIELDS, delimiter=delimiter, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "amount_uah": f"{r['amount_uah']:.2f}"})


# ----------------------------------------------------------- customers.json

INVALID_EMAIL_PATTERNS = [
    ("no_at", lambda e: e.replace("@", "", 1)),
    ("no_domain", lambda e: e.split("@")[0] + "@"),
    ("no_local_part", lambda e: "@" + e.split("@")[1]),
    ("double_at", lambda e: e.replace("@", "@@", 1)),
    ("space_in_local", lambda e: e.replace(".", " ", 1)),
    ("no_tld", lambda e: e.rsplit(".", 1)[0]),
    ("trailing_dot", lambda e: e + "."),
    ("comma_instead_of_dot", lambda e: ",".join(e.rsplit(".", 1))),
]


def build_customers(rng, manifest):
    rows, used_emails = [], set()
    for i in range(CUSTOMERS_UNIQUE):
        male, first, last, _ = person(rng)
        birth = rand_date(rng, REF_DATE - timedelta(days=int(85 * 365.25)),
                          REF_DATE - timedelta(days=int(18 * 365.25)))
        while True:
            email = f"{translit(first)}.{translit(last)}{rng.randint(1, 999)}@{rng.choice(EMAIL_DOMAINS)}"
            if email not in used_emails:
                used_emails.add(email)
                break
        rows.append({
            "customer_id": 100001 + i,
            "full_name": f"{first} {last}",
            "email": email,
            "phone": make_phone(rng),
            "birth_date": birth.isoformat(),
            "age": full_years(birth, REF_DATE),
            "city": rng.choice(CITIES),
            "registration_date": rand_date(rng, date(2018, 1, 1), date(2026, 9, 30)).isoformat(),
        })

    order = list(range(CUSTOMERS_UNIQUE))
    rng.shuffle(order)
    pos = 0

    def take(n):
        nonlocal pos
        chunk = order[pos:pos + n]
        pos += n
        return chunk

    ages = take(CUSTOMERS_DEFECTS["age_out_of_range"])
    for k, i in enumerate(ages):
        rows[i]["age"] = rng.randint(-30, -1) if k < len(ages) // 2 else rng.randint(121, 250)
        manifest.append(("customers.json", rows[i]["customer_id"], "age_out_of_range"))
    for k, i in enumerate(take(CUSTOMERS_DEFECTS["invalid_email"])):
        name, fn = INVALID_EMAIL_PATTERNS[k % len(INVALID_EMAIL_PATTERNS)]
        rows[i]["email"] = fn(rows[i]["email"])
        manifest.append(("customers.json", rows[i]["customer_id"], f"invalid_email:{name}"))
    for i in take(CUSTOMERS_DEFECTS["future_registration_date"]):
        rows[i]["registration_date"] = rand_date(rng, date(2027, 1, 1), date(2028, 12, 31)).isoformat()
        manifest.append(("customers.json", rows[i]["customer_id"], "future_registration_date"))
    cities = take(CUSTOMERS_DEFECTS["missing_city"])
    for k, i in enumerate(cities):
        null_variant = k < 25
        rows[i]["city"] = None if null_variant else ""
        manifest.append(("customers.json", rows[i]["customer_id"],
                         "missing_city:null" if null_variant else "missing_city:empty_string"))

    for i in take(CUSTOMERS_DUPLICATES):
        rows.insert(rng.randint(0, len(rows)), dict(rows[i]))
        manifest.append(("customers.json", rows[i]["customer_id"], "duplicate_row"))
    return rows


# ------------------------------------------------- файли для негативних тестів

BAD_JSON = """[
  {"customer_id": 1, "full_name": "Тест Тестович"},
  {"customer_id": 2, "full_name": "Інший Клієнт"}
  {"customer_id": 3, "full_name": "Пропущена кома в рядку вище"}
]
"""


def write_invalid(dirpath, payroll_rows, large):
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / "empty.csv").write_bytes(b"")
    (dirpath / "empty.json").write_bytes(b"")
    (dirpath / "header_only.csv").write_text(",".join(PAYROLL_FIELDS) + "\n", encoding="utf-8")
    (dirpath / "bad_syntax.json").write_text(BAD_JSON, encoding="utf-8")
    (dirpath / "not_supported.txt").write_text(
        "Це текстовий файл. Система підтримує лише CSV та JSON.\n", encoding="utf-8")
    if large:  # > 50 МБ; у git не додавати
        target = dirpath / "too_large.csv"
        with open(target, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(PAYROLL_FIELDS)
            n = 0
            while f.tell() < 51 * 1024 * 1024:
                r = payroll_rows[n % len(payroll_rows)]
                w.writerow([r["employee_id"], r["full_name"], r["ipn"], r["iban"], r["position"],
                            r["department"], f"{r['amount_uah']:.2f}", r["payment_date"]])
                n += 1
        print(f"  створено {target} ({target.stat().st_size / 1024 / 1024:.1f} МБ), не комітьте його")


# ------------------------------------------------------------- самоперевірка

def verify(out):
    """Незалежно перечитує файли з диска й звіряє кількості дефектів із планом."""
    errors = []

    def check(name, actual, expected):
        status = "OK " if actual == expected else "ПОМИЛКА"
        print(f"  [{status}] {name}: {actual} (очікувано {expected})")
        if actual != expected:
            errors.append(name)

    with open(out / "payroll.csv", newline="", encoding="utf-8") as f:
        pr = list(csv.DictReader(f))
    print("payroll.csv")
    check("рядків", len(pr), PAYROLL_UNIQUE + PAYROLL_DUPLICATES)
    check("порожніх ІПН", sum(1 for r in pr if r["ipn"] == ""), PAYROLL_DEFECTS["missing_ipn"])
    check("ІПН з некоректною контрольною цифрою",
          sum(1 for r in pr if r["ipn"] and not ipn_valid(r["ipn"])), 0)
    check("некоректних IBAN", sum(1 for r in pr if not iban_valid(r["iban"])), 0)
    amounts = [float(r["amount_uah"]) for r in pr]
    check("сум <= 0", sum(1 for a in amounts if a <= 0),
          PAYROLL_DEFECTS["amount_zero"] + PAYROLL_DEFECTS["amount_negative"])
    check("сум > 150000 (навмисні викиди)", sum(1 for a in amounts if a > 150000),
          PAYROLL_DEFECTS["amount_outlier"])
    check("дат виплати після " + REF_DATE.isoformat(),
          sum(1 for r in pr if r["payment_date"] > REF_DATE.isoformat()),
          PAYROLL_DEFECTS["future_payment_date"])
    seen, dups = set(), 0
    for r in pr:
        key = tuple(r.values())
        dups += key in seen
        seen.add(key)
    check("повних дублікатів рядків", dups, PAYROLL_DUPLICATES)
    q1, _, q3 = statistics.quantiles(amounts, n=4, method="inclusive")
    lo, hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    iqr_out = sum(1 for a in amounts if a < lo or a > hi)
    print(f"  [інфо] викидів за IQR 1.5: {iqr_out} (межі {lo:.2f} .. {hi:.2f})")

    with open(out / "customers.json", encoding="utf-8") as f:
        cs = json.load(f)
    print("customers.json")
    check("записів", len(cs), CUSTOMERS_UNIQUE + CUSTOMERS_DUPLICATES)
    check("віків поза 0..120", sum(1 for r in cs if not 0 <= r["age"] <= 120),
          CUSTOMERS_DEFECTS["age_out_of_range"])
    check("некоректних email", sum(1 for r in cs if not EMAIL_RE.match(r["email"])),
          CUSTOMERS_DEFECTS["invalid_email"])
    check("дат реєстрації після " + REF_DATE.isoformat(),
          sum(1 for r in cs if r["registration_date"] > REF_DATE.isoformat()),
          CUSTOMERS_DEFECTS["future_registration_date"])
    check("порожніх міст (null або \"\")",
          sum(1 for r in cs if r["city"] is None or str(r["city"]).strip() == ""),
          CUSTOMERS_DEFECTS["missing_city"])
    seen, dups = set(), 0
    for r in cs:
        key = json.dumps(r, sort_keys=True, ensure_ascii=False)
        dups += key in seen
        seen.add(key)
    check("повних дублікатів записів", dups, CUSTOMERS_DUPLICATES)
    bad_age_consistency = sum(
        1 for r in cs if 0 <= r["age"] <= 120
        and full_years(date.fromisoformat(r["birth_date"]), REF_DATE) != r["age"])
    check("віків, що не збігаються з датою народження (серед коректних)", bad_age_consistency, 0)
    check("телефонів не у форматі +380XXXXXXXXX",
          sum(1 for r in cs if not re.fullmatch(r"\+380\d{9}", r["phone"])), 0)

    with open(out / "alt" / "payroll_cp1251_semicolon.csv", newline="", encoding="cp1251") as f:
        alt = list(csv.DictReader(f, delimiter=";"))
    check("рядків у payroll_cp1251_semicolon.csv", len(alt), len(pr))

    try:
        json.loads((out / "invalid" / "bad_syntax.json").read_text(encoding="utf-8"))
        errors.append("bad_syntax.json має бути некоректним")
    except json.JSONDecodeError as e:
        print(f"  [інфо] bad_syntax.json: {e}")

    return errors


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "data",
                    help="каталог результату (за замовчуванням ../data)")
    ap.add_argument("--large", action="store_true", help="створити також файл > 50 МБ")
    args = ap.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "alt").mkdir(exist_ok=True)

    rng = random.Random(SEED)
    manifest = []
    payroll = build_payroll(rng, manifest)
    customers = build_customers(rng, manifest)

    write_payroll(out / "payroll.csv", payroll)
    write_payroll(out / "alt" / "payroll_cp1251_semicolon.csv", payroll, delimiter=";", encoding="cp1251")
    with open(out / "customers.json", "w", encoding="utf-8") as f:
        json.dump(customers, f, ensure_ascii=False, indent=2)
        f.write("\n")
    write_invalid(out / "invalid", payroll, args.large)
    with open(out / "defects_manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["file", "record_id", "defect"])
        w.writerows(manifest)

    print(f"Файли створено в {out}")
    errors = verify(out)
    if errors:
        print("\nЗнайдено розбіжності:", ", ".join(errors))
        sys.exit(1)
    print("\nУсі перевірки пройдено.")


if __name__ == "__main__":
    main()
