# CodeIndex

게임 서버 소스코드(.cs / .h / .cpp)를 인덱싱하고, 자연어 질의에 관련 코드 청크를 반환하는 **로컬 MCP 서버**입니다.  
VS Code, Visual Studio 2022, Claude Desktop 등 MCP를 지원하는 AI 클라이언트와 연동됩니다.

## 특징

- 외부 API 키 불필요 — 임베딩 모델을 최초 실행 시 HuggingFace에서 자동 다운로드
- Dense(HNSW) + BM25 하이브리드 검색 + RRF 점수 결합
- SHA-256 기반 증분 인덱싱 — 변경된 파일만 재처리
- GPU 자동 감지 및 CUDA wheel 자동 설치
- MCP stdio / HTTP(SSE) 두 가지 전송 방식 지원

---

## 요구 사항

- Python 3.11+
- NVIDIA GPU 권장 (CPU 동작 가능, 속도 저하)
- CUDA 11.8 이상 (GPU 사용 시)

---

## 설치

```powershell
git clone https://github.com/your-repo/CodeIndex.git
cd CodeIndex
```

의존성은 첫 실행 시 자동 설치됩니다. 수동 설치가 필요하면:

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install qdrant-client tree-sitter tree-sitter-cpp tree-sitter-c-sharp mcp sentencepiece einops
```

---

## 설정

`config/settings.json` 파일에서 인덱싱 대상 경로와 옵션을 설정합니다.

```json
{
  "indexer": {
    "source_paths": [
      "C:/MyProject/src",
      "./test/data"
    ],
    "extensions": [".cpp", ".h", ".c", ".cs"],
    "exclude_patterns": ["*/build/*", "*/.git/*", "*/generated/*"]
  },
  "models": {
    "embed": "BAAI/bge-m3"
  },
  "search": {
    "top_k": 20,
    "alpha": 0.7
  },
  "debug": false
}
```

| 항목 | 설명 | 기본값 |
|---|---|---|
| `indexer.source_paths` | 인덱싱할 소스 경로 목록 | `[]` |
| `indexer.extensions` | 대상 확장자 | `.cpp .h .c .cs` |
| `indexer.chunk_min_lines` | 최소 청크 라인 수 | `5` |
| `indexer.chunk_max_lines` | 최대 청크 라인 수 | `150` |
| `models.embed` | 임베딩 모델 (HuggingFace ID) | `BAAI/bge-m3` |
| `embedding.vector_size` | 벡터 차원 | `1024` |
| `search.top_k` | 기본 반환 결과 수 | `20` |
| `search.alpha` | Dense/BM25 가중치 (1.0=Dense 전용) | `0.7` |
| `search.use_reranker` | 재랭커 사용 여부 | `false` |
| `debug` | MCP 요청/응답 로깅 (`log.txt`) | `false` |

---

## 실행

### 인덱싱만 수행

```powershell
python -m code_index --index-only
```

### stdio 모드로 MCP 서버 실행 (단일 에디터)

```powershell
python -m code_index
```

### HTTP(SSE) 모드로 MCP 서버 실행 (여러 에디터 동시 사용)

```powershell
python -m code_index --http-port 6380
```

### 인덱싱 상태 확인

```powershell
python -m code_index --status
```

### CLI 검색 (MCP 없이 직접 질의)

```powershell
# 자연어 검색
python -m code_index --search-code "데미지 계산 로직"

# 필터 옵션
python -m code_index --search-code "CalculateDamage" --top-k 10 --language cpp --symbol-type function

# 파일 심볼 목록
python -m code_index --get-file-outline "combat.cpp"

