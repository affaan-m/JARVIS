import { useState, useEffect, useRef, useCallback } from "react";

const BW=1100,BH=680,GW=172,GH=112,BDW=215,BDH=155,FR=14;
const ZM=[0.48,1,1.65];
const CAM_W=280,CAM_H=175,CAM_PAD=18;
const CAM_ZONE={x:BW-CAM_W-CAM_PAD-10,y:CAM_PAD-10,w:CAM_W+30,h:CAM_H+30};

const PAPERS=[
  {bg:"linear-gradient(155deg,#f5e6d0,#ede0cc 40%,#e8d6be)",bd:"#c9b89a"},
  {bg:"linear-gradient(155deg,#f0f2f4,#e8eaed 40%,#eef0f2)",bd:"#c8ccd2"},
  {bg:"linear-gradient(155deg,#e8d5a3,#e0cc98 40%,#d9c48e)",bd:"#bfad7a"},
];

const SRCS=[
  {nm:"LinkedIn Profile",tp:"SOCIAL",sn:"Software engineer at Google, previously at Meta. 500+ connections with notable defense industry ties across the tech sector."},
  {nm:"County Court Records",tp:"PUBLIC RECORD",sn:"No criminal records found across federal and state databases. One civil filing from 2019 — resolved."},
  {nm:"TechCrunch Feature",tp:"MEDIA",sn:"Featured in Series A funding coverage. Company valued at $12M with Andreessen Horowitz investors."},
  {nm:"SEC Corporate Filin,tp:"CORPORATE",sn:"Listed as board director for three registered LLCs. Two incorporated in Delaware, one in Nevada."},
  {nm:"IEEE Research Paper",tp:"ACADEMIC",sn:"Co-authored neural architecture optimization paper. Cited 340 times. Collaborators from MIT and Stanford."},
  {nm:"Property Deed Record",tp:"PUBLIC RECORD",sn:"Residential property in Austin, TX acquired 2021. Estimated value $870K. Secondary property in Aspen, CO."},
  {nm:"X / Twitter Profile",tp:"SOCIAL",sn:"12.4K followers. Active in AI policy discourse. Multiple interactions with defense procurement officials."},
  {nm:"USPTO Patent Filing",tp:"IP RECORD",sn:"Two patents filed for ML-based optimization in signal processing. Assigned to Vertex Systems Inc."},
];

const PERSON={nm:"ALEX MERCER",sm:"High-priority intelligence target with cross-sector ties spanning Silicon Valley tech firms and defense contracting networks. Multiple corporate entities registered under associated aliases. Financial footprint suggests diversified asset portfolio with international exposure. Digital presence indicates active engagement with government and military procurement channels. Further investigation recommended across SIGINT and HUMINT channels."};

function catenary(x1,y1,x2,y2){
  const d=Math.hypot(x2-x1,y2-y1),sag=Math.min(d*.25,80)+25;
  return`M ${x1} ${y1} Q ${(x1+x2)/2} ${Math.max(y1,y2)+sag} ${x2} ${y2}`;
}

function inCamZone(x,y,w,h){
  return!(x+w<CAM_ZONE.x||x>CAM_ZONE.x+CAM_ZONE.w||y+h<CAM_ZONE.y||y>CAM_ZONE.y+CAM_ZONE.h);
}

function randPos(ex,bp){
  const m=35;
  for(let i=0;i<120;i++){
    const x=m+Math.random()*(BW-GW-m*2),y=55+Math.random()*(BH-GH-90);
    if(inCamZone(x,y,GW,GH))continue;
    let ok=true;
    if(bp&&Math.abs(bp.x+BDW/2-x-GW/2)<(BDW+GW)/2+22&&Math.abs(bp.y+BDH/2-y-GH/2)<(BDH+GH)/2+22)ok=false;
    for(const d of ex)if(Math.abs(d.x-x)<GW+14&&Math.abs(d.y-y)<GH+14){ok=false;break;}
    if(ok)return{x,y};
  }
  return{x:m+Math.random()*(BW-GW-m*2),y:200+Math.random()*(BH-GH-250)};
}

function genCurl(){
  if(Math.random()<0.45)return null;
  const corners=["tl","tr","bl","br"];
  return{corner:corners[Math.floor(Math.random()*4)],amt:2+Math.random()*5};
}

const TEXTURES=[
  ()=>(<>
    <div style={{position:"absolute",inset:0,borderRadius:2,pointerEvents:"none",opacity:.4,
      backgroundImage:`url("data:image/svg+xml,%3Csvg width='200' height='200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='g'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23g)' opacity='.035'/%3E%3C/svg%3E")`,
      backgroundSize:"200px 200px"}}/>
    <div style={{position:"absolute",inset:0,borderRadius:2,pointerEvents:"none",
      background:"repeating-linear-gradient(0deg,transparent,transparent 2.5px,rgba(0,0,0,.006) 2.5px,rgba(0,0,0,.006) 3px)"}}/>
  </>),
  ()=>(<>
    <div style={{position:"absolute",inset:0,borderRadius:2,pointerEvents:"none",
      background:"radial-gradient(ellipse at 50% 50%,transparent 55%,rgba(160,130,80,.08) 100%)"}}/>
    <div style={{position:"absolute",top:0,left:0,right:0,height:"15%",borderRadius:"2px 2px 0 0",pointerEvents:"none",
      background:"linear-gradient(180deg,rgba(180,155,100,.06),transparent)"}}/>
    <div style={{position:"absolute",bottom:0,left:0,right:0,height:"15%",borderRadius:"0 0 2px 2px",pointerEvents:"none",
      background:"linear-gradient(0deg,rgba(140,115,70,.07),transparent)"}}/>
    {[{t:"12%",l:"68%",w:3,h:3,o:.04},{t:"55%",l:"15%",w:5,h:4,o:.03},{t:"78%",l:"82%",w:4,h:3,o:.035}].map((s,j)=>(
      <div key={j} style={{position:"absolute",top:s.t,left:s.l,width:s.w,height:s.h,
        borderRadius:"50%",background:`rgba(120,100,60,${s.o})`,pointerEvents:"none"}}/>
    ))}
  </>),
  ()=>(<>
    <div style={{position:"absolute",top:"35%",left:0,right:0,height:1,pointerEvents:"none",
      background:"linear-gradient(90deg,transparent 5%,rgba(0,0,0,.03) 20%,rgba(0,0,0,.045) 50%,rgba(0,0,0,.03) 80%,transparent 95%)"}}/>
    <div style={{position:"absolute",top:0,bottom:0,left:"42%",width:1,pointerEvents:"none",
      background:"linear-gradient(180deg,transparent 8%,rgba(0,0,0,.025) 25%,rgba(0,0,0,.04) 50%,rgba(0,0,0,.025) 75%,transparent 92%)"}}/>
    <div style={{position:"absolute",top:"35%",left:"42%",width:6,height:6,pointerEvents:"none",
      background:"radial-gradient(circle,rgba(0,0,0,.04),transparent)"}}/>
  </>),
];

const CurlOverlay=({curl})=>{
  if(!curl)return null;
  const{corner:c,amt}=curl;
  const gDir=c==="bl"?"to top right":c==="br"?"to top left":c==="tl"?"to bottom right":"to bottom left";
  const pos={};
  if(c.includes("t"))pos.top=0;else pos.bottom=0;
  if(c.includes("l"))pos.left=0;else pos.right=0;
  const br=c==="tl"?"0 0 8px 0":c==="tr"?"0 0 0 8px":c==="bl"?"0 8px 0 0":"8px 0 0 0";
  return(
    <div style={{position:"absolute",...pos,width:amt*5,height:amt*5,pointerEvents:"none",zIndex:3,
      borderRadius:br,
      background:`linear-gradient(${gDir},rgba(0,0,0,.06) 0%,rgba(0,0,0,.02) 40%,transparent 70%)`,
      boxShadow:`inset ${c.includes("r")?"-":""}1px ${c.includes("b")?"-":""}1px 3px rgba(0,0,0,.04)`}}/>
  );
};

const PushPin=({red})=>{
  const hc=red
    ?{top:"#ef4444",mid:"#dc2626",bot:"#991b1b",rim:"#881616",hi:"rgba(255,200,200,.5)"}
    :{top:"#60a5fa",mid:"#3b82f6",bot:"#1e40af",rim:"#1a3580",hi:"rgba(200,220,255,.5)"};
  return(
    <div style={{position:"absolute",top:-13,left:"50%",transform:"translateX(-50%)",zIndex:25,width:24,height:28,pointerEvents:"none"}}>
      {/* Cast shadow */}
      <div style={{position:"absolute",top:8,left:6,width:18,height:10,borderRadius:"50%",
        background:"radial-gradient(ellipse,rgba(0,0,0,.25),transparent 70%)",
        transform:"skewX(-8deg)",filter:"blur(2px)"}}/>
      {/* Contact shadow */}
      <div style={{position:"absolute",top:5,left:4,width:16,height:8,borderRadius:"50%",
        background:"radial-gradient(ellipse,rgba(0,0,0,.32),transparent 60%)",filter:"blur(1.5px)"}}/>
      {/* Needle shaft */}
      <div style={{position:"absolute",top:15,left:"50%",transform:"translateX(-50%)",
        width:2,height:11,
        background:"linear-gradient(180deg,#b0b8c4,#8a929e,#6b7280)",
        borderRadius:"0 0 1px 1px",boxShadow:"1px 0 2px rgba(0,0,0,.15)"}}/>
      <div style={{position:"absolute",top:24,left:"50%",transform:"translateX(-50%)",
        width:1.5,height:3,background:"linear-gradient(180deg,#6b7280,#4b5563)",borderRadius:"0 0 1px 1px"}}/>
      {/* Pin head — flat cylinder shape */}
      <div style={{position:"absolute",top:0,left:"50%",transform:"translateX(-50%)",
        width:20,height:13,borderRadius:"10px/7px",overflow:"hidden",
        border:`1.5px solid ${hc.rim}`,
        boxShadow:`0 3px 6px rgba(0,0,0,.35),0 1px 2px rgba(0,0,0,.2)`}}>
        {/* Top face gradient */}
        <div style={{position:"absolute",inset:0,
          background:`linear-gradient(170deg,${hc.top} 0%,${hc.mid} 35%,${hc.bot} 100%)`}}/>
        {/* Rim lip at bottom */}
        <div style={{position:"absolute",bottom:0,left:0,right:0,height:3,
          background:`linear-grient(180deg,transparent,rgba(0,0,0,.2))`}}/>
        {/* Specular highlight */}
        <div style={{position:"absolute",top:2,left:4,width:7,height:4,borderRadius:"50%",
          background:hc.hi,filter:"blur(1.5px)",transform:"rotate(-15deg)"}}/>
        <div style={{position:"absolute",top:3,left:9,width:3,height:2,borderRadius:"50%",
          background:hc.hi,opacity:.4,filter:"blur(.5px)"}}/>
      </div>
    </div>
  );
};

const Shimmer=({pi})=>{
  const bg=pi===0?"rgba(120,90,50,":"rgba(100,100,110,";
  return(
    <div style={{display:"flex",flexDirection:"column",gap:6,padding:"2px 0"}}>
      {[70,50,35].map((w,i)=><div key={i} style={{height:7,width:`${w}%`,borderRadius:3,
        background:`linear-gradient(90deg,${bg}.04) 0%,${bg}.1) 50%,${bg}.04) 100%)`,
        backgroundSize:"300px 100%",animation:`sh 1.8s ease-in-out infinite`,animationDelay:`${i*.15}s`}}/>)}
      {[88,60].map((w,i)=><div key={`b${i}`} style={{height:5,width:`${w}%`,borderRadius:3,marginTop:3,
        background:`linear-gradient(90deg,${bg}.03) 0%,${bg}.08) 50%,${bg}.03) 100%)`,
        backgroundSize:"300px 100%",animation:`sh 1.8s ease-in-out infinite`,animationDelay:`${(i+3)*.15}s`}}/>)}
    </div>
  );
};

const CameraFeed=({connected})=>(
  <div style={{position:"absolute",top:FR+CAM_PAD,right:FR+CAM_PAD,width:CAM_W,height:CAM_H,zIndex:18}}>
    {/* Monitor bezel frame */}
    <div style={{position:"absolute",inset:-6,
      background:"linear-gradient(145deg,#1e2838,#151c28,#1a2232)",
      borderRadius:10,border:"1px solid #2a3448",
      boxShadow:"0 4px 20px rgba(0,0,0,.5),inset 0 1px 0 rgba(255,255,255,.04)"}}>
      {/* Corner screws */}
      {[{top:4,left:4},{top:4,right:4},{bottom:4,left:4},{bottom:4,right:4}].map((p,i)=>(
        <div key={i} style={{position:"absolute",width:7,height:7,borderRadius:"50%",...p,
          background:"radial-gradient(circle at 40% 35%,#5a6270,#3a4250)",
          border:"1px solid #4a5260",boxShadow:"inset 0 1px 1px rgba(255,255,255,.08)"}}/>
      ))}
    </div>
    {/* Screen surface */}
    <div style={{position:"absolute",inset:0,borderRadius:6,overflow:"hidden",
      background:connected?"#0a0a0a":"#111418",
      border:"1px solid #0a0e14"}}>
      {/* Static noise when disconnected */}
      {!connected&&(
        <>
          <div style={{position:"absolute",inset:0,opacity:.08,
            backgroundImage:`url("data:image/svg+xml,%3Csvg width='100' height='100' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence baseFrequency='0.85' numOctaves='4' seed='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
            backgroundSize:"100px 100px",animation:"staticFlicker 0.15s steps(3) infinite"}}/>
          {/* Horizontal scan distortion lines */}
          <div style={{position:"absolute",inset:0,opacity:.04,
            background:"repeating-linear-gradient(0deg,transparent 0px,transparent 2px,rgba(255,255,255,.15) 2px,rgba(255,255,255,.15) 3px)"}}/>
          {/* Camera off icon */}
          <div style={{position:"absolute",top:"50%",left:"50%",transform:"translate(-50%,-50%)",
            display:"flex",flexDirection:"column",alignItems:"center",gap:6}}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#3a4050" strokeWidth="1.5" strokeLinecap="round">
              <path d="M16.3 5H4.7A1.7 1.7 0 003 6.7v10.6A1.7 1.7 0 004.7 19h11.6a1.7 1.7 0 001.7-1.7V6.7A1.7 1.7 0 0016.3 5z"/>
              <path d="M21 8l-3 2v4l3 2V8z"/>
              <line x1="2" y1="2" x2="22" y2="22" stroke="#4a3035"/>
            </svg>
          </div>
        </>
      )}
      {/* Subtle screen reflection */}
      <div style={{position:"absolute",inset:0,pointerEvents:"none",
        background:"linear-gradient(145deg,rgba(255,255,255,.02) 0%,transparent 40%,transparent 60%,rgba(255,255,255,.01) 100%)"}}/>
      {/* Status dot */}
      <div style={{position:"absolute",top:8,right:8,width:8,height:8,borderRadius:"50%",
        background:connected
          ?"radial-gradient(circle,#4ade80,#22c55e)"
          :"radial-gradient(circle,#ef4444,#dc2626)",
        boxShadow:connected
          ?"0 0 6px rgba(74,222,128,.6),0 0 12px rgba(74,222,128,.2)"
          :"0 0 4px rgba(239,68,68,.4)",
        animation:connected?"camPulse 2s ease-in-out infinite":"none"}}/>
    </div>
  </div>
);

export default function IntelBoard(){
  const[tier,setTier]=useState(2);
  const[sources,setSources]=useState([]);
  const[bluDoc,setBluDoc]=useState(null);
  const[selDoc,setSelDoc]=useState(null);
  const[modalVis,setModalVis]=useState(false);
  const[dragId,setDragId]=useState(null);
  const[vsc,setVsc]=useState(1);
  const[camConnected]=useState(false);
  const drag=useRef({sx:0,sy:0,dx:0,dy:0,moved:false,id:null});
  const idx=useRef(0);
  const vscRef=useRef(1);

  useEffect(()=>{
    const fn=()=>{const s=Math.min((window.innerWidth-60)/BW,(window.innerHeight-90)/BH,1);vscRef.current=s;setVsc(s);};
    fn();window.addEventListener("resize",fn);return()=>window.removeEventListener("resize",fn);
  },[]);

  useEffect(()=>{},[]);

  useEffect(()=>{
    const fn=e=>{if(e.key==="Escape"&&tier===3)back();};
    window.addEventListener("keydown",fn);return()=>window.removeEventListener("keydown",fn);
  },[tier]);

  useEffect(()=>{
    const onMove=e=>{
      const d=drag.current;if(!d.id)return;
      const sc=vscRef.current*ZM[1];
      const mx=(e.clientX-d.sx)/sc,my=(e.clientY-d.sy)/sc;
      if(!d.moved&&Math.hypot(mx,my)<4)return;
      if(!d.moved){d.moved=true;setDragId(d.id);}
      if(d.id==="blue"){
        setBluDoc({x:Math.max(0,Math.min(BW-BDW,d.dx+mx)),y:Math.max(0,Math.min(BH-BDH,d.dy+my))});
      }else{
        setSources(p=>p.map(s=>s.id===d.id?{...s,
          x:Math.max(0,Math.min(BW-GW,d.dx+mx)),y:Math.max(0,Math.min(BH-GH,d.dy+my))}:s));
      }
    };
    const onUp=()=>{drag.current.id=null;setDragId(null);};
    window.addEventListener("mousemove",onMove);window.addEventListener("mouseup",onUp);
    return()=>{window.removeEventListener("mousemove",onMove);window.removeEventListener("mouseup",onUp);};
  },[]);

  const addSource=useCallback(()=>{
    if(idx.current>=SRCS.length)return;
    const s=SRCS[idx.current],pi=idx.current%3,ti=idx.current%3;
    const rot=(Math.random()-.5)*4,curl=genCurl();
    idx.current++;
    let cb=bluDoc;
    if(!cb){cb={x:BW/2-BDW/2-60,y:BH/2-BDH/2-10};setBluDoc(cb);}
    const pos=randPos(sources,cb);
    const id=Date.now()+Math.random();
    setSources(p=>[...p,{id,...s,...pos,loading:true,pi,ti,rot,curl,appeared:false}]);
    requestAnimationFrame(()=>requestAnimationFrame(()=>
      setSources(p=>p.map(d=>d.id===id?{...d,appeared:true}:d))
    ));
    setTimeout(()=>setSources(p=>p.map(d=>d.id===id?{...d,loading:false}:d)),1800+Math.random()*1200);
  },[sources,bluDoc]);

  const clickDoc=d=>{
    if(drag.current.moved||tier!==2)return;
    drag.current.moved=false;
    setSelDoc(d);setTier(3);
    setTimeout(()=>setModalVis(true),800);
  };

  const back=()=>{setModalVis(false);setTimeout(()=>{setSelDoc(null);setTier(2);},280);};

  const startDrag=(e,id,x,y)=>{
    if(tier!==2)return;e.preventDefault();
    drag.current={sx:e.clientX,sy:e.clientY,dx:x,dy:y,moved:false,id};
  };

  const cam=(()=>{
    const s=vsc;
    if(tier===1)return`scale(${s*ZM[0]})`;
    if(tier===2)return`scale(${s*ZM[1]})`;
    if(tier===3&&selDoc){
      let cx,cy;
      if(selDoc.kind==="summary"&&bluDoc){cx=bluDoc.x+BDW/2-BW/2;cy=bluDoc.y+BDH/2-BH/2;}
      else{const f=sources.find(x=>x.id===selDoc.id);if(!f)return`scale(${s})`;cx=f.x+GW/2-BW/2;cy=f.y+GH/2-BH/2;}
      return`scale(${s*ZM[2]}) translate(${-cx}px,${-cy}px)`;
    }
    return`scale(${s})`;
  })();

  const bpx=bluDoc?bluDoc.x+BDW/2:0,bpy=bluDoc?bluDoc.y+8:0;

  return(
    <div style={{width:"100vw",height:"100vh",overflow:"hidden",position:"relative",
      fontFamily:"'Inter',system-ui,sans-serif",
      background:"linear-gradient(180deg,#070b14 0%,#0a0f1c 25%,#0d1224 50%,#0f1628 75%,#111828 100%)"}}>
      <style>{`
        @keyframes sh{0%{background-position:-150px 0}100%{background-position:150px 0}}
        @keyframes fi{0%{opacity:0;transform:scale(.78)}100%{opacity:1;transform:scale(1)}}
        @keyframes sm{0%{transform:translateY(-100%)}100%{transform:translateY(100%)}}
        @keyframes pf{0%{transform:translateY(0);opacity:0}15%{opacity:.3}85%{opacity:.3}100%{transform:translateY(-140px);opacity:0}}
        @keyframes mi{0%{opacity:0;transform:scale(.93) translateY(12px)}100%{opacity:1;transform:scale(1) translateY(0)}}
        @keyframes dl{0%{stroke-dashoffset:600}100%{stroke-dashoffset:0}}
        @keyframes fl{0%,94%,100%{opacity:1}95%{opacity:.6}97%{opacity:1}98%{opacity:.5}}
        @keyframes camPulse{0%,100%{opacity:1;box-shadow:0 0 6px rgba(74,222,128,.6),0 0 12px rgba(74,222,128,.2)}50%{opacity:.55;box-shadow:0 0 3px rgba(74,222,128,.3),0 0 6px rgba(74,222,128,.1)}}
        @keyframes staticFlicker{0%{background-position:0 0}33%{background-position:50px 30px}66%{background-position:20px 60px}100%{background-position:70px 10px}}
      `}</style>

      {/* Wall texture */}
      <div style={{position:"fixed",inset:0,pointerEvents:"none",
        backgroundImage:"radial-gradient(circle,rgba(255,255,255,.006) 1px,transparent 1px)",backgroundSize:"20px 20px"}}/>
      <div style={{position:"fixed",left:40,top:0,bottom:0,width:3,
        background:"linear-gradient(180deg,#141c28,#0f1520,#141c28)",borderRight:"1px solid #1e2638",opacity:.35,pointerEvents:"none"}}/>
      <div style={{position:"fixed",right:44,top:0,bottom:0,width:3,
        background:"linear-gradient(180deg,#141c28,#0f1520,#141c28)",borderRight:"1px solid #1e2638",opacity:.35,pointerEvents:"none"}}/>
      <div style={{position:"fixed",top:30,left:40,right:44,height:2,
        background:"#141c28",borderBottom:"1px solid #1e2638",opacity:.3,pointerEvents:"none"}}/>
      <div style={{position:"fixed",bottom:0,left:0,right:0,height:100,pointerEvents:"none",
        background:"linear-gradient(180deg,transparent,rgba(3,5,10,.6))"}}>
        {[[60,55,40],[140,48,35]].map((b,i)=>(
          <div key={i} style={{position:"absolute",bottom:8,left:b[0],width:b[1],height:b[2],
            background:"#090d16",border:"1px solid #141b28",borderRadius:2,opacity:.4}}/>
        ))}
        <div style={{position:"absolute",bottom:8,right:70,width:60,height:42,
          background:"#090d16",border:"1px solid #141b28",borderRadius:2,opacity:.4}}/>
      </div>

      {/* CAMERA */}
      <div style={{position:"absolute",top:"50%",left:"50%",
        width:BW+FR*2,height:BH+FR*2,
        marginLeft:-(BW+FR*2)/2,marginTop:-(BH+FR*2)/2,
        transform:cam,transformOrigin:"center center",
        transition:tier===1?"transform 2.2s cubic-bezier(.16,1,.3,1)"
          :tier===3?"transform 0.85s cubic-bezier(.25,.46,.45,.94)"
          :"transform 1s cubic-bezier(.25,.46,.45,.94)"}}>

        {/* Fluorescent light */}
        <div style={{position:"absolute",top:-58,left:"50%",transform:"translateX(-50%)",width:340,height:14,zIndex:30,
          background:"linear-gradient(180deg,#1a2232,#222d3e)",borderRadius:3,border:"1px solid #2a3445"}}>
          <div style={{position:"absolute",bottom:-3,left:16,right:16,height:7,
            background:"linear-gradient(180deg,#dce4f0,#c8d2e2)",borderRadius:3,animation:"fl 10s infinite",
            boxShadow:"0 0 30px rgba(200,215,240,.2),0 0 80px rgba(180,200,230,.1)"}}/>
        </div>
        <div style={{position:"absolute",top:-40,left:"50%",transform:"translateX(-50%)",
          width:550,height:200,pointerEvents:"none",zIndex:0,
          background:"radial-gradient(ellipse at top center,rgba(180,200,230,.04) 0%,transparent 70%)"}}/>

        {/* BOARD FRAME */}
        <div style={{position:"absolute",inset:0,zIndex:2,
          background:"linear-gradient(145deg,#1a2235,#141c2a,#1e2840)",borderRadius:6,
          border:"1px solid #2a3448",
          boxShadow:"inset 0 1px 0 rgba(255,255,255,.04),0 10px 50px rgba(0,0,0,.6),0 2px 8px rgba(0,0,0,.3)"}}>
          {[{top:9,left:9},{top:9,right:9},{bottom:9,right:9},{bottom:9,left:9}].map((p,i)=>(
            <div key={i} style={{position:"absolute",width:13,height:13,borderRadius:"50%",...p,
              background:"radial-gradient(circle at 40% 35%,#6a7080,#3a4250,#2a3040)",
              border:"1px solid #4a5260",zIndex:3,
              boxShadow:"inset 0 1px 2px rgba(255,255,255,.1),0 1px 3px rgba(0,0,0,.5)"}}>
              <div style={{position:"absolute",top:3,left:3,width:2,height:5,
                background:"rgba(255,255,255,.08)",borderRadius:1,transform:"rotate(-30deg)"}}/>
            </div>
          ))}
        </div>

        {/* BOARD SURFACE */}
        <div style={{position:"absolute",top:FR,left:FR,right:FR,bottom:FR,zIndex:4,
          background:"linear-gradient(155deg,#0d1321 0%,#0a0f1a 35%,#0f1629 70%,#111827 100%)",borderRadius:2}}>
          <div style={{position:"absolute",inset:0,overflow:"hidden",borderRadius:2,pointerEvents:"none",zIndex:1}}>
            <div style={{position:"absolute",width:"100%",height:"200%",opacity:.025,
              background:"repeating-linear-gradient(0deg,transparent 0px,transparent 3px,rgba(148,163,184,.4) 3px,rgba(148,163,184,.4) 4px)",
              animation:"sm 12s linear infinite"}}/>
          </div>
          <div style={{position:"absolute",inset:0,pointerEvents:"none",opacity:.02,borderRadius:2,
            backgroundImage:"radial-gradient(circle,#475569 1px,transparent 1px)",backgroundSize:"26px 26px"}}/>
          <div style={{position:"absolute",inset:0,pointerEvents:"none",zIndex:2,borderRadius:2,
            background:"radial-gradient(ellipse at center,transparent 45%,rgba(3,6,16,.55) 100%)"}}/>
          {Array.from({length:12}).map((_,i)=>(
            <div key={i} style={{position:"absolute",left:`${10+Math.random()*80}%`,bottom:`${Math.random()*15}%`,
              width:1.5,height:1.5,borderRadius:"50%",background:"rgba(148,163,184,.2)",
              animation:`pf ${8+Math.random()*8}s linear infinite`,animationDelay:`${Math.random()*8}s`,
              pointerEvents:"none",zIndex:2}}/>
          ))}
        </div>

        {/* Camera feed module */}
        <CameraFeed connected={camConnected}/>

        {/* SVG strings */}
        <svg style={{position:"absolute",top:FR,left:FR,width:BW,height:BH,pointerEvents:"none",zIndex:12}}>
          {bluDoc&&sources.map(s=>(
            <g key={s.id}>
              <path d={catenary(s.x+GW/2,s.y+4,bpx,bpy)} fill="none" stroke="rgba(140,20,20,.08)" strokeWidth={5}/>
              <path d={catenary(s.x+GW/2,s.y+4,bpx,bpy)} fill="none" stroke="#b91c1c" strokeWidth={1.4} opacity={.55}
                strokeDasharray="600" style={{animation:"dl 1.5s ease-out forwards"}}/>
            </g>
          ))}
        </svg>

        {/* BLUE SUMMARY DOC */}
        {bluDoc&&(
          <div onMouseDown={e=>startDrag(e,"blue",bluDoc.x,bluDoc.y)}
            onClick={()=>clickDoc({kind:"summary"})}
            style={{position:"absolute",left:FR+bluDoc.x,top:FR+bluDoc.y,width:BDW,height:BDH,
              background:PAPERS[1].bg,border:`1px solid ${PAPERS[1].bd}`,borderRadius:2,
              padding:"14px 14px 14px",
              cursor:tier===2?(dragId==="blue"?"grabbing":"grab"):"pointer",
              zIndex:dragId==="blue"?32:22,animation:"fi .7s ease-out",
              transform:dragId==="blue"?"scale(1.04)":"scale(1)",
              boxShadow:dragId==="blue"
                ?"0 16px 45px rgba(0,0,0,.45),0 2px 6px rgba(0,0,0,.2)"
                :"0 4px 14px rgba(0,0,0,.35),0 1px 3px rgba(0,0,0,.15)",
              transition:"box-shadow .2s,transform .2s"}}>
            {TEXTURES[1]()}
            <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:10,position:"relative",zIndex:1}}>
              <div style={{width:42,height:42,borderRadius:"50%",flexShrink:0,
                background:"linear-gradient(135deg,#d0d5dd,#b8bfc8)",border:"2px solid #a0a8b4",
                display:"flex",alignItems:"center",justifyContent:"center"}}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="8" r="4" fill="#6b7280"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" fill="#6b7280"/>
                </svg>
              </div>
              <div>
                <div style={{color:"#111827",fontSize:12.5,fontWeight:700,letterSpacing:".04em"}}>{PERSON.nm}</div>
                <div style={{color:"#dc2626",fontSize:9.5,fontWeight:600,letterSpacing:".06em",marginTop:1}}>
                  {sources.length} SOURCE{sources.length!==1?"S":""} FOUND
                </div>
              </div>
            </div>
            <div style={{color:"#4b5563",fontSize:9.5,lineHeight:1.45,overflow:"hidden",position:"relative",zIndex:1,
              textOverflow:"ellipsis",display:"-webkit-box",WebkitLineClamp:2,WebkitBoxOrient:"vertical"}}>
              {PERSON.sm}
            </div>
          </div>
        )}

        {/* GREEN SOURCE DOCS */}
        {sources.map(s=>{
          const p=PAPERS[s.pi],isD=dragId===s.id;
          return(
            <div key={s.id}
              onMouseDown={e=>!s.loading&&startDrag(e,s.id,s.x,s.y)}
              onClick={()=>!s.loading&&clickDoc({kind:"source",id:s.id,...s})}
              style={{position:"absolute",left:FR+s.x,top:FR+s.y,width:GW,height:GH,
                background:p.bg,border:`1px solid ${p.bd}`,borderRadius:2,
                padding:"14px 11px 10px",
                cursor:s.loading?"default":tier===2?(isD?"grabbing":"grab"):"pointer",
                zIndex:isD?32:14,
                opacity:s.appeared?1:0,
                transform:`rotate(${s.appeared?s.rot:0}deg) scale(${isD?1.06:s.appeared?1:0.8})`,
                boxShadow:isD
                  ?"0 18px 45px rgba(0,0,0,.45),0 2px 6px rgba(0,0,0,.2)"
                  :"0 3px 10px rgba(0,0,0,.3),0 1px 2px rgba(0,0,0,.12)",
                transition:"box-shadow .2s,transform .8s ease-out,opacity .8s ease-out"}}>
              {TEXTURES[s.ti]()}
              <CurlOverlay curl={s.curl}/>
              {s.loading?<Shimmer pi={s.pi}/>:(
                <div style={{position:"relative",zIndex:1}}>
                  <div style={{marginBottom:5}}>
                    <span style={{color:"#065f46",fontSize:7,fontWeight:700,letterSpacing:".1em",
                      background:"rgba(5,150,105,.06)",padding:"2px 5px",borderRadius:2,
                      border:"1px solid rgba(5,150,105,.12)"}}>{s.tp}</span>
                  </div>
                  <div style={{color:"#111827",fontSize:10.5,fontWeight:650,marginBottom:4,letterSpacing:".01em"}}>{s.nm}</div>
                  <div style={{color:"#4b5563",fontSize:8.5,lineHeight:1.4,overflow:"hidden",
                    textOverflow:"ellipsis",display:"-webkit-box",WebkitLineClamp:2,WebkitBoxOrient:"vertical"}}>{s.sn}</div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ADD SOURCE */}
      {tier!==3&&(
        <div style={{position:"fixed",bottom:24,left:"50%",transform:"translateX(-50%)",
          display:"flex",alignItems:"center",gap:14,zIndex:50,
          opacity:tier===1?0:1,transition:"opacity .8s .8s"}}>
          <button onClick={addSource} disabled={sources.length>=SRCS.length}
            style={{padding:"10px 24px",borderRadius:6,fontSize:12,fontWeight:650,letterSpacing:".06em",
              background:sources.length>=SRCS.length?"rgba(255,255,255,.04)":"linear-gradient(135deg,#047857,#10b981)",
              color:sources.length>=SRCS.length?"#3a4a5a":"#fff",
              border:sources.length>=SRCS.length?"1px solid rgba(255,255,255,.06)":"1px solid rgba(52,211,153,.3)",
              cursor:sources.length>=SRCS.length?"not-allowed":"pointer",
              boxShadow:sources.length>=SRCS.length?"none":"0 2px 12px rgba(16,185,129,.2)",transition:"all .25s"}}>
            + ADD SOURCE
          </button>
          {sources.length>0&&(
            <div style={{display:"flex",alignItems:"center",gap:7,color:"#4a5a6a",fontSize:11.5,fontWeight:500}}>
              <div style={{width:6,height:6,borderRadius:"50%",
                background:sources.length>=SRCS.length?"#475569":"#10b981",
                boxShadow:sources.length>=SRCS.length?"none":"0 0 8px rgba(16,185,129,.4)"}}/>
              {sources.length} / {SRCS.length}
            </div>
          )}
        </div>
      )}

      {/* BACK */}
      {tier===3&&(
        <button onClick={back} style={{position:"fixed",top:20,left:20,zIndex:60,
          padding:"8px 18px",background:"rgba(255,255,255,.06)",
          border:"1px solid rgba(255,255,255,.1)",borderRadius:6,
          color:"#94a3b8",fontSize:12,fontWeight:600,cursor:"pointer",
          backdropFilter:"blur(8px)",display:"flex",alignItems:"center",gap:6}}>
          <span style={{fontSize:14}}>←</span> Back
        </button>
      )}

      {/* MODAL */}
      {modalVis&&selDoc&&(
        <div onClick={back} style={{position:"fixed",inset:0,zIndex:100,
          background:"rgba(3,6,16,.5)",backdropFilter:"blur(10px)",
          display:"flex",alignItems:"center",justifyContent:"center"}}>
          <div onClick={e=>e.stopPropagation()} style={{
            width:540,maxHeight:"80vh",overflowY:"auto",
            background:selDoc.kind==="summary"
              ?"near-gradient(140deg,rgba(15,25,50,.92),rgba(30,58,95,.8))"
              :"linear-gradient(140deg,rgba(10,30,22,.92),rgba(18,48,32,.8))",
            backdropFilter:"blur(40px)",
            border:`1px solid ${selDoc.kind==="summary"?"rgba(96,165,250,.2)":"rgba(52,211,153,.2)"}`,
            borderRadius:14,padding:"26px 30px 30px",
            boxShadow:`0 30px 80px rgba(0,0,0,.5),0 0 1px ${selDoc.kind==="summary"?"rgba(96,165,250,.3)":"rgba(52,211,153,.3)"}`,
            animation:"mi .35s ease-out"}}>
            <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:20}}>
              <div style={{color:selDoc.kind==="summary"?"#60a5fa":"#34d399",
                fontSize:9,fontWeight:700,letterSpacing:".14em",
                background:selDoc.kind==="summary"?"rgba(96,165,250,.08)":"rgba(52,211,153,.08)",
                padding:"4px 10px",borderRadius:3,
                border:`1px solid ${selDoc.kind==="summary"?"rgba(96,165,250,.18)":"rgba(52,211,153,.18)"}`}}>
                {selDoc.kind==="summary"?"INTELLIGENCE SUMMARY":selDoc.tp}
              </div>
              <button onClick={back} style={{background:"rgba(255,255,255,.04)",
                border:"1px solid rgba(255,255,255,.08)",color:"#7a8a9a",
                width:28,height:28,borderRadius:6,cursor:"pointer",
                display:"flex",alignItems:"center",justifyContent:"center",fontSize:12}}>✕</button>
            </div>
            {selDoc.kind==="summary"?(
              <>
                <div style={{display:"flex",alignItems:"center",gap:16,marginBottom:20}}>
                  <div style={{width:58,height:58,borderRadius:"50%",flexShrink:0,
                    background:"linear-gradient(135deg,#1e3a5f,rgba(37,99,235,.2))",
                    border:"2px solid #2d4a6f",display:"flex",alignItems:"center",justifyContent:"center"}}>
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="8" r="4" fill="#64748b"/><path d=4 20c0-4 3.6-7 8-7s8 3 8 7" fill="#64748b"/>
                    </svg>
                  </div>
                  <div>
                    <div style={{color:"#f1f5f9",fontSize:20,fontWeight:700}}>{PERSON.nm}</div>
                    <div style={{color:"#60a5fa",fontSize:11.5,fontWeight:600,marginTop:2}}>
                      {sources.length} SOURCE{sources.length!==1?"S":""} AGGREGATED
                    </div>
                  </div>
                </div>
                <div style={{height:1,background:"linear-gradient(90deg,transparent,rgba(96,165,250,.15),transparent)",marginBottom:16}}/>
                <div style={{color:"#b8c8d8",fontSize:13.5,lineHeight:1.75}}>{PERSON.sm}</div>
              </>
            ):(
              <>
                <div style={{color:"#f1f5f9",fontSize:18,fontWeight:700}}>{selDoc.nm}</div>
                <div style={{height:1,background:"linear-gradient(90deg,transparent,rgba(52,211,153,.15),transparent)",margin:"14px 0"}}/>
                <div style={{color:"#b8c8d8",fontSize:13.5,lineHeight:1.75}}>{selDoc.sn}</div>
              </>
            )}
            <div style={{height:1,background:`linear-gradient(90deg,transparent,${selDoc.kind==="summary"?"rgba(96,165,250,.12)":"rgba(52,211,153,.12)"},transparent)`,marginTop:24}}/>
            <div style={{marginTop:12,color:"#3a4a5a",fontSize:9,letterSpacing:".12em",textAlign:"center",fontWeight:600}}>
              CLASSIFIED • EYES ONLY • {new Date().toLocaleDateString("en-US",{year:"numeric",month:"short",day:"numeric"}).toUpperCase()}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
