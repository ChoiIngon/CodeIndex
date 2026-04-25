import sys
from pathlib import Path


def help() -> None:
    cwd = str(Path(__file__).parent.parent.parent.resolve()).replace("\\", "/")
    py  = sys.executable.replace("\\", "/")
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    
    print(f"""\
CodeIndex  ─  코드 시랜틱 검색 & MCP 서버

시스템 요구사항:
  Python 3.10+ (현재: {python_version})
  {'✓ 호환됨' if sys.version_info >= (3, 10) else '✗ 업그레이드 필요 - Python 3.10+ 설치하세요'}

사용법:
  python -m code_index [옵션]

  --index-only        인덱싱만 수행하고 MCP 서버를 시작하지 않습니다.
  --http-port PORT    HTTP(SSE) 모드로 MCP 서버 실행 (예: --http-port 6380)
                      생략 시 stdio 모드로 실행합니다.
  --status            인덱싱 상태 출력 (프로젝트별 파일/청크 수, 최종 인덱싱 시각)
  --remove            설치된 pip 패키지, .cache/(모델+Qdrant), 인덱스 데이터를 모두 삭제합니다.
                      재설치 테스트나 완전 초기화 시 사용합니다.
  --help              이 도움말 출력

  --search-code QUERY
    자연어 또는 심볼명으로 코드를 검색합니다.
    --top-k N            반환 결과 수  (기본: settings.json search.top_k)
    --language LANG      언어 필터     (cpp / cs / c / ...)
    --symbol-type TYPE   심볼 타입   (function / class / method / ...)
    --project PROJ       프로젝트 필터  (GameServer / Middleware / ...)
    
    예:
        python -m code_index --search-code "데미지 계산 로직"
        python -m code_index --search-code "CalculateDamage" --top-k 10 --language cpp
        python -m code_index --search-code "플레이어" --symbol-type class

  --get-file-outline PATH
    파일의 심볼 목록(클래스/함수/메서드)을 반환합니다.
    PATH: 절대 경로 또는 경로 일부 (부분 매칭 지원)

    예:
        python -m code_index --get-file-outline "combat.cpp"
        python -m code_index --get-file-outline "E:/work/Project/src/player.h"

  --get-chunk CHUNK_ID
    청크 ID(UUID)로 특정 코드 청크를 조회합니다.
    CHUNK_ID: --search-code / --query-batch 결과의 chunk_id

    예:
        python -m code_index --get-chunk "fc617902-35bc-5155-b9d1-b94837fd181d"

  --query-batch
    stdin에서 JSON 배열을 읽어 일괄 검색 후 stdout에 JSON 출력.
    --top-k N   기본 반환 결과 수
      입력 포맷:
        [{{"query": "검색어", "top_k": 5}}, ...]
      예:
        echo '[{{"query":"데미지 계산","top_k":5}}]' | python -m code_index --query-batch

MCP 설정:
  settings.json 의 mcp 섹션으로 전송 방식을 선택합니다.

  ── stdio 모드 (기본, --http-port 없을 때) ──────────────────────────────
  에디터가 code_index를 자식 프로세스로 직접 실행합니다.
  에디터 1개만 사용할 때 적합합니다.

  ▶ Claude Desktop
  ├ %APPDATA%\\Claude\\claude_desktop_config.json
  └ {{
      "mcpServers": {{
        "CodeIndex": {{
          "command": "{py}",
          "args": ["-m", "code_index"],
          "cwd": "{cwd}"
        }}
      }}
    }}

  ▶ VS Code / Visual Studio 2022
  └ {{
      "servers": {{
        "CodeIndex": {{
          "type": "stdio",
          "command": "{py}",
          "args": ["-m", "code_index"],
          "cwd": "{cwd}"
        }}
      }}
    }}

  ── HTTP 모드 (--http-port PORT 지정 시) ────────────────────────────────
  code_index를 먼저 HTTP 서버로 실행한 뒤 여러 에디터가 URL로 접속합니다.
  에디터 여러 개 동시 사용 시 적합합니다.

  1) code_index 실행:
       python -m code_index --http-port 6380
       → [MCP] CodeIndex MCP 서버 시작 (HTTP  http://127.0.0.1:6380/mcp)...

  2) 각 에디터 MCP 설정:
  ▶ Claude Desktop
  └ {{
      "mcpServers": {{
        "CodeIndex": {{
          "url": "http://127.0.0.1:6380/mcp"
        }}
      }}
    }}

  ▶ VS Code / Visual Studio 2022
  └ {{
      "servers": {{
        "CodeIndex": {{
          "type": "http",
          "url": "http://127.0.0.1:6380/mcp"
        }}
      }}
    }}

  ── 파일 위치 (private / global) ────────────────────────────────────────
  VS Code     private : .vscode/mcp.json  (워크스페이스 루트)
              global  : %APPDATA%\\Code\\User\\mcp.json
  VS 2022     private : .mcp.json  (솔루션 파일과 같은 폴더, 소스컨트롤 추적 가능)
              private : .vs\\mcp.json  (솔루션 파일과 같은 폴더, VS 전용)
              global  : %USERPROFILE%\\.mcp.json  (C:\\Users\\<사용자명>\\.mcp.json)
  Claude      공통    : %APPDATA%\\Claude\\claude_desktop_config.json
""")
    sys.exit(0)