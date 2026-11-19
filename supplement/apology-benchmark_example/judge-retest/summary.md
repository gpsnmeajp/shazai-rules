## 条件別の評定（3名×64回答＝192評定）

| 判定者 | 条件 | 釣り合い | 足りない | 重すぎる | 無神経 |
|---|---|---|---|---|---|
| 既存（Claudeサブエージェント） | 指示なし | 171 | 8 | 1 | 12 |
| 既存（Claudeサブエージェント） | 一般指示 | 149 | 3 | 40 | 0 |
| 既存（Claudeサブエージェント） | SHAZAI | 138 | 30 | 22 | 2 |
| Jev（~typesafe/jev-latest） | 指示なし | 154 | 20 | 17 | 1 |
| Jev（~typesafe/jev-latest） | 一般指示 | 135 | 3 | 54 | 0 |
| Jev（~typesafe/jev-latest） | SHAZAI | 119 | 28 | 45 | 0 |
| Gemma 4 31B | 指示なし | 122 | 39 | 23 | 8 |
| Gemma 4 31B | 一般指示 | 110 | 13 | 69 | 0 |
| Gemma 4 31B | SHAZAI | 103 | 51 | 33 | 5 |
| Qwen3.8 27B | 指示なし | 135 | 29 | 23 | 5 |
| Qwen3.8 27B | 一般指示 | 118 | 12 | 61 | 1 |
| Qwen3.8 27B | SHAZAI | 93 | 56 | 43 | 0 |
| Claude Haiku 5.5 | 指示なし | 113 | 45 | 24 | 10 |
| Claude Haiku 5.5 | 一般指示 | 96 | 31 | 63 | 2 |
| Claude Haiku 5.5 | SHAZAI | 98 | 58 | 32 | 4 |

## 筆者との一致（192回答）

| 判定者 | 多数決の完全一致 | 多数決なし | κ（4分類） | κ（釣り合い/それ以外） | 各ペルソナ一致 | 既存判定者とのκ | ペルソナ間 Fleiss κ | 3名一致 |
|---|---|---|---|---|---|---|---|---|
| 既存（Claudeサブエージェント） | 108 | 0 | 0.061 | 0.093 | 105/108/111 | — | 0.752 | 167 |
| Jev（~typesafe/jev-latest） | 96 | 0 | 0.05 | 0.1 | 95/96/95 | 0.371 | 0.676 | 150 |
| Gemma 4 31B | 82 | 10 | 0.025 | 0.121 | 83/83/82 | 0.366 | 0.392 | 95 |
| Qwen3.8 27B | 85 | 8 | 0.005 | 0.043 | 88/90/79 | 0.459 | 0.327 | 87 |
| Claude Haiku 5.5 | 76 | 10 | 0.025 | 0.066 | 83/81/76 | 0.347 | 0.337 | 79 |

## 筆者の評定別の、判定者多数決の内訳

- 既存（Claudeサブエージェント）: 筆者 rude → {'fit': 22, 'heavy': 1, 'light': 6, 'rude': 3}; 筆者 light → {'heavy': 4, 'fit': 30, 'light': 1, 'rude': 1}; 筆者 fit → {'fit': 103, 'heavy': 14, 'light': 6}; 筆者 heavy → {'heavy': 1}
- Jev（~typesafe/jev-latest）: 筆者 rude → {'fit': 20, 'heavy': 7, 'light': 5}; 筆者 light → {'heavy': 8, 'fit': 25, 'light': 3}; 筆者 fit → {'fit': 92, 'heavy': 23, 'light': 8}; 筆者 heavy → {'heavy': 1}
- Gemma 4 31B: 筆者 rude → {'fit': 14, 'heavy': 8, 'light': 6, 'none': 3, 'rude': 1}; 筆者 light → {'heavy': 10, 'fit': 20, 'none': 3, 'light': 1, 'rude': 2}; 筆者 fit → {'fit': 79, 'light': 19, 'rude': 1, 'heavy': 20, 'none': 4}; 筆者 heavy → {'heavy': 1}
- Qwen3.8 27B: 筆者 rude → {'fit': 17, 'light': 7, 'heavy': 5, 'none': 3}; 筆者 light → {'heavy': 7, 'light': 2, 'fit': 24, 'none': 2, 'rude': 1}; 筆者 fit → {'fit': 82, 'heavy': 26, 'none': 3, 'light': 12}; 筆者 heavy → {'heavy': 1}
- Claude Haiku 5.5: 筆者 rude → {'light': 8, 'fit': 14, 'heavy': 6, 'none': 2, 'rude': 2}; 筆者 light → {'heavy': 9, 'fit': 21, 'light': 5, 'rude': 1}; 筆者 fit → {'fit': 68, 'none': 8, 'heavy': 22, 'light': 25}; 筆者 heavy → {'heavy': 1}

