"""Compare LLM-judge retest results with the existing judges (Claude subagents) and the author's ratings.

python3 compare.py > summary.json   （judge-retest/ で実行。表は summary.md に書き出す）
"""

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
RUNS = HERE.parent / "runs"
GEN_MODELS = ("claude-opus-5.5", "gpt-6.1-sol", "muse-wonder", "gemini-4-hydrogen")
JUDGES = {
    "existing": "既存（Claudeサブエージェント）",
    "jev-latest": "Jev（~typesafe/jev-latest）",
    "gemma-4-31b-it": "Gemma 4 31B",
    "qwen3.8-27b": "Qwen3.8 27B",
    "claude-haiku-5.5": "Claude Haiku 5.5",
}
CONDITIONS = ("baseline", "japanese_posture", "shazai_full")
COND_JA = {"baseline": "指示なし", "japanese_posture": "一般指示", "shazai_full": "SHAZAI"}
LEVELS = ("0", "1", "2", "3", "4", "repair")
RATINGS = ("rude", "light", "fit", "heavy")
PERSONAS = ("P1", "P2", "P3")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def judge_dir(judge, run):
    return RUNS / run if judge == "existing" else HERE / judge / run


def kappa(a, b, labels):
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    n = len(pairs)
    if not n:
        return None
    observed = sum(x == y for x, y in pairs) / n
    ca, cb = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    expected = sum(ca[label] * cb[label] for label in labels) / n / n
    return None if expected == 1 else round((observed - expected) / (1 - expected), 3)


def fleiss(rows, labels):
    """rows: list of per-item label lists (same rater count)."""
    rows = [r for r in rows if all(x is not None for x in r)]
    if not rows:
        return None
    m = len(rows[0])
    totals = Counter()
    p_items = []
    for row in rows:
        counts = Counter(row)
        totals.update(counts)
        p_items.append((sum(c * c for c in counts.values()) - m) / (m * (m - 1)))
    p_bar = sum(p_items) / len(rows)
    p_e = sum((totals[label] / (len(rows) * m)) ** 2 for label in labels)
    return None if p_e == 1 else round((p_bar - p_e) / (1 - p_e), 3)


def majority(values):
    value, votes = Counter(values).most_common(1)[0]
    return value if votes >= 2 else None


def load():
    answers = []  # one row per generated answer
    scenarios = []
    for run in GEN_MODELS:
        manifest = read(RUNS / run / "manifest.json")
        user = read(RUNS / run / "user-ratings.json")
        for scenario in manifest["public"]["scenarios"]:
            sid = scenario["id"]
            scenarios.append({"run": run, "id": sid, "design": manifest["levels"][sid], "user": user["levels"][sid],
                              "last": scenario["messages"][-1]["content"]})
            for answer in scenario["answers"]:
                entry = manifest["mapping"][answer["id"]]
                answers.append({"run": run, "id": answer["id"], "scenario": sid, "condition": entry["condition"],
                                "level": entry["level"], "user": user["ratings"][answer["id"]]["rating"],
                                "user_level": user["levels"][sid]})
    judged = {}
    for judge in JUDGES:
        personas, checks = {}, {}
        for run in GEN_MODELS:
            directory = judge_dir(judge, run)
            for persona in PERSONAS:
                data = read(directory / f"persona-{persona}.json")
                personas.setdefault(persona, {"levels": {}, "ratings": {}})
                personas[persona]["levels"].update(data["levels"])
                personas[persona]["ratings"].update({k: v["rating"] for k, v in data["ratings"].items()})
            checks.update(read(directory / "checklist.json")["checks"])
        judged[judge] = {"personas": personas, "checks": checks}
    return answers, scenarios, judged


