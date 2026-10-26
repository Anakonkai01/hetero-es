# HeteroES — current state

One page, kept current. Update it in place (do not stack "Latest" paragraphs). Session history lives in
[archive/handoffs/](archive/handoffs/); the previous version of this file is
[HANDOFF-history-2026-10.md](archive/handoffs/HANDOFF-history-2026-10.md).

## Tóm tắt cho chủ dự án (2026-10-26)

- **Phiên Claude 26/10 tối đã chốt theo yêu cầu chủ dự án (sắp hết usage); bàn giao cho Codex.** Đọc
  [handoff Codex mới](handoff-codex-after-claude-fused-2026-10-26.md) trước. Strict B22 (số học giữ nguyên
  từng bit) Qwen batch 32 5070 Ti: `75f92c30` **4761** → `d4030b52` **7589** → `1c9a54b9` **8580** token/s
  short32; vLLM đối chứng **13835**, mục tiêu chưa đạt. Bằng chứng:
  [phép chiếu](evidence/2026-10-26-strict-projection-shapes/README.md) (niêm phong, 5070 Ti/3060 WSL2/Win11),
  [finish gộp](evidence/2026-10-26-strict-fused-finish/README.md). Việc tiếp: attention prefill, phép chiếu
  prefill, attention decode ngữ cảnh dài, wave của phép chiếu decode.
- **Chỉ đạo mới nhất: hoàn tất khảo sát vLLM, ghi lại, rồi tiếp tục tối ưu strict kernel riêng để gần ngang
  vLLM; đạt mục tiêu hiệu năng thì làm tiếp đầy đủ M0–M6.** Không dùng tốc độ của wrapper vLLM để đóng
  mục tiêu kernel. D2/D3 (cùng candidate/input, cùng token/reward trên GPU khác nhau) vẫn giữ.
- Nhánh `work/codex-frozen-perf-2026-10-25`, worktree `/home/pc5070ti/projects/heteroes-codex-frozen-perf`.
  Strict B22 `b1ef257a`: batch 32 **4504 / 4346 / 2322** token/s cho Smol/Qwen/Tiny trên 5070 Ti,
  tăng thêm **10,8% / 15,8% / 16,9%** nhờ prefetch trọng số, giữ nguyên số học. SM86 tăng thêm
  **8,2% / 8,0% / 9,2%**. Mới khoảng **30–33%** vLLM đối chứng; mục tiêu chưa đạt.
  [Bằng chứng](evidence/2026-10-26-strict-prefetch/README.md).
- Khảo sát vLLM đã đo parent và 8 candidate chuẩn ± trên hai GPU: Qwen đổi reward **51/2421** lượt trong
  bộ raw/256 token. Kiểm tra lại chat/512 token: **7/576** lượt, cả 7 câu đã xong; điểm candidate lệch
  tối đa **1,56 điểm phần trăm**, best candidate giữ nguyên nhưng ties/hệ số ES đổi. Không suy thành
  ảnh hưởng learning nhỏ hoặc bỏ strict. [Khảo sát và giới hạn](evidence/2026-10-26-vllm-impact/README.md).
- vLLM upstream chưa hỗ trợ native Windows. Strict `b1ef257a` đạt **505 test trên native Win11/3060**;
  bốn layout nhỏ B14/B22 và Qwen trained parent/canonical ±/restore khớp Linux/WSL2 về weights,
  token/reward/logits. Native throughput, installer và managed acceptance còn mở.
- Thử nghiệm riêng `c9a37059` chia sẻ storage HF với vLLM để giữ schema, candidate hash và exact restore;
  inference gần 100% vLLM vì dùng chính engine đó. Đây là control/khảo sát standalone, chưa managed.
  `3735d6db` sửa FP16 merged GEMM bị stale khi ES ghi tại chỗ.
  [Bằng chứng riêng](evidence/2026-10-25-fast-engine/README.md).
- LoRA strict `20856dea` tăng batch 32 khoảng 12–29% tùy model/GPU; artifact/adapter/candidate/restore đã
  đối chiếu hai host. Search space riêng, không phải full-weight control.
- Source `b1ef257a`: full check ALL PASS, runtime CPU **3158 pass/461 skip**, backend **452**;
  75 operator test mỗi GPU trước annotation alignment, nhóm cuối 4 test mỗi GPU, thêm 57 graph/LoRA
  test SM120, 4/4 mutation; gói Linux/SDK khớp toàn bộ 141 runtime Python file.
- Đang khảo sát tiếp: gộp projection tăng Qwen batch 32 khoảng 3%, copy 16 byte khoảng 4,7% trên SM120;
  chưa chọn. Profile gợi ý MLP khoảng 42%, attention 19% thời gian decode. Không suy prototype thành
  nghiệm thu. Khối khảo sát tiếp theo **chưa tạo thêm tăng tốc được chọn**: shared radix, capture
  prefill, bounded FP16 MMA/half2/vendor và FMA trực tiếp đều dừng ở prototype. FMA chậm hơn B22
  cả 5 shape. [Số học bounded](evidence/2026-10-26-bounded-mma/README.md),
  [kiến trúc](evidence/2026-10-26-strict-architecture/README.md),
  [FMA](evidence/2026-10-26-ordered-fma/README.md).
