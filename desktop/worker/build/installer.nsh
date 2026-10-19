; Removing the Worker removes everything it stored for this user: the pairing, the device credential, the downloaded
; runtime and model, settings and logs. electron-builder deletes "$APPDATA\@heteroes\worker" itself when
; deleteAppDataOnUninstall is on; this also removes the parent folder when nothing else (such as the Lab Server) is in it.
; An in-place upgrade (isUpdated) keeps the data, so updating never makes anyone pair again.
; A data folder chosen on another drive is named in data-folder.txt; it is removed only when its name is the app's own
; HeteroES-Worker-data (never the drive or folder the user picked), and read before the app data folder that holds it.
!macro customUnInstall
  ${ifNot} ${isUpdated}
    ClearErrors
    FileOpen $0 "$APPDATA\@heteroes\worker\data-folder.txt" r
    ${ifNot} ${Errors}
      FileRead $0 $1
      FileClose $0
      StrCpy $2 $1 "" -21
      StrCmp $2 "\HeteroES-Worker-data" 0 +2
      RMDir /r "$1"
    ${endIf}
    RMDir /r "$APPDATA\@heteroes\worker"
    RMDir "$APPDATA\@heteroes"
  ${endIf}
!macroend
