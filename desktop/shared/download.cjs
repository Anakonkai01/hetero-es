const fs = require('node:fs');
const fsp = fs.promises;
const path = require('node:path');
const crypto = require('node:crypto');
const { Readable } = require('node:stream');
const { pipeline } = require('node:stream/promises');
async function digest(file) {
  const hash = crypto.createHash('sha256');
  for await (const chunk of fs.createReadStream(file)) hash.update(chunk);
  return hash.digest('hex');
}
async function verifiedDownload(item, directory, progress = () => {}, fetcher = fetch) {
  if (
    !/^[a-f0-9]{64}$/.test(item.sha256) ||
    !Number.isSafeInteger(item.sizeBytes) ||
    item.sizeBytes < 1 ||
    path.basename(item.name) !== item.name ||
    /[\\/:]/.test(item.name) ||
    ['.', '..'].includes(item.name)
  )
    throw Error('INVALID_MANIFEST');
  const url = new URL(item.url);
  if (url.protocol !== 'https:') throw Error('HTTPS_REQUIRED');
  await fsp.mkdir(directory, { recursive: true });
  const destination = path.join(directory, item.name);
  const partial = destination + '.part';
  if (fs.existsSync(destination) && (await digest(destination)) === item.sha256) return destination;
  let offset = fs.existsSync(partial) ? (await fsp.stat(partial)).size : 0;
  if (offset >= item.sizeBytes) {
    await fsp.rm(partial);
    offset = 0;
  }
  const response = await fetcher(item.url, { headers: offset ? { Range: `bytes=${offset}-` } : {} });
  if (!response.ok || !response.body) throw Error('DOWNLOAD_UNAVAILABLE');
  if (response.status === 206) {
    const match = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(response.headers.get('content-range') ?? '');
    if (!match || Number(match[1]) !== offset || Number(match[3]) !== item.sizeBytes)
      throw Error('INVALID_DOWNLOAD_RANGE');
  } else {
    offset = 0;
  }
  let received = offset;
  const stream = Readable.fromWeb(response.body);
  stream.on('data', (chunk) => {
    received += chunk.length;
    if (received > item.sizeBytes) stream.destroy(Error('DOWNLOAD_SIZE_MISMATCH'));
    progress({ file: item.name, received, total: item.sizeBytes });
  });
  await pipeline(stream, fs.createWriteStream(partial, { flags: offset ? 'a' : 'w', mode: 0o600 }));
  if (received !== item.sizeBytes || (await digest(partial)) !== item.sha256) {
    await fsp.rm(partial, { force: true });
    throw Error('DOWNLOAD_CHECKSUM_MISMATCH');
  }
  await fsp.rename(partial, destination);
  return destination;
}
module.exports = { verifiedDownload, digest };
