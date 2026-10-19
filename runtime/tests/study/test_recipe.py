import json
import numpy as np
import pytest
import torch
from heteroes.ledger import Ledger
from heteroes.manifest import Recipe,CandidateDescriptor
from heteroes.model.schema import build_parameter_schema
from heteroes.noise.contracts import ENGINE_VERSION,DEFAULT_CHUNK_ELEMENTS
from heteroes.noise.selftest import EXPECTED_NOISE_FINGERPRINT
from heteroes.study.data import dataset,sha
from heteroes.study.recipe import RecipeV2
from heteroes.study.evaluation import pass_at_k,sampled_metrics
from heteroes.executor import CandidateExecutor


def recipe_data(schema_hash='a'*64,kind='cosine',generations=3):
    data=dataset({'all':{'format':'json','content':json.dumps([{'prompt':f'Q{i}','answer':i} for i in range(20)])}})
    revision='7ae557604adf67be50417f59c2c2f167def9a775'
    base=Recipe('Qwen/Qwen2.5-0.5B-Instruct',revision,revision,'torch.float16',schema_hash,ENGINE_VERSION,DEFAULT_CHUNK_ELEMENTS,
                EXPECTED_NOISE_FINGERPRINT,.001,1e-9,data['contentHash'],'b'*64)
    manifest={'formatVersion':1,'modelId':base.model_id,'revision':revision,'tokenizerRevision':revision,'format':'safetensors',
              'files':{'config.json':'a'*64,'model.safetensors':'b'*64,'tokenizer.json':'c'*64}}
    recipe=RecipeV2(base,manifest,{k:data[k] for k in ('contentHash','splitHashes')},8,11,
                   {'kind':kind,'initial':.001,'minimum':.00025,'generations':generations},
                   {'systemPrompt':'Solve. Answer: <number>','maxNewTokens':32,'decoder':'hf_generate','extractor':'answer-line-last-number-v1'})
    return recipe,data


def test_cosine_endpoints_midpoint_one_generation_and_constant():
    recipe,_=recipe_data()
    assert [recipe.sigma_at(g) for g in range(3)]==[float(np.float32(v)) for v in (.001,.000625,.00025)]
    one,_=recipe_data(generations=1)
    assert one.sigma_at(0)==float(np.float32(.001))
    constant,_=recipe_data(kind='constant')
    assert constant.sigma_at(2)==float(np.float32(.001))
    with pytest.raises(ValueError):recipe.sigma_at(3)


def test_recipe_round_trip_and_run_identity_stays_fixed_across_generations():
    recipe,data=recipe_data()
    assert RecipeV2.from_dict(recipe.to_dict()).hash==recipe.hash
    before=recipe.hash
    a,b=recipe.context(data,0),recipe.context(data,1)
    assert a['batchHash']!=b['batchHash'] and a['sigmaFloat32']!=b['sigmaFloat32']
    assert recipe.hash==before and a['recipeHash']==b['recipeHash']


def test_crash_resume_fences_changed_generation_inputs(tmp_path):
    recipe,data=recipe_data();context=recipe.context(data,1)
    path=tmp_path/'ledger.sqlite'
    with Ledger(path) as ledger:assert ledger.freeze_generation_context('test',1,context)==context
    with Ledger(path) as ledger:
        assert ledger.freeze_generation_context('test',1,context)==context
        changed={**context,'sigmaFloat32':.009}
        changed['contextHash']=sha({k:v for k,v in changed.items() if k!='contextHash'})
        with pytest.raises(Exception,match='Frozen'):ledger.freeze_generation_context('test',1,changed)


def test_candidate_verifies_batch_and_generation_then_restores_exactly(monkeypatch):
    model=torch.nn.Linear(2,2,bias=False).half()
    schema=build_parameter_schema(model);recipe,data=recipe_data(schema.hash)
    executor=CandidateExecutor(model,None,schema,recipe,dataset=data)
    desc=CandidateDescriptor(recipe.hash,executor.parent_sha256,'test',1,0,17)
    with pytest.raises(Exception,match='inputs'):executor(desc)
    context=recipe.context(data,1)
    with pytest.raises(ValueError,match='context'):executor.set_generation(1,{**context,'batchHash':'0'*64})
    executor.set_generation(1,context)
    parent=model.weight.clone()
    observed=[]
    def evaluate(_model,_tokenizer,rows,settings,chunk):
        observed.append(rows)
        return {'accuracy':.5}
    monkeypatch.setattr('heteroes.study.evaluation.evaluate',evaluate)
    assert executor(desc)==.5
    assert torch.equal(parent,model.weight)
    assert observed[0]==[data['splits']['train'][i] for i in context['batchIndices']]


def test_hypergeometric_pass_k_and_deterministic_majority():
    assert pass_at_k(4,1,2)==.5
    assert pass_at_k(32,0,16)==0
    assert pass_at_k(32,1,32)==1
    result=sampled_metrics(['2','1','2','1'],'1',ks=(1,2,4))
    assert result['majorityAnswer']=='1' and result['passAtK']['1']==.5
    with pytest.raises(ValueError):pass_at_k(32,33,1)
