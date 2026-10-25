"""Unselected segmented launch over two/three live matrices; no concatenated weight allocation."""
import math
import torch
from heteroes.eval import integer_cuda as ic, integer_plan as planning, strict_cuda as sc
from heteroes.eval.reference_ops import ReferenceArithmeticError

_SIGNATURE = '''(const qi_t* x,const int* ex,int* error,
const u16* w0,const u16* b0,const int* e0,float* o0,i64* p0,
const u16* w1,const u16* b1,const int* e1,float* o1,i64* p1,
const u16* w2,const u16* b2,const int* e2,float* o2,i64* p2,int rows)'''


def source_for(outputs,biases,tile,split,bits,width):
 source=ic._SOURCE
 for entry,columns in [('integer_linear',32),('integer_simt',8),('integer_finish',256)]:
  start=source.index(entry+'(');body_start=source.index('{',start);depth=1;end=body_start+1
  while depth:
   depth += (source[end]=='{')-(source[end]=='}');end+=1
  body=source[body_start+1:end]
  assert body.rstrip().endswith('}')
  body=body.replace('blockIdx.x','column_block').replace('if(HAS_BIAS)','if(has_bias)')
  route=f'''\n  int column_block=blockIdx.x,outputs=N0,has_bias=BIAS0;
  const u16* w=w0; const u16* bias=b0; const int* ew=e0; float* out=o0; i64* partials=p0;
  if(column_block >= (N0+{columns-1})/{columns}) {{
    column_block -= (N0+{columns-1})/{columns};outputs=N1;has_bias=BIAS1;w=w1;bias=b1;ew=e1;out=o1;partials=p1;
#if GROUP_COUNT == 3
    if(column_block >= (N1+{columns-1})/{columns}) {{
      column_block -= (N1+{columns-1})/{columns};outputs=N2;has_bias=BIAS2;w=w2;bias=b2;ew=e2;out=o2;partials=p2;
    }}
#endif
  }}\n'''
  source=source[:start]+'grouped_'+entry+_SIGNATURE+' {'+route+body+source[end:]
 header=dict(WIDTH=width,MAGNITUDE_BITS=bits,DIGITS=2 if bits==14 else 3,HAS_BIAS=0,M_GROUPS=tile//16,WARPS=4,SPLIT_K=split,GROUP_COUNT=len(outputs))
 for i in range(3):header['N'+str(i)]=outputs[i]if i<len(outputs)else 0;header['BIAS'+str(i)]=int(biases[i])if i<len(outputs)else 0
 return ''.join(f'#define {key} {value}\n'for key,value in header.items())+source


@torch.inference_mode()
def grouped(k,value,weights,biases=None,*,error_flag=None,split_k=None,target_ctas_per_sm=8):
 if not isinstance(weights,(tuple,list))or len(weights)not in(2,3):raise ReferenceArithmeticError('Grouped prototype needs two/three matrices')
 if biases is None:biases=(None,)*len(weights)
 if not isinstance(biases,(tuple,list))or len(biases)!=len(weights):raise ReferenceArithmeticError('Grouped biases must match')
 if not isinstance(value,torch.Tensor)or value.dtype!=torch.float32:raise ReferenceArithmeticError('Grouped activation must be FP32')
 counts=[]
 for w,b in zip(weights,biases):
  rows,width,n=sc.validate_linear(value,w,b,device=k.device);counts.append(n)
 tile=16 if rows<=16 else 32;mode='simt'if rows==1 else 'mma'
 if split_k is None:
  # Whole-block concatenation: padding never lets a warp straddle matrices. This grid is at least
  # each individual matrix's grid, so its split is no larger than independent decode planning.
  columns=8 if mode=='simt'else 32;effective=sum(math.ceil(n/columns)*columns for n in counts)
  split_k=planning.decode_linear_plan(width,rows,effective,k.multiprocessors,max_partial_bytes=k.max_partial_bytes,target_ctas_per_sm=target_ctas_per_sm).split_k
 if type(split_k)is not int or split_k not in(1,2,4,8):raise ReferenceArithmeticError('Unsupported grouped split')
 if split_k>1 and split_k*rows*sum(counts)*8>k.max_partial_bytes:raise ReferenceArithmeticError('Grouped partial workspace exceeded')
 key=f'grouped-{k.magnitude_bits}-{width}-{tuple(counts)}-{tuple(b is not None for b in biases)}-m{tile}-s{split_k}'
 if key not in k._functions:
  k._functions[key]=k._compile(key,source_for(counts,[b is not None for b in biases],tile,split_k,k.magnitude_bits,width),['grouped_integer_linear','grouped_integer_simt','grouped_integer_finish'],integer_mma=True)
 functions=k._functions[key];flag=k.new_error_flag()if error_flag is None else error_flag;q,ex=k.quantize_input(value.reshape(rows,width),error_flag=flag)
 exponents=[k._weight_exponents(w,flag)for w in weights];outs=[torch.empty((rows,n),dtype=torch.float32,device=k.device)for n in counts]
 partials=[torch.empty((split_k,rows,n),dtype=torch.int64,device=k.device)for n in counts]if split_k>1 else outs
 pointers=[q,ex,flag]
 for i in range(3):
  j=min(i,len(weights)-1);pointers.extend((weights[j],weights[j]if biases[j]is None else biases[j],exponents[j],outs[j],partials[j]))
 columns=8 if mode=='simt'else 32
 k._launch(functions['grouped_integer_simt'if mode=='simt'else'grouped_integer_linear'],grid=(sum(math.ceil(n/columns)for n in counts),min(65535,rows if mode=='simt'else math.ceil(rows/tile)),split_k),block=(256 if mode=='simt'else 128,1),pointers=tuple(pointers),integers=(rows,))
 if split_k>1:k._launch(functions['grouped_integer_finish'],grid=(sum(math.ceil(n/256)for n in counts),min(65535,rows)),block=(256,1),pointers=tuple(pointers),integers=(rows,))
 k._finish(flag,error_flag)
 return tuple(out.reshape(*value.shape[:-1],n)for out,n in zip(outs,counts))
