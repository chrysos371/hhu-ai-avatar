"""Labelled pair calibration for the configured embedding model, not a model download."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from .embeddings import OllamaEmbeddingProvider, normalized_vector


def evaluate_thresholds(pairs: list[dict], embedder, thresholds=None) -> dict:
    if not isinstance(pairs, list) or not pairs:
        raise ValueError('labelled pairs required')
    for pair in pairs:
        if (not isinstance(pair, dict) or type(pair.get('relevant')) is not bool or
                any(not isinstance(pair.get(k), str) or not pair[k].strip() for k in ('query', 'memory'))):
            raise ValueError('each pair needs query, memory and boolean relevant')
    positives = sum(pair['relevant'] for pair in pairs)
    negatives = len(pairs) - positives
    if not positives or not negatives:
        raise ValueError('both positive and negative pairs required')
    thresholds = list(thresholds) if thresholds is not None else [i / 100 for i in range(30, 91, 5)]
    if not thresholds or any(type(t) not in (float, int) or not math.isfinite(t) or not 0 <= t <= 1 for t in thresholds):
        raise ValueError('thresholds must be finite numbers within 0..1')
    vectors = {}
    scored = []
    for pair in pairs:
        for key in ('query', 'memory'):
            text = pair[key]
            if text not in vectors:
                vectors[text] = normalized_vector(embedder.embed(text))
        similarity = float(np.dot(vectors[pair['query']], vectors[pair['memory']]))
        scored.append(dict(pair, similarity=similarity))
    results = []
    for threshold in thresholds:
        tp = sum(p['similarity'] >= threshold and p['relevant'] for p in scored)
        fp = sum(p['similarity'] >= threshold and not p['relevant'] for p in scored)
        precision = tp / (tp + fp) if tp + fp else 0.
        recall = tp / positives
        results.append({'threshold': threshold, 'tp': tp, 'fp': fp,
                        'precision': precision, 'recall': recall, 'false_positive_rate': fp / negatives,
                        'f1': 2 * precision * recall / (precision + recall) if precision + recall else 0.})
    best = max(results, key=lambda r: (r['f1'], -r['false_positive_rate'], r['threshold']))
    return {'model_id': embedder.model_id, 'positive_pairs': positives, 'negative_pairs': negatives,
            'thresholds': results, 'recommended_threshold': best['threshold'], 'pairs': scored,
            'limitation': '仅评估独立向量对；不代表混合召回、历史过滤或最终回答准确率。小样本不能替代留出集验证。'}


def main():
    parser = argparse.ArgumentParser(description='基于标注样例扫描向量相似度阈值')
    parser.add_argument('--pairs', required=True, help='JSON array of query/memory/relevant')
    parser.add_argument('--model', default='bge-m3')
    parser.add_argument('--base-url', default='http://localhost:11434')
    parser.add_argument('--output', help='保存 JSON 报告；不会修改运行配置')
    args = parser.parse_args()
    pairs = json.loads(Path(args.pairs).read_text(encoding='utf-8'))
    report = evaluate_thresholds(pairs, OllamaEmbeddingProvider(args.base_url, args.model))
    result = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(result + '\n', encoding='utf-8')
    print(result)


if __name__ == '__main__':
    main()
