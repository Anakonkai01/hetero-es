# Researcher journey frictions (isolated r11 candidate2 lab, 2026-10-20)
1. Register: after "Đăng ký" nothing is shown while register + sign-in run (no "sending" state on the button).
2. Admin accounts list: missing space "Tạo không gianđược phép" / "Tạo không gianhạn chế".
3. Account menu strings untranslated in vi: "Allow workspace creation", "Revoke workspace creation", "Grant platform admin", "Remove platform admin".
4. "Hoạt động hệ thống" audit lines show raw user ids (5acdb811…) instead of names.
5. Bell badge still shows 1 after the account request was approved.
6. "Workspace details" untranslated in the create-workspace dialog.
7. Researcher gets two identical "Tài khoản của bạn đã được duyệt" notifications (approve, then workspace permission).
8. **BUG (blocks the journey):** Operations → "Duyệt máy GPU": the "Không gian cấp quyền" select lists the ADMIN's own workspaces (`frontend/src/pages/LabDevices.tsx:182` uses `session.workspaces`), but the backend requires the DEVICE OWNER to belong to the target (`backend/devices.py:382`). A researcher's device cannot be approved into the researcher's own lab from the UI. Also the card shows the raw workspace id (`LabDevices.tsx:221`).
9. Devices qualify only for the shipped model manifest (`qualifiedModelHashes` = one hash); check what happens with a new model.
10. Test harness only: the Worker needs a D-Bus session for secure storage (SECURE_STORAGE_REQUIRED without it).
11. **Model registration needs a hand-written manifest JSON** (commit + SHA-256 of every file). No helper: the web cannot build it from a HF repo id + revision, and nothing tells the researcher how to make it. Big blocker for "my own model".
12. Models page: section title "Model và dataset toán" also for Recipe v3; raw label "all"; native "Choose File / No file chosen" not translated; Recipe v2 is the default choice.
13. Create experiment: choosing a cosine/linear alpha schedule makes "Alpha tối thiểu" required with no default; the only feedback is the browser's English tooltip "Please fill out this field" (no Vietnamese inline error), placed far from the Continue button.
14. Resources step: coordinator and GPU lists show the worker id "desktop-906949218c43", not the device name the owner chose ("5070 Ti (máy của Nhân)").
15. Review step shows only name/recipe/generations/GPU/coordinator/model: none of the ES choices (dataset, batch, sigma schedule, alpha schedule, coefficient rule, momentum, scorer, tokens, chunk) are shown before saving. "Chính sách sao lưu" is empty.
16. Untranslated on the experiment page: breadcrumb "Experiments", "Not available yet", "Not ended".
17. A fresh lab starts with submissions held; the researcher sees the untranslated "Submissions are held for maintenance or restored deployment review" with no hint to ask the platform admin (who must tick the box and press "Mở lại triển khai đã kiểm tra" in Operations).
18. Experiment page: "Waiting for owner to turn contribution ON" is untranslated. A failed run (KeyError) stays in "Đang dừng an toàn" (DRAINING) for minutes.
19. Design question: "Stop safely" on the Worker (contribution OFF) cancels every QUEUED experiment that selected that GPU (`backend/store.py:138`), even one waiting for that same owner to turn contribution ON. A researcher restarting their own PC loses the queue.
20. **BUG (fixed 794069c):** managed coordinator launched before its inputs were transferred → KeyError 'datasetPath'.
21. **BUG (fixed aa3ccf9):** default study cache checked against the models' disk UUID → every managed v3 run failed when models live on another disk; the lab showed only "ValueError".
22. **BUG (fixed 204defa):** a run that failed before starting workers never released the GPU (workerAlive None) → all later experiments stuck.
23. **BLOCKER for "my own model":** a device advertises `qualifiedModelHashes` from its self-test, which only probes the shipped Qwen reference (`runtime/src/heteroes/product/qualification_v3.py:241`); the lab refuses any experiment whose model is not in every selected device's list (`backend/policies.py:64`, "Qualify every selected device for this pinned model"). There is no way to qualify a device for a newly registered model. Needs an on-demand model qualification (agent command, same probe on the new manifest, cross-device comparison of outputs).
24. (fixed 3a6c440) the first 500-row validation decoded 16 prompts per call: ~15 minutes before generation 0.
