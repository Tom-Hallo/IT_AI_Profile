// GitHub Code Rain — public-only, no credentials, no untrusted execution.
const root = document.querySelector('#ambientCode');
const form = document.querySelector('#githubRainForm');
const input = document.querySelector('#githubUsername');
const status = document.querySelector('#githubRainStatus');
const details = document.querySelector('#githubRainDetails');
const submit = document.querySelector('#githubRainSubmit');
const reduce = matchMedia('(prefers-reduced-motion: reduce)');
const small = matchMedia('(max-width: 700px)');
const examples = [
  {lang:'PYTHON · DEMO', repo:'Ví dụ minh họa', text:'async def analyze(repo):\n    return await inspect(repo)'},
  {lang:'TYPESCRIPT · DEMO', repo:'Ví dụ minh họa', text:'type Skill = { name: string; level: number };'},
  {lang:'SQL · DEMO', repo:'Ví dụ minh họa', text:'SELECT language, COUNT(*) FROM repositories GROUP BY language;'},
  {lang:'GO · DEMO', repo:'Ví dụ minh họa', text:'func Analyze(ctx context.Context) error { return nil }'},
];
const extensions = {'.py':'Python','.ts':'TypeScript','.tsx':'TypeScript','.js':'JavaScript','.jsx':'JavaScript','.go':'Go','.rs':'Rust','.java':'Java','.cs':'C#','.kt':'Kotlin','.swift':'Swift','.sql':'SQL','.html':'HTML','.css':'CSS','.cpp':'C++','.rb':'Ruby','.php':'PHP'};
let active = examples;
let controller = null;
const random = (a,b) => a+Math.random()*(b-a);
function render(items){
  if(!root)return;
  root.replaceChildren();
  const count = reduce.matches ? 5 : small.matches ? 8 : 16;
  for(let i=0;i<count;i++){
    const item=items[i%items.length];
    const stream=document.createElement('div');
    stream.className='code-stream '+['code-blue','code-teal','code-purple'][i%3];
    const heading=document.createElement('span'); heading.className='code-lang'; heading.textContent=item.lang;
    const pre=document.createElement('pre'); pre.textContent=item.text;
    stream.append(heading,pre);
    if(item.url){
      const link=document.createElement('a');link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';
      link.className='code-source';link.textContent='Đến từ repo: '+item.repo+' · Xem file ↗';
      stream.append(link);stream.title='Đến từ repo: '+item.repo;
    } else stream.title=item.repo;
    stream.style.setProperty('--x',((i+.5)/count*100+random(-2,2)).toFixed(2)+'%');
    stream.style.setProperty('--start',random(-40,100).toFixed(1)+'vh');
    stream.style.setProperty('--duration',random(28,52).toFixed(1)+'s');
    stream.style.setProperty('--delay',(-random(0,50)).toFixed(1)+'s');
    stream.style.setProperty('--scale',random(.8,1.08).toFixed(2));
    stream.style.setProperty('--opacity',random(.32,.55).toFixed(2));
    root.append(stream);
  }
}
async function api(path,signal){
  const response=await fetch('https://api.github.com'+path,{signal,headers:{Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}});
  if(!response.ok){
    if(response.status===404)throw Error('Không tìm thấy GitHub username hoặc repository.');
    if(response.status===403||response.status===429)throw Error('GitHub đang giới hạn lượt truy cập API. Hãy thử lại sau.');
    throw Error('GitHub API trả về lỗi '+response.status+'.');
  }
  return response.json();
}
const extOf = name => Object.keys(extensions).find(ext=>name.toLowerCase().endsWith(ext));
const sourceFile = f => f.type==='file' && extOf(f.name) && f.size>0 && f.size<=45000;
async function findFiles(repo,signal){
  const base='/repos/'+encodeURIComponent(repo.owner.login)+'/'+encodeURIComponent(repo.name)+'/contents/';
  const rootFiles=await api(base,signal);
  if(!Array.isArray(rootFiles))return [];
  let files=rootFiles.filter(sourceFile);
  // Limit traversal: root and one conventional source directory only.
  const folder=rootFiles.find(f=>f.type==='dir'&&['src','app','lib','backend','frontend'].includes(f.name.toLowerCase()));
  if(folder && files.length<2){
    try {const nested=await api(base+encodeURIComponent(folder.name),signal);if(Array.isArray(nested))files.push(...nested.filter(sourceFile));}
    catch(e){if(e.name==='AbortError')throw e;}
  }
  return files.slice(0,2);
}
async function readSnippet(file,repo,signal){
  const response=await fetch(file.download_url,{signal});
  if(!response.ok)throw Error('Không đọc được file');
  const content=await response.text();
  if(content.includes('\0'))throw Error('Binary');
  const lines=content.split(/\r?\n/).map(x=>x.trimEnd());
  const start=lines.findIndex(x=>x.trim()&&!/^\s*(\/\/|#|\*|\/\*|<!--)/.test(x));
  if(start<0)return null;
  const text=lines.slice(start,start+5).join('\n').slice(0,440).trim();
  if(!text)return null;
  return {lang:extensions[extOf(file.name)]||repo.language||'CODE',repo:repo.name,text,url:file.html_url};
}
async function personalize(username,signal){
  const repos=await api('/users/'+encodeURIComponent(username)+'/repos?per_page=100&type=owner&sort=updated',signal);
  if(!Array.isArray(repos))throw Error('Dữ liệu GitHub không hợp lệ.');
  const publicRepos=repos.filter(r=>!r.private&&!r.fork&&!r.archived&&!r.disabled).slice(0,8);
  if(!publicRepos.length)throw Error('Tài khoản chưa có repository public phù hợp để hiển thị.');
  const found=[];
  // Sequential requests to avoid API bursts; cap reads at 8 repos / 2 files each.
  for(const repo of publicRepos){
    if(found.length>=8)break;
    try {
      const files=await findFiles(repo,signal);
      for(const file of files){
        if(found.length>=8)break;
        try {const snippet=await readSnippet(file,repo,signal);if(snippet)found.push(snippet);}
        catch(e){if(e.name==='AbortError')throw e;}
      }
    }catch(e){if(e.name==='AbortError')throw e;}
  }
  if(!found.length)throw Error('Đã tìm thấy repository, nhưng không có file code nhỏ phù hợp để hiển thị.');
  return {found,repoCount:repos.length,scanned:publicRepos.length};
}
form?.addEventListener('submit',async event=>{
  event.preventDefault();
  const username=input.value.trim();
  if(!/^[a-z\d](?:[a-z\d-]{0,37}[a-z\d])?$/i.test(username)||username.includes('--')){
    status.textContent='Username không hợp lệ. Kiểm tra lại tên tài khoản GitHub.';return;
  }
  controller?.abort();controller=new AbortController();const current=controller;
  submit.disabled=true;status.textContent='Đang đọc repository và file code công khai…';details.hidden=true;
  try{
    const result=await personalize(username,current.signal);
    if(current!==controller)return;
    active=result.found;render(active);
    status.textContent='Đang hiển thị '+active.length+' đoạn code thật từ @'+username+'.';
    details.replaceChildren();
    const a=document.createElement('a');a.href='https://github.com/'+encodeURIComponent(username);a.target='_blank';a.rel='noopener noreferrer';a.textContent='Xem GitHub @'+username+' ↗';
    const p=document.createElement('span');p.textContent=' · Đã khảo sát tối đa '+result.scanned+' repo gần đây · Không lưu mã nguồn';
    details.append(a,p);details.hidden=false;
  }catch(e){if(e.name!=='AbortError'&&current===controller){status.textContent=e.message+' Đang giữ Code Rain trước đó.';}}
  finally{if(current===controller)submit.disabled=false;}
});
render(active);
reduce.addEventListener('change',()=>render(active));small.addEventListener('change',()=>render(active));
const aura=document.querySelector('#cursorAura');
if(aura && matchMedia('(pointer:fine)').matches){
  window.addEventListener('pointermove',e=>{if(reduce.matches)return;aura.style.left=e.clientX+'px';aura.style.top=e.clientY+'px';aura.style.opacity='1';},{passive:true});
}