def summarize(answers, scenarios, judged):
    ids = [a["id"] for a in answers]
    author = [a["user"] for a in answers]
    existing_majority = [majority([judged["existing"]["personas"][p]["ratings"][i] for p in PERSONAS]) for i in ids]
    existing_hits = judged["existing"]["checks"]
    result = {}
    for judge, data in judged.items():
        personas = data["personas"]
        ratings = {i: [personas[p]["ratings"][i] for p in PERSONAS] for i in ids}
        maj = [majority(ratings[i]) for i in ids]
        out = {"label": JUDGES[judge]}

        # 条件別の分布（3名×64回答）
        dist = {}
        for cond in CONDITIONS:
            counter = Counter(r for a in answers if a["condition"] == cond for r in ratings[a["id"]])
            dist[cond] = {r: counter[r] for r in RATINGS} | {"n": sum(counter.values())}
        out["by_condition"] = dist

        # 段階×条件の fit 件数（3名分）
        by_level = {}
        for level in LEVELS:
            by_level[level] = {}
            for cond in CONDITIONS:
                sel = [a for a in answers if a["condition"] == cond and a["level"] == level]
                counter = Counter(r for a in sel for r in ratings[a["id"]])
                by_level[level][cond] = {r: counter[r] for r in RATINGS} | {"n": sum(counter.values())}
        out["by_level"] = by_level

        # 筆者との一致
        out["agreement_author"] = {
            "majority_exact": sum(m == u for m, u in zip(maj, author)),
            "no_majority": sum(m is None for m in maj),
            "kappa_majority": kappa(maj, author, RATINGS),
            "per_persona_exact": [sum(personas[p]["ratings"][i] == a["user"] for i, a in zip(ids, answers)) for p in PERSONAS],
            "kappa_fit_vs_not": kappa(["fit" if m == "fit" else ("x" if m else None) for m in maj],
                                      ["fit" if u == "fit" else "x" for u in author], ("fit", "x")),
        }
        if judge != "existing":
            out["agreement_existing"] = {
                "majority_exact": sum(m == e for m, e in zip(maj, existing_majority)),
                "kappa_majority": kappa(maj, existing_majority, RATINGS),
            }
        out["inter_persona_fleiss"] = fleiss([ratings[i] for i in ids], RATINGS)
        out["unanimous"] = sum(len(set(ratings[i])) == 1 for i in ids)

        # 筆者の評定別に、この判定者の多数決がどうなったか（混同行列）
        confusion = defaultdict(Counter)
        for m, u in zip(maj, author):
            confusion[u][m or "none"] += 1
        out["confusion_author_rows"] = {u: dict(confusion[u]) for u in RATINGS}

        # 知覚段階
        perceived = defaultdict(Counter)
        user_match, design_match, total = 0, 0, 0
        for s in scenarios:
            for p in PERSONAS:
                level = personas[p]["levels"][s["id"]]
                perceived[s["design"]][level] += 1
                user_match += level == s["user"]
                design_match += level == (s["design"] if s["design"] != "repair" else None)
                total += 1
        out["perceived_by_design"] = {lv: dict(sorted(perceived[lv].items())) for lv in LEVELS}
        out["perceived_match_author"] = f"{user_match}/{total}"
        out["perceived_match_design"] = f"{design_match}/{total - 3 * sum(s['design'] == 'repair' for s in scenarios)}"
        out["perceived_mean_by_design"] = {
            lv: round(sum(int(k) * v for k, v in perceived[lv].items()) / max(1, sum(perceived[lv].values())), 2)
            for lv in LEVELS
        }

        # チェックリスト
        checks = data["checks"]
        ck = {}
        for cond in CONDITIONS:
            sel = [a["id"] for a in answers if a["condition"] == cond]
            hits = sum(len(checks[i]["hit"]) for i in sel)
            clear = sum(len(checks[i]["clear"]) for i in sel)
            unobs = sum(len(checks[i]["unobservable"]) for i in sel)
            na = sum(len(checks[i]["not_applicable"]) for i in sel)
            top = Counter(item for i in sel for item in checks[i]["hit"]).most_common(4)
            ck[cond] = {"hit": hits, "assessable": hits + clear, "unobservable": unobs, "not_applicable": na,
                        "rate": round(100 * hits / (hits + clear), 2) if hits + clear else None, "top": top}
        out["checklist"] = ck
        out["checklist_hits_zero_answers"] = sum(not checks[i]["hit"] for i in ids)
        # 筆者の評定別の平均該当数
        out["checklist_mean_hits_by_author"] = {
            r: round(sum(len(checks[a["id"]]["hit"]) for a in answers if a["user"] == r) /
                     max(1, sum(a["user"] == r for a in answers)), 2) for r in RATINGS
        }
        # 段階0・修復期での該当数（不要な該当の指標）
        out["checklist_hits_level0_repair"] = sum(len(checks[a["id"]]["hit"]) for a in answers if a["level"] in ("0", "repair"))
        if judge != "existing":
            a_flags, b_flags = [], []
            for i in ids:
                for item in set(checks[i]["hit"]) | set(checks[i]["clear"]) | set(checks[i]["unobservable"]) | set(checks[i]["not_applicable"]):
                    a_flags.append(item in checks[i]["hit"])
                    b_flags.append(item in existing_hits[i]["hit"])
            both = sum(x and y for x, y in zip(a_flags, b_flags))
            out["checklist_vs_existing"] = {
                "kappa_hit": kappa(a_flags, b_flags, (True, False)),
                "both_hit": both, "this_only": sum(x and not y for x, y in zip(a_flags, b_flags)),
                "existing_only": sum(y and not x for x, y in zip(a_flags, b_flags)),
            }
        result[judge] = out
    return result


