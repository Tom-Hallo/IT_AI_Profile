import {t} from './i18n.js';

export function codeReference(repo) {
  return {
    repoId:repo.id,
    file:repo.file,
    commit:repo.commit,
    start:repo.startLine,
    end:repo.startLine + repo.code.length - 1
  };
}

export function matchesCodeReference(repo,reference) {
  if (!repo || !reference) return false;
  const current = codeReference(repo);
  return Object.keys(current).every(key => current[key] === reference[key]);
}

export function codeReferenceLabel({file,start,end}) {
  return file + ' · ' + t('repos.codeLines',{start,end});
}
