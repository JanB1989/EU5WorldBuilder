const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const elements={};
const ctx={fillRect(){},drawImage(){},getImageData(){throw new Error('Local image canvas is tainted');}};
function element(){return {style:{},value:0,innerHTML:'',append(){},replaceChildren(){},getContext(){return ctx},clientWidth:1024,clientHeight:512,getBoundingClientRect(){return {left:10,top:20}},setPointerCapture(){}}}
const data=['first','second'].map(location_tag=>({location_tag,province:'test',region:'test',eu5_start_population:10,base_effective_cropland:10,capacity_multiplier:2,starting_improvement_effective_cropland:5,maximum_improvement_effective_cropland:20,inert_capacity:20,starting_improvement_capacity:10,starting_capacity:30,maximum_capacity:60,remaining_improvement_effective_cropland:15,starting_fill:1/3,physical_location_ha:10,coastline_transfer_share:0,evidence_status:'test'}));
const sandbox={console,Intl,devicePixelRatio:2,LOCATIONS:data,METRICS:[{key:'starting_capacity',label:'Starting capacity',cap:60,unit:'people',log:true},{key:'starting_fill',label:'Pressure',cap:2,unit:'ratio',log:false},{key:'starting_clearing_improvement_capacity',label:'Starting clearing',cap:10000,unit:'people',log:false},{key:'maximum_water_management_improvement_capacity',label:'Maximum irrigation',cap:10000,unit:'people',log:false}],LOCATION_LOOKUP:{width:4096,height:2048,rows:Array.from({length:2048},()=>[2048,1,4096,2])},document:{getElementById(id){return elements[id]??=element()},createElement(){return element()},querySelector(){return element()}},Image:class{constructor(){this.complete=false}get src(){return this._src}set src(v){this._src=v;this.complete=true;if(this.onload)this.onload()}}};
sandbox.window=sandbox;vm.createContext(sandbox);
const code=fs.readFileSync(process.argv[2]||path.resolve(__dirname,'../artifacts/locations/viewer_candidate.js'),'utf8');vm.runInContext(code,sandbox);
sandbox.METRICS.push({key:'starting_paddy_control_improvement_capacity',label:'Starting paddy control',cap:10000,unit:'people',log:false});
vm.runInContext('const extraOption=document.createElement("option");extraOption.value=4;select.append(extraOption);metricOptions.push(extraOption);',sandbox);
const canvas=elements.map;
function click(x,y){const e={clientX:x,clientY:y,pointerId:1};canvas.onpointerdown(e);canvas.onpointerup(e)}
click(110,120);assert.match(elements.detail.innerHTML,/<h2[^>]*>First<\/h2>/);
click(810,120);assert.match(elements.detail.innerHTML,/<h2[^>]*>Second<\/h2>/);
assert.equal(vm.runInContext('locationAt(2047,0)',sandbox),1);
assert.equal(vm.runInContext('locationAt(2048,0)',sandbox),2);
assert.equal(vm.runInContext('locationAt(4096,0)',sandbox),0);
assert.equal(vm.runInContext('locationAt(-1,0)',sandbox),0);
vm.runInContext('z=2;ox=-1500;oy=-100;',sandbox);
click(410,170);assert.match(elements.detail.innerHTML,/<h2[^>]*>Second<\/h2>/);
const before=elements.detail.innerHTML;canvas.onpointerdown({clientX:100,clientY:100,pointerId:2});canvas.onpointermove({clientX:120,clientY:100});canvas.onpointerup({clientX:120,clientY:100});assert.equal(elements.detail.innerHTML,before);
console.log('PASS: click selection with blocked canvas readback, row boundaries, high-DPI, pan/zoom and drag discrimination');

