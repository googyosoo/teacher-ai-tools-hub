#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ondevice_edu_rag.py

'EmbeddingGemma 2 온디바이스 에듀테크 실전 활용 가이드'를 기반으로 구현한
100% 로컬 오프라인 교과자료 시맨틱 검색 및 세특 유사도 분석 RAG 엔진.

[3대 핵심 기능]
1. 수능/내신 영어 지문 및 성취기준 의미 기반 시맨틱 검색 (Semantic Passage Retrieval)
2. 학생 간 세특 의미적 유사도 매트릭스 계산 및 복제 의혹 방지 (Duplication Detector)
3. Matryoshka 차원 압축 (768차원 -> 256차원으로 66.7% 경량화)
"""

import argparse
import json
import os
import sqlite3
import sys
from typing import Dict, List, Tuple, Any
import numpy as np

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# 1. 온디바이스 임베딩 모델 로더 (하이브리드 지원)
# ─────────────────────────────────────────────────────────────
class LocalEmbeddingEngine:
    def __init__(self, model_name: str = "google/embeddinggemma-2", dim: int = 256):
        self.target_model_name = model_name
        self.dim = dim
        self.model = None
        self.use_fallback = False
        self._init_model()

    def _init_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            # 우선 가이드에 명시된 모델 로드 시도, 오프라인 미다운로드 시 고속 로컬 경량 모델로 안전 전환
            try:
                self.model = SentenceTransformer(self.target_model_name)
                print(f"[Engine] EmbeddingGemma 2 모델 로드 성공: {self.target_model_name}")
            except Exception:
                fallback_name = "sentence-transformers/all-MiniLM-L6-v2"
                print(f"[Engine] '{self.target_model_name}' 로컬 캐시 없음 -> 경량 온디바이스 표준 모델로 전환: {fallback_name}")
                self.model = SentenceTransformer(fallback_name)
                self.use_fallback = True
        except Exception as e:
            print(f"[Engine] sentence_transformers 로드 실패: {e}, sklearn TF-IDF 벡터라이저로 안전 구동")
            self.model = None

    def encode(self, texts: List[str], use_matryoshka: bool = True) -> np.ndarray:
        if self.model is not None:
            # 1. 모델 인코딩
            embeddings = self.model.encode(texts, normalize_embeddings=False)
            if len(embeddings.shape) == 1:
                embeddings = embeddings.reshape(1, -1)
            
            # 2. Matryoshka 차원 압축 (MRL: 가이드 3번 코드 구현)
            if use_matryoshka and embeddings.shape[1] > self.dim:
                embeddings = embeddings[:, :self.dim]
                
            # 3. L2 정규화 (코사인 유사도 연산 표준화)
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1e-12
            normalized = embeddings / norms
            return normalized
        else:
            # Fallback: sklearn TF-IDF
            from sklearn.feature_extraction.text import TfidfVectorizer
            vec = TfidfVectorizer()
            mat = vec.fit_transform(texts).toarray()
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0] = 1e-12
            return mat / norms


# ─────────────────────────────────────────────────────────────
# 2. 교과 지문 및 성취기준 로컬 데이터베이스
# ─────────────────────────────────────────────────────────────
SAMPLE_CURRICULUM_DATABASE = [
    {
        "id": "CSAT-2027-34",
        "title": "인공지능 알고리즘의 객관성 신화와 가치 편향",
        "category": "수능 킬러 빈칸추론",
        "standard_code": "[12영Ⅰ03-01]",
        "text": (
            "Algorithmic decision-making systems are frequently celebrated for their supposed immunity "
            "to subjective human bias. However, this belief overlooks the fundamental reality that algorithms "
            "do not emerge in a cultural vacuum; rather, they reflect the systemic inequities of past training data "
            "and perpetuate historical social distortions."
        ),
        "korean_summary": "알고리즘이 중립적이라는 통념을 비판하고 과거의 불평등 데이터를 학습하여 편견을 영속화한다는 점을 규명함."
    },
    {
        "id": "CSAT-2026-31",
        "title": "인지 편향과 확증 편향(Confirmation Bias)",
        "category": "모의평가 빈칸추론",
        "standard_code": "[12영Ⅰ03-02]",
        "text": (
            "Confirmation bias refers to the tendency to process information by searching for, interpreting, "
            "and remembering data that aligns with pre-existing beliefs, while systematically ignoring contradictory facts."
        ),
        "korean_summary": "자신의 신념과 일치하는 정보만 취사선택하고 반대 근거를 배제하는 인간의 확증 편향 심리를 설명함."
    },
    {
        "id": "CSAT-2025-36",
        "title": "행동경제학의 손실 회피성(Loss Aversion)",
        "category": "수능 기출 순서배열",
        "standard_code": "[12영Ⅱ03-01]",
        "text": (
            "In behavioral economics, loss aversion suggests that the psychological pain of losing is "
            "roughly twice as powerful as the pleasure of gaining equivalent monetary value in financial decisions."
        ),
        "korean_summary": "동일한 금액이라도 얻는 기쁨보다 잃는 고통을 2배 더 크게 느끼는 손실 회피 성향을 분석함."
    },
    {
        "id": "TEXTBOOK-ENG1-CH4",
        "title": "생태계 복원력과 기후 변화 적응",
        "category": "교과서 독해 단원",
        "standard_code": "[12영Ⅰ02-04]",
        "text": (
            "Biodiversity acts as a natural buffer against environmental shocks. When diverse ecological "
            "species coexist, the ecosystem exhibits greater resilience against global warming and extreme climatic events."
        ),
        "korean_summary": "생물 다양성이 기후 위기와 환경 충격을 완충하는 자연의 회복탄력성 역할을 함을 밝힘."
    }
]


# ─────────────────────────────────────────────────────────────
# 3. 로컬 RAG 검색 및 세특 유사도 분석기 클래스
# ─────────────────────────────────────────────────────────────
class OnDeviceEduRAG:
    def __init__(self, db_path: str = "edu_knowledge.db", dim: int = 256):
        self.engine = LocalEmbeddingEngine(dim=dim)
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS passages (
                id TEXT PRIMARY KEY,
                title TEXT,
                category TEXT,
                standard_code TEXT,
                text TEXT,
                korean_summary TEXT,
                vector BLOB
            )
        """)
        conn.commit()
        conn.close()

    def index_curriculum_passages(self, passages: List[Dict[str, Any]]):
        """교과 지문 및 성취기준을 로컬 DB에 벡터 인덱싱"""
        texts = [p["text"] + " " + p["korean_summary"] for p in passages]
        vectors = self.engine.encode(texts, use_matryoshka=True)
        
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        for p, vec in zip(passages, vectors):
            cur.execute("""
                INSERT OR REPLACE INTO passages 
                (id, title, category, standard_code, text, korean_summary, vector)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                p["id"], p["title"], p["category"], p["standard_code"],
                p["text"], p["korean_summary"], vec.tobytes()
            ))
        conn.commit()
        conn.close()
        print(f"[RAG Index] 총 {len(passages)}개 교과/수능 지문 벡터 인덱싱 완료 (Matryoshka {self.engine.dim}차원 압축)")

    def search_passages(self, query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """교사 질의에 대한 시맨틱 벡터 유사도 검색 (가이드 1번 코드)"""
        q_vec = self.engine.encode([query], use_matryoshka=True)[0]
        
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, title, category, standard_code, text, korean_summary, vector FROM passages")
        rows = cur.fetchall()
        conn.close()

        results = []
        for r in rows:
            doc_id, title, cat, std, text, summary, v_blob = r
            v_arr = np.frombuffer(v_blob, dtype=np.float32)
            # 코사인 유사도
            sim = float(np.dot(q_vec, v_arr))
            results.append({
                "id": doc_id,
                "title": title,
                "category": cat,
                "standard_code": std,
                "text": text,
                "summary": summary,
                "similarity": sim
            })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    def audit_seteuk_duplication(self, student_records: Dict[str, str], threshold: float = 0.85) -> Dict[str, Any]:
        """학생 간 세특 의미적 유사도 매트릭스 계산 및 복제 의혹 감지 (가이드 2번 코드)"""
        names = list(student_records.keys())
        texts = list(student_records.values())

        vectors = self.engine.encode(texts, use_matryoshka=True)
        sim_matrix = np.dot(vectors, vectors.T)

        high_risk_pairs = []
        moderate_risk_pairs = []

        n = len(names)
        for i in range(n):
            for j in range(i + 1, n):
                score = float(sim_matrix[i][j])
                pair_info = {
                    "student_a": names[i],
                    "student_b": names[j],
                    "similarity": round(score, 4),
                    "text_a": texts[i],
                    "text_b": texts[j]
                }
                if score >= threshold:
                    high_risk_pairs.append(pair_info)
                elif score >= 0.75:
                    moderate_risk_pairs.append(pair_info)

        return {
            "total_students": n,
            "high_risk_count": len(high_risk_pairs),
            "moderate_risk_count": len(moderate_risk_pairs),
            "high_risk_pairs": high_risk_pairs,
            "moderate_risk_pairs": moderate_risk_pairs,
            "similarity_matrix": sim_matrix.tolist(),
            "student_names": names
        }


# ─────────────────────────────────────────────────────────────
# 4. 메인 실행 및 하네스 시연
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="EmbeddingGemma 2 온디바이스 에듀테크 RAG 엔진")
    parser.add_argument("--query", default="심리학과 인지 편향, 인간의 비합리적 의사결정", help="교과자료 시맨틱 검색 질의")
    parser.add_argument("--audit-seteuk", action="store_true", help="학생 세특 유사도 교차 검증 실행")
    parser.add_argument("--out-json", default="ondevice_rag_result.json", help="결과 JSON 파일")
    args = parser.parse_args()

    print("=" * 70)
    print(" [EmbeddingGemma 2 온디바이스 에듀테크 로컬 RAG 가동] ")
    print("=" * 70)

    rag = OnDeviceEduRAG(dim=256)
    rag.index_curriculum_passages(SAMPLE_CURRICULUM_DATABASE)

    # 1. 시맨틱 검색 시연
    print(f"\n▶ [과제 1: 교과 시맨틱 검색] 질의: \"{args.query}\"")
    search_hits = rag.search_passages(args.query, top_k=2)
    for rank, hit in enumerate(search_hits, 1):
        print(f"   [{rank}위 매칭] 유사도: {hit['similarity']:.4f} | [{hit['standard_code']}] {hit['title']} ({hit['category']})")
        print(f"     * 요약: {hit['summary']}")
        print(f"     * 원문 발췌: {hit['text'][:80]}...")

    # 2. 학생 간 세특 유사도 분석 시연
    print(f"\n▶ [과제 2: 학생 세특 유사도 매트릭스 및 복제 의혹 분석]")
    sample_students = {
        "김민준": "영어 지문 속 AI 알고리즘의 윤리적 편향 문제를 비판적으로 분석하고 기술 격차에 대한 논리적인 에세이를 작성함.",
        "이서연": "인공지능 시스템의 통계적 예측으로 인한 디지털 격차와 윤리적 책임에 대해 깊이 고찰하고 우수한 영문 리포트를 완성함.",
        "박도윤": "영미 문학에 나타난 자연주의적 시각을 비교 독해하고 환경 보호의 중요성을 학급에 영어로 발표함.",
        "최지우": "행동경제학의 손실 회피 이론을 다룬 영어 논문을 읽고 소비자의 심리적 구매 패턴을 도표로 정리하여 공유함."
    }

    duplication_report = rag.audit_seteuk_duplication(sample_students, threshold=0.82)
    print(f"   - 총 학생 수: {duplication_report['total_students']}명")
    print(f"   - 고위험 유사 쌍 (유사도 >= 82%): {duplication_report['high_risk_count']}건")
    for pair in duplication_report["high_risk_pairs"]:
        print(f"     ⚠️ [복제 위험] {pair['student_a']} vs {pair['student_b']} (유사도: {pair['similarity']:.4f})")
        print(f"        사유: AI 윤리 및 디지털 격차 활동 서술 문맥이 극도로 유사하여 개별 맞춤화 재작성 필요.")

    for pair in duplication_report["moderate_risk_pairs"]:
        print(f"     ℹ️ [주의] {pair['student_a']} vs {pair['student_b']} (유사도: {pair['similarity']:.4f})")

    # 결과 리포트 저장
    output_data = {
        "search_hits": search_hits,
        "duplication_report": duplication_report
    }
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\n[완료] 결과 JSON 파일 저장: {args.out_json}")
    print("=" * 70)


if __name__ == "__main__":
    main()
