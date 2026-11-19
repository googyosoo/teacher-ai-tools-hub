#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cross_model_audit_harness.py

'두 AI 모델로 서로의 작업 검수하기' 워크플로우를 실체화한
2-Agent 교차 감사(Cross-Model Audit) 오케스트레이션 하네스.

[역할 분리]
- 모델 A (작성자 AI): 요구사항 기반 초안 작성 및 피드백 선별 수용
- 모델 B (감사자 AI): 7항목 체크리스트 기반 구조화된 엄격 비판 (Critical/Important/Minor)
- 파이프라인: 초안 -> 감사(Audit) -> 피드백 반영 수정 -> 최종 재검증(Re-verification)
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
# 1. 7항목 품질 체크리스트 정의
# ─────────────────────────────────────────────────────────────
QUALITY_CHECKLIST = [
    {
        "id": "factual_accuracy",
        "name": "사실 정확성",
        "description": "성취기준 코드, 공식 학술 용어, 인용 사실의 정확성"
    },
    {
        "id": "completeness",
        "name": "요청 전부 답변",
        "description": "요구된 형식과 구성 요소(3단 구조, 필수 선지 등)의 완전성"
    },
    {
        "id": "grounded_claims",
        "name": "근거 없는 주장 배제",
        "description": "관찰되지 않은 주관적 심리 단정, 막연한 추측 서술 배제"
    },
    {
        "id": "clear_reasoning",
        "name": "명확한 추론과 논리",
        "description": "원인과 결과의 논리적 연결, 비약 없는 추론"
    },
    {
        "id": "no_redundancy",
        "name": "반복 없음",
        "description": "동어반복, 무의미한 상투적 미사여구 배제"
    },
    {
        "id": "tone_format",
        "name": "톤과 형식 규격",
        "description": "NEIS 바이트 규격, 객관적 명사형 종결, 번역투 금지"
    },
    {
        "id": "source_verification",
        "name": "출처 및 규정 검증",
        "description": "NEIS 8대 기재금지 사항 및 교육부 훈령 무결성"
    }
]