click(410,170);
const panel=elements.detail.innerHTML;
const primary=panel.split('<details>')[0];
assert.match(primary,/The four model values/);
assert.match(primary,/33% of starting capacity occupied/);
assert.match(primary,/Total limit, including existing improvements/);
assert.ok(!primary.includes('Physical location area'));
assert.ok(!primary.includes('Base contribution'));
assert.match(panel,/<details><summary>Breakdown &amp; evidence<\/summary>/);
console.log('PASS: summary first, four inputs, percentage fill, secondary details collapsed');

assert.equal(elements.areaMode,undefined);
assert.equal(vm.runInContext('img.src',sandbox),'starting_capacity_equal.png');
assert.ok(!code.includes('AREA_DATA'));
console.log('PASS: viewer exclusively uses equal-area maps without a mode selector');

data[0].is_ownable=false;vm.runInContext('show(0)',sandbox);
assert.match(elements.detail.innerHTML,/Not ownable in EU5/);
data[0].is_ownable=true;data[0].maximum_capacity=0;vm.runInContext('show(0)',sandbox);
assert.match(elements.detail.innerHTML,/Unresolved: ownable location has zero modeled food support/);
console.log('PASS: non-ownable and unresolved settlement states are explicit');

// The allocation is an additional concise table, with zero budgets explicit.
data[0].starting_distribution_status='allocated';
data[0].maximum_distribution_status='allocated';
for(const [k,s,m] of [['clearing',.6,.4],['management',.3,.35],['water_management',.1,.25]]) {
 data[0]['starting_'+k+'_improvement_share']=s;
 data[0]['maximum_'+k+'_improvement_share']=m;
 data[0]['starting_'+k+'_improvement_units']=s*10000;
 data[0]['maximum_'+k+'_improvement_units']=m*20000;
 data[0]['starting_'+k+'_improvement_capacity']=s*10000*data[0].capacity_multiplier;
 data[0]['maximum_'+k+'_improvement_capacity']=m*20000*data[0].capacity_multiplier;
}
vm.runInContext('show(0)',sandbox);
assert.match(elements.detail.innerHTML,/What the improvements represent/);
assert.match(elements.detail.innerHTML,/>60%<\/small>/);
assert.match(elements.detail.innerHTML,/>40%<\/small>/);
data[0].starting_distribution_status='no_improvement_budget';
vm.runInContext('show(0)',sandbox);
assert.match(elements.detail.innerHTML,/>—<\/td>/);
console.log('PASS: starting/maximum shares and explicit zero-budget display');

elements.tabImprovements.onclick();
assert.equal(elements.tabImprovements.ariaPressed,'true');
assert.equal(vm.runInContext('img.src',sandbox),'starting_clearing_improvement_capacity_equal.png');
assert.equal(elements.scale.textContent,'10K+ people · linear');
assert.equal(vm.runInContext('metricOptions[0].hidden',sandbox),true);
elements.metric.value=3;elements.metric.onchange();
assert.equal(vm.runInContext('img.src',sandbox),'maximum_water_management_improvement_capacity_equal.png');
elements.tabPressure.onclick();
assert.equal(vm.runInContext('img.src',sandbox),'starting_fill_equal.png');
elements.tabImprovements.onclick();
assert.equal(vm.runInContext('img.src',sandbox),'maximum_water_management_improvement_capacity_equal.png');
assert.match(elements.detail.innerHTML,/<h2/);
console.log('PASS: third tab, capacity scale, saved selection and equal-area pressure tab');

assert.match(vm.runInContext('improvementDistribution(LOCATIONS[0])',sandbox),/>16,000<br><small>40%/);
console.log('PASS: multiplied capacity contributions with secondary percentage shares');

elements.tabWater.onclick();
assert.equal(elements.tabWater.ariaPressed,'true');
assert.equal(vm.runInContext('img.src',sandbox),'starting_paddy_control_improvement_capacity_equal.png');
assert.match(elements.viewNote.textContent,/Five complete water-management layers/);
assert.match(elements.detail.innerHTML,/Five water-management types/);
console.log('PASS: fourth water tab selects subtypes and preserves location detail');
