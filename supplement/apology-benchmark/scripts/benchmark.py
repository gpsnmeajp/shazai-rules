"""Generate and score a blinded, level-calibrated apology benchmark on multi-turn conversations."""

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
POSTURE = (
    "日本語の対話で相手の負担や失望を受け止める姿勢を取る。"
    "自分にある責任を具体的に認め、相手と状況に釣り合う言葉で謝る。"
    "言い訳や許しの要求を控え、関係の修復を急がない。"
    "対応策は相手の負担と実行可能性を踏まえ、必要に応じて述べる。"
)
FIXED_CONDITIONS = ("baseline", "japanese_posture")
LEVELS = ("0", "1", "2", "3", "4", "repair")
PERCEIVED = ("0", "1", "2", "3", "4")
RATINGS = ("rude", "light", "fit", "heavy")
CHECK_STATES = ("hit", "clear", "unobservable", "not_applicable")
ROLES = ("user", "assistant")
NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
BASE = Path(__file__).resolve().parent


def resource(*candidates):
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ValueError(f"{candidates[0].name} が見つかりません")


CHECKLIST = lambda: resource(BASE.parent / "references/checklist.md", BASE / "checklist.md")
TEMPLATE = lambda: resource(BASE.parent / "assets/review.html", BASE / "review.html")
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


def validate_spec(spec):
    if not nonempty(spec.get("model")):
        raise ValueError("model は空にできません")
    prompts = spec.get("prompts")
    if not isinstance(prompts, dict) or not prompts:
        raise ValueError("prompts に評価対象プロンプトを1件以上指定してください")
    for name, text in prompts.items():
        if not NAME.match(name) or name in FIXED_CONDITIONS or not nonempty(text):
            raise ValueError(f"prompts の条件名または本文が不正です（{name}）")
    scenarios = spec.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenarios にシナリオを指定してください")
    seen = set()
    for index, item in enumerate(scenarios, 1):
        messages = item.get("messages")
        if str(item.get("level")) not in LEVELS:
            raise ValueError(f"シナリオ{index} の level は {', '.join(LEVELS)} のいずれかです")
        if not isinstance(messages, list) or not messages:
            raise ValueError(f"シナリオ{index} に messages がありません")
        for message in messages:
            if set(message) != {"role", "content"} or message["role"] not in ROLES or not nonempty(message["content"]):
                raise ValueError(f"シナリオ{index} の messages が不正です")
        if messages[-1]["role"] != "user":
            raise ValueError(f"シナリオ{index} はユーザーの発話で終えてください")
        key = json.dumps(messages, ensure_ascii=False)
        if key in seen:
            raise ValueError("重複するシナリオがあります")
        seen.add(key)
    return (*FIXED_CONDITIONS, *prompts)


def instruction_for(spec, condition):
    if condition == "baseline":
        return None
    if condition == "japanese_posture":
        return POSTURE
    return spec["prompts"][condition]


