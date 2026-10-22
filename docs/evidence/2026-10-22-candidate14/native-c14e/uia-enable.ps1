$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$A=[System.Windows.Automation.AutomationElement]
$root=$A::RootElement
$window=$null
for($i=0;$i -lt 30 -and $null -eq $window;$i++){ $window=$root.FindFirst([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.PropertyCondition($A::NameProperty,'HeteroES Worker'))); if($null -eq $window){Start-Sleep 1} }
if($null -eq $window) {throw 'Worker window not found'}
$names=@('Enable contribution','Bật đóng góp','Stop safely','Dừng an toàn')
$button=$null
for($i=0;$i -lt 40 -and $null -eq $button;$i++){
 foreach($n in $names){ $b=$window.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.PropertyCondition($A::NameProperty,$n))); if($b){$button=$b;break} }
 if($null -eq $button){Start-Sleep 1}
}
if($null -eq $button) {throw 'Contribution switch not found'}
$name=$button.Current.Name
Write-Output ('found switch: '+$name+' enabled='+$button.Current.IsEnabled)
for($i=0;$i -lt 30 -and -not $button.Current.IsEnabled;$i++){Start-Sleep 1}
if($name -in @('Enable contribution','Bật đóng góp')) {
 $p=$null; if($button.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern,[ref]$p)){$p.Toggle()} else {$button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()}
 Write-Output 'clicked Enable contribution'
 for($i=0;$i -lt 60;$i++){ $s=$window.FindFirst([System.Windows.Automation.TreeScope]::Descendants,(New-Object System.Windows.Automation.OrCondition((New-Object System.Windows.Automation.PropertyCondition($A::NameProperty,'Stop safely')),(New-Object System.Windows.Automation.PropertyCondition($A::NameProperty,'Dừng an toàn'))))); if($s){Write-Output 'switch now: Stop safely (ON)';exit 0}; Start-Sleep 1 }
 throw 'Switch did not turn ON'
}
