# CodeIndex

소스코드(.cs / .h / .cpp)를 인덱싱하고, 자연어 질의에 관련 코드 청크를 반환하는 **로컬 MCP 서버**입니다.  
VS Code, Visual Studio 2022, Claude Desktop 등 MCP를 지원하는 AI 클라이언트와 연동됩니다.

## 특징

- **프로젝트별 필터링** — 여러 프로젝트를 동시에 인덱싱하고 검색 시 특정 프로젝트로 범위 제한
- **Qdrant 벡터 DB(https://qdrant.tech/) 자동 설치 및 관리** — 최초 실행 시 Qdrant 바이너리를 자동 다운로드하고 서브프로세스로 관리
- **GPU 자동 감지 및 CUDA wheel 자동 설치** — NVIDIA GPU 검출 시 적합한 PyTorch CUDA 버전 자동 설치
- **SHA-256 기반 증분 인덱싱** — 변경된 파일만 재처리하여 대규모 코드베이스에서도 빠른 업데이트
- **content_hash 임베딩 캐싱** — 동일 코드 청크의 임베딩 벡터를 SQLite에 캐싱하여 재인덱싱 속도 향상
- **Tree-sitter AST 파싱** — C++/C/C# 소스를 AST로 분석해 함수·클래스·메서드·네임스페이스 단위로 정밀 
- **Dense(HNSW) + BM25 하이브리드 검색 + RRF 점수 결합** — 의미 기반 벡터 검색과 키워드 기반 BM25를 융합하여 정확도 향상
- **랭킹 재정렬** — cross-encoder 모델로 검색 결과를 재정렬해 정확도 향상 (`use_reranker: true`)
- **MCP 서버 지원** - stdio / HTTP(streamable-http) 두 가지 전송 방식 지원

---

## 요구 사항

- Python 3.11+
- NVIDIA GPU 권장 (CPU 동작 가능, 속도 저하)
- NVIDIA GPU 사용 시 CUDA 11.8+ 또는 12.x 드라이버 설치 필요(https://developer.nvidia.com/cuda-downloads)

---

## 설치 및 MCP 서버 에디터 연동

1. **클론 및 설치** — 레포지토리 클론 및 파이썬 패키징화

   ```powershell
   git clone https://github.com/ChoiIngon/CodeIndex.git
   cd CodeIndex
   pip install -e .
   ```

   - `pip install -e .`는 `code_index` 명령어를 시스템에 등록합니다. 이후 어느 디렉터리에서든 `python -m code_index` 또는 `code_index`로 실행할 수 있습니다.
   - **의존성을 가진 모듈들은 첫 실행 시 자동 설치됩니다.** GPU가 감지되면 적절한 PyTorch 버전을 자동 선택합니다.
   - **참고**: GPU 환경에서는 CUDA 11.8+ 또는 12.x에 맞는 PyTorch 안정 버전이 자동 설치됩니다. GPU를 찾지 못하는 경우 CPU 버전으로 실행됩니다.

2. **개인화 설정** — `config/settings.json`에 프로젝트별 인덱싱 설정 추가 (자세한 내용은 [설정](#설정) 참고)
   
   `config/settings.json.template`을 복사, `config/settings.json`로 수정하여 사용

   **2-1. 인덱싱 대상 프로젝트 경로 설정**

   ```json
   { 
     "indexer": { 
       "GameClient": { 
         "source_paths": ["C:/MyProject/Client/Assets"], // 절대 경로 사용 권장
         "extensions": [".cs"]
       },
       "GameServer": { 
         "source_paths": ["C:/MyProject/Server/src1"],
         "extensions": [".cpp", ".h", ".c"]
       }
     }
   }
   ```

   **2-2. 인덱싱 데이터 저장 위치 설정**

   ```json
   {
     "vector_store": {
      "data_dir": "C:/MyProject/CodeIndex/data"
     } 
   }
   ```

3. **MCP 서버 실행 및 에디터 연동**

   **3-1. HTTP 모드** (권장)

   먼저 MCP 서버를 실행한 뒤, 각 에디터에 URL을 등록합니다.
   ```powershell
   python -m code_index --http-port 6380
   ```
   **VS Code / Visual Studio 2022** — mcp.json
   ```json
   {
     "servers": {
       "CodeIndex": {
         "type": "http",
         "url": "http://127.0.0.1:6380/mcp"
       }
     }
   }
   ```

   **Claude Desktop** — claude_desktop_config.json
   ```json
   {
     "mcpServers": {
       "CodeIndex": {
         "type": "http",
         "url": "http://127.0.0.1:6380/mcp"
       }
     }
   }
   ```

   **3-2. stdio 모드** (비권장)

   stdio 모드에서는 MCP 서버 프로세스를 별도로 실행할 필요 없이 에디터가 직접 프로세스를 기동합니다.
   > 대규모 프로젝트 경우 로딩 시간이 길어, 에디터에서 자식 프로세스를 생성하다 타임 아웃 발생 할 수 있음.

   **VS Code / Visual Studio 2022** — mcp.json
   ```json
   {
     "servers": {
       "CodeIndex": {
         "type": "stdio",
         "command": "python",
         "args": [ "-m", "code_index" ],
         "env": {
           "PYTHONPATH": "E:\\work\\CodeIndex"
         }
       }
     }
   }
   ```

   **Claude Desktop** — claude_desktop_config.json
   ```json
   {
	"mcpServers": {
       "CodeIndex": {
         "command": "python",
         "args": ["-m", "code_index"],
         "cwd": "E:/work/CodeIndex"
       }
     }
   }
   ```

   **3-3. mcp 설정파일 경로**
   
   | 에디터 | 우선 순위 | 경로 | 범위 |
   |----------|----------|------|------|
   | VSCode| 1 | <워크스페이스폴더>/.vscode/mcp.json | 워크스페이스 단위 |
   |       | 2 | %USERPROFILE%/.vscode/mcp.json | 사용자 전체 (글로벌) |
   | Visual Studio 2022|  1 | <솔루션폴더>/.vs/mcp.json | 솔루션 단위 (VS 전용) |
   |       | 2 | <솔루션폴더>/.vscode/mcp.json | 솔루션 단위 (VS Code 공유 가능) |
   |       | 3 | %USERPROFILE%/.mcp.json | 사용자 전체 (글로벌) |
   | Claude Desktop | 1 | %APPDATA%\Claude\claude_desktop_config.json | 사용자 전체 (글로벌) |
   > 참고: Claude Desktop은 단일 글로벌 설정 파일만 지원하며, 워크스페이스/프로젝트 단위의 별도 경로는 지원하지 않습니다.

---

## 설정

`config/settings.json` 파일에서 프로젝트별 인덱싱 설정을 관리합니다.

```json
{
  "indexer": {
    "chunk_min_lines": 5,
    "chunk_max_lines": 80,
    "chunk_overlap_lines": 10,
    "chunk_workers": 0,
    "GameServer": {
      "source_paths": ["C:/MyProject/Server"],
      "extensions": [".cpp", ".h", ".c"],
      "exclude_patterns": ["*/build/*", "*/.git/*", "*/Utility/*"]
    },
    "GameClient": {
      "source_paths": ["C:/MyProject/Client/Assets"],
      "extensions": [".cs"],
      "exclude_patterns": ["*/Library/*", "*/Packages/*"]
    }
  },
  "models": {
    "cache_dir": "",
    "embed": "BAAI/bge-m3",
    "rerank": "cross-encoder/ms-marco-MiniLM-L-12-v2"
  },
  "embedding": {
    "vector_size": 1024,
    "batch_size": 64,
    "n_gpu_layers": -1
  },
  "vector_store": {
    "mode": "server",
    "host": "localhost",
    "port": 6333,
    "data_dir": "./data"
  },
  "search": {
    "top_k": 20,
    "rerank_top_k": 8,
    "min_score": 0.0,
    "alpha": 0.5,
    "use_reranker": false
  },
  "debug": false
}
```

### indexer

**구조**: `"indexer": { "chunk_설정...", "ProjectName": { ... }, "AnotherProject": { ... } }`

#### 공유 청킹 설정 (모든 프로젝트 적용)

| 항목 | 설명 | 기본값 |
|---|---|---|
| `chunk_min_lines` | 이 값 미만의 라인 수를 가진 심볼은 청크에서 제외 | `5` |
| `chunk_max_lines` | 청크 최대 라인 수. 초과 시 overlap을 유지하며 분할 | `80` |
| `chunk_overlap_lines` | 분할된 청크 간 중복 라인 수. 컨텍스트 연속성 유지 | `10` |
| `chunk_workers` | 청킹 병렬 프로세스 수. `0` = CPU 코어 수의 절반 자동 사용 | `0` |

#### 프로젝트별 개별 설정

각 프로젝트별로 독립적인 설정을 가질 수 있습니다:

| 항목 | 설명 | 기본값 |
|---|---|---|
| `source_paths` | 해당 프로젝트의 인덱싱 소스 경로 목록. 절대/상대 경로 | `[]` |
| `extensions` | 해당 프로젝트의 인덱싱 대상 확장자 목록 | `[".cpp", ".h", ".c", ".cs"]` |
| `exclude_patterns` | 해당 프로젝트의 제외 경로 패턴 (glob) | `["*/build/*", "*/.git/*", "*/generated/*"]` |

**예제**:
- `GameServer`: C++ 파일만, Utility 폴더 제외  
- `Middleware`: C# 파일만, Unity 관련 폴더 제외

**프로젝트별 필터링 활용 사례**:
- 패킷 호환성 검증: GameServer의 serialize와 Middleware의 deserialize 비교
- 언어별 코딩 패턴 분석: C++ vs C# 구현 방식 차이점 파악  
- 프로젝트 간 API 일관성 체크: 공통 모듈의 인터페이스 구현 검증

### models

| 항목 | 설명 | 기본값 |
|---|---|---|
| `cache_dir` | 모델 다운로드 캐시 경로. 비워두면 프로젝트 루트의 `.cache/` 사용 | `""` |
| `embed` | 임베딩 모델 HuggingFace ID. 변경 시 `vector_size`도 함께 변경하고 재인덱싱 필요 | `"BAAI/bge-m3"` |
| `rerank` | 재랭커 모델 HuggingFace ID. `search.use_reranker: true` 일 때만 로드됨 | `"cross-encoder/ms-marco-MiniLM-L-12-v2"` |

### embedding

| 항목 | 설명 | 기본값 |
|---|---|---|
| `vector_size` | 임베딩 벡터 차원. 사용하는 `models.embed` 모델의 출력 차원과 일치해야 함 | `1024` |
| `batch_size` | 임베딩 배치 크기. GPU VRAM에 따라 조정 (RTX 3060: 64, RTX 4090: 128+) | `64` |
| `n_gpu_layers` | (예약) GPU 레이어 수. 현재 미사용 | `-1` |

### vector_store

| 항목 | 설명 | 기본값 |
|---|---|---|
| `mode` | `"server"`: 별도 Qdrant 프로세스 사용 (권장), `"embedded"`: Python 프로세스 내 내장 모드 | `"server"` |
| `host` | Qdrant 서버 호스트. `mode: "server"` 일 때 사용 | `"localhost"` |
| `port` | Qdrant HTTP 포트. gRPC는 `port + 1` 자동 사용 | `6333` |
| `data_dir` | 데이터 저장 루트 경로. 이 경로 하위에 `qdrant/` 디렉터리가 생성되며, `metadata.db`와 `embed_cache.db`도 이 경로에 저장됨 | `"./data"` 또는 `"C:\data` |

> **server mode**: 최초 실행 시 `.cache/qdrant/qdrant.exe`를 GitHub Releases에서 자동 다운로드하고 백그라운드 프로세스로 기동합니다. code_index 종료 시 함께 종료됩니다.

### search

| 항목 | 설명 | 기본값 |
|---|---|---|
| `top_k` | 검색 결과 반환 수. 리랭커 사용 시 이 수만큼 후보를 뽑아 `rerank_top_k`로 압축 | `20` |
| `rerank_top_k` | 리랭커 최종 반환 수. `use_reranker: true` 일 때만 적용 | `8` |
| `min_score` | 최소 점수 필터. 이 값 미만 결과는 제외 (`0.0` = 필터 없음) | `0.0` |
| `alpha` | Dense/BM25 가중치. `1.0` = Dense 전용, `0.0` = BM25 전용, `0.5` = 균등 혼합 | `0.5` |
| `use_reranker` | `true` 시 `models.rerank` 모델로 결과를 재정렬해 정확도 향상. 속도 소폭 저하 | `false` |

### 디버깅

| 항목 | 설명 | 기본값 |
|---|---|---|
| `debug` | `true` 시 MCP 요청/응답을 `log.txt`에 기록 | `false` |

---

## 실행

* 인덱싱만 수행
   ```powershell
   python -m code_index --index-only
   ```

* stdio 모드로 MCP 서버 실행 (단일 에디터)

   ```powershell
   python -m code_index
   ```

* HTTP 모드로 MCP 서버 실행 (여러 에디터 동시 사용)

   ```powershell
   python -m code_index --http-port 6380
   ```

* 인덱싱 상태 확인

   ```powershell
   python -m code_index --status
   ```

* CLI 검색 (MCP 없이 직접 질의)

   ```powershell
   # 자연어 검색
   python -m code_index --search-code "데미지 계산 로직"
   
   # 필터 옵션
   python -m code_index --search-code "CalculateDamage" --top-k 10 --language cpp    --symbol-type function
   
   # 프로젝트별 검색 (GameServer 프로젝트에서만 검색)
   python -m code_index --search-code "QA_Login serialize" --project "GameServer"    --top-k 5
   
   # 프로젝트 간 비교 분석 예시
   python -m code_index --search-code "QA_Login serialize" --project "GameServer"    --top-k 3
   python -m code_index --search-code "QA_Login deserialize" --project "Middleware"    --top-k 3
   
   # 파일 심볼 목록
   python -m code_index --get-file-outline "combat.cpp"
   
   # 청크 ID로 코드 조회
   python -m code_index --get-chunk "fc617902-35bc-5155-b9d1-b94837fd181d"
   ```

---

## MCP 도구 목록

AI 클라이언트가 호출할 수 있는 도구입니다.

| 도구 | 설명 | 주요 파라미터 |
|---|---|---|
| `search_code` | 자연어/심볼명으로 코드 청크 검색 | `query`, `top_k`, `language`, `symbol_type`, `project` |
| `get_file_outline` | 파일의 심볼 목록(클래스/함수/메서드) 반환 | `file_path` |
| `get_chunk` | 청크 ID로 코드 전문 조회 | `chunk_id` |

---

## 데이터 저장 위치

| 파일/디렉터리 | 내용 |
|---|---|
| `./data/metadata.db` | 파일/청크 메타데이터 + FTS5 BM25 인덱스 (SQLite) |
| `./data/embed_cache.db` | content_hash → 임베딩 벡터 캐시 (SQLite) |
| `./data/qdrant/` | HNSW 벡터 인덱스 (Qdrant 데이터) |
| `./.cache/qdrant/qdrant.exe` | 자동 다운로드된 Qdrant 실행 파일 |
| `./.cache/` | HuggingFace 모델 캐시 (`models.cache_dir` 미설정 시) |
| `./log.txt` | MCP 요청/응답 로그 (`debug: true` 시) |

인덱스를 완전히 초기화하려면:
```powershell
python -m code_index --remove
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
│   ├── constants.py       # 전역 상수 및 설정값
│   ├── indexer/
│   │   ├── scanner.py     # 파일 스캔 및 변경 감지
│   │   ├── parser.py      # Tree-sitter AST 파싱
│   │   ├── chunker.py     # 심볼 단위 청킹
│   │   ├── embedder.py    # 임베딩 생성
│   │   └── pipeline.py    # 인덱싱 파이프라인 오케스트레이션
│   ├── options/               # CLI 옵션별 처리 모듈
│   ├── store/
│   │   ├── vector_store.py    # Qdrant HNSW 벡터 저장소
│   │   ├── metadata_store.py  # SQLite 메타데이터 + FTS5
│   │   ├── qdrant_server.py   # Qdrant 바이너리 자동 다운로드 및 서버 관리
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
│   └── settings.json.template # 설정 템플릿
├── test/
│   ├── run_test.py            # 정확도 테스트 실행
│   ├── code_index.py          # CodeIndex 자식 프로세스 관리
│   ├── utility.py             # 테스트 유틸리티
│   ├── project1/              # C++/C# 테스트용 샘플 소스코드
│   ├── project2_1/            # C++/C# 테스트용 샘플 소스코드
│   ├── project2_2/            # C++/TypeScript 테스트용 샘플 소스코드
│   └── test_suite/            # 자동화 테스트 모음
└── data/                      # 인덱스 데이터 (gitignore)
```
