import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../api/client';
import { useScopeKey } from '../app/session';

export function LabQueue() {
  const scope=useScopeKey();
  const queue=useQuery({queryKey:['queue',...scope],queryFn:()=>apiGet<{experimentId:string;position:number;reason:string}[]>('/api/v1/queue'),enabled:scope.every(Boolean),refetchInterval:2500});
  if (queue.error) return <p role="alert">Queue status unavailable.</p>;
  if (!queue.data?.length) return null;
  return <section className="card"><div className="ch"><h2>Queue</h2></div><div className="cb">{queue.data.map(row=><p key={row.experimentId}><span className="mono">{row.experimentId}</span> · Position {row.position} · {row.reason}</p>)}</div></section>;
}
