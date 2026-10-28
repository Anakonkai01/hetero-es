"""The strict evaluation engine: one exact token stream on every supported NVIDIA GPU (ADR-012/013/014).

reference_ops, qwen2_reference, integer_reference   CPU/NumPy reference arithmetic and the reference decoder
integer_plan, integer_lm_head                        B22 integer projection plan and the bounded LM head
strict_cuda, strict_prefill_cuda, strict_decode_cuda NVRTC kernels (source text is part of the identity)
integer_cuda, integer_tma, attention_stages          integer projection kernels, TMA streaming, attention stages
strict_decoder, strict_decoder_packed, strict_decoder_graph, integer_decoder, qwen2_strict_cuda   decoders
frozen_int8, frozen_int8_cuda, frozen_int8_decoder   frozen int8 base + LoRA decoder (strict_int8_lora_v1)
strict_backend                                       the entry point used by evaluation (`strict_b22_v1`)
"""
