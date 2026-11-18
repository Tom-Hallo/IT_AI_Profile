/** Real WebGL hero, Three.js r0.169.0. No bundler required. CDN connection required. */
const stage = document.getElementById('talent-three-stage');
const canvas = document.getElementById('talent-three-canvas');
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const finePointer = matchMedia('(pointer: fine)');
if (stage && canvas) {
  try {
    const THREE = await import('https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js');
    const renderer = new THREE.WebGLRenderer({canvas,alpha:true,antialias:true,powerPreference:'low-power'});
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35,1,.1,100);
    camera.position.set(0,0,9.4);
    const group = new THREE.Group(); scene.add(group);
    scene.add(new THREE.AmbientLight(0xffffff,1.2));
    const key = new THREE.PointLight(0xc7ffae,90); key.position.set(-3,4,6); scene.add(key);
    const rim = new THREE.PointLight(0x3b9f8b,65); rim.position.set(4,-2,-3); scene.add(rim);
    const core = new THREE.Mesh(new THREE.IcosahedronGeometry(1.48,5),new THREE.MeshPhysicalMaterial({color:0x205a43,metalness:.55,roughness:.23,clearcoat:1,clearcoatRoughness:.12,flatShading:false}));
    group.add(core);
    const wire = new THREE.Mesh(new THREE.IcosahedronGeometry(1.52,2),new THREE.MeshBasicMaterial({color:0xa8edaa,wireframe:true,transparent:true,opacity:.14,depthWrite:false})); group.add(wire);
    const rings=[];
    for(let i=0;i<3;i++){
      const ring = new THREE.Mesh(new THREE.TorusGeometry(2.18+i*.2,.012+i*.004,8,180),new THREE.MeshBasicMaterial({color:i===1?0x80d3c1:0xb4df9c,transparent:true,opacity:.52,depthWrite:false}));
      ring.rotation.set(.9+i*.7,.4+i*.75,i*.6); group.add(ring); rings.push(ring);
    }
    // Deterministic particle halo: no external models or texture downloads.
    const count=320, positions=new Float32Array(count*3);
    for(let i=0;i<count;i++){
      const a=i*2.399963229728653, y=1-2*(i+.5)/count, r=Math.sqrt(1-y*y),radius=2.75+(i%7)*.085;
      positions[3*i]=Math.cos(a)*r*radius;positions[3*i+1]=y*radius;positions[3*i+2]=Math.sin(a)*r*radius;
    }
    const geometry=new THREE.BufferGeometry(); geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));
    const particles=new THREE.Points(geometry,new THREE.PointsMaterial({color:0xb9f4b1,size:.027,transparent:true,opacity:.78,sizeAttenuation:true,depthWrite:false})); group.add(particles);
    let width=0,height=0;
    const resize=()=>{const r=stage.getBoundingClientRect();width=Math.max(1,r.width);height=Math.max(1,r.height);renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();};
    const ro=new ResizeObserver(resize);ro.observe(stage);resize();
    const target={x:0,y:0};
    const onPointer=e=>{if(!finePointer.matches)return;const r=stage.getBoundingClientRect();target.y=((e.clientX-r.left)/r.width-.5)*.65;target.x=((e.clientY-r.top)/r.height-.5)*.5;};
    stage.addEventListener('pointermove',onPointer);
    stage.addEventListener('pointerleave',()=>{target.x=0;target.y=0;});
    let visible=true,raf=0;
    const io=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible&&!raf)raf=requestAnimationFrame(frame);});io.observe(stage);
    const clock=new THREE.Clock();
    function frame(){raf=0;if(!visible||document.hidden)return;const t=clock.getElapsedTime();group.rotation.x+=(target.x-group.rotation.x)*.035;group.rotation.y+=(target.y-group.rotation.y)*.035;
      if(!reduced.matches){core.rotation.y=t*.10;wire.rotation.y=-t*.07;rings[0].rotation.z=t*.13;rings[1].rotation.y=t*.11;rings[2].rotation.x=t*.09;particles.rotation.y=t*.018;}
      renderer.render(scene,camera);raf=requestAnimationFrame(frame);
    }
    const visibility=()=>{if(!document.hidden&&visible&&!raf)raf=requestAnimationFrame(frame)};
    document.addEventListener('visibilitychange',visibility);
    renderer.render(scene,camera);
    stage.classList.add('three-ready');
    if(!reduced.matches)raf=requestAnimationFrame(frame);
    // Release GPU resources on navigation.
    addEventListener('pagehide',()=>{cancelAnimationFrame(raf);ro.disconnect();io.disconnect();stage.removeEventListener('pointermove',onPointer);document.removeEventListener('visibilitychange',visibility);geometry.dispose();core.geometry.dispose();wire.geometry.dispose();rings.forEach(r=>{r.geometry.dispose();r.material.dispose()});core.material.dispose();wire.material.dispose();particles.material.dispose();renderer.dispose();},{once:true});
  } catch(err) {
    console.warn('Three.js unavailable; keeping the original CSS 3D hero.',err);
  }
}
