// Only plain http(s) addresses made of characters that need no shell quoting inside single quotes.
const SAFE_URL = /^https?:\/\/[A-Za-z0-9.:[\]_~%+-]+(\/[A-Za-z0-9._~%+-]+)*$/;

/** The one-line headless install for the server-provided script, or null when the address is unusable.
 *
 * The script embeds the public lab's downloads address; HETEROES_DOWNLOADS makes it fetch the bundle from the same
 * place the script came from (a self-hosted lab, or the private LAN/Tailscale address when transfers must stay private).
 */
export function linuxInstallCommand(installerUrl: string, origin: string): string | null {
  let url: URL;
  try {
    url = new URL(installerUrl, origin);
  } catch {
    return null;
  }
  const script = url.href;
  if (url.search || url.hash || !SAFE_URL.test(script) || !script.endsWith('/install-worker.sh')) return null;
  const downloads = script.slice(0, -'/install-worker.sh'.length);
  return `curl -fsSL '${script}' | HETEROES_DOWNLOADS='${downloads}' bash`;
}
