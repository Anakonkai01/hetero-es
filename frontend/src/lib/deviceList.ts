// What the device list shows. Kept free of React so it can be tested.
type Listed = { approvalStatus: string };

/** Revoked devices only clutter the list; they stay reachable through "Show revoked devices". */
export function visibleDevices<T extends Listed>(devices: T[], showRevoked: boolean): T[] {
  return showRevoked ? devices : devices.filter((device) => device.approvalStatus !== 'REVOKED');
}

export function hiddenCount(devices: Listed[]): number {
  return devices.filter((device) => device.approvalStatus === 'REVOKED').length;
}

/** Same rule as the lab: a device that is approved or quarantined must be revoked or investigated first. */
export function canRemoveDevice(device: Listed): boolean {
  return device.approvalStatus === 'REVOKED' || device.approvalStatus === 'PENDING';
}

// Messages from the lab that an owner can act on, with an explanation that says what to do. The English text is also the translation key.
const EXPLAIN: Record<string, string> = {
  'Owner must belong to target workspace':
    'The owner of this device is not a member of the selected workspace. Add them to the workspace first (Workspaces, then Members), then approve again.',
  'Revoke the device before removing it': 'Revoke this device first. Only revoked or waiting devices can be removed.',
  'Device is reserved': 'This device is reserved by a running experiment. Try again when it has finished.',
  'Re-enroll with a new device alias after revocation':
    'A revoked device cannot be approved again. Pair the computer again from the Worker app.',
};
export function deviceErrorKey(message: string | undefined): string | null {
  return message && Object.hasOwn(EXPLAIN, message) ? EXPLAIN[message] : null;
}
