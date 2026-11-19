"""Generate and score a blinded apology benchmark on multi-turn conversations with optional tools."""

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
AXES = {"weight": ("light", "fit", "heavy"), "task": ("under", "fit", "over")}
FLAGS = ("rude", "defect")
CHECK_STATES = ("hit", "clear", "unobservable", "not_applicable")
NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
DEFECT_HINTS = re.compile(
    r"この(会話|セッション|チャット)(の中)?(に|で)は.{0,20}(含まれ|共有され|渡され)"
    r"|持ち越せ|参照する手段"
    r"|実際には.{0,20}(読んで|見て|確認して|実行して)(い|お)(ない|ません|りません)"
)
BASE = Path(__file__).resolve().parent


def resource(*candidates):
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ValueError(f"{candidates[0].name} が見つかりません")


CHECKLIST = lambda: resource(BASE.parent / "references/checklist.md", BASE / "checklist.md")
TEMPLATE = lambda: resource(BASE.parent / "assets/review.html", BASE / "review.html")
SCALE = lambda: resource(BASE.parent / "references/scale.json", BASE / "scale.json")
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


def load_scale():
    scale = read(SCALE())
    values = lambda choices: tuple(choice["value"] for choice in choices)
    axes = {axis["id"]: values(axis["choices"]) for axis in scale["axes"]}
    flags = tuple(flag["id"] for flag in scale["flags"])
    if values(scale["level"]["choices"]) != PERCEIVED or axes != AXES or flags != FLAGS:
        raise ValueError("scale.json の段階・評定軸・印が集計スクリプトの定義と一致しません")
    return scale


def validate_scenario(index, item):
    def fail(reason):
        raise ValueError(f"シナリオ{index} の{reason}")

    if not isinstance(item, dict) or set(item) - {"level", "system", "tools", "messages"}:
        fail("項目が不正です")
    if str(item.get("level")) not in LEVELS:
        fail(f" level は {', '.join(LEVELS)} のいずれかです")
    if "system" in item and not nonempty(item["system"]):
        fail(" system が空です")
    names = set()
    if "tools" in item:
        if not isinstance(item["tools"], list) or not item["tools"]:
            fail(" tools が不正です")
        for tool in item["tools"]:
            function = tool.get("function") if isinstance(tool, dict) else None
            if tool.get("type") != "function" or not isinstance(function, dict) or not nonempty(function.get("name")):
                fail(" tools が不正です")
            if function["name"] in names:
                fail(" tools に同じ名前があります")
            names.add(function["name"])
    messages = item.get("messages")
    if not isinstance(messages, list) or not messages:
        fail(" messages がありません")
    pending, used, previous = set(), set(), None
    for message in messages:
        role = message.get("role") if isinstance(message, dict) else None
        if role == "tool":
            if set(message) != {"role", "tool_call_id", "content"} or not nonempty(message["content"]):
                fail("ツール結果が不正です")
            if message["tool_call_id"] not in pending:
                fail("ツール結果に対応する呼び出しがありません")
            pending.remove(message["tool_call_id"])
        elif pending:
            fail("ツール呼び出しに結果がありません")
        elif role == "user":
            if set(message) != {"role", "content"} or not nonempty(message["content"]) or previous not in (None, "assistant"):
                fail("ユーザーの発話が不正です")
        elif role == "assistant":
            calls = message.get("tool_calls")
            if previous == "assistant" or "content" not in message or set(message) - {"role", "content", "tool_calls"}:
                fail(" AI の発話が不正です")
            if calls is None:
                if not nonempty(message["content"]):
                    fail(" AI の発話が空です")
                calls = []
            elif not isinstance(calls, list) or not calls or not (message["content"] is None or isinstance(message["content"], str)):
                fail("ツール呼び出しが不正です")
            for call in calls:
                function = call.get("function") if isinstance(call, dict) else None
                if set(call) != {"id", "type", "function"} or call["type"] != "function" or not nonempty(call["id"]):
                    fail("ツール呼び出しが不正です")
                if not isinstance(function, dict) or set(function) != {"name", "arguments"} or function["name"] not in names:
                    fail("ツール呼び出しが tools にないツールを指しています")
                try:
                    arguments = json.loads(function["arguments"])
                except (TypeError, ValueError):
                    arguments = None
                if not isinstance(arguments, dict) or call["id"] in used:
                    fail("ツール呼び出しの引数またはIDが不正です")
                used.add(call["id"])
                pending.add(call["id"])
        else:
            fail(" messages が不正です")
        previous = role
    if pending or messages[0]["role"] != "user" or messages[-1]["role"] != "user":
        fail("会話はユーザーの発話で始め、ユーザーの発話で終えてください")


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
        validate_scenario(index, item)
        key = json.dumps([item.get("system"), item["messages"]], ensure_ascii=False)
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


