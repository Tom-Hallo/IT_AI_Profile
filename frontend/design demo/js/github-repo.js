import {toast} from './common.js';
document.getElementById('repo-search').addEventListener('input',e=>{document.querySelectorAll('.repo-item').forEach(x=>x.classList.toggle('hidden',!x.textContent.toLowerCase().includes(e.target.value.toLowerCase())))});