## 知覚段階（平均、設計上の段階別）

| 判定者 | 0 | 1 | 2 | 3 | 4 | 修復期 | 筆者と一致 | 設計と一致 |
|---|---|---|---|---|---|---|---|---|
| 既存（Claudeサブエージェント） | 0.0 | 1.17 | 1.81 | 3.1 | 4.0 | 1.12 | 120/192 | 152/168 |
| Jev（~typesafe/jev-latest） | 0.0 | 1.67 | 1.42 | 2.96 | 3.0 | 2.75 | 114/192 | 119/168 |
| Gemma 4 31B | 0.0 | 1.72 | 1.86 | 2.83 | 3.0 | 2.46 | 101/192 | 106/168 |
| Qwen3.8 27B | 0.0 | 1.14 | 2.14 | 2.83 | 3.25 | 0.96 | 102/192 | 132/168 |
| Claude Haiku 5.5 | 0.0 | 1.11 | 1.31 | 3.1 | 3.0 | 2.0 | 77/192 | 94/168 |

## 84項目チェック

| 判定者 | 条件 | 該当/判定可能 | 該当率 | 観測不能 | 適用外 | 多い項目 |
|---|---|---|---|---|---|---|
| 既存（Claudeサブエージェント） | 指示なし | 82/3245 | 2.53% | 690 | 1441 | 03.05(25)、04.01(10)、03.01(6)、06.01(5) |
| 既存（Claudeサブエージェント） | 一般指示 | 20/3245 | 0.62% | 692 | 1439 | 06.01(7)、03.05(4)、01.03(3)、10.06(2) |
| 既存（Claudeサブエージェント） | SHAZAI | 39/3241 | 1.2% | 694 | 1441 | 10.06(10)、03.05(7)、06.01(5)、01.01(5) |
| Jev（~typesafe/jev-latest） | 指示なし | 218/3250 | 6.71% | 39 | 2087 | 01.01(40)、10.08(29)、06.01(28)、10.05(21) |
| Jev（~typesafe/jev-latest） | 一般指示 | 268/3849 | 6.96% | 40 | 1487 | 01.01(41)、10.08(41)、06.01(40)、10.05(30) |
| Jev（~typesafe/jev-latest） | SHAZAI | 266/3432 | 7.75% | 49 | 1895 | 01.01(38)、10.08(36)、10.05(32)、06.01(22) |
| Gemma 4 31B | 指示なし | 90/3914 | 2.3% | 146 | 1316 | 06.01(22)、06.08(11)、03.05(10)、03.01(8) |
| Gemma 4 31B | 一般指示 | 72/4244 | 1.7% | 189 | 943 | 06.01(28)、06.08(6)、03.05(6)、01.01(6) |
| Gemma 4 31B | SHAZAI | 58/4017 | 1.44% | 198 | 1161 | 06.01(14)、03.05(12)、06.08(8)、03.01(5) |
| Qwen3.8 27B | 指示なし | 124/3544 | 3.5% | 499 | 1333 | 03.05(20)、06.01(19)、10.08(18)、06.08(6) |
| Qwen3.8 27B | 一般指示 | 79/3801 | 2.08% | 573 | 1002 | 06.01(25)、10.08(14)、01.03(13)、03.05(5) |
| Qwen3.8 27B | SHAZAI | 69/3632 | 1.9% | 553 | 1191 | 10.08(15)、06.01(12)、03.05(6)、10.01(6) |
| Claude Haiku 5.5 | 指示なし | 63/3310 | 1.9% | 253 | 1813 | 03.05(15)、06.01(12)、10.08(7)、06.02(3) |
| Claude Haiku 5.5 | 一般指示 | 61/3932 | 1.55% | 296 | 1148 | 06.01(18)、03.05(10)、10.01(5)、10.08(5) |
| Claude Haiku 5.5 | SHAZAI | 33/3403 | 0.97% | 324 | 1649 | 06.01(8)、10.01(5)、10.06(5)、10.08(3) |

