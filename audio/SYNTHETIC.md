# Synthetic pilot recordings

## Source and reuse

The controlled Standard Mandarin (普通話) stimuli use Hexgrad’s Kokoro-82M-v1.1-zh, Hugging Face revision `01e7505bd6a7a2ac4975463114c3a7650a9f7218`. The model card and the selected voice-embedding pages declare Apache-2.0. The publisher reports training on licensed Chinese speech. The pilot uses the bundled `zf_001` and `zf_002` embeddings at model speed settings 0.9, 1.0, and 1.1. Voice IDs identify synthesis presets. The identities and regional accents of the underlying speakers are unavailable. The script checks the published SHA-256 of the frozen weights and both embedding files before loading tensors. The model license and the underlying text license are recorded separately. [Model card](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh) · [Frozen revision](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/commit/01e7505bd6a7a2ac4975463114c3a7650a9f7218) · [Voice zf_001](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/blob/main/voices/zf_001.pt) · [Voice zf_002](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/blob/main/voices/zf_002.pt)

## Pronunciation treatment

The [synthesis prescription](synthetic_readings.json) gives one intended Modern Mandarin reading for each syllable of the fifteen edition-pinned passages. This experimental choice applies to synthetic clips. It leaves the pilot lexical alternatives and historical categories available for analysis. The script validates source hashes, clause boundaries, syllable counts, and the existing context-reviewed Mandarin decision. Disagreements with the Stage 3 lexical inventory are carried into the manifest for review. Context-dependent choices include `huan2` for 還 in the sense of returning, `lao3` for 潦 in the sense of standing rainwater, `e1` for 阿 in 崇阿, `zai4` in 載書, and `cha4` for 刹 in the temple context. [還](https://dict.revised.moe.edu.tw/dictView.jsp?ID=5181&q=1&word=%E9%82%84) · [潦](https://dict.revised.moe.edu.tw/dictView.jsp?ID=3297&q=1&word=%E6%BD%A6) · [阿](https://dict.revised.moe.edu.tw/dictView.jsp?ID=10250&la=0&powerMode=0) · [載書](https://dict.revised.moe.edu.tw/searchR.jsp?ID=159&ID=6&ID=7&la=0&page=3&powerMode=0&word=%E8%BC%89) · [剎](https://dict.revised.moe.edu.tw/dictView.jsp?ID=8816&la=0&powerMode=0)

The script passes explicit Mandarin phoneme tokens to Kokoro’s low-level model. The prescription holds the same intended lexical tone and manual word grouping across voices and speed treatments. It omits an automatic tone-sandhi pass. Any surface realization, including tone sandhi, is an acoustic question. The manifest stores only the intended phonemes and marks pronunciation as `input_only`; alignment and acoustic measurements are based on the generated waveform. These clips serve as controlled stimuli for speed comparisons and pipeline checks. They provide no human reading-ease labels. [Kokoro inference source](https://github.com/hexgrad/kokoro/blob/main/kokoro/model.py) · [Misaki Mandarin token mapping](https://github.com/hexgrad/misaki/blob/main/misaki/zh_frontend.py)

## Building on Gilbreth

Use the shared Stage 4 environment with Python 3.12, CUDA-enabled PyTorch, and the [TTS package pins](requirements-tts.txt). The fully crossed design targets 90 mono PCM-16 recordings at 24 kHz. Run within a Gilbreth Slurm GPU allocation with package and model caches under project scratch.

```bash
python audio/synthesize.py --root "$SHUNKOU_ROOT"
```

Select passages for the initial GPU run by repeating `--passage-id`. `--validate-only` checks the prescription and can run without CUDA. `--offline` reuses the pinned model objects from the project Hugging Face cache. WAV files appear under `audio/raw/synthetic/`, the run manifest under `audio/manifests/synthetic.jsonl`, and model artifacts under `cache/hf/hub/`. The manifest lists the clips produced by the selected invocation. Each row carries audio checksum, text witness, speaker preset, controlled speed, model snapshot, and intended pronunciation.