- Control toàn luồng Qwen batch 32: thay toàn bộ projection bằng vendor FP16 đạt khoảng **7804**
  token/s ở short32, vẫn cách đối chứng vLLM **13835**. Capture prefill giữ B22 chỉ **4365→4364**;
  chat128 **3953→3956**, không có lợi đáng kể. Profile đủ operator: attention bước cuối chat128
  khoảng **2,8/7,9 ms** B22, nhưng prototype warp attention toàn luồng chỉ khoảng **+1%**, chưa chọn.
  [Profile và thử nghiệm](evidence/2026-10-26-strict-remaining/README.md).
  Không coi thời gian `read` chờ GPU là chi phí CPU.
- Đã kiểm tra trực tiếp đường GEMM FP16 khoảng 7.8k: **vi phạm D2**, không còn chỉ là thiếu kiểm tra.
  Qwen chat32, parent/seed7001 ±, 128 token: batch32 khác token **33/96** lượt giữa hai GPU;
  tắt FP16 reduced reduction vẫn khác **26/96**. Hash weights/input khớp, restore chính xác.
  Reward đều zero, hầu hết chưa kết thúc, nên không suy ảnh hưởng reward nhỏ.
  [Bằng chứng](evidence/2026-10-26-strict-fp16-parity/README.md).
- Hướng mới đặc thù ES: dùng completion trước làm proposal, **strict xác minh lại mọi token bằng
  candidate hiện tại**, không dùng KV/logits cũ. Bộ chấm B22 nhiều vị trí đã khớp CPU hai layout và
  trained Qwen tuần tự, 2/2 mutation bị bắt. Batch 1 chấm 4 vị trí gần bằng chi phí 1; batch 8 chấm
  2 vị trí thêm khoảng 9–10%; batch 32 chi phí cao, chưa có lợi đã đo.
  [Bằng chứng và việc còn thiếu](evidence/2026-10-26-strict-verification/README.md).
- Vòng speculative thử nghiệm đã đo end-to-end: Qwen chat128 seed 7001 ±, batch 1 **+30% / +145%**
  với proposal từ parent và token khớp B22. Đây chỉ một prompt và chưa tính chi phí tạo bank; không
  suy thành lợi ích ES chung. Batch 8 **chậm hơn 3–5%** ngay cả sau bỏ recapture bằng dummy prefix
  hợp lệ, nên dừng mở rộng nhánh, **chưa chọn**. Sáu test GPU mỗi host, hai CPU mỗi host, 3/3 mutant
  bị bắt; có EOS giữa block, sai/rỗng proposal, fallback nhánh tràn số, đổi/restore weights, stream và
  Parameter replacement. Chưa native/trained cross-GPU/managed. Quay lại projection throughput chính,
  không dùng lợi ích batch 1 để đóng mục tiêu kernel gần vLLM.
  [Kết quả và giới hạn](evidence/2026-10-26-strict-speculative/README.md).
- Prototype B13 radix128/Karatsuba mới: năm test local qua, operator lớn nhanh hơn B22 khoảng
  **19–33%**, nhưng bản 3 tích chưa luôn thắng bản 4 tích cùng số học. Đây là số học mới; **chưa có
  decoder B13, throughput toàn model, quality, cross-GPU/native hay mutation gate**. Dừng tại đây để
  bàn giao; chưa đưa vào bản chính. [Bằng chứng](evidence/2026-10-26-strict-karatsuba/README.md).
- Claude (26/10) audit `e6053385`: cây sạch, runtime vẫn `b1ef257a`, mọi SHA256 manifest khớp, tính lại độc lập
  33/26/14/14 dòng token khác của đường FP16. Profile CUPTI toàn luồng (không chèn event): B22 chat128
  projection **52,8%**, attention **27,9%**; đường FP16 vendor chat128 attention **42,9%**. Attention decode tăng
  tuyến tính khoảng 0,4 µs/key/layer (60→115 µs/layer), prefill 43 ms. Ưu tiên attention trước B13.
  [Profile](evidence/2026-10-26-whole-path-kernel-profile/README.md).
- **Claude (26/10) chọn attention strict mới, số học giữ nguyên từng bit.** Kernel GQA đọc K/V một lần cho
  cả nhóm head, chia việc song song, không đổi thứ tự cộng. Batch 32 5070 Ti: Qwen **4361→4776** short32,
  **3953→4906** chat128 (+24%), Smol **+15%**, Tiny **+6%**; 3060 +3,5–9,7%. Token/logits khớp bản gốc, khớp
  5070 Ti/3060 WSL2/3060 native Win11 và khớp receipts `b1ef257a`. check-all ALL PASS, mutation 14/16 (2 tương
  đương). Sau đổi, projection chiếm **65%** B22 chat128: đó là việc tiếp theo.
  [Bằng chứng](evidence/2026-10-26-strict-attention-gqa/README.md).
