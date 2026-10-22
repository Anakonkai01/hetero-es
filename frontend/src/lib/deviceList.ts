// What the device list shows. Kept free of React so it can be tested.
type Listed = { approvalStatus: string };

/** Revoked devices only clutter the list; they stay reachable through "Show revoked devices". */
export function visibleDevices<T extends Listed>(devices: T[], showRevoked: boolean): T[] {
  return showRevoked ? devices : devices.filter((device) => device.approvalStatus !== 'REVOKED');
}

export function hiddenCount(devices: Listed[]): number {
  return devices.filter((device) => device.approvalStatus === 'REVOKED').length;
}

/** Same rule as the lab: any device can be deleted (an approved one is revoked in the same step), except one under
 * restore quarantine, which an administrator investigates first. A device in a run is refused by the lab with a reason. */
export function canRemoveDevice(device: Listed): boolean {
  return device.approvalStatus !== 'QUARANTINED';
}

// Messages from the lab that an owner can act on, with an explanation that says what to do. The English text is also the translation key.
const EXPLAIN: Record<string, string> = {
  'Owner must belong to target workspace':
    'The owner of this device is not a member of the selected workspace. Add them to the workspace first (Workspaces, then Members), then approve again.',
  'Revoke the device before removing it': 'Revoke this device first. Only revoked or waiting devices can be removed.',
  'Device is reserved': 'This device is reserved by a running experiment. Try again when it has finished.',
  'Device is in a run: turn it OFF or wait for the run to end, then delete it':
    'This device is working in a run. Turn it OFF (it leaves the run) or wait for the run to end, then delete it.',
  'Re-enroll with a new device alias after revocation':
    'A revoked device cannot be approved again. Pair the computer again from the Worker app.',
};
export function deviceErrorKey(message: string | undefined): string | null {
  return message && Object.hasOwn(EXPLAIN, message) ? EXPLAIN[message] : null;
}

// Approval puts a device into a workspace of its owner (the lab checks the membership), not of the administrator.
type OwnerWorkspace = { workspaceId: string; name: string };
type Placed = { workspaceId: string | null; ownerWorkspaces?: OwnerWorkspace[] };

/** The workspace an approval form starts with: the device's current one if its owner is still a member, else the first. */
export function defaultApprovalWorkspace(device: Placed): string {
  const choices = device.ownerWorkspaces ?? [];
  return choices.some((w) => w.workspaceId === device.workspaceId)
    ? (device.workspaceId as string)
    : (choices[0]?.workspaceId ?? '');
}

/** The name of the device's workspace when the list knows it, else its identifier. */
export function workspaceName(device: Placed): string | null {
  if (!device.workspaceId) return null;
  return device.ownerWorkspaces?.find((w) => w.workspaceId === device.workspaceId)?.name ?? device.workspaceId;
}
