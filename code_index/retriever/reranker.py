from __future__ import annotations

import sys

from .hybrid_search import SearchResult


class Reranker:
    """transformers AutoModelForSequenceClassification 기반 재순위화."""

    def __init__(self, model_name: str, cfg: dict):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[Reranker] 모델 로드 중: {model_name} (device={device})", file=sys.stderr)
        self._device = device
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(model_name).to(device)
        self._model.eval()
        print("[Reranker] 모델 로드 완료.", file=sys.stderr)

    def rerank(self, query: str, results: list[SearchResult], top_k: int = 8) -> list[SearchResult]:
        if not results:
            return results

        pairs = [[query, r.content[:512]] for r in results]
        encoded = self._tokenizer(
            pairs, padding=True, truncation=True, max_length=512, return_tensors="pt"
        )
        encoded = {k: v.to(self._device) for k, v in encoded.items()}
        with self._torch.no_grad():
            scores = self._model(**encoded).logits.squeeze(-1).cpu().tolist()

        ranked = sorted(zip(scores, results), key=lambda x: x[0], reverse=True)
        return [
            SearchResult(
                chunk_id=r.chunk_id, score=float(s),
                file_path=r.file_path, language=r.language,
                start_line=r.start_line, end_line=r.end_line,
                symbol_type=r.symbol_type, symbol_name=r.symbol_name,
                parent_class=r.parent_class, namespace=r.namespace,
                content=r.content,
            )
            for s, r in ranked[:top_k]
        ]
