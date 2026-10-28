"""Pinned safetensors fixture cross-OS/GPU comparison for the separately versioned integer graph."""
import argparse,copy,hashlib,json,os,platform,sys
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gpu',action='store_true');p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():p.error('GPU opt-in and fresh evidence required')
import torch,transformers
from safetensors.torch import load_model
from test_strict_decoder import model_for
from heteroes.eval.integer_decoder import IntegerDecoderReference,IntegerDecoderGraph
from heteroes.eval.candidate import model_weights_sha256
from heteroes.model.schema import build_parameter_schema

def digest(t):return hashlib.sha256(t.detach().cpu().contiguous().numpy().tobytes()).hexdigest()
manifest=json.loads((a.fixtures/'manifest-01.json').read_text(encoding='utf-8'))
report={'status':'running','fixture':True,'hardwareQualified':False,'nativeWindows':sys.platform=='win32','probeSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'limits':'Pinned tiny safetensors, four layouts, both precisions, parent/exponent-changing/restored states. Independent CPU oracle and serial/packed/captured checks. Not trained quality, managed lifecycle, native installer or universal qualification.',
        'environment':{'python':sys.version,'platform':platform.platform(),'torch':torch.__version__,'transformers':transformers.__version__,'gpu':torch.cuda.get_device_name(),'cc':list(torch.cuda.get_device_capability())},'comparison':{},'builds':{}}
try:
 for family,entry in manifest['families'].items():
  path=a.fixtures/entry['file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
  cpu=model_for(family);missing,unexpected=load_model(cpu,str(path));assert not missing and not unexpected
  schema=build_parameter_schema(cpu);assert schema.hash==entry['schemaHash']and model_weights_sha256(cpu,schema)==entry['weightsSha256']
  snapshot=cpu.model.layers[0].mlp.down_proj.weight.detach().clone()
  family_result={'fixtureSha256':entry['sha256'],'schemaHash':schema.hash,'parentWeightsSha256':entry['weightsSha256'],'precisions':{}}
  report['comparison'][family]=family_result;report['builds'][family]={}
  for bits in (14,22):
   cuda=copy.deepcopy(cpu).cuda();oracle=IntegerDecoderReference(cpu,magnitude_bits=bits,max_context=64,allow_fixture=True)
   engine=IntegerDecoderGraph(cuda,magnitude_bits=bits,max_context=64,allow_fixture=True)
   ids=torch.tensor([[0,0,3,5],[7,11,13,17],[0,19,23,29]],device='cuda');mask=ids!=0;rows=[ids[i:i+1,mask[i]]for i in range(3)]
   cases=[]
   for state,factor in [('parent',1.),('changed',-16.),('restored',1.)]:
    with torch.no_grad():
     cpu.model.layers[0].mlp.down_proj.weight.copy_(snapshot*factor)
     cuda.model.layers[0].mlp.down_proj.weight.copy_((snapshot*factor).cuda())
    eager=[oracle.forward_tokens(row.cpu())for row in rows];expected=torch.cat([x[0]for x in eager]);logits,caches=engine.forward_batch(rows)
    direct=torch.cat([engine.forward_tokens(row)[0]for row in rows]);assert digest(logits)==digest(expected)==digest(direct)
    cache_hashes=[[(digest(k),digest(v))for k,v in cache]for cache in caches]
    assert cache_hashes==[[(digest(k),digest(v))for k,v in item[1]]for item in eager]
    options=dict(max_new_tokens=4,eos_token_id=[],repetition_penalty=1.2)
    actual=engine.generate(ids,attention_mask=mask,**options);tokens=oracle.generate(ids.cpu(),attention_mask=mask.cpu(),**options)
    assert torch.equal(actual.cpu(),tokens)
    fed=[torch.cat((row,actual[i:i+1,ids.shape[1]:-1]),1)for i,row in enumerate(rows)]
    final=torch.cat([oracle.forward_tokens(row.cpu())[0]for row in fed]);assert digest(engine._session.last_logits)==digest(final)
    assert engine._session.capture_count==1 and all(not bool(t.any())for t in engine._session.caches)
    assert all(not bool(t.any())for t in engine.kernels.weight_metadata_buffers())
    weight_hash=model_weights_sha256(cuda,schema);assert weight_hash==model_weights_sha256(cpu,schema)
    cases.append({'state':state,'weightsSha256':weight_hash,'prefillLogitsSha256':digest(logits),'capturedLogitsSha256':digest(engine._session.last_logits),'tokenIds':actual.tolist(),'cacheHashes':cache_hashes,'captureCount':engine._session.capture_count,'requestBuffersCleared':True})
   assert cases[0]['weightsSha256']==cases[2]['weightsSha256']==entry['weightsSha256']
   assert cases[0]['prefillLogitsSha256']==cases[2]['prefillLogitsSha256']and cases[0]['tokenIds']==cases[2]['tokenIds']
   family_result['precisions'][str(bits)]={'identity':engine.identity,'cases':cases,'restoreExact':True}
   report['builds'][family][str(bits)]=engine.kernel_identity();engine.release_graph()
   del engine,cuda,oracle,logits,direct,caches,eager,actual,final
   torch.cuda.empty_cache()
 report['status']='ok'
except Exception as exc:report.update(status='error',errorType=type(exc).__name__,error=str(exc))
with a.out.open('x',encoding='utf-8')as f:json.dump(report,f,indent=2,allow_nan=False);f.write('\n')
print(json.dumps({'status':report['status'],'nativeWindows':report['nativeWindows'],'error':report.get('error')}));raise SystemExit(report['status']!='ok')
