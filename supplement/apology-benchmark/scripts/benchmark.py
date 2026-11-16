"""Generate and score a blinded, three-condition apology benchmark."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
from random import SystemRandom
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
COMMON = "以下の状況で、応答者として相手にそのまま返す発話だけを日本語で書いてください。"
POSTURE = (
    "日本語の対話で相手の負担や失望を受け止める姿勢を取る。"
    "自分にある責任を具体的に認め、相手と状況に釣り合う言葉で謝る。"
    "言い訳や許しの要求を控え、関係の修復を急がない。"
    "対応策は相手の負担と実行可能性を踏まえ、必要に応じて述べる。"
)
CONDITIONS = ("baseline", "japanese_posture", "custom_prompt")
GROUPS = ("related", "general")
RATINGS = ("none", "surface", "enough", "excess")
CHECK_STATES = ("hit", "clear", "unobservable", "not_applicable")
CHECKLIST = Path(__file__).resolve().parents[1] / "references/checklist.md"
TEMPLATE = Path(__file__).resolve().parents[1] / "assets/review.html"
RANDOM = SystemRandom()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSONに重複したキーがあります")
        result[key] = value
    return result


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def write(path, value):
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def save(path, data):
    write(path, json.dumps(data, ensure_ascii=False, indent=2))


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def request_completion(key, model, scenario, instruction):
    messages = [{"role": "user", "content": f"{COMMON}\n\n{scenario}"}]
    if instruction is not None:
        messages.insert(0, {"role": "system", "content": instruction})
    body = {"model": model, "messages": messages, "stream": False}
    request = Request(ENDPOINT, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    })
    try:
        with urlopen(request, timeout=90) as response:
            result = json.load(response)
    except HTTPError as error:
        raise ValueError(f"OpenRouter HTTP {error.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ValueError("OpenRouterとの通信に失敗しました") from None
    try:
        choice = result["choices"][0]
        content = choice["message"]["content"]
        if choice["finish_reason"] != "stop" or not nonempty(content):
            raise ValueError
    except (KeyError, IndexError, TypeError, ValueError):
        raise ValueError("OpenRouterから完全な応答を取得できませんでした") from None
    return {field: result.get(field) for field in ("id", "model", "provider", "usage")} | {
        "text": content,
    }


def generate(input_path, run_dir):
    spec = read(input_path)
    scenarios = spec["scenarios"]
    if not nonempty(spec["model"]) or not nonempty(spec["apology_prompt"]):
        raise ValueError("model と apology_prompt は空にできません")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenarios にシナリオを指定してください")
    if any(item["group"] not in GROUPS or not nonempty(item["text"]) for item in scenarios):
        raise ValueError("シナリオの group または text が不正です")
    if len({item["text"].strip() for item in scenarios}) != len(scenarios):
        raise ValueError("重複するシナリオがあります")
    template_path = TEMPLATE if TEMPLATE.is_file() else Path(__file__).with_name("review.html")
    template = template_path.read_text(encoding="utf-8")
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = run_dir / "checkpoint.json"
    state = read(checkpoint) if checkpoint.exists() else {
        "spec": spec, "run_id": uuid4().hex, "responses": {},
    }
    if state["spec"] != spec:
        raise ValueError("入力が既存の実行と異なります。新しい実行先を使ってください")
    responses = state["responses"]
    instructions = (None, POSTURE, spec["apology_prompt"])
    if state.get("posture", POSTURE) != POSTURE:
        raise ValueError("日本人的姿勢の指示文が既存の実行と異なります")
    state["posture"] = POSTURE
    tasks = [
        (f"{index}:{condition}", item["text"], instruction)
        for index, item in enumerate(scenarios)
        for condition, instruction in zip(CONDITIONS, instructions)
        if f"{index}:{condition}" not in responses
    ]
    if tasks:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("OPENROUTER_API_KEY が設定されていません")
        RANDOM.shuffle(tasks)
        failures = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            pending = {
                executor.submit(request_completion, key, spec["model"], scenario, instruction): slot
                for slot, scenario, instruction in tasks
            }
            for future in as_completed(pending):
                slot = pending[future]
                try:
                    result = future.result()
                except ValueError as error:
                    failures.append(str(error))
                    continue
                responses[slot] = {"answer_id": uuid4().hex, **result}
                save(checkpoint, state)
        if failures:
            errors = "、".join(sorted(set(failures)))
            raise ValueError(f"{len(failures)} 件の生成に失敗しました（{errors}）。同一入力と実行先で再開できます")
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        manifest = read(manifest_path)
        if manifest["public"]["run_id"] != state["run_id"]:
            raise ValueError("マニフェストと生成記録の実行IDが一致しません")
    else:
        public = {"run_id": state["run_id"], "scenarios": []}
        mapping = {}
        for index, item in enumerate(scenarios):
            answers = []
            for condition in CONDITIONS:
                response = responses[f"{index}:{condition}"]
                answer_id = response["answer_id"]
                answers.append({"id": answer_id, "text": response["text"]})
                mapping[answer_id] = {
                    "condition": condition,
                    "group": item["group"],
                    "completion": {k: v for k, v in response.items() if k not in ("answer_id", "text")},
                }
            RANDOM.shuffle(answers)
            public["scenarios"].append({"text": item["text"], "answers": answers})
        RANDOM.shuffle(public["scenarios"])
        manifest = {
            "public": public, "mapping": mapping, "model": spec["model"],
            "apology_prompt": spec["apology_prompt"], "japanese_posture": POSTURE,
        }
        save(manifest_path, manifest)
    embedded = json.dumps(manifest["public"], ensure_ascii=False).replace("<", "\\u003c")
    write(run_dir / "review.html", template.replace("__BENCHMARK_DATA__", embedded, 1))


def load_ratings(path, run_id, answer_ids):
    data = read(path)
    ratings = data["ratings"]
    if data["run_id"] != run_id or not isinstance(ratings, dict) or set(ratings) != answer_ids:
        raise ValueError(f"{Path(path).name} の実行IDまたは回答IDが一致しません")
    for entry in ratings.values():
        if entry["rating"] not in RATINGS or not isinstance(entry["comment"], str):
            raise ValueError(f"{Path(path).name} の評定またはコメントが不正です")
    return ratings


def load_manifest(manifest_path):
    manifest = read(manifest_path)
    public = manifest["public"]
    ids = [answer["id"] for scenario in public["scenarios"] for answer in scenario["answers"]]
    answer_ids = set(ids)
    mapping = manifest["mapping"]
    if len(ids) != len(answer_ids) or set(mapping) != answer_ids:
        raise ValueError("回答IDと条件対応表が一致しません")
    for scenario in public["scenarios"]:
        entries = [mapping[answer["id"]] for answer in scenario["answers"]]
        if Counter(entry["condition"] for entry in entries) != Counter(CONDITIONS):
            raise ValueError("各シナリオに3条件が必要です")
        groups = {entry["group"] for entry in entries}
        if len(groups) != 1 or not groups.issubset(GROUPS):
            raise ValueError("シナリオの区分が不正です")
    return public, mapping, ids


def check(manifest_path, user_path, persona_paths):
    persona_files = {Path(path).resolve() for path in persona_paths}
    if persona_paths and (len(persona_paths) != 3 or len(persona_files) != 3):
        raise ValueError("ペルソナ評定には3名分の個別ファイルが必要です")
    if Path(user_path).resolve() in persona_files:
        raise ValueError("ユーザー評定とペルソナ評定には別のファイルを指定してください")
    public, mapping, ids = load_manifest(manifest_path)
    answer_ids = set(ids)
    user = load_ratings(user_path, public["run_id"], answer_ids)
    panel = [load_ratings(path, public["run_id"], answer_ids) for path in persona_paths]
    summaries = []
    for group in ("all", *GROUPS):
        for condition in CONDITIONS:
            selection = [
                answer_id for answer_id, entry in mapping.items()
                if entry["condition"] == condition and group in ("all", entry["group"])
            ]
            user_counts = Counter(user[answer_id]["rating"] for answer_id in selection)
            panel_counts = Counter(p[answer_id]["rating"] for p in panel for answer_id in selection)
            summaries.append({
                "group": group, "condition": condition,
                "user": {rating: user_counts[rating] for rating in RATINGS},
                "personas": {rating: panel_counts[rating] for rating in RATINGS},
            })
    agreement = [
        sum(user[answer_id]["rating"] == p[answer_id]["rating"] for answer_id in ids)
        for p in panel
    ]
    majority = {}
    if len(panel) == 3:
        for answer_id in ids:
            rating, votes = Counter(p[answer_id]["rating"] for p in panel).most_common(1)[0]
            majority[answer_id] = rating if votes >= 2 else None
    result = {
        "run_id": public["run_id"], "answers": len(ids), "summaries": summaries,
        "exact_matches_by_persona": agreement,
    }
    if majority:
        result.update({
            "majority": majority,
            "majority_exact_matches": sum(majority[i] == user[i]["rating"] for i in ids),
            "no_majority": sum(majority[i] is None for i in ids),
        })
    print(json.dumps(result, ensure_ascii=False, indent=2))


def load_checklists(paths, run_id, answer_ids, item_ids):
    checks = {}
    for path in paths:
        data = read(path)
        entries = data["checks"]
        if data["run_id"] != run_id or not isinstance(entries, dict):
            raise ValueError(f"{path.name} の実行IDまたはチェックリスト形式が不正です")
        for answer_id, entry in entries.items():
            if answer_id not in answer_ids or answer_id in checks:
                raise ValueError(f"{path.name} の回答ID {answer_id} が不明または重複しています")
            if not isinstance(entry, dict) or set(entry) != set(CHECK_STATES):
                raise ValueError(f"{answer_id} のチェックリスト判定区分が不正です")
            hits = entry["hit"]
            if not isinstance(hits, dict) or any(not nonempty(reason) for reason in hits.values()):
                raise ValueError(f"{answer_id} の該当項目に根拠が必要です")
            seen = list(hits)
            for state in CHECK_STATES[1:]:
                values = entry[state]
                if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
                    raise ValueError(f"{answer_id} の {state} には項目IDの配列が必要です")
                seen.extend(values)
            if len(seen) != len(item_ids) or set(seen) != set(item_ids):
                raise ValueError(f"{answer_id} の項目IDに過不足または重複があります")
            checks[answer_id] = entry
    missing = answer_ids - checks.keys()
    if missing:
        raise ValueError(f"チェックリスト判定がない回答ID {', '.join(sorted(missing))}")
    return checks


def summarize_checklists(manifest_path, paths):
    public, mapping, ids = load_manifest(manifest_path)
    item_ids = re.findall(r"^- (\d{2}\.\d{2}) ", CHECKLIST.read_text(encoding="utf-8"), re.M)
    if len(item_ids) != 84 or len(set(item_ids)) != 84:
        raise ValueError("チェックリスト原文の項目IDは重複のない84個である必要があります")
    checks = load_checklists(paths, public["run_id"], set(ids), item_ids)
    answer_results = {}
    item_counts = {}
    for answer_id in ids:
        entry = checks[answer_id]
        answer_results[answer_id] = {
            "counts": {state: len(entry[state]) for state in CHECK_STATES},
            "findings": entry["hit"],
        }
        item_counts[answer_id] = {
            item: state for state in CHECK_STATES for item in entry[state]
        }
    summaries = []
    for group in ("all", *GROUPS):
        for condition in CONDITIONS:
            selection = [
                answer_id for answer_id, entry in mapping.items()
                if entry["condition"] == condition and group in ("all", entry["group"])
            ]
            items = {}
            for item in item_ids:
                counts = Counter(item_counts[answer_id][item] for answer_id in selection)
                items[item] = {
                    **{state: counts[state] for state in CHECK_STATES},
                    "assessable": counts["hit"] + counts["clear"],
                }
            summaries.append({
                "group": group, "condition": condition,
                "answers": len(selection), "items": items,
            })
    result = {
        "run_id": public["run_id"], "items_per_answer": len(item_ids),
        "answers": answer_results, "summaries": summaries,
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generation = commands.add_parser("generate")
    generation.add_argument("input", type=Path)
    generation.add_argument("run_dir", type=Path)
    scoring = commands.add_parser("check")
    scoring.add_argument("manifest")
    scoring.add_argument("user")
    scoring.add_argument("personas", nargs="*")
    checklist = commands.add_parser("checklist")
    checklist.add_argument("manifest", type=Path)
    checklist.add_argument("judgments", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        if args.command == "generate":
            generate(args.input, args.run_dir)
        elif args.command == "check":
            check(args.manifest, args.user, args.personas)
        else:
            summarize_checklists(args.manifest, args.judgments)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"処理を完了できませんでした。{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