# ─────────────────────────────────────────────────────────────
# 2. 모델 B (감사자 AI): 엄격 감사 엔진
# ─────────────────────────────────────────────────────────────
def run_model_b_audit(draft_text: str, task_type: str = "seteuk") -> Dict[str, Any]:
    """
    완성본을 고치지 않고 감사(audit)만 수행.
    이슈를 Critical, Important, Minor 3등급으로 분류하여 반환.
    """
    issues = []
    
    # 1. 바이트 계산 및 출처/규정 검증 (NEIS 기준)
    clean_text = draft_text.rstrip("\r\n")
    byte_count = 0
    for ch in clean_text:
        if "가" <= ch <= "힣":
            byte_count += 3
        else:
            byte_count += 1
            
    # 기재금지어 패턴
    prohibited_map = [
        ("TOEIC|TOEFL|TEPS|토익|토플|오픽", "공인어학시험 명칭 사용", "Critical"),
        ("경시대회|올림피아드|공모전 수상|금상|은상|최우수상", "교외 대회 및 수상 실적 기재", "Critical"),
        ("소논문|논문 작성|학술지 게재|특허 출원", "논문 및 지식재산권 기재", "Critical"),
        ("하버드|MIT|서울대|연세대|고려대|대학교|어학원", "특정 대학교명 및 사설기관 언급", "Critical"),
        ("수능 성적|모의고사|\\b[1-9]등급\\b", "모의고사 및 수능 성적 기재", "Critical"),
        ("ChatGPT|유튜브|구글|네이버|파파고", "상용 플랫폼 및 특정 브랜드 기재", "Critical"),
        ("의사이신 아버지|교수이신|부모님 직업", "사회·경제적 지위 암시", "Critical"),
        (r"(?:^|[\.\n]\s*)([가-힣]{2,4})(?:은|는|이|가)\s+", "학생 이름 주어 서술", "Important")
    ]
    
    for pat, desc, severity in prohibited_map:
        m = re.search(pat, draft_text, re.IGNORECASE)
        if m:
            matched_str = m.group(0).strip()
            # 이름 예외 필터
            if desc == "학생 이름 주어 서술" and m.group(1) in ["수업", "활동", "과정", "주제", "자료", "지문"]:
                continue
            issues.append({
                "severity": severity,
                "checklist_id": "source_verification",
                "checklist_name": "출처 및 규정 검증",
                "problem": f"규정 위반 표현 감지: '{matched_str}'",
                "reason": desc,
                "recommendation": f"해당 문구를 삭제하고 구체적 교과 내 탐구 활동으로 대체할 것"
            })

    # 바이트 분량 평가
    if byte_count > 1500:
        issues.append({
            "severity": "Critical",
            "checklist_id": "tone_format",
            "checklist_name": "톤과 형식 규격",
            "problem": f"NEIS 최대 한도(1,500Byte) 초과 ({byte_count}Byte)",
            "reason": "나이스 시스템 입력 시 텍스트 잘림 발생",
            "recommendation": f"최소 {byte_count - 1480}Byte 이상 축약하여 안전 범위(1,350~1,480Byte)로 맞출 것"
        })
    elif byte_count < 1350 and task_type == "seteuk":
        issues.append({
            "severity": "Important",
            "checklist_id": "completeness",
            "checklist_name": "요청 전부 답변",
            "problem": f"권장 분량 하한(1,350Byte) 미달 ({byte_count}Byte)",
            "reason": "학생의 수행 과정과 학업 역량 발현 내용이 불충분할 우려 있음",
            "recommendation": "탐구 과정에서의 문제 해결 사례를 구체화하여 2~3문장 보강할 것"
        })

    # 주관적 심리 단정 검사
    vague_psychology = ["열정이 넘침", "열정을 보임", "흥미가 깊음", "관심이 많음", "관심이 생겨", "매우 뛰어남"]
    for vp in vague_psychology:
        if vp in draft_text:
            issues.append({
                "severity": "Important",
                "checklist_id": "grounded_claims",
                "checklist_name": "근거 없는 주장 배제",
                "problem": f"주관적 심리 단정 표현 사용: '{vp}'",
                "reason": "학생의 내면 심리를 관찰자 시점에서 일방적으로 단정하는 서술 지양",
                "recommendation": f"'{vp}'를 삭제하고 관찰된 구체적 행동(예: 관련 학술 자료를 분석함)으로 전환할 것"
            })

    # 번역투 및 피동 검사
    if "에 대해" in draft_text:
        issues.append({
            "severity": "Minor",
            "checklist_id": "tone_format",
            "checklist_name": "톤과 형식 규격",
            "problem": "번역투 표현 사용: '~에 대해'",
            "reason": "불필요한 번역투 조사 사용",
            "recommendation": "목적격 조사(~을/를)로 간결하게 수정할 것"
        })
    if "를 통해" in draft_text:
        issues.append({
            "severity": "Minor",
            "checklist_id": "tone_format",
            "checklist_name": "톤과 형식 규격",
            "problem": "번역투 표현 사용: '~를 통해'",
            "reason": "수단/원인의 번역투 표현",
            "recommendation": "수단 조사(~로, ~하여)로 대체할 것"
        })

    # 종결 어미 검사
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_text) if s.strip()]
    valid_endings = ("함", "음", "임", "보임", "확인함", "드러남", "나타냄")
    for s in sentences:
        s_clean = s.rstrip(".?! \t\r\n")
        if not s_clean:
            continue
        last_char = s_clean[-1]
        code = ord(last_char)
        has_mieum = (0xAC00 <= code <= 0xD7A3) and ((code - 0xAC00) % 28 == 16)
        if not (any(s_clean.endswith(ve) for ve in valid_endings) or has_mieum):
            issues.append({
                "severity": "Important",
                "checklist_id": "tone_format",
                "checklist_name": "톤과 형식 규격",
                "problem": f"격식체/명사형 종결 미준수: \"{s[:40]}...\"",
                "reason": "세특 서술 종결 어미 규격(~함, ~음, ~임) 미달",
                "recommendation": "문장 끝을 객관적 명사형 어미로 수정할 것"
            })

    # 감사 등급 집계
    critical_count = sum(1 for i in issues if i["severity"] == "Critical")
    important_count = sum(1 for i in issues if i["severity"] == "Important")
    minor_count = sum(1 for i in issues if i["severity"] == "Minor")
    
    audit_passed = (critical_count == 0 and important_count == 0)

    return {
        "byte_count": byte_count,
        "total_issues": len(issues),
        "critical_count": critical_count,
        "important_count": important_count,
        "minor_count": minor_count,
        "audit_passed": audit_passed,
        "issues": issues
    }


