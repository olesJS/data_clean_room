#!/usr/bin/env python3
"""Порахувати recall і precision PII-детектора за еталоном data/pii/ground_truth.csv.

Вхід: CSV з прогнозом детектора, колонки  dataset,column,pii_type  (confidence за бажанням).
У прогнозі мають бути лише колонки, які детектор вважає PII; решта вважається «не PII».

  python scripts/evaluate_pii.py predictions.csv [--min-recall 0.9]
  python scripts/evaluate_pii.py --self-test        # перевірка самого скрипта

Правила підрахунку (колонковий рівень):
  TP  - колонка з expected_class=pii, яку детектор позначив як PII
  FN  - колонка pii, яку детектор пропустив
  FP  - колонка none (зокрема «пастка»), яку детектор позначив як PII
  quasi-колонки (birth_date) не рахуються ні як TP, ні як FP
  type accuracy - частка TP, у яких pii_type збігається з еталоном (окрема метрика)
Код виходу 1, якщо recall нижче --min-recall.
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRUTH = ROOT / "data" / "pii" / "ground_truth.csv"


def load_truth():
    with open(TRUTH, encoding="utf-8", newline="") as f:
        return {(r["dataset"], r["column"]): r for r in csv.DictReader(f)}


def load_predictions(path):
    with open(path, encoding="utf-8", newline="") as f:
        return {(r["dataset"], r["column"]): r.get("pii_type", "") for r in csv.DictReader(f)}


def evaluate(truth, pred):
    unknown = [k for k in pred if k not in truth]
    if unknown:
        raise SystemExit(f"Невідомі колонки у прогнозі (немає в ground_truth.csv): {unknown}")
    tp, fn, fp, type_ok = [], [], [], 0
    for key, row in truth.items():
        cls, flagged = row["expected_class"], key in pred
        if cls == "pii":
            if flagged:
                tp.append(key)
                type_ok += pred[key] == row["pii_type"]
            else:
                fn.append(key)
        elif cls == "none" and flagged:
            fp.append(key)
    recall = len(tp) / (len(tp) + len(fn)) if tp or fn else 0.0
    precision = len(tp) / (len(tp) + len(fp)) if tp or fp else 0.0
    return {"tp": tp, "fn": fn, "fp": fp, "recall": recall, "precision": precision,
            "type_accuracy": type_ok / len(tp) if tp else 0.0}


def report(res):
    print(f"Recall    : {res['recall']:.1%}  (TP {len(res['tp'])}, FN {len(res['fn'])})")
    print(f"Precision : {res['precision']:.1%}  (FP {len(res['fp'])})")
    print(f"Тип PII правильний у {res['type_accuracy']:.1%} знайдених колонок")
    for title, key in (("Пропущено (FN)", "fn"), ("Хибні спрацювання (FP)", "fp")):
        if res[key]:
            print(f"{title}:")
            for ds, col in res[key]:
                print(f"  - {ds} :: {col}")


def self_test():
    truth = load_truth()
    perfect = {k: r["pii_type"] for k, r in truth.items() if r["expected_class"] == "pii"}
    r = evaluate(truth, perfect)
    assert r["recall"] == 1.0 and r["precision"] == 1.0 and r["type_accuracy"] == 1.0, r
    naive = dict(perfect)                                  # + хибні спрацювання на «пастках»
    naive[("traps.csv", "order_number")] = "ipn"
    naive[("traps.csv", "city_name")] = "person_name"
    r2 = evaluate(truth, naive)
    assert r2["recall"] == 1.0 and len(r2["fp"]) == 2 and r2["precision"] < 1.0, r2
    missed = dict(perfect)
    del missed[("benchmark_people.csv", "address")]
    r3 = evaluate(truth, missed)
    assert len(r3["fn"]) == 1 and r3["recall"] < 1.0, r3
    print("self-test: OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("predictions", nargs="?")
    ap.add_argument("--min-recall", type=float, default=0.9)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.predictions:
        ap.error("потрібен файл з прогнозом або --self-test")
    res = evaluate(load_truth(), load_predictions(args.predictions))
    report(res)
    if res["recall"] < args.min_recall:
        print(f"\nRecall нижчий за {args.min_recall:.0%}")
        sys.exit(1)


if __name__ == "__main__":
    main()
