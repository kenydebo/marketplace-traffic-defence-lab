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
  const result=candidate ? (holdout ? p.holdout_result : selected) : (holdout ? p.baseline_holdout_result : p.baseline_result);
  write('owner',p.owner+' / PROPOSED OWNER'); write('route','/api/'+p.route+(p.route==='products'?'/{id}':'')); write('risk',p.risk);
  write('decision-badge',p.decision==='propose_observation'?'Count-mode proposal':'Keep in review');
  $('decision-badge').className='pill'+(p.decision==='propose_observation'?'':' warn');
  write('abuse-rate',result ? pct(result.abuse_rejection_rate) : '—'); write('buyer-rate',result ? pct(result.legitimate_rejection_rate) : '—');
  write('abuse-count', result ? `${result.abusive_rejected} / ${result.abusive_rejected+result.abusive_allowed} labelled abusive requests` : 'Review sample coverage');
  const policy=candidate?selected:p.baseline_policy;
  write('capacity',policy?.capacity ?? '—'); write('refill',policy ? policy.refill_per_second+' tokens / second' : 'Review candidate settings');
  write('p99',p.calibration.p99_cost_per_key_second); write('distinct',p.observations.maximum_distinct_resources_per_actor); write('fingerprint',p.observations.maximum_sources_sharing_fingerprint);
  write('reason',`Python starts with the normal baseline P99 of ${p.calibration.p99_cost_per_key_second} cost units per key per second and compares candidate limits. The lab target is at most 1% buyer rejection and at least 50% abuse rejection across both samples.`);
  write('edge',p.decision==='propose_observation'?`Count ${p.edge_proposal.limit} requests per source address per ${p.edge_proposal.window_seconds} seconds on ${p.edge_proposal.scope}. This is 1.5 times the normal source-minute P99 of ${p.calibration.p99_requests_per_source_minute} requests.`:'Keep this endpoint in review. Adjust the proposal and repeat the buyer-impact test before adding a WAF observation.');
  write('holdout-status',p.holdout_passed?'The separate sample meets the lab targets. Review WAF Count results before enforcement.':`The separate sample rejects ${pct(p.holdout_result?.legitimate_rejection_rate ?? 0)} of buyer requests against a 1% lab budget. Keep the proposal in review.`);
  $('candidates').replaceChildren(); for(const c of p.candidates){const row=document.createElement('tr');for(const value of [c.capacity,c.refill_per_second,pct(c.abuse_rejection_rate),pct(c.legitimate_rejection_rate)])appendText(row,'td',value);$('candidates').append(row);}
  $('limitations').replaceChildren();
  for(const note of ['Evaluation data: generated, labelled buyer and abuse scenarios.', 'Buyer-impact review: validation and a separate test sample.', 'Further investigation: slow traffic, rotating sessions and distributed sources.', 'WAF review: evaluate rate-window behaviour using Count results.', 'JA4: supporting context during investigation.']) appendText($('limitations'),'li',note);
  write('rollback','Rollback trigger: buyer rejection above the agreed budget. The lab budget is 1%; the service owner sets the production target.');
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
const checkLabels = {
  'shared allowance across two instances':'Both instances share one request allowance',
  'no fallback during shared-state test':'All shared-limit requests used Redis',
  'independent signed session gets own allowance':'Each signed session receives its own allowance',
  'modified token rejected':'Session signatures are validated',
  'arbitrary account header grants no identity':'Cart requests require an application-issued session',
  'product IDs share one route-class allowance':'Product IDs share an endpoint allowance',
  'query cost consumes shared tokens':'Search cost consumes shared credits',
  'excessive query cost rejected':'Search request size is bounded',
  'health remains available':'Health checks remain available',
  'Redis outage gives bounded browsing fallback':'Browsing uses a small local allowance during a Redis outage',
  'Redis outage rejects login':'Login pauses during a Redis outage',
  'Redis outage rejects cart':'Cart updates pause during a Redis outage',
  'normal edge request':'Normal requests reach the application through CloudFront',
  'synthetic WAF marker blocked':'WAF blocks the configured test marker',
  'anonymous signed session issued':'The application issues signed anonymous sessions',
  'shared Redis allowance in AWS':'AWS requests share the Redis allowance',
  'both application instances observed':'Requests reach both application instances',
  'tampered session rejected':'Altered session tokens are rejected',
  'fixture account authenticates':'The demo account signs in',
  'signed account can submit synthetic cart':'The signed account submits a mock cart item',
  'unsigned cart request rejected':'Cart requests require a signed session',
  'scoped WAF rate enforcement':'The scoped WAF rate test blocks excess traffic',
  'WAF catalog probe preserves health':'Health checks stay available during the WAF test',
  'WAF probe rollback to Count':'The WAF test rule returns to Count mode',
  'AWS product ID rotation shares route allowance':'Changing product IDs uses the same endpoint allowance',
  'AWS expensive queries consume shared cost budget':'Expensive searches consume shared credits',
  'AWS excessive query cost rejected':'Search cost stays within the configured bound',
  'AWS origin load balancer is internal':'The origin load balancer is private',
  'eligible recommendations and JA4 remain Count; withheld login absent':'Eligible endpoint and JA4 policies are verified in Count'
};
function appendCheck(parent, check) {
  appendText(parent,'li',`${check.passed?'✓':'✕'} ${checkLabels[check.check] ?? check.check}`,check.passed?'':'failed');
}
function tableRow(parent, values) {
  const row=document.createElement('tr');
  for(const value of values) appendText(row,'td',String(value));
  parent.append(row);
}
function evidence(){
  const passed=local.checks.filter(c=>c.passed).length;
  write('local-status',`${passed} / ${local.checks.length} application checks passed`);
  write('local-check-summary',`View all ${local.checks.length} application checks`);
  const shared=local.checks.find(c=>c.check==='shared allowance across two instances').detail;
  write('shared-result',`${shared.requests} concurrent test requests across two instances: ${shared.allowed} allowed and ${shared.rejected} rate limited.`);
  for(const c of local.checks) appendCheck($('local-checks'),c);
  if(!cloud){
    write('cloud-status','AWS verification pending');
    write('aws-title','Run the AWS verification');
    write('aws-summary','Use the manual GitHub workflow to deploy, test and collect AWS results.');
    return;
  }
  const count=cloud.checks?.filter(c=>c.passed).length ?? 0;
  const total=cloud.checks?.length ?? 0;
  const ok=cloud.evidence_type==='aws_live_verified' && count===total && total>0;
  write('cloud-status',`${count} / ${total} AWS checks passed · ${cloud.cleanup_verified?'cleanup verified':'cleanup verification pending'}`);
  $('cloud-dot').className='dot '+(ok?'green':'amber');
  write('aws-title',`${count} / ${total} AWS checks passed`);
  write('aws-check-summary',`View all ${total} AWS checks`);
  write('aws-summary',`${ok?'CloudFront, WAF, application and Redis controls verified.':'Review the recorded deployment checks.'} ${cloud.cleanup_verified?'AWS resources removed after testing.':'Resource cleanup verification pending.'} ${cloud.failure_summary ?? ''}`);
  for(const c of cloud.checks ?? []) appendCheck($('aws-checks'),c);
  if(cloud.tested_at){
    const date=new Date(cloud.tested_at);
    if(Number.isFinite(date.getTime())) write('aws-run-date','AWS run · '+date.toLocaleDateString('en-CA',{year:'numeric',month:'short',day:'numeric',timeZone:'UTC'}));
  }
  const ruleLabels={Default_Action:'Default action',SyntheticMarker:'Test marker',EnforcementProbe:'Rate-limit test',CatalogObserve:'Catalog',ProductsObserve:'Products',SearchObserve:'Search',CartObserve:'Cart',SessionObserve:'Session',JA4Observe:'JA4 observation'};
  for(const [key,value] of Object.entries(cloud.live_aggregates?.waf ?? {})){
    const [name,action]=key.split(' / ');
    tableRow($('waf-decisions'),[ruleLabels[name] ?? name,action,value]);
  }
  const rules=cloud.deployed_edge_rules ?? [];
  if(rules.some(rule=>rule.action!=='Count')) write('waf-policy-title','Recorded WAF policy actions');
  for(const rule of rules) tableRow($('waf-policies'),[ruleLabels[rule.name] ?? rule.name,rule.limit,rule.action]);
  $('aws-download').hidden=false;
}
Promise.all([get('recommendations.json'),get('integration.json'),get('aws.json',true)]).then(([r,l,c])=>{
  data=r;local=l;cloud=c; for(const p of data.proposals){const b=document.createElement('button');b.className='endpoint-button';b.dataset.route=p.route;appendText(b,'strong',p.route.charAt(0).toUpperCase()+p.route.slice(1));appendText(b,'small',labels[p.route]);b.addEventListener('click',()=>{current=p.route;render();});$('endpoints').append(b);}
  $('policy-view').addEventListener('change',render);$('dataset').addEventListener('change',render);render();evidence();
}).catch(()=>{const e=document.createElement('p');e.className='error';e.textContent='Reload to load the test results, or open the result files in the repository.';document.querySelector('main').prepend(e);});
