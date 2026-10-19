const os = require('node:os');
const net = require('node:net');

function addresses(interfaces = os.networkInterfaces()) {
  const result = new Map();
  for (const [name, entries] of Object.entries(interfaces))
    for (const entry of entries ?? []) {
      if (entry.family !== 'IPv4' || entry.internal || net.isIP(entry.address) !== 4) continue;
      const parts = entry.address.split('.').map(Number);
      const overlay = parts[0] === 100 && parts[1] >= 64 && parts[1] <= 127;
      if (
        overlay ||
        parts[0] === 10 ||
        (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) ||
        (parts[0] === 192 && parts[1] === 168)
      ) {
        // WireGuard can use ordinary private ranges; interface names are hints only.
        result.set(entry.address, {
          host: entry.address,
          name,
          network: overlay || /^(wg|tailscale)/i.test(name) ? 'overlay' : 'lan',
        });
      }
    }
  return [...result.values()];
}

function qualified(selfTest, platform = process.platform) {
  return (
    platform === 'linux' &&
    selfTest?.platform === 'linux' &&
    selfTest.passed === true &&
    selfTest.coordinator === true &&
    selfTest.vramTotalMb >= 11000
  );
}

function computeConfig(value, selfTest, platform, localAddresses) {
  const config = value ?? { network: 'lan', coordinator: false, host: '127.0.0.1' };
  if (!['lan', 'overlay', 'internet'].includes(config.network)) throw Error('INVALID_NETWORK');
  if (typeof config.coordinator !== 'boolean') throw Error('INVALID_ARGUMENT');
  if (config.coordinator) {
    if (!qualified(selfTest, platform)) throw Error('COORDINATOR_NOT_QUALIFIED');
    if (
      !localAddresses.some(
        (a) => a.host === config.host && (config.network === 'internet' || a.network === config.network),
      )
    )
      throw Error('INVALID_COMPUTE_ADDRESS');
  }
  return {
    network: config.network,
    coordinator: config.coordinator,
    host: config.coordinator ? config.host : '127.0.0.1',
  };
}

module.exports = { addresses, qualified, computeConfig };