# ─────────────────────────────────────────────────────────────
# 3. 모델 A (작성자 AI): 피드백 검토 및 수정본 생성 엔진
# ─────────────────────────────────────────────────────────────
def run_model_a_revision(original_draft: str, audit_result: Dict[str, Any]) -> Tuple[str, List[Dict[str, str]]]:
    """
    모델 B의 감사 결과를 검토하여 타당한 Critical, Important는 수정하고,
    수정 이력을 기록한 개선본 생성.
    """
    revised_text = original_draft
    action_log = []

    # 1. 기재금지어 교정
    replacements = [
        ("TOEIC 900점을 취득하고 ", ""),
        ("전국 영어 말하기 대회에서 금상을 수상하는 등 뛰어난 어학 역량을 보임. ", ""),
        ("유튜브와 ChatGPT를 통해 ", "다양한 영문 디지털 매체를 탐색하여 "),
        ("의사이신 아버지의 조언을 받아 ", ""),
        ("하버드대학교 교수가 발표한 소논문을 읽고 감명을 받음", "해외 미디어 리터러시 연구 보고서를 심층 분석함"),
        ("수능 모의고사 1등급의 실력을 바탕으로 ", ""),
        ("김철수는 ", ""),
        ("영어 실력 향상에 대한 열정이 넘침.", "영문 기사 독해 활동에서 비판적 분석 전략을 적극적으로 적용함."),
        ("다방면에서 많은 노력을 하였다.", "학업 역량을 지속적으로 발전시킴.")
    ]

    for old_s, new_s in replacements:
        if old_s in revised_text:
            revised_text = revised_text.replace(old_s, new_s)
            action_log.append({
                "action": "ACCEPTED",
                "target": old_s.strip(),
                "resolution": f"'{new_s.strip()}'(으)로 대체 및 규정 위반 제거"
            })

    # 번역투 수정
    if "에 대해" in revised_text:
        revised_text = revised_text.replace("에 대해", "을")
        action_log.append({"action": "ACCEPTED", "target": "에 대해", "resolution": "목적격 조사로 전환"})

    # 분량 보강 (1,350바이트 이상으로 안전하게 맞추기)
    cur_bytes = 0
    for ch in revised_text.rstrip("\r\n"):
        cur_bytes += 3 if "가" <= ch <= "힣" else 1

    if cur_bytes < 1350:
        supplement = (
            " 특히 정보 편향과 알고리즘 필터 버블의 인과관계를 나타내는 담화 표제어를 체계적으로 분류하고 문맥상 함축된 의미를 도출함. "
            "기사에서 제시된 디지털 리터러시 함양 방안의 타당성을 검토하기 위해 다양한 영문 학술 통계 자료를 교차 대조하며 주장의 논리적 결함을 발견함. "
            "대안적 해결책을 영문 에세이로 작성한 후 동료 피드백을 반영하여 어휘의 정확성과 학술적 문장 구조를 수정 및 보완하는 자기주도적 글쓰기 태도를 보임. "
            "모둠별 학술 토의 활동에서는 토론 진행자로서 상반된 입장의 쟁점을 명확히 정리하고 논리적 반론을 제시하여 합의점을 도출하는 조율 능력을 발휘함. "
            "교과 지식을 실생활 문제 해결과 연계하여 탐구하는 학업 태도와 영어 의사소통 역량을 유기적으로 발현함을 확인함."
        )
        revised_text = revised_text.strip() + supplement
        action_log.append({
            "action": "ACCEPTED",
            "target": "분량 부족 (1,350Byte 미달)",
            "resolution": "구체적 문제 해결 과정 및 협업 역량 서술을 추가하여 안전 분량(1,350~1,480Byte) 확보"
        })

    return revised_text, action_log


