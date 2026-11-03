"""Two human pages. No build step, no framework, demo-honest auth."""
import json
from html import escape


def homepage() -> str:
    return """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>
<title>Roomind — shared AI rooms</title>
<meta name=description content='Roomind: shared AI rooms where teams and agents work live, remember as one team, and decide with receipts.'>
<link rel=icon href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%23177245'/%3E%3Ctext x='32' y='44' font-size='36' text-anchor='middle' fill='white' font-family='sans-serif'%3ER%3C/text%3E%3C/svg%3E">
<link rel=preconnect href='https://fonts.googleapis.com'>
<link href='https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap' rel=stylesheet>
<style>:root{--bg:#F7F6F3;--surface:#fff;--ink:#1a1814;--mut:#57534E;
--line:#E7E2D8;--acc:#177245;--acc-d:#0F5A35;--danger:#9F2F2D}
*{box-sizing:border-box}
body{font-family:Outfit,system-ui,-apple-system,sans-serif;background:var(--bg);
color:var(--ink);max-width:720px;margin:0 auto;padding:3em 1.25em;min-height:100dvh}
.brand{display:flex;align-items:center;gap:.6em}
.logo{display:inline-flex;align-items:center;justify-content:center;width:2.2em;
height:2.2em;border-radius:.6em;background:var(--acc);color:#fff;font-weight:700;
font-size:1.2em}
h1{font-size:2em;letter-spacing:-.02em;line-height:1.1;margin:.4em 0 .2em}
.sub{color:var(--mut);font-size:1.05em;margin:0 0 1.5em}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;
padding:1.25em 1.4em;margin:1em 0;box-shadow:0 2px 10px rgba(26,24,20,.05)}
.card h3{margin:0 0 .6em;font-size:1em;letter-spacing:.02em}
input,button{font:inherit;font-size:1em;padding:.55em .8em;margin:.25em .25em .25em 0;
border-radius:9px;border:1px solid var(--line);background:#fff;color:var(--ink)}
input{min-width:0}
input:focus-visible,button:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
button{cursor:pointer;font-weight:500;transition:background .2s,transform .1s}
button:hover{background:#F0EEE8}
button:active{transform:scale(.98)}
.card button:last-child{background:var(--acc);border-color:var(--acc);color:#fff}
.card button:last-child:hover{background:var(--acc-d)}
#shelf .card button:last-child{background:#fff;border-color:var(--line);color:var(--ink)}
#shelf .card button:last-child:hover{background:#F0EEE8}
.mono{font-family:'JetBrains Mono',ui-monospace,monospace}</style>
</head><body>
<div class=brand><span class=logo>R</span></div>
<h1>Roomind</h1>
<p class=sub>Shared AI rooms. Remember as one team. Decide with receipts.</p>
<div class=card><h3>New chat</h3>
<input id=m placeholder='Mission, e.g. Ship Friday'>
<input id=cn placeholder='Your name'>
<button onclick='createChat()'>Chat</button></div>
<div class=card><h3>New room</h3>
<input id=rm placeholder='Mission, e.g. Ship Friday'>
<input id=rn placeholder='Your name'>
<button onclick='createRoom()'>Room</button><p id=rout></p></div>
<div class=card><h3>Join room</h3>
<input id=r placeholder='Room id'><input id=i placeholder='Invite code'>
<input id=n placeholder='Your name'><button onclick='joinRoom()'>Join</button></div>
<div id=shelf></div>
<script>
async function createChat(){
  const m=document.getElementById('m').value||'Untitled mission';
  const n=document.getElementById('cn').value.trim();
  if(!n){alert('Type your name');return;}
  const r=await fetch('/rooms?mission='+encodeURIComponent(m)
    +'&name='+encodeURIComponent(n),{method:'POST'});
  const j=await r.json();
  location='/rooms/'+j.room_id+'/app?token='+j.token;
}
async function createRoom(){
  const m=document.getElementById('rm').value||'Untitled mission';
  const n=document.getElementById('rn').value.trim();
  if(!n){alert('Type your name');return;}
  const r=await fetch('/rooms?mission='+encodeURIComponent(m)
    +'&name='+encodeURIComponent(n),{method:'POST'});
  const j=await r.json();
  const t=await fetch('/rooms/'+j.room_id+'/invites?token='+j.token
    +'&uses=20&hours=0',{method:'POST'});
  const l=await t.json();
  document.getElementById('rout').innerHTML='Room <b>'+j.room_id
    +'</b><br>Team code <b>'+l.invite+'</b><br><button data-e="'+j.room_id
    +'|'+j.token+'" onclick="openPin(this.dataset.e)">Enter</button>';
}
async function joinRoom(){
  const r=document.getElementById('r').value.trim(),
        i=document.getElementById('i').value.trim(),
        n=document.getElementById('n').value.trim()||'Guest';
  const q=await fetch('/rooms/'+r+'/join?name='+encodeURIComponent(n)
    +'&invite='+encodeURIComponent(i),{method:'POST'});
  if(!q.ok){alert('Bad or expired invite');return;}
  const j=await q.json();
  location='/rooms/'+r+'/app?token='+j.token;
}
function escH(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');}
function shelf(){try{return JSON.parse(localStorage.getItem('roomind.rooms')||'[]')}catch(e){return[]}}
function dropPin(u){const i=u.split('|');localStorage.setItem('roomind.rooms',JSON.stringify(shelf().filter(p=>!(p.rid===i[0]&&p.token===i[1]))));renderShelf();}
function openPin(u){const i=u.split('|');location='/rooms/'+i[0]+'/app?token='+i[1];}
function whoAmI(){try{return sessionStorage.getItem('roomind.me')||''}catch(e){return''}}
function whichTab(){try{return sessionStorage.getItem('roomind.tab')||''}catch(e){return''}}
function renderShelf(){const me=whoAmI(),tab=whichTab();
  let s=(me&&tab)?shelf().filter(p=>p.tab===tab):[];
  let h='<div class=card><h3>My rooms</h3>';
  if(!s.length)h+=me?'<p>No rooms for '+escH(me)+' here yet.</p>'
    :'<p>This tab knows nobody yet. Join a room and your shelf wakes here.</p>';
  s.forEach(p=>{const twin=s.filter(q=>q.rid===p.rid&&q.name===p.name).length>1;
    const label=escH(p.mission||p.rid)+(twin?' ···'+String(p.token).slice(-4):'');
    h+='<p><b>'+label+'</b>'
    +' <button data-u="'+p.rid+'|'+p.token+'" onclick="openPin(this.dataset.u)">Open</button>'
    +' <button data-d="'+p.rid+'|'+p.token+'" onclick="dropPin(this.dataset.d)">x</button></p>';});
  h+='</div>';document.getElementById('shelf').innerHTML=h;}
renderShelf();
</script></body></html>"""