def request_completion(key, model, history, instruction):
    messages = [dict(message) for message in history]
    if instruction is not None:
        messages.insert(0, {"role": "system", "content": instruction})
    body = {"model": model, "messages": messages, "stream": False}
    request = Request(ENDPOINT, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    })
    try:
        with urlopen(request, timeout=120) as response:
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
    conditions = validate_spec(spec)
    scenarios = spec["scenarios"]
    template = TEMPLATE().read_text(encoding="utf-8")
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = run_dir / "checkpoint.json"
    state = read(checkpoint) if checkpoint.exists() else {
        "spec": spec, "run_id": uuid4().hex, "posture": POSTURE, "responses": {},
    }
    if state["spec"] != spec:
        raise ValueError("入力が既存の実行と異なります。新しい実行先を使ってください")
    if state["posture"] != POSTURE:
        raise ValueError("一般的な謝罪指示の文面が既存の実行と異なります")
    responses = state["responses"]
    tasks = [
        (f"{index}:{condition}", item["messages"], instruction_for(spec, condition))
        for index, item in enumerate(scenarios)
        for condition in conditions
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
                executor.submit(request_completion, key, spec["model"], history, instruction): slot
                for slot, history, instruction in tasks
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
        mapping, levels = {}, {}
        for index, item in enumerate(scenarios):
            scenario_id = uuid4().hex
            levels[scenario_id] = str(item["level"])
            answers = []
            for condition in conditions:
                response = responses[f"{index}:{condition}"]
                answer_id = response["answer_id"]
                answers.append({"id": answer_id, "text": response["text"]})
                mapping[answer_id] = {
                    "condition": condition, "scenario": scenario_id, "level": str(item["level"]),
                    "completion": {k: v for k, v in response.items() if k not in ("answer_id", "text")},
                }
            RANDOM.shuffle(answers)
            public["scenarios"].append({"id": scenario_id, "messages": item["messages"], "answers": answers})
        RANDOM.shuffle(public["scenarios"])
        manifest = {
            "public": public, "mapping": mapping, "levels": levels, "conditions": list(conditions),
            "model": spec["model"], "prompts": spec["prompts"], "japanese_posture": POSTURE,
        }
        save(manifest_path, manifest)
    embedded = json.dumps(manifest["public"], ensure_ascii=False).replace("<", "\\u003c")
    write(run_dir / "review.html", template.replace("__BENCHMARK_DATA__", embedded, 1))


def load_manifest(manifest_path):
    manifest = read(manifest_path)
    public, mapping, levels = manifest["public"], manifest["mapping"], manifest["levels"]
    conditions = manifest["conditions"]
    ids = [answer["id"] for scenario in public["scenarios"] for answer in scenario["answers"]]
    scenario_ids = [scenario["id"] for scenario in public["scenarios"]]
    if len(ids) != len(set(ids)) or set(mapping) != set(ids):
        raise ValueError("回答IDと条件対応表が一致しません")
    if len(scenario_ids) != len(set(scenario_ids)) or set(levels) != set(scenario_ids):
        raise ValueError("シナリオIDと段階表が一致しません")
    for scenario in public["scenarios"]:
        entries = [mapping[answer["id"]] for answer in scenario["answers"]]
        if Counter(entry["condition"] for entry in entries) != Counter(conditions):
            raise ValueError("各シナリオに全条件の回答が必要です")
        if any(entry["scenario"] != scenario["id"] or entry["level"] != levels[scenario["id"]] for entry in entries):
            raise ValueError("回答とシナリオの対応が不正です")
        if levels[scenario["id"]] not in LEVELS:
            raise ValueError("シナリオの段階が不正です")
    return manifest, ids, scenario_ids


def load_ratings(path, run_id, answer_ids, scenario_ids):
    data = read(path)
    ratings, perceived = data["ratings"], data["levels"]
    if data["run_id"] != run_id:
        raise ValueError(f"{Path(path).name} の実行IDが一致しません")
    if not isinstance(ratings, dict) or set(ratings) != answer_ids:
        raise ValueError(f"{Path(path).name} の回答IDが一致しません")
    if not isinstance(perceived, dict) or set(perceived) != scenario_ids:
        raise ValueError(f"{Path(path).name} のシナリオIDが一致しません")
    for entry in ratings.values():
        if entry["rating"] not in RATINGS or not isinstance(entry["comment"], str):
            raise ValueError(f"{Path(path).name} の評定またはコメントが不正です")
    if any(value not in PERCEIVED for value in perceived.values()):
        raise ValueError(f"{Path(path).name} の不満段階が不正です")
    return data


def selections(manifest):
    mapping = manifest["mapping"]
    present = [level for level in LEVELS if level in manifest["levels"].values()]
    for level in ("all", *present):
        for condition in manifest["conditions"]:
            yield level, condition, [
                answer_id for answer_id, entry in mapping.items()
                if entry["condition"] == condition and level in ("all", entry["level"])
            ]


def check(manifest_path, user_path, persona_paths):
    persona_files = {Path(path).resolve() for path in persona_paths}
    if persona_paths and (len(persona_paths) != 3 or len(persona_files) != 3):
        raise ValueError("ペルソナ評定には3名分の個別ファイルが必要です")
    if Path(user_path).resolve() in persona_files:
        raise ValueError("ユーザー評定とペルソナ評定には別のファイルを指定してください")
    manifest, ids, scenario_ids = load_manifest(manifest_path)
    run_id = manifest["public"]["run_id"]
    user = load_ratings(user_path, run_id, set(ids), set(scenario_ids))
    panel = [load_ratings(path, run_id, set(ids), set(scenario_ids)) for path in persona_paths]
    summaries = []
    for level, condition, selection in selections(manifest):
        user_counts = Counter(user["ratings"][i]["rating"] for i in selection)
        panel_counts = Counter(p["ratings"][i]["rating"] for p in panel for i in selection)
        summaries.append({
            "level": level, "condition": condition, "answers": len(selection),
            "user": {rating: user_counts[rating] for rating in RATINGS},
            "personas": {rating: panel_counts[rating] for rating in RATINGS},
        })
    perceived = {
        scenario_id: {
            "design": manifest["levels"][scenario_id],
            "user": user["levels"][scenario_id],
            "personas": [p["levels"][scenario_id] for p in panel],
        }
        for scenario_id in scenario_ids
    }
    result = {
        "run_id": run_id, "answers": len(ids), "scenarios": len(scenario_ids),
        "conditions": manifest["conditions"], "summaries": summaries, "perceived_levels": perceived,
        "exact_matches_by_persona": [
            sum(user["ratings"][i]["rating"] == p["ratings"][i]["rating"] for i in ids) for p in panel
        ],
    }
    if len(panel) == 3:
        majority = {}
        for answer_id in ids:
            rating, votes = Counter(p["ratings"][answer_id]["rating"] for p in panel).most_common(1)[0]
            majority[answer_id] = rating if votes >= 2 else None
        result.update({
            "majority": majority,
            "majority_exact_matches": sum(majority[i] == user["ratings"][i]["rating"] for i in ids),
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
    manifest, ids, _ = load_manifest(manifest_path)
    item_ids = re.findall(r"^- (\d{2}\.\d{2}) ", CHECKLIST().read_text(encoding="utf-8"), re.M)
    if len(item_ids) != 84 or len(set(item_ids)) != 84:
        raise ValueError("チェックリスト原文の項目IDは重複のない84個である必要があります")
    checks = load_checklists(paths, manifest["public"]["run_id"], set(ids), item_ids)
    answer_results, states = {}, {}
    for answer_id in ids:
        entry = checks[answer_id]
        answer_results[answer_id] = {
            "counts": {state: len(entry[state]) for state in CHECK_STATES},
            "findings": entry["hit"],
        }
        states[answer_id] = {item: state for state in CHECK_STATES for item in entry[state]}
    summaries = []
    for level, condition, selection in selections(manifest):
        items = {}
        for item in item_ids:
            counts = Counter(states[answer_id][item] for answer_id in selection)
            items[item] = {
                **{state: counts[state] for state in CHECK_STATES},
                "assessable": counts["hit"] + counts["clear"],
            }
        summaries.append({"level": level, "condition": condition, "answers": len(selection), "items": items})
    result = {
        "run_id": manifest["public"]["run_id"], "items_per_answer": len(item_ids),
        "answers": answer_results, "summaries": summaries,
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validation = commands.add_parser("validate")
    validation.add_argument("input", type=Path)
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
        if args.command == "validate":
            spec = read(args.input)
            conditions = validate_spec(spec)
            counts = Counter(str(item["level"]) for item in spec["scenarios"])
            print(json.dumps({
                "model": spec["model"], "conditions": list(conditions),
                "scenarios": len(spec["scenarios"]), "levels": {k: counts[k] for k in LEVELS if counts[k]},
                "answers": len(spec["scenarios"]) * len(conditions),
            }, ensure_ascii=False))
        elif args.command == "generate":
            generate(args.input, args.run_dir)
        elif args.command == "check":
            check(args.manifest, args.user, args.personas)
        else:
            summarize_checklists(args.manifest, args.judgments)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        print(f"処理を完了できませんでした。{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
