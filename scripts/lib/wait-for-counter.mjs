/** Poll actual receipts; an unresolved Promise or a missing/zero counter cannot satisfy acceptance. */
export async function waitForCounter(read, name, minimum, { timeout = 30000, interval = 250 } = {}) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const receipt = await read();
    if (typeof receipt[name] === 'number' && receipt[name] >= minimum) return receipt;
    await new Promise((resolve) => setTimeout(resolve, interval));
  }
  throw new Error('Required receipt counter did not advance');
}
