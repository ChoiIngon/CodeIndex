from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from utility import log_error, log_info, log_verbose
from code_index import CodeIndexProcess


def test_get_chunk() -> bool:
    """get_chunk 조회 테스트 (search_code 결과의 chunk_id로 청크 조회)"""
    log_info("get_chunk 조회 테스트를 시작합니다...")

    child = CodeIndexProcess()
    pid = child.run(None, wait=False)
    if pid is None:
        log_error("MCP 서버 시작 실패")
        return False

    try:
        # 1단계: search_code 로 chunk_id 수집
        log_verbose("1단계: search_code 로 chunk_id 수집")
        results = child.search_code("데미지 계산", top_k=5)
        if not results:
            log_error("search_code 결과 없음 - chunk_id 를 얻을 수 없습니다")
            return False

        chunk_ids = [r.get("chunk_id") for r in results if r.get("chunk_id")]
        if not chunk_ids:
            log_error("결과에 chunk_id 필드가 없습니다")
            return False
        log_verbose(f"수집된 chunk_id {len(chunk_ids)}건")

        # 2단계: 각 chunk_id 로 get_chunk 호출 및 검증
        log_verbose("2단계: chunk_id 로 get_chunk 호출 및 검증")
        all_passed = True
        for i, chunk_id in enumerate(chunk_ids, 1):
            chunk = child.get_chunk(chunk_id)
            if chunk is None:
                log_error(f"[{i}] chunk_id='{chunk_id}' 조회 실패")
                all_passed = False
                continue

            returned_id = chunk.get("chunk_id", "")
            if returned_id != chunk_id:
                log_error(f"[{i}] chunk_id 불일치: 요청={chunk_id}, 응답={returned_id}")
                all_passed = False
                continue

            required_fields = ["file_path", "language", "start_line", "end_line", "content"]
            missing = [f for f in required_fields if not chunk.get(f)]
            if missing:
                log_error(f"[{i}] 필수 필드 누락: {missing}")
                all_passed = False
                continue

            log_verbose(
                f"  [{i}] {chunk.get('symbol_name', '')} ({chunk.get('symbol_type', '')})"
                f" | {chunk.get('file_path', '')} L{chunk.get('start_line', '')}-{chunk.get('end_line', '')}"
            )

        # 3단계: 존재하지 않는 chunk_id 로 조회 시 None 반환 확인
        log_verbose("3단계: 잘못된 chunk_id 로 조회 시 None 반환 확인")
        invalid_chunk = child.get_chunk("00000000-0000-0000-0000-000000000000")
        if invalid_chunk is not None:
            log_error("잘못된 chunk_id 에 대해 None 이 아닌 값 반환")
            all_passed = False
        else:
            log_verbose("잘못된 chunk_id → None 정상 확인")

        if all_passed:
            log_info("get_chunk 조회 테스트가 성공적으로 완료되었습니다")
        return all_passed

    except Exception as e:
        log_error(f"get_chunk 조회 테스트 중 예외 발생: {e}")
        return False
    finally:
        child.kill()