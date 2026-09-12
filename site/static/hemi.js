/* ilsvotentquoi.fr — hémicycle nominatif, tableau des députés et bascule daltoniens.
   Lit les données inscrites dans la page (data-vote, data-date) et /api/deputes.json. */
(function(){
  const ORDER=["LFI","GDR","ECO","SOC","LIOT","DEM","EPR","HOR","DR","UDR","RN","NI"];
  const CFG=window.IVQ||{}; const COL_AN=CFG.colors||{}; const GN=CFG.names||{};
  const COL_CVD={LFI:"#D55E00",GDR:"#8C3A00",ECO:"#009E73",SOC:"#CC79A7",LIOT:"#F0E442",DEM:"#E69F00",EPR:"#56B4E9",HOR:"#9AD3F2",DR:"#0072B2",UDR:"#004C7A",RN:"#000000",NI:"#999999"};
  let COL=COL_AN;
  try{ if(localStorage.getItem("ivq-cvd")==="1") COL=COL_CVD; }catch(e){}
  const VL={P:"a voté pour",C:"a voté contre",A:"s'est abstenu·e",N:"n'a pas pris part au vote",".":"absent·e"};
  const LBL={P:"Pour",C:"Contre",A:"Abstention",N:"Non-votant",".":"Absent"};
  const SEATS=(()=>{ const rows=11,n=577,CX=300,CY=290,r0=95,r1=280,seats=[],rad=[];
    for(let i=0;i<rows;i++) rad.push(r0+(r1-r0)*i/(rows-1));
    const tot=rad.reduce((a,b)=>a+b,0); let left=n;
    rad.forEach((r,i)=>{ const k=i===rows-1?left:Math.round(n*r/tot); left-=k; for(let j=0;j<k;j++){ const a=Math.PI*(k===1?.5:j/(k-1)); seats.push({x:CX-Math.cos(a)*r,y:CY-Math.sin(a)*r,a}); } });
    seats.sort((p,q)=>p.a-q.a); return seats; })();
  const esc=s=>String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;");
  function groupAt(dep,date){ let g=dep.g[0][1]; for(const [d,gi] of dep.g){ if(d<=date) g=gi; } return ORDER[g]; }

  function people(deps,vote,date){
    const out=[];
    for(let i=0;i<deps.length;i++){ const d=deps[i], v=vote[i]||"."; if(v==="."&&!(d.f&&d.l&&d.f<=date&&date<=d.l)) continue; out.push({i,d,v,g:groupAt(d,date)}); }
    out.sort((a,b)=>ORDER.indexOf(a.g)-ORDER.indexOf(b.g)||a.d.nom.localeCompare(b.d.nom));
    return out;
  }
  function hemiSVG(list){
    const dots=list.slice(0,SEATS.length).map((p,k)=>{ const st=SEATS[k],c=COL[p.g],x=st.x.toFixed(1),y=st.y.toFixed(1);
      if(p.v==="P") return `<circle cx="${x}" cy="${y}" r="6.2" fill="${c}" data-i="${p.i}" data-v="P" data-g="${p.g}"/>`;
      if(p.v==="C") return `<g data-i="${p.i}" data-v="C" data-g="${p.g}"><circle cx="${x}" cy="${y}" r="6.2" fill="${c}"/><path d="M${x-2.6} ${y-2.6}l5.2 5.2M${x+2.6} ${y-2.6}l-5.2 5.2" stroke="#fff" stroke-width="1.7" stroke-linecap="round"/></g>`;
      if(p.v==="A") return `<circle cx="${x}" cy="${y}" r="6.2" fill="url(#h-${p.g})" data-i="${p.i}" data-v="A" data-g="${p.g}"/>`;
      return `<circle cx="${x}" cy="${y}" r="6.2" fill="#fff" stroke="${c}" stroke-width="1.2" data-i="${p.i}" data-v="${p.v}" data-g="${p.g}"/>`; }).join("");
    return `<svg class="hemi" viewBox="0 0 600 300" role="img" aria-label="Hémicycle : vote de chaque député"><defs>${ORDER.map(g=>`<pattern id="h-${g}" patternUnits="userSpaceOnUse" width="4" height="4" patternTransform="rotate(45)"><rect width="4" height="4" fill="${COL[g]}"/><rect width="2" height="4" fill="#fff" opacity=".75"/></pattern>`).join("")}</defs>${dots}</svg>`;
  }
  function table(list){
    const rows=list.map(p=>`<tr data-n="${esc(p.d.nom.toLowerCase())}" data-g="${p.g}" data-v="${p.v}"><td><a href="/depute/${p.d.slug}-${p.d.id}/">${esc(p.d.nom)}</a></td><td>${p.d.dept?esc(p.d.dept)+(p.d.circo?" ("+p.d.circo+"ᵉ)":""):""}</td><td><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${COL[p.g]};margin-right:6px"></i>${p.g}</td><td class="v">${LBL[p.v]}</td></tr>`).join("");
    return `<input class="search" type="search" placeholder="Chercher un député, un département, un groupe" aria-label="Filtrer"><table class="deps"><thead><tr><th data-k="n">Député·e</th><th>Circonscription</th><th data-k="g">Groupe</th><th data-k="v">Vote</th></tr></thead><tbody>${rows}</tbody></table>`;
  }
  function tip(){
    const t=document.createElement("div"); t.className="tip"; t.hidden=true; document.body.appendChild(t);
    document.addEventListener("mousemove",e=>{ const el=e.target.closest&&e.target.closest("[data-i]"); if(!el){t.hidden=true;return;}
      const d=window.__deps[+el.dataset.i], g=el.dataset.g, v=el.dataset.v;
      t.innerHTML=`<b>${esc(d.nom)}</b>${d.dept?`<span style="color:var(--muted)">${esc(d.dept)}${d.circo?", "+d.circo+"ᵉ circ.":""}</span>`:""}<div class="g"><i style="background:${COL[g]}"></i>${GN[g]||g}</div><div class="v">${VL[v]||VL["."]}</div>`;
      t.hidden=false; t.style.left=Math.min(e.clientX+14,window.innerWidth-280)+"px"; t.style.top=(e.clientY+14)+"px"; });
  }
  function init(){
    const slot=document.querySelector("[data-vote]"); if(!slot) return;
    fetch("/api/deputes.json").then(r=>r.json()).then(deps=>{
      window.__deps=deps;
      const list=people(deps,slot.dataset.vote,slot.dataset.date);
      slot.innerHTML=hemiSVG(list);
      const tb=document.querySelector("#deps"); if(tb){ tb.innerHTML=table(list);
        const inp=tb.querySelector(".search"); inp.addEventListener("input",()=>{ const q=inp.value.toLowerCase(); tb.querySelectorAll("tbody tr").forEach(tr=>{ tr.hidden=!(tr.textContent.toLowerCase().includes(q)); }); });
        tb.querySelectorAll("th[data-k]").forEach(th=>th.addEventListener("click",()=>{ const k=th.dataset.k, body=tb.querySelector("tbody"); [...body.rows].sort((a,b)=>(a.dataset[k]||"").localeCompare(b.dataset[k]||"")).forEach(r=>body.appendChild(r)); })); }
      tip();
    });
    const cvd=document.querySelector("#cvd"); if(cvd){ cvd.checked=COL===COL_CVD; cvd.addEventListener("change",()=>{ try{localStorage.setItem("ivq-cvd",cvd.checked?"1":"0");}catch(e){} location.reload(); }); }
    document.querySelectorAll("[data-share]").forEach(b=>b.addEventListener("click",async()=>{ const url=location.href, title=document.title;
      if(navigator.share){ try{ await navigator.share({title,url}); }catch(e){} } else { await navigator.clipboard.writeText(url); b.textContent="Lien copié"; } }));
  }
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",init); else init();
})();