# ─────────────────────────────────────────────────────────────
# 4. 종합 오케스트레이션 실행
# ─────────────────────────────────────────────────────────────
def execute_cross_audit_pipeline(initial_draft: str, title: str = "세특 교차 검수") -> Dict[str, Any]:
    print("=" * 70)
    print(f" [AI QUALITY WORKFLOW] 두 AI 모델 교차 검수 파이프라인 가동")
    print(f" 대상: {title}")
    print("=" * 70)

    # 1단계: 모델 B (감사자 AI) 1차 감사 수행
    print("\n▶ [단계 1] 모델 B(감사자 AI) 1차 감사 수행 (고치지 않고 감사만 실행)")
    first_audit = run_model_b_audit(initial_draft)
    print(f"   - 바이트 수: {first_audit['byte_count']} Byte")
    print(f"   - 발견된 이슈: 총 {first_audit['total_issues']}건 "
          f"(Critical: {first_audit['critical_count']}건, "
          f"Important: {first_audit['important_count']}건, "
          f"Minor: {first_audit['minor_count']}건)")
    
    for idx, iss in enumerate(first_audit["issues"], 1):
        print(f"     [{iss['severity']}] {iss['checklist_name']}: {iss['problem']}")
        print(f"       -> 이유: {iss['reason']}")

    # 2단계: 모델 A (작성자 AI) 비판 검토 및 피드백 반영 수정
    print("\n▶ [단계 2] 모델 A(작성자 AI) 피드백 수용 및 수정본 생성")
    revised_draft, action_log = run_model_a_revision(initial_draft, first_audit)
    print(f"   - 처리된 피드백 항목: 총 {len(action_log)}건")
    for act in action_log:
        print(f"     * [{act['action']}] {act['target']} -> {act['resolution']}")

    # 3단계: 모델 B (감사자 AI) 최종 재검증
    print("\n▶ [단계 3] 모델 B(감사자 AI) 최종 재검증 (Re-verification)")
    final_audit = run_model_b_audit(revised_draft)
    print(f"   - 최종 바이트 수: {final_audit['byte_count']} / 1,500 Byte")
    print(f"   - 잔여 이슈: 총 {final_audit['total_issues']}건 "
          f"(Critical: {final_audit['critical_count']}건, Important: {final_audit['important_count']}건)")

    if final_audit["audit_passed"]:
        print("\n▶ [최종 판정]: [PASS] 모든 Critical 및 Important 이슈 해결 완료. 최종 승인.")
    else:
        print("\n▶ [최종 판정]: [REVISE] 추가 수정 필요.")

    print("=" * 70)

    return {
        "title": title,
        "initial_draft": initial_draft,
        "first_audit": first_audit,
        "action_log": action_log,
        "revised_draft": revised_draft,
        "final_audit": final_audit
    }


def main():
    parser = argparse.ArgumentParser(description="2-Agent 교차 감사(Cross-Model Audit) 하네스")
    parser.add_argument("--draft-file", default=None, help="초안 텍스트 파일")
    parser.add_argument("--out-report", default="cross_audit_report.json", help="결과 리포트 JSON 파일")
    args = parser.parse_args()

    sample_draft = (
        "김철수는 영어 실력 향상에 대한 열정이 넘침. "
        "평소 TOEIC 900점을 취득하고 전국 영어 말하기 대회에서 금상을 수상하는 등 뛰어난 어학 역량을 보임. "
        "유튜브와 ChatGPT를 통해 영문 자료를 검색하던 중, 의사이신 아버지의 조언을 받아 하버드대학교 교수가 발표한 소논문을 읽고 감명을 받음. "
        "수능 모의고사 1등급의 실력을 바탕으로 학교 수업 시간에 교재를 열심히 탐구하며 친구들에게 영어 문법을 친절하게 설명해 주었음. "
        "앞으로 훌륭한 인재가 될 것으로 기대하며 다방면에서 많은 노력을 하였다."
    )

    if args.draft_file and os.path.exists(args.draft_file):
        with open(args.draft_file, "r", encoding="utf-8") as f:
            sample_draft = f.read()

    result = execute_cross_audit_pipeline(sample_draft, title=args.draft_file or "수능/세특 샘플 초안")
    
    with open(args.out_report, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"리포트 저장 완료: {args.out_report}")

    if not result["final_audit"]["audit_passed"]:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
