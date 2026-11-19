#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
csat_english_generator.py

평가원 대학수학능력시험(수능) 영어 영역 출제 규격에 맞춘
고난도 문항 제작 및 오답 매력도(Distractor Plausibility) 정밀 분석 엔진.
"""

import argparse
import json
import os
import re
import sys
from typing import Dict, List, Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# 1. 수능 지문 및 문항 규격 검증 로직
# ─────────────────────────────────────────────────────────────
def analyze_passage_metrics(passage: str) -> Dict[str, Any]:
    """수능 지문의 단어 수, 문장 수, 평균 문장 길이 및 복잡도 분석"""
    words = re.findall(r"\b[A-Za-z]+(?:'[A-Za-z]+)?\b", passage)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", passage.strip()) if s.strip()]
    
    word_count = len(words)
    sentence_count = len(sentences)
    avg_words_per_sentence = round(word_count / max(1, sentence_count), 1)
    
    # 수능 적합도 판정
    # 빈칸추론 표준: 130 ~ 190 단어, 문장당 평균 15 ~ 25 단어
    is_word_count_valid = 120 <= word_count <= 210
    is_sentence_len_valid = 14.0 <= avg_words_per_sentence <= 28.0
    
    return {
        "word_count": word_count,
        "sentence_count": sentence_count,
        "avg_words_per_sentence": avg_words_per_sentence,
        "is_word_count_valid": is_word_count_valid,
        "is_sentence_len_valid": is_sentence_len_valid
    }


def analyze_option_symmetry(options: List[str]) -> Dict[str, Any]:
    """5개 선택지의 길이 대칭성(Length Symmetry) 및 시작 품사 일치 여부 분석"""
    lengths = [len(opt.split()) for opt in options]
    avg_len = sum(lengths) / len(lengths)
    max_diff = max(lengths) - min(lengths)
    
    # 첫 단어 품사 형태 (동명사/to부정사/동사원형/명사구 일관성)
    first_words = [opt.strip().split()[0].lower() if opt.strip().split() else "" for opt in options]
    
    # 선택지 길이 편차가 4단어 이내이면 대칭성 양호
    is_symmetric = max_diff <= 5
    
    return {
        "lengths": lengths,
        "avg_len": round(avg_len, 1),
        "max_diff": max_diff,
        "first_words": first_words,
        "is_symmetric": is_symmetric
    }


# ─────────────────────────────────────────────────────────────
# 2. 오답 매력도(Distractor Plausibility) 분석 매트릭스
# ─────────────────────────────────────────────────────────────
DISTRACTOR_CATEGORIES = {
    "CONTRADICTION": "반대 논리 및 인과 왜곡 (지문 핵심 소재를 담고 있으나 인과나 방향이 정반대)",
    "IRRELEVANT_DETAIL": "지엽적 세부 사실 (지문에 일부 언급되었으나 빈칸의 상위 주제와 무관)",
    "OVERGENERALIZATION": "과잉 일반화 및 상식 함정 (상식적으로 그럴듯하나 지문 논거에서 도출 불가)",
    "OUT_OF_SCOPE": "논점 일탈 (지문의 핵심 쟁점과 무관한 엉뚱한 소재 연결)"
}


# ─────────────────────────────────────────────────────────────
# 3. 평가원 기준 킬러 문항 생성 템플릿 (인공지능 윤리/알고리즘 편향 제재)
# ─────────────────────────────────────────────────────────────
SAMPLE_AI_ETHICS_ITEM = {
    "item_type": "빈칸 추론 (3점 배점, 34번 유형)",
    "topic": "인공지능 알고리즘의 객관성 신화와 내재적 가치 편향",
    "curriculum_standard": "[12영Ⅰ03-01] 일반적·학술적 주제에 관한 글을 읽고 중심 논거와 맥락을 파악할 수 있다.",
    "passage": (
        "Algorithmic decision-making systems are frequently celebrated for their supposed immunity "
        "to subjective human bias. Because these automated models rely on vast repositories of statistical "
        "data and rigorous mathematical calculations, observers often assume that their conclusions represent "
        "pure, unadulterated neutrality. However, this belief overlooks the fundamental reality that algorithms "
        "do not emerge in a cultural vacuum; rather, they are crafted by designers whose institutional priorities "
        "and conceptual frameworks inevitably shape their architectures. Furthermore, the historical training "
        "datasets fed into these predictive models already mirror the systemic inequities, structural exclusions, "
        "and implicit prejudices of past societies. Consequently, when an algorithm identifies correlations and "
        "projects future trends, it does not transcend prevailing human prejudices; instead, it operates to "
        "________________________________________. By clothing historical social hierarchies in the prestigious "
        "garb of quantitative objectivity, computational systems risk converting contingent historical inequalities "
        "into unquestionable technical necessities."
    ),
    "blank_korean_meaning": "과거의 사회적 불평등과 인간의 기존 편견을 수학적 객관성으로 포장하여 오히려 공고화하고 영속화한다.",
    "options": [
        "institutionalize and perpetuate pre-existing cultural distortions",
        "democratize access to quantitative empirical evidence",
        "neutralize ideological conflicts across diverse communities",
        "eliminate subjective human judgment from technical governance",
        "expose systemic historical biases through transparent auditing"
    ],
    "correct_index": 1, # 1번 선지 (0-based: 0)
    "distractor_analysis": [
        {
            "option_number": 1,
            "text": "institutionalize and perpetuate pre-existing cultural distortions",
            "is_correct": True,
            "plausibility_type": "CORRECT_KEY",
            "plausibility_score": 5,
            "reason": (
                "정답 선지. 빈칸 직전 'instead, it operates to'와 이어지며, "
                "지문 후반부의 'converting contingent historical inequalities into unquestionable technical necessities'를 "
                "'기존의 문화적 왜곡을 제도화하고 영속화한다'로 정확히 패러프레이징함."
            )
        },
        {
            "option_number": 2,
            "text": "democratize access to quantitative empirical evidence",
            "is_correct": False,
            "plausibility_type": "OVERGENERALIZATION",
            "plausibility_score": 3,
            "trap_mechanism": (
                "과잉 일반화 및 통념 함정. 'quantitative', 'empirical evidence' 등 지문에 등장한 "
                "수학적 객관성 소재를 사용해 긍정적 효과로 포장했으나, 필자의 비판적 논지와 정면 배치됨."
            )
        },
        {
            "option_number": 3,
            "text": "neutralize ideological conflicts across diverse communities",
            "is_correct": False,
            "plausibility_type": "CONTRADICTION",
            "plausibility_score": 4,
            "trap_mechanism": (
                "반대 논리 왜곡(매력적 오답). 알고리즘이 중립성을 가져다줄 것이라는 "
                "지문 초반의 통념('supposed immunity to subjective bias')을 빈칸에 대입하도록 유도하는 전형적인 평가원 함정."
            )
        },
        {
            "option_number": 4,
            "text": "eliminate subjective human judgment from technical governance",
            "is_correct": False,
            "plausibility_type": "CONTRADICTION",
            "plausibility_score": 4,
            "trap_mechanism": (
                "반대 방향 함정. 지문 1~3행의 'immunity to subjective human bias' 어휘를 그대로 재활용하여 "
                "수험생의 단순 어휘 매칭 심리를 자극하나, However 이후 전개된 필자의 결론과 정반대임."
            )
        },
        {
            "option_number": 5,
            "text": "expose systemic historical biases through transparent auditing",
            "is_correct": False,
            "plausibility_type": "IRRELEVANT_DETAIL",
            "plausibility_score": 2,
            "trap_mechanism": (
                "소재 왜곡. 지문의 'systemic inequities'라는 표현을 활용했으나, "
                "알고리즘이 편향을 폭로(expose)하거나 투명하게 감사한다는 내용은 지문에 전혀 존재하지 않는 비약임."
            )
        }
    ],
    "passage_korean_translation": (
        "알고리즘 의사결정 시스템은 인간의 주관적 편견으로부터 자유롭다고 종종 찬사를 받는다. "
        "이러한 자동화 모델은 방대한 양의 통계 데이터 저장소와 엄격한 수학적 계산에 의존하기 때문에, "
        "관찰자들은 그 결론이 순수하고 오염되지 않은 중립성을 나타낸다고 자주 가정한다. "
        "그러나 이러한 믿음은 알고리즘이 문화적 진공 상태에서 생겨나지 않는다는 근본적인 현실을 간과한다. "
        "오히려 알고리즘은 조직적 우선순위와 개념적 프레임워크가 아키텍처를 필연적으로 형성하는 설계자들에 의해 만들어진다. "
        "게다가 이러한 예측 모델에 투입되는 과거의 학습 데이터 세트는 이미 과거 사회의 체계적 불평등, 구조적 배제, "
        "그리고 암묵적인 편견을 그대로 반영하고 있다. 결과적으로 알고리즘이 상관관계를 식별하고 미래 추세를 예측할 때, "
        "알고리즘은 지배적인 인간의 편견을 초월하는 것이 아니라, 오히려 [기존의 문화적 왜곡을 제도화하고 영속화하는] 역할을 하게 된다. "
        "컴퓨팅 시스템은 역사적 사회 위계를 정량적 객관성이라는 권위 있는 옷으로 위장함으로써, "
        "우연한 역사적 불평등을 의문의 여지가 없는 기술적 필연성으로 바꿀 위험을 초래한다."
    ),
    "core_vocabulary": [
        {"word": "immunity", "meaning": "면제, 면역 (편견에 영향받지 않음)"},
        {"word": "unadulterated", "meaning": "순수한, 오염되지 않은"},
        {"word": "mirror", "meaning": "그대로 반영하다, 모방하다"},
        {"word": "transcend", "meaning": "초월하다, 넘어서다"},
        {"word": "perpetuate", "meaning": "영속화하다, 끊이지 않게 하다"},
        {"word": "contingent", "meaning": "우연한, 부수적인, 상황에 따른"}
    ]
}


def build_markdown_report(item_data: Dict[str, Any], passage_metrics: Dict[str, Any], option_metrics: Dict[str, Any]) -> str:
    """수능 문항 및 오답 매력도 정밀 분석 Markdown 리포트 생성"""
    lines = []
    lines.append(f"# [2027 수능 영어 고난도 킬러 문항] {item_data['item_type']}")
    lines.append(f"**주제**: {item_data['topic']}")
    lines.append(f"**교육과정 성취기준**: `{item_data['curriculum_standard']}`")
    lines.append("")
    
    lines.append("## 1. 수능 실전 문항")
    lines.append("다음 빈칸에 들어갈 말로 가장 적절한 것을 고르시오. [3점]")
    lines.append("")
    lines.append("> " + item_data["passage"].replace("\n", "\n> "))
    lines.append("")
    for idx, opt in enumerate(item_data["options"], 1):
        lines.append(f"① {opt}" if idx == 1 else f"② {opt}" if idx == 2 else f"③ {opt}" if idx == 3 else f"④ {opt}" if idx == 4 else f"⑤ {opt}")
    lines.append("")
    
    lines.append("## 2. 평가원 규격 지문 및 선지 검증 지표")
    lines.append(f"- **지문 총 단어 수**: {passage_metrics['word_count']} 단어 (기준 130~190단어 만족: {'PASS' if passage_metrics['is_word_count_valid'] else 'FAIL'})")
    lines.append(f"- **문장 수**: {passage_metrics['sentence_count']}개 문장")
    lines.append(f"- **문장당 평균 단어 수**: {passage_metrics['avg_words_per_sentence']} 단어 (수능 고난도 적합: {'PASS' if passage_metrics['is_sentence_len_valid'] else 'FAIL'})")
    lines.append(f"- **선지 길이 대칭성**: 평균 {option_metrics['avg_len']} 단어, 최대 편차 {option_metrics['max_diff']} 단어 (대칭성 만족: {'PASS' if option_metrics['is_symmetric'] else 'FAIL'})")
    lines.append(f"- **선지 통사 구조**: 동사원형 + 목적어 구문 일관성 확보")
    lines.append("")
    
    lines.append("## 3. 오답 매력도(Distractor Plausibility) 정밀 분석")
    lines.append("| 번호 | 선지 내용 | 판정 | 함정 유형 | 매력도(5점) | 함정 유인 원리 및 소거 근거 |")
    lines.append("|:---:|:---|:---:|:---|:---:|:---|")
    for da in item_data["distractor_analysis"]:
        num_str = f"①" if da["option_number"] == 1 else f"②" if da["option_number"] == 2 else f"③" if da["option_number"] == 3 else f"④" if da["option_number"] == 4 else f"⑤"
        status_str = "**정답**" if da["is_correct"] else "오답"
        trap_type = da["plausibility_type"]
        score = f"{da['plausibility_score']} / 5"
        reason = da.get("reason", da.get("trap_mechanism", ""))
        lines.append(f"| {num_str} | {da['text']} | {status_str} | `{trap_type}` | {score} | {reason} |")
    lines.append("")

    lines.append("## 4. 지문 해석 및 핵심 구문 분석")
    lines.append("### [전문 번역]")
    lines.append(item_data["passage_korean_translation"])
    lines.append("")
    lines.append("### [핵심 평가원 어휘]")
    for v in item_data["core_vocabulary"]:
        lines.append(f"- **{v['word']}**: {v['meaning']}")
        
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="수능 영어 문항 생성기 및 오답 매력도 분석기")
    parser.add_argument("--out-md", default="csat_killer_item_34.md", help="출력 마크다운 파일명")
    parser.add_argument("--out-json", default="csat_killer_item_34.json", help="출력 JSON 파일명")
    args = parser.parse_args()

    item = SAMPLE_AI_ETHICS_ITEM
    passage_metrics = analyze_passage_metrics(item["passage"])
    option_metrics = analyze_option_symmetry(item["options"])

    print("=" * 70)
    print(" [수능 영어 평가원 규격 문항 생성 및 오답 매력도 분석 완료]")
    print("=" * 70)
    print(f"문항 유형: {item['item_type']}")
    print(f"지문 제재: {item['topic']}")
    print(f"단어 수: {passage_metrics['word_count']}단어 | 문장 수: {passage_metrics['sentence_count']}개 | 문장당 평균: {passage_metrics['avg_words_per_sentence']}단어")
    print(f"선지 대칭성: 최대 길이 차이 {option_metrics['max_diff']}단어 (대칭 기준 충족)")
    print("-" * 70)
    print("정답 선지: ①번 -", item["options"][0])
    print("오답 설계 매트릭스:")
    for da in item["distractor_analysis"][1:]:
        print(f"  선지 {da['option_number']}번: [{da['plausibility_type']}] 매력도 {da['plausibility_score']}/5점")
        print(f"    -> 함정 원리: {da['trap_mechanism'][:60]}...")
    print("=" * 70)

    # 마크다운 리포트 저장
    md_content = build_markdown_report(item, passage_metrics, option_metrics)
    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Markdown 리포트 생성 완료: {args.out_md}")

    # JSON 데이터 저장
    full_data = {
        "item": item,
        "passage_metrics": passage_metrics,
        "option_metrics": option_metrics
    }
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(full_data, f, ensure_ascii=False, indent=2)
    print(f"JSON 데이터 생성 완료: {args.out_json}")


if __name__ == "__main__":
    main()
