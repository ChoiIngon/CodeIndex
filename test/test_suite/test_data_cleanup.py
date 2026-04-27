from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from utility import log_error, log_info, log_verbose
from code_index import CodeIndexProcess

ROOT = Path(__file__).parent.parent.parent.resolve()


def test_data_cleanup() -> bool:
    """데이터 정리 테스트 (파일 삭제 시)"""
    log_info("데이터 정리 테스트를 시작합니다...")

    child = None
    try:
        # 테스트 파일 경로
        test_file = ROOT / "test" / "project2_1" / "test_cleanup.cpp"
        
        # 1단계: 테스트 파일 생성
        log_verbose("1단계: 테스트 파일 생성")
        test_content = '''// 테스트용 정리 파일 - C++
#include <string>
#include <iostream>

namespace TestCleanup {
    
    std::string cleanup_test_function() {
        // 이 함수는 삭제 테스트용입니다
        return "cleanup_test_marker_unique_string";
    }
    
    class CleanupTestClass {
    public:
        CleanupTestClass() {
            marker = "cleanup_test_class_marker";
        }
        
        std::string get_marker() const {
            return marker;
        }
        
    private:
        std::string marker;
    };
    
    // 고유 식별자
    const std::string CLEANUP_MARKER = "very_unique_cleanup_marker_12345";
    
    void initialize_cleanup_test() {
        CleanupTestClass testObj;
        std::cout << "Cleanup test initialized: " << testObj.get_marker() << std::endl;
    }
    
} // namespace TestCleanup'''
        
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_content)
        
        # 2단계: 인덱싱 + 검색 확인 (run()은 인덱싱 후 MCP 서버 시작)
        log_verbose("2단계: 파일 포함하여 인덱싱 및 검색 확인")
        child = CodeIndexProcess()
        if child.run(None, wait=False) is None:
            log_error("인덱싱/MCP 서버 시작 실패")
            return False

        result = child.search_code("cleanup_test_marker_unique_string", top_k=5)
        child.kill()
        child = None

        # result가 None이면 오류, 빈 리스트이면 검색 결과 없음, 키워드가 실제로 포함된 결과가 있어야 성공
        if result is None:
            log_error("초기 내용 검색 중 오류 발생 (타임아웃 또는 프로세스 종료)")
            return False
        found, _ = result.hit("cleanup_test_marker_unique_string")
        if not found:
            log_error("초기 내용 검색 실패 - 키워드가 검색 결과에 없음")
            return False
        
        # 3단계: 파일 삭제
        log_verbose("3단계: 테스트 파일 삭제")
        test_file.unlink()
        
        # 4단계: 증분 업데이트 + 삭제 반영 확인 (run()은 변경분 재인덱싱 후 MCP 서버 시작)
        log_verbose("4단계: 증분 업데이트 (삭제 반영) 및 검색 불가 확인")
        child = CodeIndexProcess()
        if child.run(None, wait=False) is None:
            log_error("증분 업데이트/MCP 서버 시작 실패")
            return False

        result_after = child.search_code("cleanup_test_marker_unique_string", top_k=5)
        if result_after is None:
            log_error("삭제 후 검색 중 오류 발생 (타임아웃 또는 프로세스 종료)")
            return False
        found_after, _ = result_after.hit("cleanup_test_marker_unique_string")
        if found_after:
            log_error("삭제된 파일의 내용이 여전히 검색됨 - 데이터 정리 실패")
            return False

        # 다른 고유 마커들도 확인
        markers = ["cleanup_test_class_marker", "very_unique_cleanup_marker_12345"]
        for marker in markers:
            result_marker = child.search_code(marker, top_k=5)
            if result_marker is None:
                log_error(f"마커 '{marker}' 검색 중 오류 발생")
                return False
            found_marker, _ = result_marker.hit(marker)
            if found_marker:
                log_error(f"삭제된 파일의 마커 '{marker}'가 여전히 검색됨")
                return False

        child.kill()
        child = None

        log_info("데이터 정리 테스트가 성공적으로 완료되었습니다")
        return True
        
    except Exception as e:
        log_error(f"데이터 정리 테스트 중 예외 발생: {e}")
        if 'test_file' in locals():
            Path(test_file).unlink(missing_ok=True)
        return False
    finally:
        if child is not None:
            child.kill()
