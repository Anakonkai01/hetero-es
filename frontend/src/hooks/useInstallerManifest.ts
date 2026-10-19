import { useQuery } from '@tanstack/react-query';

export type Installer = { platform: string; name: string; url: string };
export type Manifest = { installers: Installer[]; serverInstallers?: Installer[]; privateTransferRequired?: boolean };

export function useInstallerManifest() {
  return useQuery({
    queryKey: ['worker-installers'],
    queryFn: async () => {
      const reply = await fetch('/downloads/manifest.json');
      if (!reply.ok) throw Error('BUILD_UNAVAILABLE');
      return reply.json() as Promise<Manifest>;
    },
    retry: false,
  });
}
