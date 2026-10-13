'use strict';
const $ = id => document.getElementById(id);
const write = (id, value) => { $(id).textContent = value; };
const pct = value => (value * 100).toFixed(1) + '%';
const labels = {catalog:'Browse catalog',products:'View products',search:'Search inventory',login:'Sign in',cart:'Add to cart',session:'Start anonymous session'};
let data, local, cloud, current = 'catalog';
async function get(file, optional=false) { const r = await fetch('data/'+file); if(!r.ok) { if(optional) return null; throw new Error('Evidence could not be loaded'); } return r.json(); }
function appendText(parent, tag, text, className) { const el=document.createElement(tag); el.textContent=text; if(className) el.className=className; parent.append(el); return el; }
function render() {
  const p=data.proposals.find(x=>x.route===current);
  document.querySelectorAll('.endpoint-button').forEach(b=>b.setAttribute('aria-pressed', String(b.dataset.route===current)));
  const candidate=$('policy-view').value==='selected';
  const holdout=$('dataset').value==='holdout';
  const selected=p.selected;
  let result=candidate ? (holdout ? p.holdout_result : selected) : p.baseline_result;
  // A current-policy holdout was not measured in this output; do not substitute another dataset.
  if(!candidate && holdout) { $('dataset').value='validation'; result=p.baseline_result; }
  write('owner',p.owner+' / PROPOSED LAB OWNER'); write('route','/api/'+p.route+(p.route==='products'?'/{id}':'')); write('risk',p.risk);
  write('decision-badge',p.decision==='propose_observation'?'Observation proposal':'Withheld: holdout failed');
  $('decision-badge').className='pill'+(p.decision==='propose_observation'?'':' warn');
  write('abuse-rate',result ? pct(result.abuse_rejection_rate) : '—'); write('buyer-rate',result ? pct(result.legitimate_rejection_rate) : '—');
  write('abuse-count', result ? `${result.abusive_rejected} / ${result.abusive_rejected+result.abusive_allowed} labelled abusive requests` : 'Insufficient evidence');
  const policy=candidate?selected:p.baseline_policy;
  write('capacity',policy?.capacity ?? '—'); write('refill',policy ? policy.refill_per_second+' tokens / second' : 'No candidate');
  write('p99',p.calibration.p99_cost_per_key_second); write('distinct',p.observations.maximum_distinct_resources_per_actor); write('fingerprint',p.observations.maximum_sources_sharing_fingerprint);
  write('reason',`Candidates start from the trusted baseline P99 (${p.calibration.p99_cost_per_key_second} cost units per key per second). Explicit margins form the candidate grid. Validation requires ≤1% legitimate rejection and ≥50% abuse rejection; a separate holdout must pass too. Login and session use source-address keys, so shared networks matter.`);
  write('edge',p.decision==='propose_observation'?`COUNT / ${p.edge_proposal.limit} requests per source IP / ${p.edge_proposal.window_seconds} seconds, scoped to ${p.edge_proposal.scope}. ${p.edge_proposal.reason}`:'No edge proposal is deployed for this endpoint. The candidate is retained for inspection, not promotion.');
  write('holdout-status',p.holdout_passed?'Separate synthetic holdout passed. Real WAF Count validation is still required before enforcement.':`Separate holdout failed: ${pct(p.holdout_result?.legitimate_rejection_rate ?? 0)} legitimate rejection. Recommendation withheld.`);
  $('candidates').replaceChildren(); for(const c of p.candidates){const row=document.createElement('tr');for(const value of [c.capacity,c.refill_per_second,pct(c.abuse_rejection_rate),pct(c.legitimate_rejection_rate)])appendText(row,'td',value);$('candidates').append(row);}
  $('limitations').replaceChildren(); p.limitations.forEach(l=>appendText($('limitations'),'li',l)); write('rollback',p.rollback);
  chart(result?.timeline ?? []);
}
function chart(points){
  const svg=$('timeline'); svg.replaceChildren(); const ns='http://www.w3.org/2000/svg';
  const max=Math.max(1,...points.map(p=>p.legitimate+p.abusive)); const width=660/Math.max(1,points.length);
  function rect(x,y,w,h,fill){const el=document.createElementNS(ns,'rect');Object.entries({x,y,width:w,height:Math.max(0,h),fill,rx:2}).forEach(([k,v])=>el.setAttribute(k,v));svg.append(el);}
  points.forEach((p,i)=>{const x=20+i*width; const legit=p.legitimate/max*108, abuse=p.abusive/max*108;
    rect(x,125-legit,width*.55,legit,'#277a68');rect(x,125-legit-abuse,width*.55,abuse,'#cda880');
    rect(x+width*.62,125-p.rejected/max*108,width*.23,p.rejected/max*108,'#203b43');
    const t=document.createElementNS(ns,'text');t.setAttribute('x',x);t.setAttribute('y',146);t.setAttribute('font-size',9);t.setAttribute('fill','#63777c');t.textContent=p.second+'s';svg.append(t);});
}
function evidence(){
  const passed=local.checks.filter(c=>c.passed).length;write('local-status',`${passed} / ${local.checks.length} local integration checks passed`);
  const shared=local.checks.find(c=>c.check==='shared allowance across two instances').detail;
  write('shared-result',`${shared.requests} concurrent requests across two application instances: ${shared.allowed} allowed, ${shared.rejected} rate limited. Synthetic clients; this is not a production performance benchmark.`);
  for(const c of local.checks)appendText($('local-checks'),'li',`${c.passed?'✓':'✕'} ${c.check}`, c.passed?'':'failed');
  if(!cloud){write('cloud-status','No current AWS deployment evidence');write('aws-title','Not yet verified');write('aws-summary','The AWS template and manual workflow are available in the repository. No successful full-stack deployment is claimed here.');return;}
  const count=cloud.checks?.filter(c=>c.passed).length ?? 0;
  const ok=cloud.evidence_type==='aws_live_verified' && cloud.checks?.every(c=>c.passed) && count>0;
  write('cloud-status',`${ok?'Live tests verified':'Deployment attempt recorded'}${cloud.cleanup_verified?' · cleanup verified':''}`);
  $('cloud-dot').className='dot '+(ok?'green':'amber');write('aws-title',ok?'Live controls, verified.':'Deployment evidence');
  write('aws-summary',`${count} cloud checks passed. ${cloud.cleanup_verified?'Disposable resources removed; the evidence remains.':'Cleanup is not yet verified.'} ${cloud.failure_summary ?? ''}`);
  for(const c of cloud.checks ?? [])appendText($('aws-checks'),'li',`${c.passed?'✓':'✕'} ${c.check}`,c.passed?'':'failed');
  if(cloud.live_aggregates){appendText($('live-aggregates'),'h4','Live WAF decisions');for(const [k,v] of Object.entries(cloud.live_aggregates.waf))appendText($('live-aggregates'),'p',`${k}: ${v}`);appendText($('live-aggregates'),'p','Live traffic is unlabelled. It does not establish detection accuracy.');}
  $('aws-download').hidden=false;
}
Promise.all([get('recommendations.json'),get('integration.json'),get('aws.json',true)]).then(([r,l,c])=>{
  data=r;local=l;cloud=c; for(const p of data.proposals){const b=document.createElement('button');b.className='endpoint-button';b.dataset.route=p.route;appendText(b,'strong',p.route.charAt(0).toUpperCase()+p.route.slice(1));appendText(b,'small',labels[p.route]);b.addEventListener('click',()=>{current=p.route;render();});$('endpoints').append(b);}
  $('policy-view').addEventListener('change',render);$('dataset').addEventListener('change',render);render();evidence();
}).catch(()=>{const e=document.createElement('p');e.className='error';e.textContent='Evidence could not be loaded. Please reload or inspect the JSON files in the repository.';document.querySelector('main').prepend(e);});