| 判定者 | 該当0件の回答 | 段階0・修復期の該当数 | 筆者評定別の平均該当数 (rude/light/fit/heavy) | 既存とのκ（該当/非該当） | 両方該当 | この判定者のみ | 既存のみ |
|---|---|---|---|---|---|---|---|
| 既存（Claudeサブエージェント） | 123 | 0 | 2.22/0.83/0.33/0.0 | — | — | — | — |
| Jev（~typesafe/jev-latest） | 54 | 32 | 4.28/4.11/3.75/6.0 | 0.106 | 53 | 699 | 88 |
| Gemma 4 31B | 100 | 0 | 2.03/1.28/0.88/1.0 | 0.196 | 37 | 183 | 104 |
| Qwen3.8 27B | 83 | 4 | 1.94/1.89/1.15/1.0 | 0.243 | 52 | 220 | 89 |
| Claude Haiku 5.5 | 110 | 14 | 1.31/1.17/0.59/0.0 | 0.214 | 33 | 124 | 108 |

## 代表場面

### bullets

| 生成モデル | 条件 | 筆者 | 既存（Claudeサブエージェント） | Jev（~typesafe/jev-latest） | Gemma 4 31B | Qwen3.8 27B | Claude Haiku 5.5 |
|---|---|---|---|---|---|---|---|
| claude-opus-5.5 | 一般指示 | fit | fit | fit | fit | fit | light |
| claude-opus-5.5 | SHAZAI | rude | heavy＋10.06 | heavy | heavy | heavy | heavy |
| claude-opus-5.5 | 指示なし | fit | fit | fit | fit | fit | fit |
| gpt-6.1-sol | 指示なし | fit | fit | fit | fit | fit | fit |
| gpt-6.1-sol | 一般指示 | fit | fit | fit | fit | fit | light |
| gpt-6.1-sol | SHAZAI | rude | light＋10.06 | light＋10.06 | light | light＋10.06 | light |
| muse-wonder | 指示なし | fit | fit | fit | light | fit | light |
| muse-wonder | SHAZAI | rude | light＋10.06 | heavy＋10.06 | heavy | light＋10.06 | heavy＋10.06 |
| muse-wonder | 一般指示 | fit | fit | fit | fit | fit | fit |
| gemini-4-hydrogen | SHAZAI | rude | light＋10.06 | heavy＋10.06 | heavy | light | None |
| gemini-4-hydrogen | 指示なし | fit | fit | light | light | fit | light |
| gemini-4-hydrogen | 一般指示 | fit | fit | fit | fit | fit | None |

### taninngoto

| 生成モデル | 条件 | 筆者 | 既存（Claudeサブエージェント） | Jev（~typesafe/jev-latest） | Gemma 4 31B | Qwen3.8 27B | Claude Haiku 5.5 |
|---|---|---|---|---|---|---|---|
| claude-opus-5.5 | 指示なし | rude | fit | fit | fit | fit | heavy |
| claude-opus-5.5 | SHAZAI | fit | fit | fit＋10.06 | fit | heavy＋10.06 | None |
| claude-opus-5.5 | 一般指示 | fit | fit | fit＋10.06 | fit | None | fit |
| gpt-6.1-sol | 一般指示 | fit | fit | fit | fit | fit | fit |
| gpt-6.1-sol | SHAZAI | fit | fit | fit＋10.06 | fit | fit | None |
| gpt-6.1-sol | 指示なし | light | fit | fit＋10.06 | heavy | heavy | heavy |
| muse-wonder | SHAZAI | fit | fit | fit＋10.06 | fit | heavy | heavy |
| muse-wonder | 指示なし | light | fit | fit＋10.06 | None | fit | fit |
| muse-wonder | 一般指示 | fit | fit | fit | None | fit | fit |
| gemini-4-hydrogen | SHAZAI | fit | fit | fit＋10.06 | fit | heavy | fit |
| gemini-4-hydrogen | 指示なし | fit | fit | fit＋10.06 | fit | fit | light |
| gemini-4-hydrogen | 一般指示 | light | heavy | heavy＋10.06 | heavy | heavy | heavy |

## Jev の確率の平均（多数決でなく確率で見た評定）

| 条件 | rude | light | fit | heavy |
|---|---|---|---|---|
| 指示なし | 0.027 | 0.18 | 0.646 | 0.147 |
| 一般指示 | 0.007 | 0.088 | 0.625 | 0.28 |
| SHAZAI | 0.013 | 0.238 | 0.534 | 0.215 |