def signature_cases(answers, judged):
    """既存報告で取り上げた場面について、各判定者の多数決を並べる。"""
    keys = {
        "bullets": "箇条書きは使わないでください",
        "taninngoto": "他人事みたいですね",
    }
    manifests = {run: read(RUNS / run / "manifest.json") for run in GEN_MODELS}
    out = {}
    for name, needle in keys.items():
        rows = []
        for a in answers:
            scenario = next(s for s in manifests[a["run"]]["public"]["scenarios"] if s["id"] == a["scenario"])
            if needle not in scenario["messages"][-1]["content"]:
                continue
            row = {"run": a["run"], "condition": a["condition"], "author": a["user"]}
            for judge, data in judged.items():
                row[judge] = majority([data["personas"][p]["ratings"][a["id"]] for p in PERSONAS])
                row[judge + ":10.06"] = "10.06" in data["checks"][a["id"]]["hit"]
            rows.append(row)
        out[name] = rows
    return out


def jev_soft(answers):
    """Jev の確率分布の平均（多数決ではなく確率の期待値で見た条件別の評定）。"""
    mass = {cond: Counter() for cond in CONDITIONS}
    counts = Counter()
    condition = {a["id"]: a["condition"] for a in answers}
    for run in GEN_MODELS:
        raw = read(HERE / "jev-latest" / run / "decisions-raw.json")
        for slot, value in raw.items():
            if not slot.startswith("persona:"):
                continue
            for answer_id, ans in value["ratings"]["answers"].items():
                cond = condition[answer_id]
                mass[cond].update(ans["probabilities"])
                counts[cond] += 1
    return {cond: {r: round(mass[cond][r] / counts[cond], 3) for r in RATINGS} for cond in CONDITIONS}


