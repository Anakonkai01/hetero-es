# r5 user feedback — 2026-10-12

During the public onboarding walkthrough, the owner tested the flow as an outside
user and reported completing account registration. The following feedback is
recorded for follow-up; no UI or authentication policy changes have been made.

| Area | User feedback | Follow-up |
| --- | --- | --- |
| Password requirement | The 12-character minimum feels excessive during registration. | Reconsider the requirement together with authentication protections; make the chosen requirement clear before submission and consistent across clients and backend. No replacement minimum has been decided. |
| Password field | The registration password control feels unpolished. | Improve the field's visual treatment, visibility control and clear validation feedback. |
| Administrator awareness | New registrations have no visible notification; the administrator must open management to discover them. | Surface pending registration requests in the administrator's normal navigation, with a clear route to review. |
| Approval screen | The approval interface looks unattractive. | Improve layout, request information, action clarity and confirmation after approval. |

These are user-reported observations, not findings from an independent browser
inspection of the administrator account. Source inspection confirms the
registration form currently uses `minLength={12}` and a plain password input.

The walkthrough continues with downloading the public r5 Worker and testing the
real desktop installation. Account creation alone does not establish account
approval, device approval, GPU compatibility or successful contribution.