def request_completion(key, model, item, instruction):
    messages = [dict(message) for message in item["messages"]]
    system = "\n\n".join(part for part in (item.get("system"), instruction) if part)
    if system:
        messages.insert(0, {"role": "system", "content": system})
    body = {"model": model, "messages": messages, "stream": False}
    if "tools" in item:
        body["tools"] = item["tools"]
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
        text = choice["message"].get("content") or ""
        calls = [
            {"name": call["function"]["name"], "arguments": call["function"]["arguments"]}
            for call in choice["message"].get("tool_calls") or []
        ]
        if choice["finish_reason"] not in ("stop", "tool_calls") or not isinstance(text, str):
            raise ValueError
        if not (text.strip() or calls) or any(not nonempty(call["name"]) or not isinstance(call["arguments"], str) for call in calls):
            raise ValueError
    except (KeyError, IndexError, TypeError, AttributeError, ValueError):
        raise ValueError("OpenRouterから完全な応答を取得できませんでした") from None
    return {field: result.get(field) for field in ("id", "model", "provider", "usage")} | {
        "text": text, "tool_calls": calls,
    }


def generate(input_path, run_dir):
    spec = read(input_path)
    conditions = validate_spec(spec)
    scenarios = spec["scenarios"]
    scale = load_scale()
    template = TEMPLATE().read_text(encoding="utf-8")
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = run_dir / "checkpoint.json"
    state = read(checkpoint) if checkpoint.exists() else {
        "spec": spec, "run_id": uuid4().hex, "posture": POSTURE, "scale": scale, "responses": {},
    }
    if state["spec"] != spec:
        raise ValueError("入力が既存の実行と異なります。新しい実行先を使ってください")
    if state["posture"] != POSTURE or state["scale"] != scale:
        raise ValueError("一般的な謝罪指示または尺度の文面が既存の実行と異なります")
    responses = state["responses"]
    tasks = [
        (f"{index}:{condition}", item, instruction_for(spec, condition))
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
                executor.submit(request_completion, key, spec["model"], item, instruction): slot
                for slot, item, instruction in tasks
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
        public = {"run_id": state["run_id"], "scale": scale, "scenarios": []}
        mapping, levels, candidates = {}, {}, []
        for index, item in enumerate(scenarios):
            scenario_id = uuid4().hex
            levels[scenario_id] = str(item["level"])
            answers = []
            for condition in conditions:
                response = responses[f"{index}:{condition}"]
                answer_id = response["answer_id"]
                answers.append({"id": answer_id, "text": response["text"], "tool_calls": response["tool_calls"]})
                mapping[answer_id] = {
                    "condition": condition, "scenario": scenario_id, "level": str(item["level"]),
                    "completion": {k: v for k, v in response.items() if k not in ("answer_id", "text", "tool_calls")},
                }
                if DEFECT_HINTS.search(response["text"]):
                    candidates.append(answer_id)
            RANDOM.shuffle(answers)
            scenario = {"id": scenario_id, "messages": item["messages"], "answers": answers}
            if "system" in item:
                scenario["system"] = item["system"]
            if "tools" in item:
                scenario["tools"] = [
                    {"name": tool["function"]["name"], "description": tool["function"].get("description", "")}
                    for tool in item["tools"]
                ]
            public["scenarios"].append(scenario)
        RANDOM.shuffle(public["scenarios"])
        manifest = {
            "public": public, "mapping": mapping, "levels": levels, "conditions": list(conditions),
            "defect_candidates": candidates,
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


def scale_text(scale):
    lines = [
        "# 評定の尺度", "", scale["intro"], "",
        f"## {scale['level']['label']}", "",
        "回答を読む前に、各シナリオについて次から一つ選ぶ。", "",
        *(f"- `{choice['value']}` {choice['label'].split(' ', 1)[1]}" for choice in scale["level"]["choices"]),
    ]
    for axis in scale["axes"]:
        lines += ["", f"## {axis['label']}（`{axis['id']}`）", "", "各回答について次から一つ選ぶ。", ""]
        lines += [f"- `{c['value']}` {c['label']}：{c['description']}" for c in axis["choices"]]
    lines += ["", "## 印", "", "各回答について、当てはまる場合に `true`、当てはまらない場合に `false` とする。", ""]
    lines += [f"- `{flag['id']}` {flag['label']}：{flag['description']}" for flag in scale["flags"]]
    example = {"run_id": "…", "levels": {"シナリオID": "2"}, "ratings": {"回答ID": {
        **{axis: "fit" for axis in AXES}, **{flag: False for flag in FLAGS}, "comment": "…",
    }}}
    lines += ["", "## 返すJSON", "", "```json", json.dumps(example, ensure_ascii=False), "```", ""]
    return "\n".join(lines)


def prepare(manifest_path, out_dir, parts):
    manifest, _, _ = load_manifest(manifest_path)
    public = manifest["public"]
    scenarios = public["scenarios"]
    if not 1 <= parts <= len(scenarios):
        raise ValueError("チェックリストの分割数が不正です")
    out_dir.mkdir(parents=True, exist_ok=True)
    write(out_dir / "persona-scale.md", scale_text(public["scale"]))
    for number in range(3):
        rotated = [
            {**scenario, "answers": scenario["answers"][number % len(scenario["answers"]):]
             + scenario["answers"][:number % len(scenario["answers"])]}
            for scenario in scenarios
        ]
        save(out_dir / f"persona-P{number + 1}-input.json", {"run_id": public["run_id"], "scenarios": rotated})
    for number in range(parts):
        save(out_dir / f"checklist-{number + 1}-input.json", {
            "run_id": public["run_id"], "scenarios": scenarios[number::parts],
        })


def load_ratings(path, run_id, answer_ids, scenario_ids):
    data = read(path)
    ratings, perceived = data["ratings"], data["levels"]
    name = Path(path).name
    if data["run_id"] != run_id:
        raise ValueError(f"{name} の実行IDが一致しません")
    if not isinstance(ratings, dict) or set(ratings) != answer_ids:
        raise ValueError(f"{name} の回答IDが一致しません")
    if not isinstance(perceived, dict) or set(perceived) != scenario_ids:
        raise ValueError(f"{name} のシナリオIDが一致しません")
    for entry in ratings.values():
        if not isinstance(entry, dict) or set(entry) != {*AXES, *FLAGS, "comment"}:
            raise ValueError(f"{name} の評定の項目が不正です")
        if any(entry[axis] not in values for axis, values in AXES.items()):
            raise ValueError(f"{name} の評定値が不正です")
        if any(not isinstance(entry[flag], bool) for flag in FLAGS) or not isinstance(entry["comment"], str):
            raise ValueError(f"{name} の印またはコメントが不正です")
    if any(value not in PERCEIVED for value in perceived.values()):
        raise ValueError(f"{name} の不満段階が不正です")
    return data


def passed(entry):
    return all(entry[axis] == "fit" for axis in AXES) and not entry["rude"]


def tally(entries):
    result = {"ratings": len(entries)}
    for axis, values in AXES.items():
        counts = Counter(entry[axis] for entry in entries)
        result[axis] = {value: counts[value] for value in values}
    result["rude"] = sum(entry["rude"] for entry in entries)
    result["pass"] = sum(passed(entry) for entry in entries)
    return result


def agreement(pairs, order):
    """Exact matches and linear-weighted kappa over pairs where both sides have a value."""
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    result = {"n": len(pairs), "exact": sum(a == b for a, b in pairs), "kappa": None}
    index = {value: position for position, value in enumerate(order)}
    cost = lambda a, b: abs(index[a] - index[b]) / (len(order) - 1)
    left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(left[a] * right[b] * cost(a, b) for a in left for b in right)
    if expected:
        observed = sum(cost(a, b) for a, b in pairs)
        result["kappa"] = round(1 - observed * len(pairs) / expected, 3)
    return result


def majority(values):
    value, votes = Counter(values).most_common(1)[0]
    return value if votes * 2 > len(values) else None


def compare(user, other, ids):
    fields = {axis: (lambda entry, axis=axis: entry[axis], values) for axis, values in AXES.items()}
    fields["rude"] = (lambda entry: entry["rude"], (False, True))
    fields["pass"] = (lambda entry: entry["pass"] if "pass" in entry else passed(entry), (False, True))
    return {"answers": len(ids)} | {
        name: agreement([(pick(user[i]), pick(other[i])) for i in ids], order)
        for name, (pick, order) in fields.items()
    }


def check(manifest_path, user_path, persona_paths):
    persona_files = {Path(path).resolve() for path in persona_paths}
    if persona_paths and (len(persona_paths) != 3 or len(persona_files) != 3):
        raise ValueError("ペルソナ評定には3名分の個別ファイルが必要です")
    if Path(user_path).resolve() in persona_files:
        raise ValueError("ユーザー評定とペルソナ評定には別のファイルを指定してください")
    manifest, ids, scenario_ids = load_manifest(manifest_path)
    mapping, design, conditions = manifest["mapping"], manifest["levels"], manifest["conditions"]
    run_id = manifest["public"]["run_id"]
    user = load_ratings(user_path, run_id, set(ids), set(scenario_ids))
    panel = [load_ratings(path, run_id, set(ids), set(scenario_ids)) for path in persona_paths]

    flagged = [i for i in ids if user["ratings"][i]["defect"]]
    excluded = sorted({mapping[i]["scenario"] for i in flagged})
    count_by_condition = lambda selection: {
        condition: sum(mapping[i]["condition"] == condition for i in selection) for condition in conditions
    }

    def summaries(basis, level_of, order):
        present = [level for level in order if level in {level_of(i) for i in ids}]
        for level in ("all", *present):
            for condition in conditions:
                selection = [
                    i for i in ids
                    if mapping[i]["condition"] == condition and level in ("all", level_of(i))
                ]
                kept = [i for i in selection if mapping[i]["scenario"] not in excluded]
                row = {"basis": basis, "level": level, "condition": condition}
                for name, chosen in (("all", selection), ("without_defects", kept)):
                    row[name] = {"user": tally([user["ratings"][i] for i in chosen])}
                    if panel:
                        row[name]["personas"] = tally([p["ratings"][i] for p in panel for i in chosen])
                yield row

    result = {
        "run_id": run_id, "answers": len(ids), "scenarios": len(scenario_ids), "conditions": conditions,
        "levels": {
            scenario_id: {
                "design": design[scenario_id], "user": user["levels"][scenario_id],
                "personas": [p["levels"][scenario_id] for p in panel],
            }
            for scenario_id in scenario_ids
        },
        "level_agreement": {
            "design_vs_user": agreement(
                [(design[s], user["levels"][s]) for s in scenario_ids if design[s] in PERCEIVED], PERCEIVED,
            ),
            "user_vs_personas": [
                agreement([(user["levels"][s], p["levels"][s]) for s in scenario_ids], PERCEIVED) for p in panel
            ],
        },
        "defects": {
            "user_flagged": count_by_condition(flagged),
            "candidates": count_by_condition(manifest.get("defect_candidates", [])),
            "excluded_scenarios": excluded,
        },
        "summaries": [
            *summaries("design", lambda i: mapping[i]["level"], LEVELS),
            *summaries("perceived", lambda i: user["levels"][mapping[i]["scenario"]], PERCEIVED),
        ],
        "agreement": [
            {"rater": f"P{number}", "scope": "all", **compare(user["ratings"], p["ratings"], ids)}
            for number, p in enumerate(panel, 1)
        ],
    }
    if len(panel) == 3:
        votes = {
            i: {
                **{axis: majority([p["ratings"][i][axis] for p in panel]) for axis in AXES},
                "rude": majority([p["ratings"][i]["rude"] for p in panel]),
                "pass": majority([passed(p["ratings"][i]) for p in panel]),
            }
            for i in ids
        }
        level_votes = {s: majority([p["levels"][s] for p in panel]) for s in scenario_ids}
        matched = [i for i in ids if level_votes[mapping[i]["scenario"]] == user["levels"][mapping[i]["scenario"]]]
        unmatched = [i for i in ids if i not in set(matched)]
        result["agreement"] += [
            {"rater": "majority", "scope": scope, **compare(user["ratings"], votes, selection)}
            for scope, selection in (("all", ids), ("level_matched", matched), ("level_unmatched", unmatched))
        ]
        result["majority"] = votes
        result["no_majority"] = {axis: sum(votes[i][axis] is None for i in ids) for axis in AXES}
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
    mapping = manifest["mapping"]
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
    present = [level for level in LEVELS if level in manifest["levels"].values()]
    for level in ("all", *present):
        for condition in manifest["conditions"]:
            selection = [
                i for i in ids
                if mapping[i]["condition"] == condition and level in ("all", mapping[i]["level"])
            ]
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
    preparation = commands.add_parser("prepare")
    preparation.add_argument("manifest", type=Path)
    preparation.add_argument("out_dir", type=Path)
    preparation.add_argument("--checklist-parts", type=int, default=2)
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
            load_scale()
            counts = Counter(str(item["level"]) for item in spec["scenarios"])
            print(json.dumps({
                "model": spec["model"], "conditions": list(conditions),
                "scenarios": len(spec["scenarios"]), "levels": {k: counts[k] for k in LEVELS if counts[k]},
                "with_system": sum("system" in item for item in spec["scenarios"]),
                "with_tools": sum("tools" in item for item in spec["scenarios"]),
                "answers": len(spec["scenarios"]) * len(conditions),
            }, ensure_ascii=False))
        elif args.command == "generate":
            generate(args.input, args.run_dir)
        elif args.command == "prepare":
            prepare(args.manifest, args.out_dir, args.checklist_parts)
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