def room_page(rid: str, name: str, role: str = "member",
              mission: str = "", solo: bool = False) -> str:
    r, n = escape(rid), escape(name)
    mission_e = escape(mission)
    isowner = "true" if role == "owner" else "false"
    ismanage = "true" if role in ("owner", "operator") else "false"
    issolo = "true" if solo else "false"
    me_js = json.dumps(name)
    mission_js = json.dumps(mission)
    invite_html = ""
    owner_html = ""
    if role in ("owner", "operator"):
        invite_html = ("<button onclick='invite(1)'>Single link</button>\n"
            "<input id=uses type=number value=20 min=1 max=50 "
            "style='width:4em'>\n<button onclick='invite("
            'document.getElementById("uses").value||20)\'>Team link</button>\n'
            "<button onclick='links()'>Links</button>\n"
            "<button id=lockbtn onclick='lockRoom()'>Lock</button>")
    if role == "owner":
        owner_html = "<button onclick='closeRoom()'>Close room</button>"
    return f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>
<title>Room {r} — Roomind</title>
<meta name=description content='Roomind shared AI room. The team plus the agent, live.'>
<link rel=icon href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%23177245'/%3E%3Ctext x='32' y='44' font-size='36' text-anchor='middle' fill='white' font-family='sans-serif'%3ER%3C/text%3E%3C/svg%3E">
<link rel=preconnect href='https://fonts.googleapis.com'>
<link href='https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap' rel=stylesheet>
<style>:root{{--bg:#F7F6F3;--surface:#fff;--ink:#1a1814;--mut:#57534E;
--line:#E7E2D8;--acc:#177245;--acc-d:#0F5A35;--acc-t:#E9F4ED;
--danger:#9F2F2D;--amber:#8A6116;--amber-t:#FFFBEB;--side:#16130E;
--side-tx:#EDE8DF;--side-mut:#A8A094}}
*{{box-sizing:border-box}}
body.app{{font-family:Outfit,system-ui,-apple-system,sans-serif;background:var(--bg);
color:var(--ink);margin:0;height:100dvh;display:flex;overflow:hidden;
font-size:16px;line-height:1.5}}
input,select,button{{font:inherit;font-size:.95em;padding:.55em .8em;
border-radius:9px;border:1px solid var(--line);background:#fff;color:var(--ink);
min-width:0}}
input:focus-visible,select:focus-visible,button:focus-visible{{
outline:2px solid var(--acc);outline-offset:2px}}
button{{cursor:pointer;font-weight:500;transition:background .2s,transform .1s}}
button:hover{{background:#F0EEE8}}
button:active{{transform:scale(.98)}}
button:disabled{{opacity:.45;cursor:default}}
button[onclick='leaveRoom()'],button[onclick='closeRoom()'],
button[onclick='kickSeat(this)']{{color:var(--danger);border-color:#E5C9C7}}
#bar{{width:264px;flex:none;background:var(--side);color:var(--side-tx);
display:flex;flex-direction:column;gap:.7em;padding:1.1em .95em;overflow-y:auto}}
body.barshut #bar{{display:none}}
.brand{{display:flex;align-items:center;gap:.55em;font-weight:700;
font-size:1.1em;letter-spacing:-.01em}}
.logo{{display:inline-flex;align-items:center;justify-content:center;width:1.9em;
height:1.9em;border-radius:.55em;background:var(--acc);color:#fff}}
.newchat{{background:var(--acc);border-color:var(--acc);color:#fff;
font-weight:600;width:100%}}
.newchat:hover{{background:var(--acc-d)}}
.sideh{{font-size:.72em;letter-spacing:.12em;text-transform:uppercase;
color:var(--side-mut);margin:.5em 0 -.3em}}
#rooms{{display:flex;flex-direction:column;gap:.3em}}
#rooms .rm{{background:transparent;border-color:transparent;color:var(--side-tx);
text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
#rooms .rm:hover{{background:rgba(255,255,255,.07)}}
#rooms .rm.on{{background:rgba(255,255,255,.12);border-color:rgba(255,255,255,.14)}}
#rooms .dim{{color:var(--side-mut);font-size:.9em;margin:.2em}}
.grow{{flex:1}}
#mecard{{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);
border-radius:11px;padding:.6em .8em;display:flex;flex-direction:column}}
#mecard b{{font-size:.95em}}
#mecard span{{font-size:.8em;color:var(--side-mut)}}
#meter{{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:.78em;
color:var(--side-mut);margin:0;font-variant-numeric:tabular-nums}}
#core{{flex:1;display:flex;flex-direction:column;min-width:0}}
#top{{display:flex;align-items:center;gap:.8em;padding:.65em 1.1em;
background:var(--surface);border-bottom:1px solid var(--line);flex:none}}
#menu{{border-color:transparent;background:transparent;font-size:1.1em;
padding:.3em .55em}}
.rtitle{{display:flex;flex-direction:column;min-width:0;line-height:1.3}}
.rtitle b{{font-size:1.02em;letter-spacing:-.01em;white-space:nowrap;
overflow:hidden;text-overflow:ellipsis}}
.rmission{{font-size:.82em;color:var(--mut);white-space:nowrap;overflow:hidden;
text-overflow:ellipsis}}
#strip{{margin-left:auto;font-family:'JetBrains Mono',ui-monospace,monospace;
font-size:.78em;background:var(--acc-t);border:1px solid #CBE3D6;color:var(--acc-d);
border-radius:999px;padding:.45em 1em;cursor:pointer;white-space:nowrap;
font-variant-numeric:tabular-nums}}
#strip:hover{{background:#DDF0E5}}
#wrap{{flex:1;display:flex;gap:.9em;padding:.9em;min-height:0}}
#agentcol{{flex:2;display:flex;flex-direction:column;background:var(--surface);
border:1px solid var(--line);border-radius:16px;min-width:0;overflow:hidden;
box-shadow:0 2px 12px rgba(26,24,20,.05)}}
.colh{{padding:.7em 1.1em;border-bottom:1px solid var(--line);font-weight:600;
font-size:.9em;letter-spacing:.02em;flex:none}}
#thread{{flex:1;overflow-y:auto;padding:1em 1.1em;min-height:0}}
#emptyq,#emptyc,.emptyp{{color:var(--mut);text-align:center;margin:3em 1em}}
.composer{{display:flex;gap:.5em;padding:.7em .9em;border-top:1px solid var(--line);
flex:none;background:var(--surface)}}
.composer input{{flex:1}}
#modelsel{{max-width:11em}}
#sendbtn{{background:var(--acc);border-color:var(--acc);color:#fff;
display:inline-flex;align-items:center}}
#sendbtn:hover{{background:var(--acc-d)}}
#rsn{{padding:.45em 1.1em .7em}}
.rsn{{color:var(--mut);font-size:.9em}}
#roomcol{{flex:1;min-width:300px;background:var(--surface);border:1px solid var(--line);
border-radius:16px;overflow-y:auto;padding-bottom:1em;box-shadow:0 2px 12px rgba(26,24,20,.05)}}
#roomcol .colh:first-child{{position:sticky;top:0;background:var(--surface)}}
#share,#side,#props{{padding:0 1em}}
#share:empty,#props:empty{{padding:0}}
#side{{max-height:320px;overflow-y:auto;margin:.4em 0}}
#chatrow{{display:flex;gap:.5em;padding:.6em 1em;border-top:1px solid var(--line);
border-bottom:1px solid var(--line);margin-bottom:.6em}}
#chatrow input{{flex:1}}
.tools{{display:flex;flex-wrap:wrap;gap:.4em;padding:.2em 1em .8em}}
.tools button{{font-size:.88em;padding:.45em .7em}}
#uses{{max-width:4.5em}}
.forgetrow{{display:flex;gap:.5em;padding:0 1em .6em}}
.forgetrow input{{flex:1}}
#out{{padding:0 1em;font-size:.92em}}
#out pre{{background:#F1EEE7;border:1px solid var(--line);border-radius:10px;
padding:.8em;white-space:pre-wrap;word-break:break-word;
font-family:'JetBrains Mono',ui-monospace,monospace;font-size:.85em}}
#out p{{margin:.45em 0}}
.msg{{background:#FBFAF7;border:1px solid var(--line);border-radius:12px;
padding:.55em .8em;margin:.5em 0;animation:rise .25s cubic-bezier(.16,1,.3,1)}}
.msg .who{{font-size:.78em;font-weight:600;color:var(--mut);margin-bottom:.15em}}
.msg .txt{{line-height:1.55;overflow-wrap:break-word}}
.msg.me{{background:var(--acc-t);border-color:#CBE3D6}}
.msg.agent{{background:#fff}}
.msg.agent .who{{color:var(--acc-d)}}
.msg .rate{{margin-top:.35em;display:flex;gap:.35em}}
.msg .rate button{{font-size:.8em;padding:.25em .6em}}
.card{{background:#fff;border:1px solid var(--line);border-radius:12px;
padding:.7em .9em;margin:.55em 0;animation:rise .25s cubic-bezier(.16,1,.3,1)}}
.card.dissent{{background:var(--amber-t);border-color:#EAD9A6;
border-left:4px solid var(--amber)}}
.card.prop{{border-left:4px solid var(--acc)}}
.card .meta{{font-size:.9em;color:var(--mut)}}
.card button{{font-size:.85em;padding:.4em .7em;margin:.3em .3em 0 0}}
.card input{{margin:.25em .25em .25em 0}}
@keyframes rise{{from{{opacity:0;transform:translateY(8px)}}
to{{opacity:1;transform:none}}}}
#dots .txt span{{display:inline-block;width:.5em;height:.5em;border-radius:50%;
background:var(--acc);margin-right:.25em;animation:bl 1s infinite}}
#dots .txt span:nth-of-type(2){{animation-delay:.2s}}
#dots .txt span:nth-of-type(3){{animation-delay:.4s}}
@keyframes bl{{0%,100%{{opacity:.2}}50%{{opacity:1}}}}
::-webkit-scrollbar{{width:10px;height:10px}}
::-webkit-scrollbar-thumb{{background:#D6D0C4;border-radius:8px;
border:2px solid var(--bg)}}
::-webkit-scrollbar-track{{background:transparent}}
@media(max-width:900px){{#wrap{{flex-direction:column;overflow-y:auto}}
#agentcol{{min-height:72dvh;flex:none}}
#roomcol{{overflow:visible}}
#bar{{position:fixed;z-index:30;height:100dvh;transform:translateX(-105%);
transition:transform .25s cubic-bezier(.16,1,.3,1)}}
body.baropen #bar{{transform:none}}
.rmission{{display:none}}}}
@media(prefers-reduced-motion:reduce){{*,*::before,*::after{{
animation-duration:.01ms!important;transition-duration:.01ms!important}}}}
</style>
</head><body class=app>
<aside id=bar>
<div class=brand><span class=logo>R</span> Roomind</div>
<button class=newchat onclick="location='/'">+ New chat</button>
<div class=sideh>Rooms</div>
<div id=rooms></div>
<div class=grow></div>
<div class=me id=mecard></div>
<p id=meter></p>
</aside>
<main id=core>
<header id=top>
<button id=menu onclick='toggleBar()' aria-label='Menu' title='Menu'>☰</button>
<div class=rtitle><b>Room {r} — {n}</b><span class=rmission>{mission_e}</span></div>
<div id=strip onclick='evalPanel()' title='Eval breakdown'>…</div>
</header>
<div id=wrap>
<section id=agentcol>
<div class=colh>Agent</div>
<div id=thread></div>
<div class=composer><input id=q placeholder='Ask...' onkeydown='if(event.key==="Enter")ask()'><select id=modelsel onchange='setModel(this.value)' title='Your model'></select><button id=sendbtn onclick='ask()' aria-label='Send' title='Send'><svg width=18 height=18 viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d='M22 2 11 13'/><path d='M22 2 15 22 11 13 2 9z'/></svg></button></div>
<div id=rsn class=rsn></div>
</section>
<aside id=roomcol>
<div class=colh>Room chat</div>
<div id=share></div>
<div id=side></div>
<div id=props></div>
<span id=chatrow><input id=t placeholder='Say hello...' onkeydown='if(event.key==="Enter")send()'><button onclick='send()'>Send</button></span>
<div class=colh>Decide</div>
<div class=tools>
<button onclick='brief()'>Brief</button>
<button onclick='catchup()'>Catch me up</button>
<button onclick='ledger()'>Ledger</button>
<button onclick='propNew()'>Propose</button>
<button onclick='check()'>Challenge us</button>
</div>
<div class=colh>Room</div>
<div class=tools>
<button onclick='usage()'>Spend</button>
<button onclick='mute()'>Mute/unmute</button>
<button onclick='people()'>People</button>
{invite_html}
{owner_html}
</div>
<div class=colh>You</div>
<div class=tools>
<button onclick="location='/'">Step out</button>
<button onclick='leaveRoom()'>Leave</button>
</div>
<div class=forgetrow><input id=fk placeholder='Forget fact key'><button onclick='forgetKey()'>Forget</button></div>
<div id=out></div>
</aside>
</div>
</main>
<script>
const R='{r}',T=new URLSearchParams(location.search).get('token');
const ISOWNER={isowner};
const ISMANAGE={ismanage};
const ISSOLO={issolo};
if(ISSOLO){{document.getElementById('chatrow').style.display='none';
  const u=document.getElementById('uses');if(u)u.style.display='none';
  document.querySelectorAll("button[onclick='links()'],button[onclick='people()'],"
    +"button[onclick='catchup()'],button[onclick='check()'],"
    +"button[onclick='lockRoom()'],button[onclick^='invite(']")
    .forEach(b=>b.style.display='none');}}
