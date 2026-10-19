; Removing the Worker removes everything it stored for this user: the pairing, the device credential, the downloaded
; runtime and model, settings and logs. electron-builder deletes "$APPDATA\@heteroes\worker" itself when
; deleteAppDataOnUninstall is on; this also removes the parent folder when nothing else (such as the Lab Server) is in it.
; An in-place upgrade (isUpdated) keeps the data, so updating never makes anyone pair again.
!macro customUnInstall
  ${ifNot} ${isUpdated}
    RMDir /r "$APPDATA\@heteroes\worker"
    RMDir "$APPDATA\@heteroes"
  ${endIf}
!macroend
