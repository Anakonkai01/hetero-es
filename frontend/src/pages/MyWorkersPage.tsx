import { useProduct } from '@heteroes/product-ui';
import { useState } from 'react';
import { useSession } from "../app/session";
import { PageHeader } from "../components/ui/PageHeader";
import { WorkerFleet } from '../components/workers/WorkerFleet';
import { LabDevices } from './LabDevices';
export function MyWorkersPage() {
  const {t}=useProduct();
  const {workspace}=useSession();
  const [view,setView]=useState('fleet');
  return <><PageHeader title={t('Workers')} description={t('Live GPU resources, allocation and hardware measurements.')} actions={<button className="btn pri" onClick={()=>setView('devices')}>+ {t('Add a GPU computer')}</button>}/>
  <><div className="tabs" role="tablist" aria-label={t('GPU views')}><button className={view==='fleet'?'tab on':'tab'} role="tab" aria-selected={view==='fleet'} onClick={()=>setView('fleet')}>{t('Workspace GPU fleet')}</button><button className={view==='devices'?'tab on':'tab'} role="tab" aria-selected={view==='devices'} onClick={()=>setView('devices')}>{t('My devices & contribution')}</button></div>{view==='devices'?<LabDevices/>:workspace?<WorkerFleet/>:<p>{t('Join a workspace to view its live GPU inventory.')}</p>}</>
  </>;
}
