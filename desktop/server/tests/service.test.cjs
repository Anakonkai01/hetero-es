const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const {Service}=require('../electron/service.cjs');
test('an existing lab boots stopped and does not start on an unavailable address',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'server-service-'));t.after(()=>fs.rm(root,{recursive:true,force:true}));
 await fs.mkdir(path.join(root,'lab'));await fs.writeFile(path.join(root,'lab/config.json'),JSON.stringify({apiUrl:'http://192.0.2.1:8000',serverHost:'192.0.2.1'}));
 let spawned=false;
 const service=new Service(root,root,{setup:{status:()=>({installed:true}),paths:()=>({source:root})},spawn:()=>{spawned=true;}});
 assert.equal((await service.status()).running,false);
 assert.equal(service.environment().CUDA_VISIBLE_DEVICES,'');
 await assert.rejects(service.start(),/LAB_ADDRESS_UNAVAILABLE/);
 assert.equal(spawned,false);
 assert.equal((await service.stop()).running,false);
});
