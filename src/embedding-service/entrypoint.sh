#!/bin/bash

exec vllm serve Qwen/Qwen3-Embedding-8B \
    --served-model-name "Qwen3-Embedding-8B" \
    --task "embed" \
    --dtype "auto" \
    --kv-cache-dtype "auto" \
    --max-model-len 32768 \
    --max-num-seqs 1 \
    --gpu-memory-utilization 0.9