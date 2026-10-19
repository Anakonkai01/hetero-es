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
| Download discoverability | After registration, the user could not find the download page and had to navigate through GPU machines and devices to download Worker. | Provide an obvious download entry in the signed-in navigation and a direct next step after registration. Having a public URL alone does not resolve discoverability. |
| Post-registration navigation | Registration sends the user directly into a workspace area, with no obvious homepage or onboarding route. | Give the new user a clear path to the homepage, Worker installation and account approval status. |
| Overall presentation | The signed-in experience feels sparse and unprofessional. | Review the complete onboarding sequence and navigation together with the password and approval interfaces, rather than treating these as isolated cosmetic changes. |
| Worker onboarding clarity | After downloading and opening the Windows Worker, the user found the screen confusing and could not understand why sign-in appeared alongside other sections. | Make the current step visually dominant, explain that Worker uses the website's lab account, and progressively disclose network, role and connection diagnostics at the appropriate step. |
| Worker exit / tray | The user reports that tray actions only reopen the app and that the in-app exit action does not close it. | Reproduce native Windows tray and in-app shutdown from an unpaired profile; expose errors rather than silently reopening the window. Preserve confirmed drain for owned compute processes. |
| Worker sign-out | The user reports being unable to sign out. | Reproduce sign-out, inspect command/busy state and show an actionable result. Successful app sign-in has not been independently established. |
| Worker network / role controls | The user reports being unable to select network or role. | Diagnose locked controls and onboarding state. Explain that Windows supports the Worker role; coordinator selection requires qualified Linux hardware. |
| Worker lab connection | The user later clarified that they could not get through entering the lab address, before runtime installation or pairing. | Start the next reproduction at a clean Windows launch and lab connection; do not assume a download, GPU job or paired agent caused the problem. |

These are user-reported observations, not findings from an independent browser
inspection of the administrator account. Source inspection confirms the
registration form currently uses `minLength={12}` and a plain password input.
Source inspection also confirms registration redirects a signed-in user to
`/workspace`. The missing homepage/download entry describes the user's experience;
the public homepage and download URLs do exist.

The walkthrough continues with downloading the public r5 Worker and testing the
real desktop installation, starting with Windows at the owner's request. Account creation alone does not establish account
approval, device approval, GPU compatibility or successful contribution.

The user subsequently reported downloading and opening the Windows app. The
current walkthrough is at connection/sign-in; runtime installation, compatibility
and pairing have not been reported complete. Opening the app is user-reported,
not an independently observed full Windows acceptance result.

The owner then explicitly stopped testing and requested session close and rest.
Do not continue debugging or ask for further test evidence until they resume.
No Worker source changes or replacement installer were made in response to these
reports. The investigation is recorded in
`evidence/2026-10-12-worker-lifecycle/README.md` and the latest checkpoint in
`session-handoff-2026-10-12-close.md`.