def markdown(summary, cases, soft):
    lines = []
    lines.append("## 条件別の評定（3名×64回答＝192評定）\n")
    lines.append("| 判定者 | 条件 | 釣り合い | 足りない | 重すぎる | 無神経 |")
    lines.append("|---|---|---|---|---|---|")
    for judge, out in summary.items():
        for cond in CONDITIONS:
            d = out["by_condition"][cond]
            lines.append(f"| {out['label']} | {COND_JA[cond]} | {d['fit']} | {d['light']} | {d['heavy']} | {d['rude']} |")
    lines.append("\n## 筆者との一致（192回答）\n")
    lines.append("| 判定者 | 多数決の完全一致 | 多数決なし | κ（4分類） | κ（釣り合い/それ以外） | 各ペルソナ一致 | 既存判定者とのκ | ペルソナ間 Fleiss κ | 3名一致 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for judge, out in summary.items():
        a = out["agreement_author"]
        e = out.get("agreement_existing", {})
        lines.append(f"| {out['label']} | {a['majority_exact']} | {a['no_majority']} | {a['kappa_majority']} | {a['kappa_fit_vs_not']} | "
                     f"{'/'.join(map(str, a['per_persona_exact']))} | {e.get('kappa_majority', '—')} | {out['inter_persona_fleiss']} | {out['unanimous']} |")
    lines.append("\n## 筆者の評定別の、判定者多数決の内訳\n")
    for judge, out in summary.items():
        lines.append(f"- {out['label']}: " + "; ".join(f"筆者 {u} → {out['confusion_author_rows'][u]}" for u in RATINGS))
    lines.append("\n## 知覚段階（平均、設計上の段階別）\n")
    lines.append("| 判定者 | 0 | 1 | 2 | 3 | 4 | 修復期 | 筆者と一致 | 設計と一致 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for judge, out in summary.items():
        m = out["perceived_mean_by_design"]
        lines.append(f"| {out['label']} | " + " | ".join(str(m[lv]) for lv in LEVELS) +
                     f" | {out['perceived_match_author']} | {out['perceived_match_design']} |")
    lines.append("\n## 84項目チェック\n")
    lines.append("| 判定者 | 条件 | 該当/判定可能 | 該当率 | 観測不能 | 適用外 | 多い項目 |")
    lines.append("|---|---|---|---|---|---|---|")
    for judge, out in summary.items():
        for cond in CONDITIONS:
            c = out["checklist"][cond]
            top = "、".join(f"{k}({v})" for k, v in c["top"])
            lines.append(f"| {out['label']} | {COND_JA[cond]} | {c['hit']}/{c['assessable']} | {c['rate']}% | {c['unobservable']} | {c['not_applicable']} | {top} |")
    lines.append("\n| 判定者 | 該当0件の回答 | 段階0・修復期の該当数 | 筆者評定別の平均該当数 (rude/light/fit/heavy) | 既存とのκ（該当/非該当） | 両方該当 | この判定者のみ | 既存のみ |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for judge, out in summary.items():
        h = out["checklist_mean_hits_by_author"]
        v = out.get("checklist_vs_existing", {})
        lines.append(f"| {out['label']} | {out['checklist_hits_zero_answers']} | {out['checklist_hits_level0_repair']} | "
                     f"{h['rude']}/{h['light']}/{h['fit']}/{h['heavy']} | {v.get('kappa_hit', '—')} | {v.get('both_hit', '—')} | {v.get('this_only', '—')} | {v.get('existing_only', '—')} |")
    lines.append("\n## 代表場面\n")
    for name, rows in cases.items():
        lines.append(f"### {name}\n")
        lines.append("| 生成モデル | 条件 | 筆者 | " + " | ".join(JUDGES[j] for j in JUDGES) + " |")
        lines.append("|---|---|---|" + "---|" * len(JUDGES))
        for r in rows:
            cells = [f"{r[j]}{'＋10.06' if r[j + ':10.06'] else ''}" for j in JUDGES]
            lines.append(f"| {r['run']} | {COND_JA[r['condition']]} | {r['author']} | " + " | ".join(cells) + " |")
        lines.append("")
    lines.append("## Jev の確率の平均（多数決でなく確率で見た評定）\n")
    lines.append("| 条件 | rude | light | fit | heavy |")
    lines.append("|---|---|---|---|---|")
    for cond in CONDITIONS:
        lines.append(f"| {COND_JA[cond]} | " + " | ".join(str(soft[cond][r]) for r in RATINGS) + " |")
    return "\n".join(lines) + "\n"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    answers, scenarios, judged = load()
    summary = summarize(answers, scenarios, judged)
    cases = signature_cases(answers, judged)
    soft = jev_soft(answers)
    (HERE / "summary.md").write_text(markdown(summary, cases, soft), encoding="utf-8")
    print(json.dumps({"judges": summary, "signature_cases": cases, "jev_soft": soft}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
