#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline_seteuk_audit.py

교육부 훈령 및 학교생활기록부 기재요령, NEIS 공식 바이트 기준,
전역 교육 지침을 기계적으로 엄격 검증하는 세특 자동 감수 파이프라인 엔진.
"""

import argparse
import json
import os
import re
import sys
from typing import Dict, List, Tuple, Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────
# 1. NEIS 공식 바이트 계산 함수
# ─────────────────────────────────────────────────────────────
def count_neis_bytes(text: str) -> Tuple[int, int]:
    """
    NEIS 공식 바이트 산출:
    - 한글 1자 = 3바이트
    - 영문, 숫자, 공백, 기본 특수문자 = 1바이트
    - 줄바꿈(\\r\\n, \\n) = 2바이트 (단, 텍스트 끝 줄바꿈은 제외)
    반환값: (바이트수, 글자수)
    """
    clean_text = text.rstrip("\r\n")
    byte_count = 0
    char_count = len(clean_text)
    
    i = 0
    n = len(clean_text)
    while i < n:
        ch = clean_text[i]
        if ch == "\r":
            if i + 1 < n and clean_text[i + 1] == "\n":
                byte_count += 2
                i += 2
                continue
            else:
                byte_count += 2
                i += 1
                continue
        elif ch == "\n":
            byte_count += 2
            i += 1
            continue
        elif "가" <= ch <= "힣":
            byte_count += 3
        else:
            byte_count += 1
        i += 1
        
    return byte_count, char_count


# ─────────────────────────────────────────────────────────────
# 2. NEIS 8대 기재 금지 사항 정규식 및 키워드
# ─────────────────────────────────────────────────────────────
PROHIBITED_RULES = [
    {
        "category": "공인어학시험",
        "description": "TOEIC, TOEFL, TEPS, JLPT, HSK, OPIC, SAT, AP, ACT, FLEX 등 모든 어학시험 명칭",
        "pattern": re.compile(
            r"(?i)\b(TOEIC|TOEFL|TEPS|JLPT|HSK|OPIC|OPIc|SAT|AP|ACT|FLEX|G-TELP|IELTS|DELE|DELF|DALF|TORFL|SNULT)\b|"
            r"(토익|토플|텝스|오픽|토익스피킹|어학인증시험|공인어학)"
        )
    },
    {
        "category": "교외 대회 및 수상 실적",
        "description": "교외대회, 올림피아드, 경시대회, 인증시험, 공모전, 수상 실적 등",
        "pattern": re.compile(
            r"(교외\s*대회|올림피아드|경시대회|공모전\s*수상|전국대회\s*수상|교육청\s*대회|"
            r"금상|은상|최우수상|우수상|장려상|입상함|대회에서\s*수상|상\s*수여|대회\s*참가)"
        )
    },
    {
        "category": "논문 및 출판물",
        "description": "소논문, 논문, 학술지, 저널, 도서출간, 특허, R&E 등",
        "pattern": re.compile(
            r"(소논문|논문\s*작성|학술지\s*게재|저널에\s*발표|R&E|알앤이|도서\s*출간|책을\s*출판|"
            r"단행본\s*발간|특허\s*출원|특허\s*등록|실용신안)"
        )
    },
    {
        "category": "외부 기관 및 대학교명",
        "description": "대학교명, 해외 명문대(하버드, MIT 등), 사설학원, 영재교육원 등",
        "pattern": re.compile(
            r"(?i)(하버드|MIT|스탠퍼드|옥스퍼드|캠브리지|예일|프린스턴|서울대|연세대|고려대|카이스트|포항공대|"
            r"[가-힣]{2,6}대학교|[가-힣]{2,6}대학원|어학원|영재교육원|사설학원|메가스터디|이투스|대성마이맥)"
        )
    },
    {
        "category": "모의고사 및 석차",
        "description": "수능, 모의고사, n등급, 전교 n등, 석차, 백분위 등 시험 성적",
        "pattern": re.compile(
            r"(수능\s*성적|모의고사\s*(?:등급|점수|성적)|전국연합학력평가\s*(?:등급|점수)|"
            r"\b[1-9]등급\b|전교\s*[0-9]+등|석차|백분위\s*[0-9]+%?)"
        )
    },
    {
        "category": "상용 플랫폼 및 브랜드",
        "description": "유튜브, ChatGPT, 파파고, 네이버, 구글 등 특정 상호명",
        "pattern": re.compile(
            r"(?i)\b(ChatGPT|OpenAI|Claude|Google|YouTube|Papago|Naver|Kakao|Facebook|Instagram|TikTok)\b|"
            r"(유튜브|챗지피티|파파고|네이버|구글|카카오톡|인스타그램|틱톡)"
        )
    },
    {
        "category": "사회·경제적 지위 암시",
        "description": "부모 및 친인척의 직업/지위(교수, 의사, 법조인 등) 암시 서술",
        "pattern": re.compile(
            r"(아버지(?:의|께서|\s*직업)|어머니(?:의|께서|\s*직업)|부모님(?:의|께서|\s*직업)|"
            r"의사이신\s*(?:부모|아버지|어머니)|교수이신\s*(?:부모|아버지|어머니)|"
            r"법조인\s*(?:집안|부모)|친척|가정\s*형편|집안\s*배경)"
        )
    },
    {
        "category": "학생 이름 주어 서술",
        "description": "문장 서두에 '학생 이름 + 은/는/이/가' 서술 금지",
        "pattern": re.compile(
            r"(?:^|[\.\?\!\n]\s*)([가-힣]{2,4})(?:은|는|이|가)\s+"
        )
    }
]


# ─────────────────────────────────────────────────────────────
# 3. 문체, 심리 서술, 번역투 및 종결어미 검사
# ─────────────────────────────────────────────────────────────
SUBJECTIVE_PSYCHOLOGY_WORDS = [
    "열정이 넘침", "열정을 보임", "흥미가 깊음", "관심이 많음", "관심이 생겨",
    "매우 뛰어남", "소질이 있음", "탁월함", "자부심을 느낌", "동기가 생겨"
]

TRANSLATION_TONE_PATTERNS = [
    (re.compile(r"~에 대해|[가-힣]+에\s*대해"), "목적격 조사(~을/를)로 대체 권장"),
    (re.compile(r"~를 통해|[가-힣]+를\s*통해"), "수단/원인 조사(~로, ~해서)로 대체 권장"),
    (re.compile(r"판단되어지|보여지|생각되어지"), "이중 피동 표현 단일화 권장 (판단됨, 보임)")
]

VALID_ENDINGS = ("함", "음", "임", "보임", "확인함", "드러남", "나타냄", "제시함", "파악함", "도출함")


# ─────────────────────────────────────────────────────────────
# 4. 감수 파이프라인 코어
# ─────────────────────────────────────────────────────────────
def audit_seteuk_text(text: str) -> Dict[str, Any]:
    """단일 세특 텍스트에 대한 종합 진단 수행"""
    byte_count, char_count = count_neis_bytes(text)
    
    # 1. 분량 평가
    byte_status = "적정"
    byte_comment = "권장 안전 범위(1,350~1,480Byte) 내에 위치함."
    if byte_count > 1500:
        byte_status = "위험 (초과)"
        byte_comment = f"NEIS 최대 한도(1,500Byte)를 {byte_count - 1500}Byte 초과함. 나이스 입력 시 잘림 발생."
    elif byte_count > 1480:
        byte_status = "주의 (경계)"
        byte_comment = f"안전 한도(1,480Byte)를 근소 초과함({byte_count}Byte). 줄바꿈 및 특수문자 여유 확보 권장."
    elif byte_count < 1350:
        byte_status = "보완 권장"
        byte_comment = f"권장 하한(1,350Byte)보다 적음({byte_count}Byte). 구체적 탐구 과정 및 발현 역량 보강 권장."

    # 2. 기재 금지 사항 검사
    violations = []
    for rule in PROHIBITED_RULES:
        category = rule["category"]
        pattern = rule["pattern"]
        matches = list(pattern.finditer(text))
        if matches:
            for m in matches:
                matched_str = m.group(0).strip()
                # 오탐 예외 처리: 미술 '동상' 등 문맥 확인
                if matched_str == "동상" and "조각" in text:
                    continue
                # 학생 이름 주어 서술의 경우 일상 명사 제외 필터
                if category == "학생 이름 주어 서술":
                    word = m.group(1)
                    if word in ["수업", "활동", "과정", "주제", "자료", "탐구", "문제", "내용", "결과", "본문", "지문"]:
                        continue
                violations.append({
                    "category": category,
                    "matched": matched_str,
                    "description": rule["description"],
                    "position": m.span()
                })

    # 3. 주관적 내면 심리 단정 검사
    psychology_found = []
    for w in SUBJECTIVE_PSYCHOLOGY_WORDS:
        if w in text:
            psychology_found.append(w)

    # 4. 번역투 및 이중피동 검사
    translation_tone_found = []
    for pat, guide in TRANSLATION_TONE_PATTERNS:
        m = pat.search(text)
        if m:
            translation_tone_found.append({"matched": m.group(0), "guide": guide})

    # 5. 종결 어미 검사 (문장별)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    invalid_endings = []
    for s in sentences:
        s_clean = s.rstrip(".?! \t\r\n")
        if not s_clean:
            continue
        last_char = s_clean[-1]
        # 종결어미가 명사형 종결인지 체크
        ends_with_valid = any(s_clean.endswith(ve) for ve in VALID_ENDINGS)
        # 한글 음절 종성 확인 (ㅁ 받침)
        code = ord(last_char)
        has_mieum_batchim = False
        if 0xAC00 <= code <= 0xD7A3:
            final_idx = (code - 0xAC00) % 28
            if final_idx == 16:  # ㅁ 받침
                has_mieum_batchim = True
                
        if not (ends_with_valid or has_mieum_batchim):
            invalid_endings.append(s)

    # 전체 판정
    is_passed = (len(violations) == 0) and (byte_count <= 1500)

    return {
        "byte_count": byte_count,
        "char_count": char_count,
        "byte_status": byte_status,
        "byte_comment": byte_comment,
        "violations": violations,
        "psychology_found": psychology_found,
        "translation_tone_found": translation_tone_found,
        "invalid_endings": invalid_endings,
        "total_sentences": len(sentences),
        "is_passed": is_passed
    }


# ─────────────────────────────────────────────────────────────
# 5. 터미널 및 리포트 출력 포맷터
# ─────────────────────────────────────────────────────────────
def print_terminal_report(result: Dict[str, Any], title: str = "세특 자동 감수 진단 보고서"):
    print("=" * 70)
    print(f" [진단 결과] {title}")
    print("=" * 70)
    
    # 종합 판정 배너
    if result["is_passed"] and len(result["violations"]) == 0 and result["byte_status"] == "적정":
        print("▶ 최종 판정: [PASS] NEIS 규정 준수 및 안전 분량 확인")
    else:
        print("▶ 최종 판정: [REVISE REQUIRED] 수정 및 보완 필요 항목 발견")
    print("-" * 70)

    # 1. 분량 및 바이트 분석
    print(f"1. 분량 및 바이트 분석")
    print(f"   - 글자 수: {result['char_count']}자")
    print(f"   - NEIS 바이트: {result['byte_count']} / 1,500 Byte ({result['byte_status']})")
    print(f"   - 상태 소견: {result['byte_comment']}")
    print()

    # 2. 기재 금지 사항
    print(f"2. NEIS 기재 금지 사항 검출 (위반 건수: {len(result['violations'])}건)")
    if result["violations"]:
        for idx, v in enumerate(result["violations"], 1):
            print(f"   [{idx}] [{v['category']}] 감지 단어: '{v['matched']}'")
            print(f"       규격: {v['description']}")
    else:
        print("   - 위반 항목 없음 (공인어학, 수상, 논문, 대학명, 모의고사, 브랜드, 부모배경 등 무결)")
    print()

    # 3. 서술 문체 및 종결어미
    print("3. 서술 문체 및 종결 어미 점검")
    if result["invalid_endings"]:
        print(f"   - 격식체/명사형 미준수 종결 문장 ({len(result['invalid_endings'])}건):")
        for ie in result["invalid_endings"][:3]:
            print(f"     * \"{ie[:60]}...\"")
    else:
        print("   - 모든 문장이 객관적 명사형/격식체(~함, ~음, ~임)로 일관성 있게 종결됨.")

    if result["psychology_found"]:
        print(f"   - 주관적 내면 심리 단정 표현 감지: {', '.join(result['psychology_found'])}")
        print("     (관찰 가능한 구체적 행동 및 문제 해결 과정 서술로 전환 권장)")
        
    if result["translation_tone_found"]:
        print("   - 번역투 표현 감지:")
        for tt in result["translation_tone_found"]:
            print(f"     * '{tt['matched']}' -> {tt['guide']}")
            
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="NEIS 규정 및 세특 자동 감수 파이프라인")
    parser.add_argument("text", nargs="?", default=None, help="검사할 세특 텍스트")
    parser.add_argument("--file", default=None, help="검사할 텍스트 파일 경로")
    parser.add_argument("--json-out", default=None, help="검사 결과를 JSON 파일로 저장")
    args = parser.parse_args()

    text_to_audit = ""
    title = "직접 입력 세특"

    if args.file:
        if not os.path.exists(args.file):
            print(f"오류: 파일을 찾을 수 없습니다: {args.file}", file=sys.stderr)
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as f:
            text_to_audit = f.read()
        title = os.path.basename(args.file)
    elif args.text:
        text_to_audit = args.text
    else:
        # 표준 입력(stdin) 확인
        if not sys.stdin.isatty():
            text_to_audit = sys.stdin.read()
        else:
            parser.error("세특 텍스트 또는 --file 경로를 지정해야 합니다.")
            sys.exit(1)

    result = audit_seteuk_text(text_to_audit)
    print_terminal_report(result, title=title)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as jf:
            json.dump(result, jf, ensure_ascii=False, indent=2)
        print(f"진단 JSON 리포트 저장 완료: {args.json_out}")

    # 리턴 코드: 통과 시 0, 위반 사항 존재 시 2 (CI/CD 또는 파이프라인 연동용)
    if not result["is_passed"]:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
