import {toast} from './common.js';
document.getElementById('cv-rewrite').onclick=()=>{const input=document.getElementById('cv-input').value.trim();document.getElementById('cv-output').textContent=input?'Suggested structure: “Designed and delivered [feature] using [technology], improving [measurable outcome].” Add your actual metrics; do not invent results.':'Enter a CV bullet first.'};
