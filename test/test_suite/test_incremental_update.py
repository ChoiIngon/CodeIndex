from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from utility import log_error, log_info, log_verbose
from code_index import CodeIndexProcess

ROOT = Path(__file__).parent.parent.parent.resolve()


def test_incremental_update() -> bool:
    """증분 업데이트 테스트"""
    log_info("증분 업데이트 테스트를 시작합니다...")
    
    child = None
    try:
        # 테스트 파일 경로
        test_file = ROOT / "test" / "project1" / "test_update.cpp"
        
        # 1단계: 새 파일 생성
        log_verbose("1단계: 새 파일 생성")
        test_content_v1 = '''// 테스트용 업데이트 파일 - C++
#include <string>
#include <iostream>

class TestClass {
public:
    std::string testFunction() {
        return "version 1";
    }
    
    int getValue() {
        return value;
    }
    
private:
    int value = 1;
};'''
        
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_content_v1)
        
        # 2단계: 초기 인덱싱 + 검색 확인 (run()은 인덱싱 후 MCP 서버 시작)
        log_verbose("2단계: 초기 인덱싱 및 검색 확인")
        child = CodeIndexProcess()
        if child.run(None, wait=False) is None:
            log_error("초기 인덱싱/MCP 서버 시작 실패")
            return False
        
        result = child.search_code("version 1", top_k=5)
        child.kill()
        child = None
        
        hit, rank = result.hit("version 1")
        if not hit:
            log_error("초기 내용 검색 실패")
            return False
        
        # 3단계: 파일 수정
        log_verbose("3단계: 파일 수정")
        test_content_v2 = '''// 테스트용 업데이트 파일 - C++ (수정됨)
#include <string>
#include <iostream>

class TestClass {
public:
    std::string testFunction() {
        return "version 2 updated";
    }
    
    bool newFunction() {
        return true;
    }
    
    int getValue() {
        return value;
    }
    
    std::string getNewField() {
        return newField;
    }
    
private:
    int value = 2;
    std::string newField = "added";
};

struct NewInterface {
    std::string id;
    std::string name;
};'''
        
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_content_v2)
        
        # 4단계: 증분 업데이트 + 검색 확인 (run()은 변경분 재인덱싱 후 MCP 서버 시작)
        log_verbose("4단계: 증분 업데이트 및 검색 확인")
        child = CodeIndexProcess()
        if child.run(None, wait=False) is None:
            log_error("증분 업데이트/MCP 서버 시작 실패")
            return False
        
        # 새로운 내용 검색
        result_v2 = child.search_code("version 2 updated", top_k=5)
        if not result_v2:
            log_error("새로운 내용 검색 실패")
            return False
        
        # 이전 내용이 검색되지 않는지 확인
        result_v1 = child.search_code("version 1", top_k=5)
        child.kill()
        child = None
        
        if result_v1 and any(
            "version 1" in r.get("content", "") and "version 2" not in r.get("content", "")
            for r in result_v1
        ):
            log_error("이전 내용이 여전히 검색됨 - 증분 업데이트 실패")
            return False
        
        # 5단계: 정리
        test_file.unlink(missing_ok=True)
        
        log_info("증분 업데이트 테스트가 성공적으로 완료되었습니다")
        return True

    except Exception as e:
        log_error(f"증분 업데이트 테스트 중 예외 발생: {e}")
        if 'test_file' in locals():
            Path(test_file).unlink(missing_ok=True)
        return False
    finally:
        if child is not None:
            child.kill()