- Tiếp tục projection throughput, số học có đặc tả và gate chất lượng/portable/native; không sửa recipe
  lịch sử để lấy tốc độ. Kế hoạch đã duyệt vẫn giữ hash
  `4ee6838fa47f810ee40348b5f0bc556834bf50825eb0b7b0795b5053743cb17f`.
  M0–M6, watchdog/D10, storage/replacement, ownership/lifecycle và qualification vẫn còn việc.
- Không push/merge/deploy, đổi device state, learning run hay sửa môi trường `ai`. Hai worktree gốc không sửa.

## Live

Deployment remains `82c37fc`. Service status re-read on 2026-10-26: all three lab services stopped; no lab operation was performed. The disk entry below is historical (2026-10-23).

| What           | State                                                                                                                                                                                                                                                      |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lab            | `lab.heteroes.site`, deployed clone `~/.local/share/heteroes-lab/app` at `82c37fc`; operations: [local-lab-operations.md](local-lab-operations.md)                                                                                                         |
| Devices        | Standalone probes: local 5070 Ti Linux and Thao 3060 WSL2/native Win11. Live approval/contribution was not changed; follow AGENTS.md. Native source/fixtures and finite trained Qwen candidates pass; installer/throughput/managed acceptance remains open |
| Default engine | engine v2 noise made on the GPU (same bits as CPU; `HETEROES_NOISE_DEVICE=cpu` forces CPU)                                                                                                                                                                 |
| Code           | Owned performance branch `work/codex-frozen-perf-2026-10-25`; strict B22 + GQA attention + streamed/fused projections (`1c9a54b9`, 26/10), experimental live FP16/vLLM views `c9a37059`. No push/merge/deployment |
| Disk (nhan)    | `/` 90 % used; Archive (NTFS/FUSE, also personal data) **full**, holds lab recovery storage and moved run data                                                                                                                                             |

## Open work, in order

1. **Own strict kernels approaching vLLM, then complete M0–M6.** The vLLM impact survey is recorded;
   the vendor path remains a separate control. Preserve D2/D3 across GPU architectures and the native
   Windows direction. Alternative arithmetic may have a new namespace and must pass numerical, quality,
   footprint and portability gates; historical recipes remain intact. Focus on full-weight projections,
   then remaining shared operators and lifecycle/ownership qualification. M2 watchdog/hard caps/D10,
   M3 storage/replacement, native installers and managed activation gates remain open. See the
   [approved plan](PLAN-SUA-HUMAN-REVIEW.md), [effort split](HUMAN-REVIEW-EFFORT-SPLIT.md), and
   [impact results](evidence/2026-10-26-vllm-impact/README.md).

2. **oomd / recovery-point upload loop.** Evidence and five proposed fixes:
   [evidence/2026-10-23-oomd-review/](evidence/2026-10-23-oomd-review/README.md). Policy:
   [operations-decisions-2026-10-23.md](operations-decisions-2026-10-23.md) (keep oomd on; supervisor recovers a run
   only once).
3. **Disk retention.** Policy agreed (Q1 in the decisions file), not implemented. Low-disk pause is not accepted under a
   real full disk (Q4, deferred).
4. **Benefit of extra/slower GPUs:** [next-codex-heterogeneous-benefit.md](next-codex-heterogeneous-benefit.md).
   Includes the per-generation bookkeeping that grows from ~1.7 s to ~11 s over a 600-generation run.
5. **Two audit timeouts at generation 63** of the soak (722 selected, 720 matched); reporting is fixed, cause is not.
6. Planned, not started: [plan-sdk-lab-bridge.md](plan-sdk-lab-bridge.md). Runtime polish list: [RUNTIME-TODO.md](RUNTIME-TODO.md).
7. Claims audit needs the owner's review: [CLAIMS_AUDIT.md](../runtime/docs/report/CLAIMS_AUDIT.md).

## Where things are

- Rules for agents: [../AGENTS.md](../AGENTS.md). Numerical contract: [numerical-contract.md](../runtime/docs/numerical-contract.md).
- User guides: [quickstart-vi.md](quickstart-vi.md), [worker-desktop-guide.md](worker-desktop-guide.md),
  [server-desktop-guide.md](server-desktop-guide.md). Security findings: [SECURITY-NOTES.md](SECURITY-NOTES.md).
- Design notes still in use: [resource-monitoring-design.md](resource-monitoring-design.md), ADRs in `runtime/docs/adr/`.
- Dated receipts: `evidence/YYYY-MM-DD-*/` (never rewritten). Current strict work: `2026-10-25-strict-throughput`; earlier audit work: `2026-10-25-audit-safety`.
  Historical live/soak/storage evidence remains under the 2026-10-23 folders.
- Superseded plans, handoffs and qualification notes: [archive/](archive/README.md).