# 청크 ID로 코드 조회
python -m code_index --get-chunk "fc617902-35bc-5155-b9d1-b94837fd181d"
```

---

## MCP 에디터 연동

### stdio 모드 (기본 — 에디터 1개)

에디터가 code_index를 자식 프로세스로 직접 실행합니다.

**Claude Desktop** — `%APPDATA%\Claude\claude_desktop_config.json`
```json
{
  "mcpServers": {
    "MapleCodeIndex": {
      "command": "python",
      "args": ["-m", "code_index"],
      "cwd": "E:/work/CodeIndex"
    }
  }
}
```

**VS Code** — `.vscode/mcp.json` (워크스페이스 전용) 또는 `%APPDATA%\Code\User\mcp.json` (전역)
```json
{
  "servers": {
    "MapleCodeIndex": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "code_index"],
      "cwd": "E:/work/CodeIndex"
    }
  }
}
```

**Visual Studio 2022** — `.vs\mcp.json` (솔루션 전용) 또는 `%USERPROFILE%\.vs\mcp.json` (전역)
```json
{
  "servers": {
    "MapleCodeIndex": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "code_index"],
      "cwd": "E:/work/CodeIndex"
    }
  }
}
```

### HTTP(SSE) 모드 (에디터 여러 개 동시 사용)

먼저 서버를 실행합니다:
```powershell
python -m code_index --http-port 6380
```

각 에디터 MCP 설정에 URL을 등록합니다:

**Claude Desktop**
```json
{
  "mcpServers": {
    "MapleCodeIndex": {
      "url": "http://127.0.0.1:6380/sse"
    }
  }
}
```

**VS Code / Visual Studio 2022**
```json
{
  "servers": {
    "MapleCodeIndex": {
      "type": "sse",
      "url": "http://127.0.0.1:6380/sse"
    }
  }
}
```

---

## MCP 도구 목록

AI 클라이언트가 호출할 수 있는 도구입니다.

| 도구 | 설명 | 주요 파라미터 |
|---|---|---|
| `search_code` | 자연어/심볼명으로 코드 청크 검색 | `query`, `top_k`, `language`, `symbol_type` |
| `get_file_outline` | 파일의 심볼 목록(클래스/함수/메서드) 반환 | `file_path` |
| `get_chunk` | 청크 ID로 코드 전문 조회 | `chunk_id` |

---

## 데이터 저장 위치

| 파일 | 내용 |
|---|---|
| `./data/metadata.db` | 파일/청크 메타데이터 + FTS5 BM25 인덱스 (SQLite) |
| `./data/embed_cache.db` | content_hash → 임베딩 벡터 캐시 (SQLite) |
| `./data/qdrant/` | HNSW 벡터 인덱스 (Qdrant embedded) |
| `./log.txt` | MCP 요청/응답 로그 (`debug: true` 시) |

인덱스를 완전히 초기화하려면:
```powershell
Remove-Item ./data -Recurse
python -m code_index --index-only
```

---

## 아키텍처

```
인덱싱 파이프라인
  소스코드 → 파일 스캐너(변경 감지) → Tree-sitter 파싱
          → 청킹 → 임베딩(GPU) → Qdrant + SQLite FTS5

검색 파이프라인
  질의 → 쿼리 임베딩
       ├─ Dense 검색 (HNSW)
       └─ BM25 검색 (FTS5)
            └─ RRF 점수 결합 → [재랭킹(선택)] → 결과 반환
```

## 프로젝트 구조

```
CodeIndex/
├── code_index/
│   ├── __main__.py        # 진입점, CLI 옵션 처리
│   ├── config.py          # 설정 로드 및 기본값
│   ├── indexer/
│   │   ├── scanner.py     # 파일 스캔 및 변경 감지
│   │   ├── parser.py      # Tree-sitter AST 파싱
│   │   ├── chunker.py     # 심볼 단위 청킹
│   │   ├── embedder.py    # 임베딩 생성
│   │   └── pipeline.py    # 인덱싱 파이프라인 오케스트레이션
│   ├── store/
│   │   ├── vector_store.py    # Qdrant HNSW 벡터 저장소
│   │   ├── metadata_store.py  # SQLite 메타데이터 + FTS5
│   │   └── cache.py           # 임베딩 캐시
│   ├── retriever/
│   │   ├── hybrid_search.py   # Dense + BM25 + RRF
│   │   └── reranker.py        # 재랭킹 (선택)
│   ├── mcp/
│   │   ├── server.py          # FastMCP 서버 (도구 정의)
│   │   └── debug_logger.py    # 요청/응답 로거
│   └── models/
│       └── model_manager.py   # HuggingFace 모델 경로 관리
├── config/
│   └── settings.json      # 사용자 설정
├── test/
│   ├── run_test.py         # 정확도 테스트
│   └── data/               # 테스트용 샘플 소스코드
└── data/                   # 인덱스 데이터 (gitignore)
```
