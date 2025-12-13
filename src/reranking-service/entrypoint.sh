#!/bin/bash

exec vllm serve Qwen/Qwen3-Reranker-8B \
    --served-model-name "Qwen3-Reranker-8B" \
    --task "score" \
    --dtype "auto" \
    --kv-cache-dtype "auto" \
    --max-model-len 32768 \
    --max-num-seqs 1 \
    --gpu-memory-utilization 0.9