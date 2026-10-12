import {useQuery} from '@tanstack/react-query';
import {useProduct} from '@heteroes/product-ui';

type Installer={platform:string;name:string;url:string};
type Manifest={installers:Installer[];serverInstallers?:Installer[];privateTransferRequired?:boolean};

export function InstallerDownloads(){
 const {t}=useProduct();
 const manifest=useQuery({queryKey:['worker-installers'],queryFn:async()=>{const reply=await fetch('/downloads/manifest.json');if(!reply.ok)throw Error('BUILD_UNAVAILABLE');return reply.json() as Promise<Manifest>;},retry:false});
 const apps=[{name:'Worker',items:manifest.data?.installers??[],description:'Connect your GPU and choose when to contribute.'},{name:'Lab Server',items:manifest.data?.serverInstallers??[],description:'Host the dashboard, queue and checkpoint service on a CPU computer.'}];
 return <section className="landing-downloads" id="downloads"><div className="section-title"><div><span className="eyebrow">{t('Desktop apps')}</span><h2>{t('Bring your computers into the lab.')}</h2><p>{t('Use Worker on GPU computers and Lab Server on the computer hosting your lab.')}</p></div></div>
 {manifest.data?.privateTransferRequired&&<p className="note">{t('Connect to the lab LAN or Tailscale to download installers and large files.')}</p>}
 {manifest.isPending?<p role="status">{t('Loading…')}</p>:manifest.isError?<p className="hint">{t('App downloads are unavailable on this server. Ask your administrator for the current installer.')}</p>:<div className="download-cards">{apps.map(({name,items,description})=><article key={name}><h3>HeteroES {name}</h3><p>{t(description)}</p><div className="acts">{items.filter(item=>item.platform!=='linux-appimage').map(item=><a className="btn" href={item.url} download={item.name} key={item.platform}>{item.platform==='windows'?'Windows':'Linux'} <span aria-hidden="true">↓</span></a>)}</div>{!items.length&&<p className="hint">{t('No installer available')}</p>}</article>)}</div>}
 </section>;
}
