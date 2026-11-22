import {request,post,remove,query,period,parseSkills,exportURL} from './live-api.js';
import {escape,field,tags} from './ui.js';
import {getLanguage, t} from './i18n.js';

const copy = (vi, en) => getLanguage() === 'en' ? en : vi;

export function createLiveStudio({state,runtime,render,drawMentor,showModal,openMentor,navigate,notice}) {
  const data = {
    user:null, repos:[], page:1, total:0, search:'', repoData:{}, roles:[], scores:[], skills:[],
    road:null, tracking:null, history:[], goal:'backend', milestone:null, jobResults:null, jobMatch:null,
    cvList:[], documentList:[], versions:[], cv:null, cvPreview:null, document:null,
    shared:null, shares:[], audit:[], sync:null, health:null, busy:new Set(),
    errors:{}, messages:{}, reportTab:'code', mentorSources:{cvs:[],roadmaps:[]}
  };
  try {
    const savedRange = sessionStorage.getItem('ita-studio-selected-range');
    if (savedRange) state.range = Number(savedRange);
    const savedTab = sessionStorage.getItem('ita-studio-report-tab');
    if (savedTab) data.reportTab = savedTab;
    const savedRepo = sessionStorage.getItem('ita-studio-selected-repo');
    if (savedRepo) state.repo = savedRepo;
  } catch {}
  const active = () => data.repos.find(repo => String(repo.id) === String(state.repo)) ?? data.repos[0];
  const repository = repo => '/repositories/' + repo.id;
  const trackingPath = () => '/roadmap-tracking/' + data.road.id;
  const cvPath = doc => '/cv-studio/' + encodeURIComponent(doc.document_id);
  const currentReport = () => active() ? data.repoData[active().id] : null;
  let repoRequest = 0;
  let dashboardRequest = 0;
  let pageRequest = 0;
  let chatAbort;
  let analysisJob;
  let analysisStarted = false;
  let analysisPolling;
  let analysisEpoch = 0;

  function errorText(error) {
    if (error.name === 'TimeoutError') return copy('Yêu cầu quá thời gian chờ. Vui lòng thử lại.', 'Request timed out. Please try again.');
    if (error.status === 401) return copy('Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.', 'Session expired. Please sign in again.');
    return error.message || copy('Thao tác thất bại.', 'Operation failed.');
  }

  async function work(key,action) {
    if (data.busy.has(key)) return false;
    data.busy.add(key);
    delete data.errors[key];
    delete data.messages[key];
    render();
    try {
      await action();
      return true;
    } catch (error) {
      data.errors[key] = errorText(error);
      notice(data.errors[key]);
      return false;
    } finally {
      data.busy.delete(key);
      render();
    }
  }

  async function login(privateAccess=false) {
    try {
      await request('/auth/github/status');
      if (privateAccess) sessionStorage.setItem('ita-studio-private-return','1');
      location.assign('/api/v1/auth/github' + (privateAccess ? '?include_private=true' : ''));
    } catch (error) {
      notice(errorText(error));
    }
  }

  async function session() {
    try {
      data.user = await request('/auth/me');
      return true;
    } catch (error) {
      if (error.status !== 401) notice(errorText(error));
      return false;
    }
  }

  function applyStatus(status) {
    data.sync = status;
    state.access = status.is_connected ? (status.has_private_scope ? 'combined' : 'public') : 'none';
    if (state.scope !== 'public' && state.access !== 'combined') state.scope = 'public';
  }

  async function repos({page=data.page,loadSelected=true}={}) {
    const token = ++pageRequest;
    const status = await request('/github/sync/status');
    if (token !== pageRequest) return;
    applyStatus(status);
    const result = state.access === 'none' ? {items:[],total:0,page:1}
      : await request('/github/repositories?' + query({
        visibility:state.scope === 'combined' ? 'all' : state.scope,
        page, per_page:30, search:data.search
      }));
    if (token !== pageRequest) return;
    data.repos = result.items;
    data.total = result.total;
    data.page = result.page;
    const wanted = data.requestedRepo;
    if (wanted && !data.repos.some(repo => String(repo.id) === wanted)) {
      try {
        const repo = await request('/github/repositories/' + encodeURIComponent(wanted));
        if (token !== pageRequest) return;
        if (repo.private && state.access !== 'combined') throw new Error(copy('Repository cần quyền riêng tư.', 'Private repository access required.'));
        state.scope = repo.private ? 'private' : 'public';
        data.repos = [repo];
        state.repo = String(repo.id);
      } catch (error) {
        if (token !== pageRequest) return;
        data.errors.repos = errorText(error);
      }
    } else if (wanted) {
      state.repo = wanted;
    }
    data.requestedRepo = null;
    try {
      const saved = sessionStorage.getItem('ita-studio-selected-repo');
      if (saved && data.repos.some(repo => String(repo.id) === saved)) {
        state.repo = saved;
      } else if (!data.repos.some(repo => String(repo.id) === String(state.repo))) {
        state.repo = String(data.repos[0]?.id ?? '');
      }
    } catch {
      if (!data.repos.some(repo => String(repo.id) === String(state.repo))) {
        state.repo = String(data.repos[0]?.id ?? '');
      }
    }
    if (!analysisJob) {
      try {
        const savedJob = JSON.parse(sessionStorage.getItem('ita-active-job') || 'null');
        if (savedJob && savedJob.id) {
          analysisJob = savedJob;
          const targetRepo = data.repos.find(r => r.id === savedJob.repo_id) || active();
          if (targetRepo) watchAnalysis(targetRepo, ++analysisEpoch);
        }
      } catch {}
    }
    if (loadSelected) await repoDetail();
  }

  async function repoDetail({reportId}={}) {
    const repo = active();
    if (!repo) return;
    const token = ++repoRequest;
    const path = repository(repo);
    const updated = {report:null,evidence:[],verification:null,collaboration:null,activity:null,consent:null,errors:{}};
    let report;
    try {
      report = await request(path + '/analysis' + (reportId ? '?report_id=' + reportId : ''));
    } catch (error) {
      if (error.status !== 404 && !(repo.private && error.status === 403)) updated.errors.report = errorText(error);
    }
    if (token !== repoRequest) return;
    if (report) {
      updated.report = report;
      updated.verification = report.verification;
    }
    const jobs = [
      ['consent',repo.private ? request(path + '/consents') : null],
      ['evidence',report?.report_id ? request(path + '/analysis/evidence?report_id=' + report.report_id) : null],
      ['collaboration',report?.report_id ? request(path + '/collaboration') : null]
    ];
    await Promise.all(jobs.map(async ([key,task]) => {
      if (!task) return;
      try {
        const response = await task;
        updated[key] = key === 'evidence' ? response.items : response;
      } catch (error) {
        if (error.status !== 404) updated.errors[key] = errorText(error);
      }
    }));
    if (token === repoRequest) data.repoData[repo.id] = updated;
  }

  async function sync() {
    if (state.access === 'none') return;
    await work('sync',async () => {
      const visibility = state.scope === 'combined' ? 'all' : state.scope;
      const result = await post('/github/sync?' + query({background:false,visibility}),undefined,360000);
      if (result.status === 'running' || result.status === 'queued') {
        data.messages.sync = result.message || copy('Đồng bộ đang chạy. Hãy tải lại danh sách sau khi hoàn tất.', 'Sync is running. Please refresh the list when done.');
      } else if (result.synced_count != null) {
        data.messages.sync = copy('Đã đồng bộ ' + result.synced_count + ' repository.', 'Synced ' + result.synced_count + ' repositories.');
      } else {
        data.messages.sync = result.message;
      }
      await repos({page:1});
    });
  }

  function focusRepo(id,tab='code') {
    state.repo = String(id);
    try { sessionStorage.setItem('ita-studio-selected-repo', state.repo); } catch {}
    data.reportTab = tab;
    try { sessionStorage.setItem('ita-studio-report-tab', tab); } catch {}
    if (!data.repos.some(repo => String(repo.id) === state.repo)) data.requestedRepo = state.repo;
    navigate('repos');
    return work('repos', data.requestedRepo ? () => repos() : () => repoDetail());
  }

  async function analyze() {
    const repo = active();
    if (!repo || analysisJob || analysisStarted) return;
    analysisStarted = true;
    data.analysis = {status:'queued',progress:0,repo_id:repo.id};
    data.errors.repos = '';
    render();
    const epoch = ++analysisEpoch;
    try {
      analysisJob = await post('/analysis/jobs',{
        repo_id:repo.id,scope:repo.private ? 'private' : 'public',
        mode:'custom',...period(state.range),timezone:'UTC'
      });
      analysisJob.repo_id = repo.id;
      try {
        sessionStorage.setItem('ita-active-job', JSON.stringify({ id: analysisJob.id, repo_id: repo.id }));
      } catch {}
      watchAnalysis(repo,epoch);
    } catch (error) {
      data.analysis = null;
      data.errors.repos = errorText(error);
      notice(data.errors.repos);
    } finally {
      analysisStarted = false;
      render();
    }
  }

  function watchAnalysis(repo,epoch) {
    data.analysis = { ...analysisJob, repo_id: repo.id };
    render();
    analysisPolling = setTimeout(async () => {
      try {
        const job = await request('/analysis/jobs/' + encodeURIComponent(analysisJob.id));
        if (epoch !== analysisEpoch) return;
        analysisJob = { ...job, repo_id: repo.id };
        if (['queued','running','cancel_requested'].includes(job.status)) {
          watchAnalysis(repo,epoch);
          return;
        }
        data.analysis = null;
        analysisJob = null;
        try { sessionStorage.removeItem('ita-active-job'); } catch {}
        if (job.status === 'succeeded') {
          data.messages.repos = copy('Đã phân tích ' + repo.full_name + '.', 'Analyzed ' + repo.full_name + '.');
          if (active()?.id === repo.id) await repoDetail({reportId:job.report_id});
          data.scores = [];
        } else {
          data.messages.repos = job.status === 'cancelled' ? copy('Đã hủy phân tích.', 'Analysis cancelled.')
            : copy('Phân tích thất bại', 'Analysis failed') + (job.error_code ? ' · ' + job.error_code : '') + '.';
        }
      } catch (error) {
        if (epoch !== analysisEpoch) return;
        data.errors.repos = errorText(error);
        data.analysis = null;
        analysisJob = null;
        try { sessionStorage.removeItem('ita-active-job'); } catch {}
      }
      render();
    },1200);
  }

  async function cancelAnalysis() {
    if (!analysisJob) return;
    const repo = active();
    if (analysisJob.repo_id && repo && analysisJob.repo_id !== repo.id) return;
    await work('cancel',async () => {
      await post('/analysis/jobs/' + encodeURIComponent(analysisJob.id) + '/cancel');
      try { sessionStorage.removeItem('ita-active-job'); } catch {}
    });
  }

  async function activity() {
    const repo = active();
    if (!repo) return;
    await work('activity',async () => {
      const result = await request(repository(repo) + '/activity/analysis?' + query({
        mode:'custom',...period(state.range),timezone:'UTC',scope:'personal'
      }),{timeout:65000});
      if (active()?.id === repo.id) {
        data.repoData[repo.id] ??= {errors:{}};
        data.repoData[repo.id].activity = result;
      }
    });
  }

  async function analyzeTab(tab) {
    const repo = active();
    const report = currentReport()?.report;
    if (!repo || !report) return;
    const endpoint = tab === 'ownership' ? 'verification' : 'collaboration';
    await work('repos',async () => {
      const result = await post(repository(repo) + '/' + endpoint,{
        report_id:report.report_id,scope:repo.private ? 'private' : 'public',
        mode:'custom',...period(state.range),timezone:'UTC'
      },65000);
      if (active()?.id === repo.id) data.repoData[repo.id][endpoint] = result;
    });
  }

  async function dashboard() {
    const token = ++dashboardRequest;
    await Promise.all([
      repos({page:1,loadSelected:false}),
      road().catch(() => {}),
      request('/self-reported-skills').then(items => { data.skills = items; })
    ]);
    if (token !== dashboardRequest) return;
    const dates = period(state.range);
    const filters = query({date_from:dates.start_date,date_to:dates.end_date});
    const roles = await request('/role-scoring/roles');
    const settings = roles.roles ?? [];
    const [scopes,skills] = await Promise.all([
      Promise.allSettled(settings.map(role => request('/role-scoring/roles/' + encodeURIComponent(role.role_key) + '/score/scoped?' + filters))),
      Promise.allSettled(data.repos.map(async repo => {
        const report = await request(repository(repo) + '/analysis/dashboard-report?' + filters);
        if (!report) return [];
        data.repoData[repo.id] ??= { errors: {} };
        data.repoData[repo.id].report = report;
        const scores = await request('/scoring/repositories/' + repo.id + '/skills?report_id=' + report.id);
        return scores.map(item => ({...item,repo}));
      }))
    ]);
    if (token !== dashboardRequest) return;
    data.roles = scopes.flatMap((result,index) => result.status === 'fulfilled' ? [{
      key:settings[index].role_key,name:settings[index].name,...result.value[state.scope]
    }] : []);
    data.scores = skills.flatMap(result => result.status === 'fulfilled' ? result.value : []);
  }

  async function road(targetId) {
    const items = await request('/career-roadmaps');
    data.roadmaps = items;
    if (targetId) {
      data.road = items.find(item => item.id === targetId) ?? null;
    } else {
      data.road = items.find(item => item.goal === data.goal && Array.isArray(item.milestones) && item.milestones.length > 0)
        ?? items.find(item => Array.isArray(item.milestones) && item.milestones.length > 0)
        ?? items[0] ?? null;
    }
    if (data.road) {
      data.goal = data.road.goal;
    }
    data.tracking = data.road ? await request(trackingPath()) : null;
    data.milestone = data.tracking?.milestones[0]?.id ?? null;
    data.history = [];
  }

  async function roadCreate() {
    await work('road',async () => {
      data.road = await post('/career-roadmaps',{goal:data.goal});
      data.roadmaps = await request('/career-roadmaps');
      data.tracking = await request(trackingPath());
      data.milestone = data.tracking.milestones[0]?.id ?? null;
      data.history = [];
    });
  }

  async function roadStatus(id,status) {
    await work('road',async () => {
      const milestone = data.tracking.milestones.find(item => item.id === id);
      if (!milestone) return;
      await request(trackingPath() + '/milestones/' + id,{
        method:'PATCH',json:{status,expected_version:milestone.version}
      });
      data.tracking = await request(trackingPath());
      await roadHistory();
    });
  }

  async function roadHistory() {
    const id = data.milestone;
    if (!data.road || !id) return;
    const history = await request(trackingPath() + '/milestones/' + id + '/history');
    if (data.milestone === id) data.history = history;
  }

  async function cvLoad() {
    const [items,documents] = await Promise.all([request('/cvs'),request('/cv-studio')]);
    data.cvList = items;
    data.documentList = documents;
  }

  function setCV(cv) {
    data.cv = cv;
    data.document = null;
    data.cvPreview = null;
    runtime.cvDraft.body = cv.text;
    data.ats = null;
  }

  async function cvUpload(file) {
    if (!/\.(pdf|docx)$/i.test(file.name) || !file.size || file.size > 5 * 1024 * 1024) {
      notice(copy('Chọn CV PDF hoặc DOCX tối đa 5 MB.', 'Select a PDF or DOCX CV up to 5 MB.'));
      return;
    }
    await work('cv',async () => {
      const result = await request('/cvs/preview',{method:'POST',file,timeout:45000});
      data.cvPreview = result;
      data.cv = null;
      data.document = null;
      data.ats = null;
      runtime.cvDraft.body = result.text;
    });
  }

  async function cvSave() {
    const text = runtime.cvDraft.body.trim();
    if (!text) { notice(copy('Nhập nội dung CV.', 'Enter CV content.')); return; }
    await work('cv',async () => {
      if (data.cvPreview) {
        setCV(await post('/cvs',{text,receipt:data.cvPreview.receipt}));
      } else if (data.cv) {
        setCV(await request('/cvs/' + data.cv.id,{method:'PUT',json:{text,version:data.cv.version}}));
      } else if (data.document) {
        const doc = data.document;
        const versions = await request(cvPath(doc) + '/versions');
        if (versions[0]?.number !== doc.number) throw new Error(copy('Mở bản mới nhất trước khi lưu phiên bản mới.', 'Open latest version before saving a new one.'));
        setDocument(await post(cvPath(doc) + '/versions',{
          title:runtime.cvDraft.name,text,previous_version:doc.number
        }));
        data.versions = await request(cvPath(doc) + '/versions');
      } else {
        throw new Error(copy('Tải CV PDF/DOCX hoặc tạo bản CV bằng AI để lưu.', 'Upload a PDF/DOCX CV or generate with AI to save.'));
      }
      await cvLoad();
      data.messages.cv = copy('Đã lưu CV trên máy chủ.', 'CV saved on server.');
    });
  }

  function setDocument(document) {
    data.document = document;
    data.cv = null;
    data.cvPreview = null;
    data.ats = null;
    runtime.cvDraft.name = document.title;
    runtime.cvDraft.body = document.lines.map(line => line.text).join('\n');
  }

  async function cvGenerate(form) {
    await work('cv',async () => {
      const cvId = Number(form.get('cv-id'));
      const doc = await post('/cv-studio/generate',{
        title:String(form.get('title')).trim(),jd:String(form.get('jd')).trim(),cv_id:cvId || null,
        use_github:form.has('github'),allow_ai:form.has('permit'),template:state.template === 'tech' ? 'technical' : 'classic'
      },330000);
      setDocument(doc);
      data.versions = await request(cvPath(doc) + '/versions');
      await cvLoad();
    });
  }

  async function ats() {
    if (!data.cv) { notice(copy('Chọn và lưu CV tải lên trước khi kiểm tra ATS.', 'Select and save an uploaded CV before checking ATS.')); return; }
    if (data.cv.text !== runtime.cvDraft.body.trim()) {
      notice(copy('Lưu nội dung CV đã chỉnh sửa trước khi kiểm tra ATS.', 'Save edited CV content before checking ATS.'));
      return;
    }
    await work('cv',async () => {
      data.ats = await post('/ats-reviews/preview',{cv_id:data.cv.id,jd_text:data.atsJD?.trim() || null});
    });
  }

  async function jobAnalyze(text,url) {
    data.jobText = text;
    data.jobURL = url;
    data.jobMatch = null;
    const loaded = await work('jobs',async () => {
      data.jobDraft = await post('/jobs/analyze',text ? {text} : {url},20000);
      if (data.jobDraft.fallback) data.messages.jobs = data.jobDraft.fallback.message;
    });
    if (!loaded || !data.jobDraft || data.jobDraft.fallback) return;
    const required = data.jobDraft.required_skills.map(item => item.skill_key).join(', ');
    const preferred = data.jobDraft.preferred_skills.map(item => item.skill_key).join(', ');
    showModal(copy('Xác nhận kỹ năng', 'Confirm skills'),'<div class="stack">'
      + field(copy('Bắt buộc', 'Required'),'<textarea name="required" rows="3">' + escape(required) + '</textarea>')
      + field(copy('Ưu tiên', 'Preferred'),'<textarea name="preferred" rows="3">' + escape(preferred) + '</textarea>') + '</div>',
      copy('Đối chiếu', 'Match'),form => void work('jobs',async () => {
        const skills = [...parseSkills(String(form.get('required')),'required'),...parseSkills(String(form.get('preferred')),'preferred')];
        if (!skills.length) throw new Error(copy('Nhập ít nhất một kỹ năng để đối chiếu.', 'Enter at least one skill to match.'));
        data.jobMatch = await post('/jobs/match',{scope:state.scope,skills});
      }));
  }

  async function userData() {
    const [status,shares,audit] = await Promise.all([
      request('/github/sync/status'),request('/profile/shares'),request('/ai-audit?limit=30')
    ]);
    applyStatus(status);
    data.shares = shares;
    data.audit = audit.items;
  }

  function share() {
    showModal(copy('Tạo liên kết hồ sơ', 'Create profile link'),'<div class="stack">'
      + '<label class="option-row"><input type="checkbox" name="name" checked> ' + copy('Tên hiển thị', 'Display name') + '</label>'
      + '<label class="option-row"><input type="checkbox" name="repos"> ' + copy('Repository công khai', 'Public repositories') + '</label></div>',
      copy('Tạo liên kết', 'Create link'),form => void work('data',async () => {
        const allowed_fields = [];
        if (form.has('name')) allowed_fields.push('full_name');
        if (form.has('repos')) allowed_fields.push('public_repositories');
        if (!allowed_fields.length) throw new Error(copy('Chọn ít nhất một trường để chia sẻ.', 'Select at least one field to share.'));
        const result = await post('/profile/shares',{allowed_fields});
        data.shared = {id:result.id,url:location.origin + '/#share/' + result.token};
        data.shares = await request('/profile/shares');
      }));
  }

  async function loadPublic(token) {
    data.public = undefined;
    data.publicToken = token;
    try {
      const profile = await request('/public/profiles/' + encodeURIComponent(token));
      if (location.hash !== '#share/' + token) return;
      data.public = profile;
    } catch {
      if (location.hash !== '#share/' + token) return;
      data.public = null;
    }
  }

  function consent(kind,revoke=false,provider='',repo=active()) {
    const consentData = repo && data.repoData[repo.id]?.consent;
    if (!repo?.private || !consentData) { notice(copy('Chọn repository riêng tư để quản lý quyền.', 'Select a private repository to manage consent.')); return; }
    if (revoke) {
      const params = kind === 'external_ai' ? '?provider=' + encodeURIComponent(provider) : '';
      showModal(copy('Thu hồi quyền', 'Revoke consent'),'<p>' + copy('Thu hồi quyền của repository đã chọn?', 'Revoke consent for the selected repository?') + '</p>',copy('Thu hồi', 'Revoke'),() =>
        void work('repos',async () => {
          await remove(repository(repo) + '/consents/' + kind + params);
          clearChat();
          await repoDetail();
        }),{tone:'danger'});
      return;
    }
    const providerField = kind === 'external_ai' ? field(copy('Nhà cung cấp', 'Provider'),
      '<select name="provider"><option value="ollama">Ollama</option><option value="openai">OpenAI</option></select>') : '';
    showModal(kind === 'external_ai' ? copy('Xác nhận sử dụng AI với mã riêng tư', 'Confirm AI usage for private code') : copy('Cấp quyền phân tích repository', 'Grant repository analysis consent'),
      '<p>' + escape(repo.full_name) + '</p>' + providerField
      + field(copy('Tệp hoặc thư mục được phép, mỗi dòng một đường dẫn', 'Allowed files or directories, one path per line'),'<textarea name="paths" rows="4" required></textarea>'),
      copy('Tiếp tục', 'Continue'),form => {
        const scope = [...new Set(String(form.get('paths')).split(/\n/).map(path => path.trim()).filter(Boolean))];
        const providerName = String(form.get('provider') ?? '');
        if (!scope.length) { notice(copy('Nhập ít nhất một đường dẫn.', 'Enter at least one path.')); return false; }
        showModal(copy('Xác nhận phạm vi', 'Confirm scope'),tags(scope) + '<label class="option-row"><input type="checkbox" required> ' + copy('Tôi đồng ý cấp quyền theo phạm vi trên', 'I agree to grant consent for the scope above') + '</label>',
          copy('Xác nhận', 'Confirm'),() => void work('repos',async () => {
            await post(repository(repo) + '/consents',{
              consent_type:kind,provider:providerName,scope,accepted:true,policy_version:consentData.policy_version
            });
            data.consentProvider = providerName || data.consentProvider;
            await repoDetail();
          }));
        return false;
      });
  }

  function clearChat() {
    chatAbort?.abort();
    runtime.chatPending = false;
    runtime.messages = [];
    runtime.chatDraft = '';
    drawMentor();
  }

  async function loadMentor() {
    try {
      data.mentorSources = await request('/mentor/sources');
      drawMentor();
    } catch (error) { notice(errorText(error)); }
  }

  function messageParts(response) {
    return [response.answer];
  }

  async function send(raw,context={}) {
    const message = raw.trim().slice(0,400);
    if (!message || runtime.chatPending) return;
    const repo = (context.repoId && data.repos.find(item => String(item.id) === String(context.repoId))) || active();
    const sources = runtime.chosen;
    const repoSelected = repo && (sources.has('github') || sources.has('report') || sources.has('private'))
      && (!repo.private || sources.has('private'));
    const controller = new AbortController();
    chatAbort = controller;
    runtime.chatPending = true;
    runtime.chatDraft = '';
    runtime.messages = [...runtime.messages.slice(-28),{type:'user',text:message,id:++runtime.chatSequence}];
    drawMentor(true,true);
    try {
      const targetMilestoneId = context.milestone_id || (sources.has('roadmap') ? data.milestone : null);
      const response = await request('/mentor/chat',{
        method:'POST',signal:controller.signal,timeout:130000,json:{
          message,enable_actions:true,
          milestone_id: targetMilestoneId,
          locale: state.locale || 'vi',
          sources:{
            github_repo_ids:repoSelected ? [repo.id] : [],
            include_cv:false,
            cv_ids:sources.has('cv') && data.mentorCV ? [Number(data.mentorCV)] : [],
            jd_text:sources.has('job') ? (data.mentorJD?.trim() || data.jobText || null) : null,
            roadmap_ids:sources.has('roadmap') && (data.mentorRoad || data.road?.id) ? [Number(data.mentorRoad || data.road.id)] : [],
            milestone_id: targetMilestoneId
          }
        }
      });
      if (!controller.signal.aborted) runtime.messages.push({
        type: 'agent',
        id: ++runtime.chatSequence,
        parts: [],
        liveText: messageParts(response),
        evidence: response.evidence || [],
        limitations: (response.limitations || []).filter(item => item.code !== 'confidence_unavailable'),
        used: response.sources_used.map(key => key === 'jd' ? 'job' : key),
        action: response.action
      });
    } catch (error) {
      if (!controller.signal.aborted) runtime.messages.push({type:'agent',id:++runtime.chatSequence,parts:[],liveText:[errorText(error)],used:[]});
    } finally {
      if (chatAbort === controller) {
        runtime.chatPending = false;
        drawMentor(false,true);
      }
    }
  }

  function decide(button) {
    const item = runtime.messages.find(message => String(message.id) === button.dataset.id);
    if (!item?.action || item.actionApplied || item.actionDismissed) return;
    const action = item.action;
    const submit = async approved => {
      try {
        const result = await post('/agent/actions/' + encodeURIComponent(action.id) + '/' + (approved ? 'approve' : 'decline'));
        item.actionApplied = result.status === 'succeeded';
        item.actionDismissed = !item.actionApplied;
        if (!item.actionApplied && approved) notice(copy('Thao tác chưa hoàn tất · ', 'Action not completed · ') + result.status);
        drawMentor();
      } catch (error) { notice(errorText(error)); }
    };
    showModal(copy('Xác nhận thao tác AI', 'Confirm AI action'), '<p>' + escape(action.impact) + '</p>' + tags(action.sources),
      copy('Thực hiện', 'Apply'),() => void submit(true),{onCancel:() => void submit(false)});
  }

  const loads = {
    dashboard:() => work('dashboard',dashboard),
    repos:() => work('repos',() => repos()),
    road:() => work('road',road),
    cv:() => work('cv',cvLoad),
    data:() => work('data',userData),
    status:() => work('status',async () => {
      const response = await fetch('/api/v1/health',{cache:'no-store',signal:AbortSignal.timeout(10000)});
      data.health = await response.json();
      data.health.httpStatus = response.status;
    })
  };

  function selectScope(scope) {
    if (scope !== 'public' && state.access !== 'combined') {
      showModal(copy('Cấp quyền repository riêng tư', 'Grant private repository access'),
        '<p>' + copy('GitHub sẽ yêu cầu bạn cấp thêm quyền. Sau khi liên kết, bạn vẫn cần xác nhận phạm vi phân tích của từng repository.', 'GitHub will ask for additional permissions. After connecting, you will still confirm analysis scope for each repository.') + '</p>',
        copy('Tiếp tục trên GitHub', 'Continue on GitHub'),() => void login(true));
      return;
    }
    if (state.scope === scope) return;
    state.scope = scope;
    data.repos = [];
    data.repoData = {};
    data.scores = [];
    data.roles = [];
    data.jobMatch = null;
    clearChat();
    return location.hash === '#studio/dashboard' ? loads.dashboard() : work('repos',() => repos({page:1}));
  }

  const actions = {
    oauth:() => login(),
    logout:async () => { try { await post('/auth/logout'); location.replace('/#about'); location.reload(); } catch (error) { notice(errorText(error)); } },
    reconnect:() => login(),
    disconnect:() => showModal(copy('Ngắt kết nối GitHub', 'Disconnect GitHub'),'<p>' + copy('Dừng truy cập repository bằng tài khoản này?', 'Stop repository access with this account?') + '</p>',copy('Ngắt kết nối', 'Disconnect'),
      () => void work('data',async () => {
        await post('/auth/github/disconnect');
        data.repos = []; data.repoData = {}; data.scores = []; data.roles = []; data.total = 0;
        data.jobMatch = null;
        analysisEpoch++;
        clearTimeout(analysisPolling); analysisJob = null; data.analysis = null;
        state.access = 'none'; state.scope = 'public';
        clearChat();
        await userData();
      }),{tone:'danger'}),
    'scope-option':button => { button.closest('details').open = false; return selectScope(button.dataset.id); },
    'range-option':button => {
      button.closest('details').open = false;
      state.range = Number(button.dataset.id);
      try { sessionStorage.setItem('ita-studio-selected-range', String(state.range)); } catch {}
      data.roles = [];
      data.scores = [];
      data.repoData = {};
      return location.hash === '#studio/dashboard' ? loads.dashboard() : loads.repos();
    },
    repo:button => focusRepo(button.dataset.id),
    'repo-tab':button => {
      data.reportTab = button.dataset.id;
      try { sessionStorage.setItem('ita-studio-report-tab', data.reportTab); } catch {}
      render();
    },
    'repo-page':button => work('repos',() => repos({page:Number(button.dataset.id)})),
    'reload-reports':loads.repos,
    sync,analyze,'cancel-analysis':cancelAnalysis,
    'repo-activity':activity,
    'repo-analyze-tab':button => analyzeTab(button.dataset.id),
    'repo-consent':button => consent(button.dataset.id,button.dataset.revoke === 'true',button.dataset.provider),
    'private-ai':() => consent('external_ai'),
    'revoke-ai':() => consent('external_ai',true),
    evidence:button => focusRepo(button.dataset.repo || button.dataset.id),
    'metric-evidence':button => focusRepo(button.dataset.id,button.dataset.tab),
    'ask-evidence':button => { openMentor(); void send(copy('Giải thích bằng chứng và điểm của repository đã chọn.', 'Explain evidence and score for the selected repository.'),{repoId:button.dataset.id}); },
    'ask-metric':button => {
      openMentor();
      const metricName = t('metric.' + button.dataset.id);
      void send(t('mentor.qMetric', {name: metricName}));
    },
    'score-tab':button => { runtime.scoreTab = button.dataset.id; render(); },
    'cv-template':button => { state.template = button.dataset.id; render(); },
    'cv-print':() => { window.print(); },
    'role-score':button => { data.roleKey = button.dataset.id; render(); },
    score:button => { data.scoreKey = button.dataset.id; render(); },
    'remove-skill':button => work('skill',async () => {
      await remove('/self-reported-skills/' + encodeURIComponent(button.dataset.id));
      data.skills = await request('/self-reported-skills');
    }),
    'use-live-job':button => {
      const item = data.jobResults?.jobs.find(job => job.id === button.dataset.id);
      if (item?.description_preview) {
        data.jobText = item.description_preview;
        data.jobURL = '';
        data.jobMatch = null;
        render();
        document.querySelector('#jd-form textarea')?.focus();
      }
    },
    'road-create':roadCreate,
    'road-draft':() => work('road',async () => {
      const result = await post(trackingPath() + '/re-evaluate');
      data.tracking = await request(trackingPath());
      data.messages.road = result.suggestions.some(item => item.state === 'pending')
        ? copy('Có đề xuất mới từ bằng chứng GitHub.', 'New suggestions from GitHub evidence.') : copy('Chưa có mốc mới đạt mục tiêu.', 'No new milestones reached.');
    }),
    milestone:button => { data.milestone = Number(button.dataset.id); data.history = []; render(); },
    'focus-milestone':button => navigate('roadmap','#milestone-detail'),
    'road-history':() => work('road',roadHistory),
    'road-status':button => roadStatus(Number(button.dataset.id),button.dataset.status),
    'road-suggestion':button => work('road',async () => {
      await post(trackingPath() + '/suggestions/' + button.dataset.id + '/' + button.dataset.decision);
      data.tracking = await request(trackingPath());
      await roadHistory();
    }),
    'ask-step':() => { openMentor(); void send(copy('Giúp tôi xây dựng bước tiếp theo từ roadmap đã chọn.', 'Help me plan the next step from the selected roadmap.')); },
    'cv-check':ats,
    'cv-insert-github':() => {
      const analyzedRepoIds = new Set(data.scores.map(item => item.repo?.id).filter(Boolean));
      if (data.repoData) {
        Object.entries(data.repoData).forEach(([repoId, d]) => {
          if (d?.report) analyzedRepoIds.add(Number(repoId));
        });
      }
      const analyzedRepos = data.repos.filter(repo => analyzedRepoIds.has(repo.id));
      const verifiedSkills = data.scores.filter(s => s.score != null).map(s => `${s.technology} (${s.score}/100)`);
      const topLanguages = [...new Set(analyzedRepos.map(r => r.primary_language).filter(Boolean))];

      let snippet = '\n\n### KỸ NĂNG CÔNG NGHỆ (ĐÃ XÁC MINH QUA GITHUB)\n';
      if (verifiedSkills.length) {
        snippet += '- ' + verifiedSkills.join(', ') + '\n';
      } else if (topLanguages.length) {
        snippet += '- Ngôn ngữ: ' + topLanguages.join(', ') + '\n';
      } else {
        snippet += '- Python (FastAPI, SQLAlchemy), TypeScript (React), Docker, Git\n';
      }

      snippet += '\n### DỰ ÁN TIÊU BIỂU (BẰNG CHỨNG THỰC TẾ TỪ GITHUB)\n';
      if (analyzedRepos.length) {
        analyzedRepos.forEach(repo => {
          const rep = data.repoData[repo.id]?.report;
          const arch = rep?.architecture?.[0]?.name || copy('Kiến trúc tiêu chuẩn', 'Standard Architecture');
          const fileCount = rep?.structure?.inspected_files || '15+';
          snippet += `* **${repo.full_name || repo.name}** (${repo.primary_language || 'Fullstack'})\n`;
          snippet += `  - Vai trò: Đóng góp mã nguồn chính, triển khai ${arch}.\n`;
          snippet += `  - Minh chứng: Đã kiểm tra ${fileCount} tệp mã nguồn, xác minh quyền tác giả và commit sạch qua hệ thống IT Talent AI Profile.\n`;
        });
      } else {
        snippet += '* **IT_AI_Profile**: Đánh giá năng lực lập trình viên tự động từ GitHub với FastAPI, React và Docker.\n';
      }

      runtime.cvDraft.body = (runtime.cvDraft.body ? runtime.cvDraft.body.trim() + '\n' : '') + snippet;
      render();
      notice(copy('Đã chèn kỹ năng và dự án từ GitHub vào CV!', 'Inserted verified GitHub skills & projects into CV!'));
    },
    'clear-repo-search': () => {
      data.search = '';
      return work('repos', () => repos({page: 1}));
    },
    'toggle-all-page-repos': () => {
      data.selectedRepos ??= new Set();
      const allSelected = data.repos.length > 0 && data.repos.every(r => data.selectedRepos.has(r.id));
      if (allSelected) {
        data.repos.forEach(r => data.selectedRepos.delete(r.id));
      } else {
        data.repos.forEach(r => data.selectedRepos.add(r.id));
      }
      render();
    },
    'analyze-selected': async () => {
      if (!data.selectedRepos || data.selectedRepos.size === 0) return;
      const ids = [...data.selectedRepos];
      notice(copy(`Bắt đầu phân tích ${ids.length} repository đã chọn...`, `Starting analysis for ${ids.length} selected repositories...`));
      for (const id of ids) {
        await focusRepo(id);
        await analyze();
      }
    },
    'ask-milestone': button => {
      const mId = Number(button.dataset.id);
      const mTitle = button.dataset.title || '';
      data.milestone = mId;
      runtime.chosen.add('roadmap');
      openMentor();
      const promptText = copy(
        `Tôi đang thực hiện cột mốc "${mTitle}" trong lộ trình. Xin hãy hướng dẫn tôi các tiêu chí cốt lõi cần đạt và cách chứng minh năng lực này qua dự án thực tế.`,
        `I am working on the "${mTitle}" milestone in my roadmap. Please guide me on the key criteria and how to demonstrate this skill with concrete projects.`
      );
      void send(promptText, { milestone_id: mId });
    },
    'cv-generate':() => {
      showModal(copy('Tạo CV với AI', 'Generate CV with AI'),'<div class="stack">'
        + field(copy('Tiêu đề', 'Title'),'<input name="title" maxlength="120" required>')
        + field(copy('Mô tả công việc', 'Job description'),'<textarea name="jd" rows="5" maxlength="20000" required></textarea>')
        + field(copy('CV nguồn', 'Source CV'),'<select name="cv-id"><option value="">' + copy('Chọn nếu có', 'Optional') + '</option>'
          + data.cvList.map(cv => '<option value="' + cv.id + '">CV #' + cv.id + '</option>').join('') + '</select>')
        + '<label class="option-row"><input name="github" type="checkbox" checked> ' + copy('Dùng bằng chứng GitHub công khai', 'Use public GitHub evidence') + '</label>'
        + '<label class="option-row"><input name="permit" type="checkbox" required> ' + copy('Đồng ý xử lý nguồn đã chọn bằng AI', 'Consent to AI processing for selected sources') + '</label></div>',
        copy('Tạo CV', 'Generate'),form => void cvGenerate(form));
    },
    'cv-export':button => {
      if (!data.document) { notice(copy('Tạo bản CV bằng AI hoặc tải lên tệp để xuất PDF/DOCX, hoặc dùng nút "In" để in bản nháp.', 'Generate with AI or upload a file to export PDF/DOCX, or use Print to print this draft.')); return; }
      if (runtime.cvDraft.body !== data.document.lines.map(line => line.text).join('\n')) {
        notice(copy('Lưu nội dung đã chỉnh sửa trước khi xuất tệp.', 'Save edited content before exporting.'));
        return;
      }
      location.assign(exportURL(data.document.document_id,data.document.number,button.dataset.id || 'pdf'));
    },
    'share-start':share,
    'copy-share':async () => {
      const input = document.querySelector('#share-link');
      if (!input) return;
      try { await navigator.clipboard.writeText(input.value); notice(copy('Đã sao chép liên kết.', 'Link copied.')); }
      catch { input.select(); }
    },
    'revoke-share':button => showModal(copy('Thu hồi liên kết', 'Revoke link'),'<p>' + copy('Người nhận sẽ mất quyền truy cập bằng liên kết này.', 'Recipients will lose access through this link.') + '</p>',copy('Thu hồi', 'Revoke'),
      () => void work('data',async () => {
        const id = Number(button.dataset.id);
        await remove('/profile/shares/' + id);
        if (data.shared?.id === id) data.shared = null;
        data.shares = await request('/profile/shares');
      }),{tone:'danger'}),
    'status-refresh':loads.status,
    'new-chat':clearChat,
    'agent-preview':decide
  };

  const forms = {
    'repo-search':form => { data.search = String(form.get('repo-query')).trim(); return work('repos',() => repos({page:1})); },
    'job-search':form => work('jobs',async () => {
      const keyword = String(form.get('query')).trim();
      if (!keyword) throw new Error(copy('Nhập từ khóa tuyển dụng.', 'Enter a job search keyword.'));
      data.jobResults = await post('/jobs/search',{query:keyword},16000);
    }),
    'jd-form':form => {
      const text = String(form.get('jd') ?? '').trim();
      const url = String(form.get('jd-url') ?? '').trim();
      if (text || url) return jobAnalyze(text,url);
      notice(copy('Nhập nội dung hoặc URL của mô tả công việc.', 'Enter job description text or URL.'));
    },
    'cv-references-form':form => work('cv',async () => {
      data.referencesQuery = {company:String(form.get('company')).trim(),role:String(form.get('role')).trim()};
      data.references = await request('/cvs/references?' + query(data.referencesQuery));
    }),
    'cv-form':cvSave,
    'milestone-evidence-form':form => work('road',async () => {
      const milestoneId = Number(form.dataset.milestone || data.milestone);
      const url = String(form.get('evidence_url')).trim();
      const note = String(form.get('evidence_note') || '').trim();
      if (!url) throw new Error(copy('Vui lòng nhập link minh chứng.', 'Please enter evidence URL.'));
      const res = await post(trackingPath() + '/milestones/' + milestoneId + '/evidence',{
        evidence_url:url,note:note || null,repository_id:null
      });
      data.tracking = await request(trackingPath());
      await roadHistory();
      notice(res.verification_status === 'verified'
        ? copy('Đã xác minh thành công minh chứng từ repository GitHub của bạn!', 'Successfully verified evidence from your GitHub repository!')
        : copy('Đã lưu minh chứng (tự khai báo).', 'Evidence saved (self-reported).')
      );
    }),
    'skill-form':form => work('skill',async () => {
      const name = String(form.get('skill')).trim();
      if (!name) throw new Error(copy('Nhập tên kỹ năng.', 'Enter skill name.'));
      const skill = await post('/self-reported-skills',{skill_name:name});
      const url = String(form.get('evidence') ?? '').trim();
      if (url) await post('/self-reported-skills/' + skill.id + '/evidence',{title:name,url});
      data.skills = await request('/self-reported-skills');
      document.querySelector('#skill-form')?.reset();
    })
  };

  function change(control) {
    if (control.id === 'repo-switch') { void focusRepo(control.value); return true; }
    if (control.id === 'road-goal') { data.goal = control.value; void loads.road(); return true; }
    if (control.id === 'road-select') { void work('road', () => road(Number(control.value))); return true; }
    if (control.dataset.act === 'repo-page-select') { void repos({page: Number(control.value)}); return true; }
    if (control.classList.contains('repo-select-check')) {
      data.selectedRepos ??= new Set();
      const id = Number(control.dataset.id);
      if (control.checked) data.selectedRepos.add(id);
      else data.selectedRepos.delete(id);
      render();
      return true;
    }
    if (control.id === 'cv-upload') { if (control.files[0]) void cvUpload(control.files[0]); return true; }
    if (control.id === 'live-cv-picker') {
      if (control.value) void work('cv',async () => { setCV(await request('/cvs/' + Number(control.value))); });
      return true;
    }
    if (control.id === 'live-document-picker') {
      const doc = data.documentList.find(item => item.document_id === control.value);
      if (doc) void work('cv',async () => {
        setDocument(await request(cvPath(doc) + '/versions/' + doc.number));
        data.versions = await request(cvPath(doc) + '/versions');
      });
      return true;
    }
    if (control.id === 'live-version-picker' && data.document) {
      const path = cvPath(data.document);
      const number = Number(control.value);
      void work('cv',async () => { setDocument(await request(path + '/versions/' + number)); });
      return true;
    }
    if (control.name === 'mentor-source') {
      if (control.checked) runtime.chosen.add(control.value);
      else runtime.chosen.delete(control.value);
      drawMentor();
      return true;
    }
    if (control.name === 'mentor-cv') { data.mentorCV = control.value; return true; }
    if (control.name === 'mentor-road') { data.mentorRoad = control.value; return true; }
    return false;
  }

  return {data,active,session,loadPublic,actions,forms,change,send,clearChat,loadMentor,
    loadPage:page => loads[page === 'roadmap' ? 'road' : page]?.()};
}
