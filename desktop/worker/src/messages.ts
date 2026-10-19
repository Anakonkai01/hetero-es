export const connectionMessages: Record<string, string> = {
  LAB_REACHABLE: 'Lab server is reachable.',
  CONTROL_REACHABLE: 'Coordinator accepted the compute credential.',
  BULK_REACHABLE: 'A 64-byte weights range was received.',
  NO_ASSIGNMENT: 'Not tested yet: no current worker assignment.',
  REPLAY_ONLY: 'Public route: replay only. Full weights need the private network.',
  NO_PUBLISHED_WEIGHTS: 'Not tested yet: no weights are published for this job.',
  COORDINATOR_UNREACHABLE: 'Coordinator did not answer on the private or public route.',
  CONTROL_REQUIRED: 'Check coordinator control before checking weights.',
  BULK_CHECK_FAILED: 'Could not read a bounded weights range on the private route.',
  LAB_UNREACHABLE: 'Lab server did not answer.',
  AGENT_CHECK_FAILED: 'Could not obtain connection checks from the local agent.',
  PROBE_LIMIT: 'Not tested yet: another retained assignment was checked first.',
};
export const explanations: Record<string, string> = {
  LAB_HTTP_401: 'Incorrect username or password. Sign in again.',
  LAB_HTTP_403: 'This action requires the device owner or administrator.',
  LAB_HTTP_409: 'The device or assignment is not ready. Refresh and try again.',
  SELF_TEST_REQUIRED: 'Run the GPU compatibility check before pairing.',
  SECURE_STORAGE_REQUIRED: 'Secure credential storage is unavailable. Unlock your system keyring and restart.',
  INSUFFICIENT_DISK_SPACE:
    'Free some disk space, or choose another drive before installing, and retry. Partial downloads are kept.',
  RUNTIME_ALREADY_INSTALLED: 'The runtime is already installed in its data folder; it cannot move now.',
  INVALID_STORAGE_DIRECTORY: 'Choose an existing folder or drive.',
  CUDA_UNAVAILABLE: 'CUDA_UNAVAILABLE',
  WINDOWS_RUNTIME_MISSING: 'WINDOWS_RUNTIME_MISSING',
  COMPATIBILITY_FAILED: 'The numerical check failed. Keep contribution OFF and export diagnostics.',
  AGENT_UNAVAILABLE: 'A process state is unknown; resources remain reserved.',
  RUNTIME_PROCESS_FAILED: 'Runtime setup or GPU check failed. Export diagnostics and retry.',
  ACTION_IN_PROGRESS: 'Wait for the current action to finish.',
  DRAIN_NOT_CONFIRMED: 'Waiting for owned processes to stop.',
  SETUP_IN_PROGRESS: 'Wait for runtime setup or the compatibility check to finish.',
};
Object.assign(explanations, {
  LAB_UPDATE_REQUIRED: 'This lab needs a server update before changing a paired device role.',
  STOP_WORK_FIRST: 'Stop contribution and wait for all processes to drain.',
  INVALID_COMPUTE_ADDRESS: 'Select an available private address on this computer.',
  COORDINATOR_NOT_QUALIFIED: 'Coordinator requires a qualified Linux GPU with at least 11000 MB VRAM.',
});
Object.assign(explanations, {
  INVALID_LAB_ADDRESS: 'This is not a valid lab address. Example: lab.example.org',
  HTTPS_OR_PRIVATE_NETWORK_REQUIRED:
    'Use an https:// address. Plain http:// is only allowed for private network addresses.',
  LAB_UNREACHABLE: 'The lab did not answer. Check the address and your internet connection.',
  LAB_TIMEOUT: 'The lab took too long to answer. Check the address and try again.',
  NOT_A_LAB: 'This address answered, but it is not a HeteroES lab.',
  LAB_AGENT_MODE_REQUIRED: 'This lab does not accept desktop Workers yet. Ask its administrator to update it.',
  LAB_BAD_RESPONSE: 'The lab sent a reply this app does not understand. Update the app or ask the administrator.',
  DIFFERENT_LAB_REQUIRES_NEW_PAIRING: 'This computer is paired to another lab. Pair it again to use this one.',
  LAB_DNS_FAILED: 'This computer could not find the lab address. Check the spelling, your DNS or VPN settings.',
  LAB_CONNECTION_REFUSED: 'The lab refused the connection. It may be restarting, or a firewall is blocking it.',
  LAB_CONNECTION_RESET: 'The connection to the lab was cut. A firewall, antivirus or proxy may be inspecting it.',
  LAB_NETWORK_DOWN: 'There is no network route to the lab. Check your internet or VPN connection.',
  LAB_CERTIFICATE_REJECTED:
    "This computer does not trust the lab's security certificate. Antivirus or a proxy that inspects HTTPS is the usual cause.",
  OLD_LAB_UNREACHABLE:
    'The lab this computer was paired to cannot be reached (an address that needs Tailscale does not work while Tailscale is off). Turn Tailscale on, or press Forget this pairing and pair again.',
  AGENT_SPAWN_FAILED:
    'The local agent program could not be started. The runtime may be incomplete or blocked by antivirus software. Export diagnostics.',
  AGENT_EXITED: 'The local agent stopped right after it started. Export diagnostics and send the log file.',
  SELECT_LAB_FIRST: 'Enter the lab address first.',
  SIGN_IN_REQUIRED: 'Sign in first.',
  ACTION_CANCELLED: 'Cancelled.',
});
export const explain = (code: string) =>
  explanations[code] ??
  (/^LAB_HTTP_5\d\d$/.test(code)
    ? 'The lab server is not answering right now. Try again later or ask the lab administrator.'
    : 'Could not complete the action. Check the connection and export diagnostics.');