const ME={me_js};
const MISSION={mission_js};
(function pin(){{try{{const k='roomind.rooms';let s=[];
  try{{s=JSON.parse(localStorage.getItem(k)||'[]');}}catch(e){{}}
  let tab='';
  try{{tab=sessionStorage.getItem('roomind.tab')||'';
    if(!tab){{tab=Math.random().toString(36).slice(2);
      sessionStorage.setItem('roomind.tab',tab);}}}}catch(e){{}}
  s=s.filter(p=>!(p.rid===R&&p.token===T));
  s.unshift({{rid:R,name:ME,token:T,mission:MISSION,tab:tab}});
  localStorage.setItem(k,JSON.stringify(s.slice(0,20)));
  try{{sessionStorage.setItem('roomind.me',ME);}}catch(e){{}}
  }}catch(e){{}}}})();
const box=document.getElementById('thread');
const box2=document.getElementById('side');
function esc(s){{return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');}}
function show(a,b,t){{const el=t||box;
  el.innerHTML+='<div class=msg><div class=who>'+esc(a)
    +'</div><div class=txt>'+esc(b)+'</div></div>';
  el.scrollTop=el.scrollHeight;}}
function who(m){{return m.author+(m.tag?' ·'+m.tag:'')+(m.badge?' ['+m.badge+']':'');}}
async function load(){{const r=await fetch('/rooms/'+R+'/messages?token='+T);
  if(!r.ok){{try{{const k='roomind.rooms';const s=JSON.parse(localStorage.getItem(k)||'[]');localStorage.setItem(k,JSON.stringify(s.filter(p=>!(p.rid===R&&p.token===T))));}}catch(e){{}}alert('Room gone or access revoked');location='/';return;}}
  const ms=await r.json();box.innerHTML='';box2.innerHTML='';
  ms.forEach(m=>{{if(m.kind==='answer')showAns(m);
    else if(m.kind==='ask')show(who(m),m.body);
    else if(m.kind==='dissent'){{if(!m.rating)showDissent(m,box2);}}
    else show(who(m)+(m.kind!=='chat'?' ['+m.kind+']':''),m.body,box2);}});
  if(!box.innerHTML)box.innerHTML='<p id=emptyq>Ask your first question below.</p>';
  if(!box2.innerHTML&&ISSOLO)
    box2.innerHTML='<p id=emptyc>Chat wakes when the second seat joins.</p>';
  evalBar();shareBox();propList();meter();state();sideRooms();sideMe();}}
async function shareBox(){{if(!ISMANAGE)return;
  const r=await fetch('/rooms/'+R+'/members?token='+T);
  const ms=await r.json();
  document.getElementById('share').innerHTML=ms.length<2
    ?"<p>Solo chat. <button onclick='shareRoom()'>Share</button></p>"
    :"<p><button onclick='shareRoom()'>Invite more</button></p>";}}
async function shareRoom(){{const r=await fetch('/rooms/'+R+'/invites?token='+T
  +'&uses=20&hours=0',{{method:'POST'}});
  const j=await r.json();
  document.getElementById('share').innerHTML='<p>Invite: <b>'+j.invite
    +'</b> · Room: <b>'+R+'</b><br>Send both; join from the home page.</p>';}}
function showAns(m){{box.innerHTML+='<div class="msg agent"><div class=who>'
  +esc(m.author)+'</div><div class=txt>'+esc(m.body)+'</div><div class=rate>'
  +" <button data-v='"+m.id+"|1' onclick='rate(this)' title='Good answer'>▲</button>"
  +" <button data-v='"+m.id+"|0' onclick='rate(this)' title='Bad answer'>▼</button></div></div>";
  box.scrollTop=box.scrollHeight;}}
async function rate(el){{const v=el.dataset.v.split('|');
  await fetch('/rooms/'+R+'/messages/'+v[0]+'/rate?token='+T
    +'&up='+(v[1]==='1'),{{method:'POST'}});
  load();}}
function cardHTML(c,mid){{let h='<div class="card dissent"><b>Dissent:</b> '+esc(c.question||'');
  if((c.hats||[]).length||c.source)h+='<div class=meta>Hats: '
    +esc((c.hats||[]).join(', ')||'general')+' · From: '+esc(c.source||'thread')+'</div>';
  (c.points||[]).forEach(p=>{{h+='<br>• '+esc(p.flaw||'')+' — <i>'+esc(p.receipt||'')+'</i>';}});
  if(c.conflict&&c.conflict.key){{h+='<br>Memory says “'+esc(c.conflict.memory_says||'')
    +'” · room says “'+esc(c.conflict.room_says||'')+'”';
    if(ISMANAGE)h+=' <button data-k="'+encodeURIComponent(c.conflict.key)
      +'" data-v="'+encodeURIComponent(c.conflict.room_says||'')
      +'" onclick="fixMem(this)">Room is right — fix</button>';}}
  h+='<br><button data-v="'+mid+'|1" onclick="rate(this)">Fair catch</button>'
    +' <button data-v="'+mid+'|0" onclick="rate(this)">False alarm</button>';
  return h+'</div>';}}
function showDissent(m,t){{let c;try{{c=JSON.parse(m.body);}}catch(e){{
  show(who(m)+' [dissent]',m.body,t);return;}}
  const el=t||box;el.innerHTML+=cardHTML(c,m.id);el.scrollTop=el.scrollHeight;}}
async function fixMem(el){{const r=await fetch('/rooms/'+R+'/memory/fix?token='+T
  +'&key='+el.dataset.k+'&value='+el.dataset.v,{{method:'POST'}});
  alert(r.ok?'Memory fixed.':'Fix refused: '+r.status);if(r.ok)load();}}
async function propList(){{const box3=document.getElementById('props');
  if(!box3)return;
  const r=await fetch('/rooms/'+R+'/proposals?token='+T);
  if(!r.ok){{box3.innerHTML='';return;}}
  const ps=await r.json();let h='';
  ps.forEach(p=>{{h+=propHTML(p);}});
  box3.innerHTML=h;}}
function propHTML(p){{return '<div class="card prop"><b>Proposed:</b> '+esc(p.what)
  +'<div class=meta>'+esc(p.who||'unowned')
  +' · '+esc(p.why||'no reason yet')+(p.deadline?' · by '+esc(p.deadline):'')+'</div>'
  +((p.updates_what||p.updates)?'<div class=meta>Updates: '+esc(p.updates_what||p.updates)+'</div>':'')
  +(p.needs_detail?'<br><b>Vague — edit to sharpen</b>':'')
  +'<br><button data-p="'+p.id+'" onclick="propEdit(this)">Edit</button>'
  +' <button data-p="'+p.id+'" onclick="propConfirm(this)">Confirm</button>'
  +' <button data-p="'+p.id+'" onclick="propDismiss(this)">Dismiss</button></div>';}}
function escQ(s){{return esc(s).replace(/"/g,'&quot;');}}
async function propEdit(el){{const r=await fetch('/rooms/'+R+'/proposals?token='+T);
  const ps=await r.json();const p=ps.filter(x=>x.id==el.dataset.p)[0];
  if(!p)return;
  el.parentElement.innerHTML='<input id=pw value="'+escQ(p.what)+'" style="width:90%">'
    +'<input id=po value="'+escQ(p.who||'')+'" placeholder="Owner" style="width:44%">'
    +'<input id=pd value="'+escQ(p.deadline||'')+'" placeholder="Deadline" style="width:44%">'
    +'<input id=py value="'+escQ(p.why||'')+'" placeholder="Why" style="width:90%">'
    +'<br><button data-p="'+p.id+'" onclick="propSave(this)">Stamp it</button>';}}
async function propSave(el){{const q='&what='+encodeURIComponent(document.getElementById('pw').value)
  +'&who='+encodeURIComponent(document.getElementById('po').value)
  +'&why='+encodeURIComponent(document.getElementById('py').value)
  +'&deadline='+encodeURIComponent(document.getElementById('pd').value);
  const r=await fetch('/rooms/'+R+'/proposals/'+el.dataset.p+'/confirm?token='+T+q,{{method:'POST'}});
  if(!r.ok){{alert('Stamp failed: '+r.status);return;}}
  propList();load();}}
async function propConfirm(el){{const r=await fetch('/rooms/'+R+'/proposals/'+el.dataset.p+'/confirm?token='+T,{{method:'POST'}});
  if(!r.ok){{alert('Stamp failed: '+r.status);return;}}
  propList();load();}}
async function propDismiss(el){{await fetch('/rooms/'+R+'/proposals/'+el.dataset.p+'/dismiss?token='+T,{{method:'POST'}});
  propList();}}
function propNew(){{const box3=document.getElementById('props');
  const d=document.createElement('div');d.className='card';
  d.innerHTML='<b>New proposal</b><br><input id=nw placeholder="Decide what?" style="width:90%">'
    +'<input id=no placeholder="Owner" style="width:44%">'
    +'<input id=nd placeholder="Deadline" style="width:44%">'
    +'<input id=ny placeholder="Why" style="width:90%">'
    +'<br><button onclick="propCreate()">Propose it</button>';
  box3.prepend(d);}}
async function propCreate(){{const q='&what='+encodeURIComponent(document.getElementById('nw').value)
  +'&who='+encodeURIComponent(document.getElementById('no').value)
  +'&why='+encodeURIComponent(document.getElementById('ny').value)
  +'&deadline='+encodeURIComponent(document.getElementById('nd').value);
  const r=await fetch('/rooms/'+R+'/proposals?token='+T+q,{{method:'POST'}});
  if(!r.ok){{alert('Propose failed: '+r.status);return;}}
  propList();}}
function connect(){{const ws=new WebSocket(
  (location.protocol=='https:'?'wss:':'ws:')+'//'+location.host
  +'/rooms/'+R+'/live?token='+T);
  ws.onmessage=e=>{{const m=JSON.parse(e.data);
    if(m.kind==='closed'){{location.reload();return;}}
    if(m.kind==='kicked'){{alert('You were kicked from the room.');location='/';return;}}
    if(m.kind==='locked'){{show('room [system]',m.body,box2);return;}}
    if(m.kind==='system'&&/lock/.test(m.body||'')){{state();}}
    const e2=document.getElementById('emptyc');if(e2)e2.remove();
    if(m.kind==='dissent'){{showDissent(m,box2);return;}}
    if(m.kind==='proposal'){{propList();return;}}
    if(m.kind==='answer'){{showAns(m);return;}}
    if(m.kind==='ask'){{const e1=document.getElementById('echo');
      if(e1&&m.author===ME&&m.body===window._retry){{
        e1.outerHTML='<div class="msg me"><div class=who>'+esc(who(m))
          +'</div><div class=txt>'+esc(m.body)+'</div></div>';return;}}
      show(who(m),m.body);return;}}
    show(who(m)+(m.kind&&m.kind!=='chat'?' ['+m.kind+']':''),m.body,box2);}};
  ws.onclose=e=>{{if(e&&e.code===4000){{location.reload();return;}}
    if(e&&e.code===4001){{location='/';return;}}
    setTimeout(connect,2000);}};window._ws=ws;}}
function send(){{const i=document.getElementById('t');
  window._ws.send(i.value);i.value='';}}
function askRetry(){{const i=document.getElementById('q');
  if(window._retry&&!i.value)i.value=window._retry;
  ask();}}
function ask(){{const i=document.getElementById('q');
  const b=document.getElementById('sendbtn');
  const v=i.value.trim();
  if(!v||b.disabled)return;
  const now=Date.now();
  if(v===window._lastQ&&now-window._lastT<5000)return;
  window._retry=v;
  b.disabled=true;
  const e0=document.getElementById('emptyq');if(e0)e0.remove();
  box.innerHTML+='<div class="msg me" id=echo><div class=who>'+esc(ME)
    +'</div><div class=txt>'+esc(v)+'</div></div>';i.value='';
  box.innerHTML+='<div class="msg agent" id=dots><div class=who>agent</div>'
    +'<div class=txt><span></span><span></span><span></span></div></div>';
  box.scrollTop=box.scrollHeight;
  const es=new EventSource('/rooms/'+R+'/askstream?token='+T+'&text='+encodeURIComponent(v));
  let st=null,n=0;
  es.onmessage=e=>{{const d=JSON.parse(e.data);
    if(d.tok){{n++;if(!st){{const p=document.getElementById('dots');
      if(p)p.outerHTML='<div class="msg agent"><div class=who>agent</div>'
        +'<div class=txt id=stream></div></div>';
      st=document.getElementById('stream');}}
      st.innerHTML+=esc(d.tok);box.scrollTop=box.scrollHeight;}}
    if(d.done){{es.close();window._lastQ=v;window._lastT=Date.now();
      document.getElementById('rsn').innerHTML=(d.done.reasons
        ?'Why: '+d.done.reasons.map(esc).join(' · '):'')+(n>1?'':' · all at once');
      b.disabled=false;load();}}
    if(d.error){{es.close();
      document.getElementById('rsn').innerHTML=d.error+" <button onclick='askRetry()'>Retry</button>";
      b.disabled=false;load();}}}};
  es.onerror=()=>{{es.close();
    document.getElementById('rsn').innerHTML="Send failed. <button onclick='askRetry()'>Retry</button>";
    b.disabled=false;load();}};}}
async function brief(){{const r=await fetch('/rooms/'+R+'/brief?token='+T);
  document.getElementById('out').innerHTML='<pre>'+esc(JSON.stringify(
    await r.json(),null,1))+'</pre>';}}
async function catchup(){{const r=await fetch('/rooms/'+R+'/catchup?token='+T
  +'&since_id=0');document.getElementById('out').innerHTML='<pre>'
  +esc(JSON.stringify(await r.json(),null,1))+'</pre>';}}
async function ledger(){{const r=await fetch('/rooms/'+R+'/ledger?token='+T);
  document.getElementById('out').innerHTML='<pre>'+esc(JSON.stringify(
    await r.json(),null,1))+'</pre>';}}
async function check(){{const r=await fetch('/rooms/'+R+'/dissent/check?token='
  +T,{{method:'POST'}});document.getElementById('out').innerHTML='<pre>'
  +esc(JSON.stringify(await r.json(),null,1))+'</pre>';load();}}
async function usage(){{const r=await fetch('/rooms/'+R+'/usage?token='+T);
  document.getElementById('out').innerHTML='<pre>'+esc(JSON.stringify(
    await r.json(),null,1))+'</pre>';}}
async function mute(){{const r=await fetch('/rooms/'+R+'/dissent/mute?token='+T
  +'&on=true',{{method:'POST'}});
  alert(r.ok?'muted: agent talks only when asked':'Mute refused: '+r.status);}}
async function invite(u){{const r=await fetch('/rooms/'+R+'/invites?token='+T
  +'&uses='+u+'&hours=0',{{method:'POST'}});
  if(!r.ok){{document.getElementById('out').innerHTML='Denied (owner or operator only)';return;}}
  links();}}
async function leaveRoom(){{
  const r=await fetch('/rooms/'+R+'/members?token='+T);
  const ms=await r.json();
  if(ms.length<2){{
    if(!confirm('You are the last seat. Leaving closes the room forever for everyone. No one can access it after. Close it?'))return;
    await fetch('/rooms/'+R+'/leave?token='+T,{{method:'POST'}});location='/';return;}}
  if(!confirm('Leave this room? Your access ends at once. Rejoin needs a fresh invite from the owner or operator.'))return;
  if(!ISOWNER){{await fetch('/rooms/'+R+'/leave?token='+T,{{method:'POST'}});location='/';return;}}
  let h='<div><p>Hand the crown first:</p>';
  ms.forEach(m=>{{if(m.role==='owner')return;
    h+="<p><button data-s='"+m.id+"' onclick='leaveAs(this.dataset.s)'>"+esc(m.name)+" · "+esc(m.nick)+" ("+m.role+")</button></p>";}});
  h+="<p><button data-s='' onclick='leaveAs(this.dataset.s)'>Auto-pick</button></p></div>";
  document.getElementById('out').innerHTML=h;}}
async function leaveAs(id){{const r=await fetch('/rooms/'+R+'/leave?token='+T+'&successor_id='+id,{{method:'POST'}});
  if(r.ok)location='/';else alert('Leave failed: '+r.status);}}
async function links(){{const r=await fetch('/rooms/'+R+'/invites?token='+T);
  if(!r.ok){{document.getElementById('out').innerHTML='Links failed: '+r.status;return;}}
  const ls=await r.json();const now=new Date().toLocaleTimeString();
  let h='<div data-links=1><p>Room <b>'+R+'</b> · Updated '+now+'</p>';
  ls.forEach(l=>{{h+="<p><b>"+l.token+"</b> "+l.used+" joined · "+l.left
    +" left of "+l.max_uses+" ("+l.role+")"
    +" <button data-c='"+l.token+"' "
    +"onclick='topup(this.dataset.c)'>+5</button></p>";}});
  h+='</div>';
  document.getElementById('out').innerHTML=ls.length?h:'No links';
  if(!window._lp){{window._lp=setInterval(()=>{{
    if(document.querySelector('#out [data-links]'))links();}},5000);}}}}
async function topup(code){{const r=await fetch('/rooms/'+R+'/invites/topup?token='+T
  +'&invite='+code+'&add_uses=5',{{method:'POST'}});
  if(!r.ok){{document.getElementById('out').innerHTML='Top-up failed: '+r.status;return;}}
  links();}}
async function people(){{const r=await fetch('/rooms/'+R+'/members?token='+T);
  if(!r.ok){{document.getElementById('out').innerHTML='People failed: '+r.status;return;}}
  const ms=await r.json();let h='<div><p>People</p>';
  ms.forEach(m=>{{let row="<p><b>"+esc(m.name)+"</b> · "+esc(m.nick)+" ("+m.role+")";
    if(ISOWNER){{row+=" <button data-m='"+m.id+"' onclick='makeOwner(this.dataset.m)'>Make owner</button>";
      row+=" <button data-o='"+m.id+"' onclick='makeOp(this.dataset.o)'>Operator</button>";}}
    if(ISMANAGE&&(m.role==='member'||(ISOWNER&&m.role==='operator'))){{
      row+=" <button data-k='"+m.id+"' data-n=\\""+escQ(m.name)+"\\" onclick='kickSeat(this)'>Kick</button>";}}
    h+=row+"</p>";}});
  document.getElementById('out').innerHTML=h+'</div>';}}
async function makeOwner(id){{const r=await fetch('/rooms/'+R+'/owner?token='+T+'&member_id='+id,{{method:'POST'}});
  document.getElementById('out').innerHTML=r.ok?'Crown moved.':"Transfer failed: "+r.status;}}
async function makeOp(id){{const r=await fetch('/rooms/'+R+'/operators?token='+T+'&member_id='+id,{{method:'POST'}});
  document.getElementById('out').innerHTML=r.ok?'Operator named.':"Grant failed: "+r.status;people();}}
async function closeRoom(){{if(!confirm('Close this room forever for everyone?'))return;
  const r=await fetch('/rooms/'+R+'?token='+T,{{method:'DELETE'}});
  if(r.ok)location='/';else alert('Close failed: '+r.status);}}
async function forgetKey(){{const k=document.getElementById('fk').value;
  await fetch('/rooms/'+R+'/memory?token='+T+'&key='+encodeURIComponent(k),
  {{method:'DELETE'}});alert('forgotten');}}
async function evalBar(){{try{{
  const r=await fetch('/rooms/'+R+'/eval?token='+T);
  if(!r.ok)return;
  const e=await r.json();
  const g=e.golden||{{}},ap=e.approval;
  const pc=v=>v==null?'—':Math.round(v*100)+'%';
  let h='Golden '+(g.score==null?'—':g.score+'/'+g.total
    +' · P '+pc(g.precision)+' · R '+pc(g.recall));
  h+=' · OK '+(ap.n?pc(ap.pct)+' ('+ap.n+')':'—');
  h+=' · '+(e.speed_s==null?'—':e.speed_s.toFixed(1)+'s/ans');
  h+=' · '+(e.cost_per_decision==null?'—':'$'+e.cost_per_decision.toFixed(3)+'/dec');
  h+=' · Trust '+e.trust.word;
  document.getElementById('strip').innerHTML=h;
}}catch(_){{}}}}
async function evalPanel(){{const r=await fetch('/rooms/'+R+'/eval?token='+T);
  const e=await r.json(),g=e.golden;let h='<div><p><b>Eval breakdown</b></p>';
  if(!g)h+='<p>Exam never run.</p>';
  else{{h+='<p>Golden '+g.score+'/'+g.total
    +' · False alarms: '+(g.false_alarms.join(', ')||'none')
    +' · Misses: '+(g.misses.join(', ')||'none')+'</p>';
  g.details.forEach(d=>{{h+='<p>'+(d.hit?'✓':'✗')+' <b>'+d.id+'</b> '
    +esc(d.title)+' — '+(d.expected?'must fire':'must silence')
    +' · '+(d.fired?'fired':'silent')+' · '+esc(d.why)+'</p>';}});}}
  const tr=e.trust;
  h+='<p>Trust: '+tr.word+' · fair '
    +(tr.n?Math.round(tr.pct*100)+'% ('+tr.n+')':'no verdicts yet')+'</p>';
  if(ISMANAGE)h+="<p><button onclick='runExam()'>Run exam</button> "
    +"Ten judge calls. Spend lands in the meter.</p>";
  h+='</div>';document.getElementById('out').innerHTML=h;}}
async function runExam(){{document.getElementById('out').innerHTML='Examining, one call per case…';
  const x=await fetch('/rooms/'+R+'/eval/exam?token='+T,{{method:'POST'}});
  if(!x.ok){{document.getElementById('out').innerHTML='Exam failed: '+x.status;return;}}
  evalBar();evalPanel();}}
async function kickSeat(el){{const id=el.dataset.k,nm=el.dataset.n;
  if(!confirm('Kick '+nm+'? Their access ends at once. Rejoin needs a fresh invite.'))return;
  const r=await fetch('/rooms/'+R+'/members/'+id+'/kick?token='+T,{{method:'POST'}});
  document.getElementById('out').innerHTML=r.ok?nm+' kicked.':'Kick refused: '+r.status;
  if(r.ok)people();}}
async function lockRoom(){{
  const on=document.getElementById('lockbtn').textContent==='Lock';
  const r=await fetch('/rooms/'+R+'/lock?token='+T+'&on='+on,{{method:'POST'}});
  if(!r.ok){{alert('Lock refused: '+r.status);return;}}
  state();}}
async function state(){{
  const r=await fetch('/rooms/'+R+'/state?token='+T);
  if(!r.ok)return;
  const s=await r.json();
  const L=document.getElementById('lockbtn');if(L)L.textContent=s.locked?'Unlock':'Lock';
  ['t','q','sendbtn'].forEach(id=>{{const e=document.getElementById(id);
    if(e)e.disabled=!!s.locked;}});
  const sel=document.getElementById('modelsel');
  if(sel){{let cur=s.model||s.default;
    if(!window._models){{try{{
      const mr=await fetch('/rooms/'+R+'/models?token='+T);
      window._models=(await mr.json()).models||[];
    }}catch(_){{
      window._models=[];
    }}}}
    const opts=[cur].concat(
      (window._models||[]).filter(m=>m&&m!==cur));
    sel.innerHTML=opts.map(m=>"<option value='"+esc(m)+"'>"+esc(m)
      +"</option>").join('')+"<option value='__other__'>Other…</option>";
    sel.value=cur;}}}}
async function setModel(v){{
  if(v==='__other__'){{v=prompt('Model id (same key must allow it):')||'';}}
  v=(v||'').trim();if(!v){{state();return;}}
  const r=await fetch('/rooms/'+R+'/model?token='+T+'&model='+encodeURIComponent(v),
    {{method:'POST'}});
  if(!r.ok)alert('Model refused: '+r.status);
  state();}}
async function meter(){{
  const r=await fetch('/rooms/'+R+'/usage?token='+T);
  if(!r.ok)return;
  const u=await r.json();
  let mine=u.default;
  try{{
    const sr=await fetch('/rooms/'+R+'/state?token='+T);
    const s=await sr.json();
    mine=s.model||s.default;
  }}catch(_){{
  }}
  document.getElementById('meter').innerHTML='Spend $'
    +(u.spent_usd||0).toFixed(4)+' of $'+(u.cap_usd||0)
    +' · Model: '+esc(mine);}}
function sideRooms(){{try{{
  let tab='';try{{tab=sessionStorage.getItem('roomind.tab')||'';}}catch(e){{}}
  let s=[];try{{s=JSON.parse(localStorage.getItem('roomind.rooms')||'[]');}}catch(e){{}}
  if(tab)s=s.filter(p=>p.tab===tab);
  const el=document.getElementById('rooms');if(!el)return;
  if(!s.length){{el.innerHTML='<p class=dim>Join a room and it lands here.</p>';return;}}
  el.innerHTML=s.map(p=>'<button class="rm'+(p.rid===R?' on':'')
    +'" data-u="'+p.rid+'|'+p.token+'" onclick="openRoom(this.dataset.u)">'
    +esc(p.mission||p.rid)+'</button>').join('');
}}catch(e){{}}}}
function openRoom(u){{const i=u.split('|');location='/rooms/'+i[0]+'/app?token='+i[1];}}
function sideMe(){{const el=document.getElementById('mecard');if(!el)return;
  el.innerHTML='<b>'+esc(ME)+'</b><span>'
    +(ISOWNER?'owner':(ISMANAGE?'operator':'member'))+'</span>';}}
function toggleBar(){{const small=window.matchMedia('(max-width:900px)').matches;
  document.body.classList.toggle(small?'baropen':'barshut');}}
load();connect();if(ISOWNER)links();
if(ISSOLO)setInterval(async()=>{{try{{const m=await fetch('/rooms/'+R+'/members?token='+T);
  if((await m.json()).length>1)location.reload();}}catch(_){{}}}},5000);
</script></body></html>"""


def gone_page() -> str:
    return """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>
<title>Roomind</title>
<link rel=icon href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%23177245'/%3E%3Ctext x='32' y='44' font-size='36' text-anchor='middle' fill='white' font-family='sans-serif'%3ER%3C/text%3E%3C/svg%3E">
<link rel=preconnect href='https://fonts.googleapis.com'>
<link href='https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap' rel=stylesheet>
<style>body{font-family:Outfit,system-ui,sans-serif;background:#F7F6F3;color:#1a1814;
max-width:640px;margin:0 auto;padding:4em 1.25em;min-height:100dvh}
h1{letter-spacing:-.02em;line-height:1.15}
p{color:#57534E}
button{font:inherit;font-size:1em;padding:.55em .9em;border-radius:9px;cursor:pointer;
background:#177245;border:1px solid #177245;color:#fff;font-weight:500}</style>
</head><body>
<h1>You are no longer in this room</h1>
<p>You left, or your seat was removed. Your old link will not open it again.</p>
<p>Ask the owner or operator for a fresh invite to rejoin.</p>
<button onclick="location='/'">My rooms</button>
</body></html>"""


def closed_page() -> str:
    return """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>
<title>Roomind</title>
<link rel=icon href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%23177245'/%3E%3Ctext x='32' y='44' font-size='36' text-anchor='middle' fill='white' font-family='sans-serif'%3ER%3C/text%3E%3C/svg%3E">
<link rel=preconnect href='https://fonts.googleapis.com'>
<link href='https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap' rel=stylesheet>
<style>body{font-family:Outfit,system-ui,sans-serif;background:#F7F6F3;color:#1a1814;
max-width:640px;margin:0 auto;padding:4em 1.25em;min-height:100dvh}
h1{letter-spacing:-.02em;line-height:1.15}
p{color:#57534E}
button{font:inherit;font-size:1em;padding:.55em .9em;border-radius:9px;cursor:pointer;
background:#177245;border:1px solid #177245;color:#fff;font-weight:500}</style>
</head><body>
<h1>This room is closed</h1>
<p>It was closed forever and its chat, memory, and ledger are wiped.</p>
<button onclick="location='/'">My rooms</button>
</body></html>"""
