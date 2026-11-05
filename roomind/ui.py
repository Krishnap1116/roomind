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
  if(!q.ok){let m='Join failed ('+q.status+')';try{m=(await q.json()).detail||m;}catch(e){}alert(m);return;}
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
    const label=(p.parent?'↳ ':'')+escH(p.mission||p.rid)+(twin?' ···'+String(p.token).slice(-4):'');
    h+='<p><b>'+label+'</b>'
    +' <button data-u="'+p.rid+'|'+p.token+'" onclick="openPin(this.dataset.u)">Open</button>'
    +' <button data-d="'+p.rid+'|'+p.token+'" onclick="dropPin(this.dataset.d)">x</button></p>';});
  h+='</div>';document.getElementById('shelf').innerHTML=h;}
renderShelf();
</script></body></html>"""


def room_page(rid: str, name: str, role: str = "member",
              mission: str = "", solo: bool = False,
              parent: str = "", my_id: str = "") -> str:
    r, n = escape(rid), escape(name)
    mission_e = escape(mission)
    p = escape(parent)
    isowner = "true" if role == "owner" else "false"
    ismanage = "true" if role in ("owner", "operator") else "false"
    issolo = "true" if solo else "false"
    me_js = json.dumps(name)
    myid_js = json.dumps(my_id)
    mission_js = json.dumps(mission)
    invite_html = ""
    lock_html = ""
    mute_html = ""
    owner_html = ""
    parent_html = ""
    side_html = ""
    showcase_html = ""
    sharenote_html = ""
    sharehead_html = "<div class=sech>Invite links</div>"
    if parent:
        sharehead_html = "<div class=sech>Read-only link</div>"
        parent_html = "<button onclick='goMain()'>← Main</button>"
        if role in ("owner", "operator"):
            side_html = "<button onclick='shareBack()'>Report to main</button>"
        sharenote_html = ("<p class=dim>No invite links here — the owner "
            "or operator adds people from the roster in the Room tab. "
            "The public link shares a read-only story.</p>")
    if role in ("owner", "operator") and not parent:
        invite_html = ("<button onclick='invite(1)'>Single link</button>\n"
            "<input id=uses type=number value=20 min=1 max=50 "
            "style='width:4em'>\n<button onclick='invite("
            'document.getElementById("uses").value||20)\' class=primary>Team link</button>\n'
            "<button onclick='links()'>Invites</button>\n")
        lock_html = "<button id=lockbtn onclick='lockRoom()'>Lock</button>"
    if role in ("owner", "operator"):
        mute_html = "<button id=mutebtn onclick='mute()'>Mute judge</button>"
    if not parent and role not in ("owner", "operator"):
        sharenote_html = ("<p class=dim>Only the owner or an operator can "
            "make invite links — ask them for one.</p>")
    if role == "owner":
        owner_html = "<button class=quiet onclick='closeRoom()'>Close room</button>"
    if role in ("owner", "operator"):
        showcase_html = "<button onclick='showcase()'>Read-only link</button>"
    sharetools_html = (f"<div class=tools>\n{invite_html}\n{showcase_html}\n</div>"
                       if (invite_html or showcase_html) else "")
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
input,select,button,textarea{{font:inherit;font-size:.95em;padding:.55em .8em;
border-radius:9px;border:1px solid var(--line);background:#fff;color:var(--ink);
min-width:0}}
textarea{{resize:none;overflow-y:auto;max-height:9em}}
input:focus-visible,select:focus-visible,button:focus-visible,textarea:focus-visible{{
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
#rooms .rmrow{{display:flex;gap:.25em;align-items:center}}
#rooms .rmrow .rm{{flex:1;min-width:0}}
#rooms .dots{{flex:none;background:transparent;border-color:transparent;color:var(--side-mut);padding:.4em .55em}}
#rooms .dots:hover{{background:rgba(255,255,255,.07);color:var(--side-tx)}}
#rmmenu{{position:fixed;z-index:50;background:#fff;border:1px solid var(--line);
border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.15);padding:.35em;display:none}}
#rmmenu.show{{display:block}}
#rmmenu button{{display:block;width:100%;text-align:left;background:none;border:none}}
#rooms .dim{{color:var(--side-mut);font-size:.9em;margin:.2em}}
.grow{{flex:1}}
#mecard{{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);
border-radius:11px;padding:.6em .8em;display:flex;flex-direction:column}}
#mecard b{{font-size:.95em}}
#mecard span{{font-size:.8em;color:var(--side-mut)}}
#meter{{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:.78em;
color:var(--side-mut);margin:0;font-variant-numeric:tabular-nums}}
#nudgeback,#newback{{display:none;position:fixed;inset:0;z-index:40;
background:rgba(26,24,20,.45);align-items:center;justify-content:center}}
#nudgeback.show,#newback.show{{display:flex}}
#nudgecard,#newcard{{background:#fff;border-radius:14px;max-width:26em;width:90%;
padding:1.2em 1.4em;box-shadow:0 12px 40px rgba(26,24,20,.3);
animation:rise .25s cubic-bezier(.16,1,.3,1)}}
#nudgetxt{{white-space:pre-wrap;margin:.6em 0;line-height:1.55}}
#nudgecard button,#newcard button{{background:var(--acc);border-color:var(--acc);color:#fff;
font-weight:600;width:100%}}
#nudgecard button:hover,#newcard button:hover{{background:var(--acc-d)}}
#newcard input{{display:block;width:100%;box-sizing:border-box;margin:.55em 0}}
#newcard .mrow{{display:flex;gap:.5em;margin-top:.6em}}
#newcard .mrow button{{width:auto;flex:1}}
#newcard button.plain{{background:#fff;border-color:var(--line);color:var(--ink);font-weight:500}}
#newcard button.plain:hover{{background:#F0EEE8}}
#core{{flex:1;display:flex;flex-direction:column;min-width:0}}
#top{{display:flex;align-items:center;gap:.8em;padding:.65em 1.1em;
background:var(--surface);border-bottom:1px solid var(--line);flex:none;flex-wrap:wrap}}
#menu{{border-color:transparent;background:transparent;font-size:1.1em;
padding:.3em .55em}}
.rtitle{{display:flex;flex-direction:column;min-width:0;line-height:1.3}}
.rtitle b{{font-size:1.02em;letter-spacing:-.01em;white-space:nowrap;
overflow:hidden;text-overflow:ellipsis}}
#strip{{margin-left:auto;font-family:'JetBrains Mono',ui-monospace,monospace;
font-size:.78em;background:var(--acc-t);border:1px solid #CBE3D6;color:var(--acc-d);
border-radius:12px;padding:.45em 1em;white-space:nowrap;
font-variant-numeric:tabular-nums}}
.detailslink{{text-decoration:underline;font-weight:700}}
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
.composer input,.composer textarea{{flex:1}}
#modelsel{{max-width:11em}}
#sendbtn{{background:var(--acc);border-color:var(--acc);color:#fff;
display:inline-flex;align-items:center}}
#sendbtn:hover{{background:var(--acc-d)}}
#rsn{{padding:.45em 1.1em .7em}}
.rsn{{color:var(--mut);font-size:.9em}}
.src{{color:var(--mut);font-size:.85em;margin:.35em 0;overflow-wrap:anywhere}}
.src a{{color:var(--acc)}}
#roomcol{{flex:1;min-width:300px;background:var(--surface);border:1px solid var(--line);
border-radius:16px;overflow:hidden;padding-bottom:1em;box-shadow:0 2px 12px rgba(26,24,20,.05);
display:flex;flex-direction:column}}
.tabs{{display:flex;gap:.25em;padding:.6em 1em .5em;border-bottom:1px solid var(--line);
position:sticky;top:0;background:var(--surface);z-index:2}}
.tabbtn{{position:relative;font-size:.9em;padding:.5em .9em;border-radius:10px 10px 0 0}}
.tabbtn.on{{background:var(--acc);border-color:var(--acc);color:#fff}}
.tabbtn .dot{{position:absolute;top:4px;right:4px;width:8px;height:8px;border-radius:50%;
background:#E4572E;display:none}}
.tabbtn.live .dot{{display:block}}
.tabpane{{display:none}}
.tabpane.on{{display:flex;flex-direction:column;flex:1 1 auto;min-height:0;overflow-y:auto}}
#tab-chat #side{{flex:1 1 auto;min-height:0;max-height:none;overflow-y:auto}}
#chatrow{{flex:none;background:var(--surface);z-index:1}}
#share,#side,#props{{padding:0 1em}}
#share:empty,#props:empty{{padding:0}}
#arts,#tasks,#polls,#redsec,#rems,#sides,#sidepick{{padding:0 1em}}
#arts:empty,#tasks:empty,#polls:empty,#redsec:empty,#rems:empty{{padding:0}}
#side{{max-height:320px;overflow-y:auto;margin:.4em 0}}
#chatrow{{display:flex;gap:.5em;padding:.6em 1em;border-top:1px solid var(--line);
margin-bottom:0}}
#chatrow input,#chatrow textarea{{flex:1}}
.tools{{display:flex;flex-wrap:wrap;gap:.4em;padding:.2em 1em .8em;align-items:center}}
.tools button{{font-size:.82em;padding:.4em .65em}}
.tools button.primary{{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600}}
.tools button.primary:hover{{background:var(--acc-d)}}
button.quiet{{background:transparent;border-color:transparent;color:var(--mut);
text-decoration:underline;text-underline-offset:2px}}
button.quiet:hover{{background:transparent;color:var(--danger)}}
.sech{{font-size:.72em;font-weight:600;text-transform:uppercase;letter-spacing:.07em;
color:var(--mut);padding:.9em 1.4em .25em}}
.sechrow{{display:flex;justify-content:space-between;align-items:center;
padding:.9em 1.1em .25em}}
.sechrow span{{font-size:.72em;font-weight:600;text-transform:uppercase;
letter-spacing:.07em;color:var(--mut)}}
.sechrow button{{font-size:.78em;padding:.25em .6em}}
.newform.nudge{{animation:nudge .45s}}
@keyframes nudge{{0%,100%{{box-shadow:none}}30%{{box-shadow:0 0 0 3px var(--danger);
border-color:var(--danger)}}}}
.tabpane>p{{padding:0 1em}}
#uses{{max-width:4.5em}}
#remindtime{{max-width:9em}}
#sideinput{{flex:1;min-width:8em}}
.dim{{color:var(--mut);font-size:.9em}}
#planout,#workout,#roomout{{padding:0 1em;font-size:.92em}}
#planout:empty,#workout:empty,#roomout:empty,#invout:empty{{padding:0}}
#invout{{padding:0 1em;font-size:.92em}}
#invout p{{margin:.45em 0}}
.mutebadge{{display:none;font-size:.72em;font-weight:700;letter-spacing:.06em;
text-transform:uppercase;padding:.35em .9em;border-radius:9999px;margin:.5em 1em 0;width:fit-content}}
.mutebadge.off{{display:inline-block;background:#EDF3EC;color:#346538}}
.mutebadge.muted{{display:inline-block;background:#FDEBEC;color:#9F2F2D}}
#mutebtn.muted{{border-color:#9F2F2D;color:#9F2F2D;font-weight:700}}
.invrow{{display:flex;flex-wrap:wrap;gap:.5em;align-items:center;
padding:.5em 0;border-top:1px solid var(--line)}}
.invrow code{{font-family:'JetBrains Mono',ui-monospace,monospace;
font-size:.85em;overflow-wrap:anywhere}}
#planout pre,#workout pre,#roomout pre,#invout pre{{background:#F1EEE7;
border:1px solid var(--line);border-radius:10px;
padding:.8em;white-space:pre-wrap;word-break:break-word;
font-family:'JetBrains Mono',ui-monospace,monospace;font-size:.85em}}
#planout p,#workout p,#roomout p{{margin:.45em 0}}
.result{{background:#FBFAF7;border:1px solid var(--line);border-radius:12px;
padding:.2em .9em .6em;margin:.6em 0;animation:rise .25s cubic-bezier(.16,1,.3,1)}}
.rhead{{font-size:.72em;font-weight:600;text-transform:uppercase;letter-spacing:.07em;
color:var(--mut);padding:.6em 0 .2em}}
.msg{{background:#FBFAF7;border:1px solid var(--line);border-radius:12px;
padding:.55em .8em;margin:.5em 0;animation:rise .25s cubic-bezier(.16,1,.3,1)}}
.msg .who{{font-size:.78em;font-weight:600;color:var(--mut);margin-bottom:.15em}}
.msg .txt{{line-height:1.55;overflow-wrap:break-word;white-space:pre-wrap}}
.msg.me{{background:var(--acc-t);border-color:#CBE3D6;margin-left:auto;max-width:92%;width:fit-content}}
.msg.sys{{background:#E1F3FE;border-color:#BEE0F5}}
.msg.sys .who{{color:#1F6C9F}}
.msg.agent{{background:#fff}}
.msg.agent .who{{color:var(--acc-d)}}
.msg .rate{{margin-top:.35em;display:flex;gap:.35em}}
.msg .rate button{{font-size:.8em;padding:.25em .6em}}
.card{{background:#fff;border:1px solid var(--line);border-radius:12px;
padding:.7em .9em;margin:.55em 0;animation:rise .25s cubic-bezier(.16,1,.3,1)}}
.card.dissent{{background:var(--amber-t);border-color:#D9C48A}}
.card.prop{{background:var(--acc-t);border-color:#CBE3D6}}
.card.done{{opacity:.55}}
.card .meta{{font-size:.9em;color:var(--mut)}}
.card button{{font-size:.85em;padding:.4em .7em;margin:.3em .3em 0 0}}
.card input,.card textarea{{margin:.25em .25em .25em 0}}
@keyframes rise{{from{{opacity:0;transform:translateY(8px)}}
to{{opacity:1;transform:none}}}}
#dots .txt span,.pdots span{{display:inline-block;width:.5em;height:.5em;border-radius:50%;
background:var(--acc);margin-right:.25em;animation:bl 1s infinite}}
#dots .txt span:nth-of-type(2),.pdots span:nth-of-type(2){{animation-delay:.2s}}
#dots .txt span:nth-of-type(3),.pdots span:nth-of-type(3){{animation-delay:.4s}}
@keyframes bl{{0%,100%{{opacity:.2}}50%{{opacity:1}}}}
::-webkit-scrollbar{{width:10px;height:10px}}
::-webkit-scrollbar-thumb{{background:#D6D0C4;border-radius:8px;
border:2px solid var(--bg)}}
::-webkit-scrollbar-track{{background:transparent}}
::selection{{background:#CBE3D6}}
@media(max-width:900px){{#wrap{{flex-direction:column;overflow-y:auto}}
#agentcol{{min-height:72dvh;flex:none}}
#roomcol{{overflow:visible}}
#bar{{position:fixed;z-index:30;height:100dvh;transform:translateX(-105%);
transition:transform .25s cubic-bezier(.16,1,.3,1)}}
body.baropen #bar{{transform:none}}}}
@media(prefers-reduced-motion:reduce){{*,*::before,*::after{{
animation-duration:.01ms!important;transition-duration:.01ms!important}}}}
</style>
</head><body class=app>
<aside id=bar>
<div class=brand><span class=logo>R</span> Roomind</div>
<button class=newchat onclick='newChat()'>+ New chat</button>
<div class=sideh>Rooms</div>
<div id=rooms></div>
<div id=rmmenu></div>
<div class=grow></div>
<div class=me id=mecard></div>
<p id=meter></p>
</aside>
<main id=core>
<header id=top>
<button id=menu onclick='toggleBar()' aria-label='Menu' title='Menu'>☰</button>
<div class=rtitle><b>{mission_e}</b></div>
{parent_html}{side_html}
<div id=strip>…</div>
</header>
<div id=wrap>
<section id=agentcol>
<div class=colh>Agent</div>
<div id=thread></div>
<div class=composer><textarea id=q rows=1 placeholder='Ask... (Shift+Enter for a new line)' onkeydown='if(event.key==="Enter"&&!event.shiftKey){{event.preventDefault();ask()}}' oninput='grow(this)'></textarea><select id=modelsel onchange='setModel(this.value)' title='Your model'></select><button id=sendbtn onclick='ask()' aria-label='Send' title='Send'><svg width=18 height=18 viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d='M22 2 11 13'/><path d='M22 2 15 22 11 13 2 9z'/></svg></button></div>
<div id=rsn class=rsn></div>
</section>
<aside id=roomcol>
<div class=tabs>
<button id=tabbtn-chat class='tabbtn on' onclick="tab('chat')">Chat<span class=dot></span></button>
<button id=tabbtn-plan class=tabbtn onclick="tab('plan')">Plan<span class=dot></span></button>
<button id=tabbtn-work class=tabbtn onclick="tab('work')">Work<span class=dot></span></button>
<button id=tabbtn-room class=tabbtn onclick="tab('room')">Room<span class=dot></span></button>
<button id=tabbtn-share class=tabbtn onclick="tab('share')">Share<span class=dot></span></button>
</div>
<div id=tab-chat class='tabpane on'>
<div id=side></div>
<span id=chatrow><textarea id=t rows=1 placeholder='Say hello... (Shift+Enter for a new line)' onkeydown='if(event.key==="Enter"&&!event.shiftKey){{event.preventDefault();send()}}' oninput='grow(this)'></textarea><button class=primary onclick='send()'>Send</button></span>
</div>
<div id=tab-plan class=tabpane>
<div class=sech>Recap</div>
<div class=tools>
<button class=primary onclick='brief()'>Summary</button>
<label><input type=checkbox id=incside> Include sides</label>
</div>
<div class=sech>Decisions</div>
<div class=tools>
<button onclick='ledger()'>Decisions</button>
<button onclick='propNew()'>Log decision</button>
</div>
<div class=sech>Red team</div>
<div class=tools>
<button onclick='redteam()'>Attack our plan</button>
</div>
<div id=planout></div>
<div class=sech>Open cards <span id=judgestate class=meta></span></div>
<div id=props></div>
<div class=sech>Red-team findings</div>
<div id=redsec></div>
</div>
<div id=tab-work class=tabpane>
<div class=sechrow><span>Docs</span><button onclick='artNew()'>+ Doc</button></div>
<div id=arts></div>
<div class=sechrow><span>Tasks</span><button onclick='taskNew()'>+ Task</button></div>
<div id=tasks></div>
<div class=sechrow><span>Votes</span><button onclick='pollNew()'>+ Vote</button></div>
<div id=polls></div>
<div class=sech>People</div>
<div class=tools>
<button onclick='team()'>Team</button>
</div>
<div id=workout></div>
<div class=sech>Reminders</div>
<div class=tools>
<button onclick='remindNow()'>Remind now</button>
<input id=remindtime onchange='setRemindTime(this.value)' placeholder='HH:MM or off' title='Daily nudge time, 24-hour'>
</div>
<div id=rems></div>
</div>
<div id=tab-room class=tabpane>
<div id=sidesec><div class=colh>Side rooms</div>
<div id=sides></div>
<div class=tools id=sidepickrow>
<button id=sidepickbtn onclick='sidePickOpen()'>Select people</button>
</div>
<div id=sidepick style='display:none'></div>
<div class=tools>
<input id=sideinput placeholder='Side mission'>
<button onclick='sideCreate()'>New side room</button>
</div></div>
<div id=rostersec style='display:none'><div class=colh>Side roster</div>
<div class=tools>
<select id=rosterpick></select>
<button onclick='rosterAdd()'>Add member</button>
</div>
<p class=dim>Remove via People → Remove.</p></div>
<div class=sech>People</div>
<div class=tools>
<button onclick='people()'>People</button>
{mute_html}
<button onclick='exportRoom()'>Download</button>
<label><input type=checkbox id=expside> Include sides</label>
</div>
<div id=mutestate class=mutebadge></div>
<div id=roomout></div>
<div class=sech>Room controls</div>
<div class=tools>
{lock_html}
{owner_html}
<button onclick="location='/'">Step out</button>
<button class=quiet onclick='leaveRoom()'>Leave</button>
</div>
<p class=dim id=memkeys></p>
</div>
<div id=tab-share class=tabpane>
{sharehead_html}
<div id=share></div>
{sharetools_html}
<div id=invout></div>
{sharenote_html}
</div>
</aside>
</div>
<div id=nudgeback><div id=nudgecard><b>Reminder</b><div id=nudgetxt></div><button onclick='dismissNudge()'>Got it</button></div></div>
<div id=newback><div id=newcard><b>New chat</b><input id=nm placeholder='Mission, e.g. Ship Friday'><input id=nn placeholder='Your name'><div class=mrow><button onclick='newChatGo()'>Create</button><button class=plain onclick='newChatHide()'>Cancel</button></div></div></div>
</main>
<script>
const R='{r}',T=new URLSearchParams(location.search).get('token');
const ISOWNER={isowner};
const ISMANAGE={ismanage};
const ISSOLO={issolo};
if(ISSOLO){{document.getElementById('chatrow').style.display='none';
  const u=document.getElementById('uses');if(u)u.style.display='none';
  document.querySelectorAll("button[onclick='links()'],button[onclick='people()'],"
    +"button[onclick='lockRoom()'],button[onclick='remindNow()'],"
    +"button[onclick^='invite('],input#remindtime,#sidesec")
    .forEach(b=>b.style.display='none');}}
const ME={me_js};
const MYID={myid_js};
function mine(m){{return !!(MYID&&m.author_id&&m.author_id===MYID);}}
const MISSION={mission_js};
const PARENT='{p}';
(function pin(){{try{{const k='roomind.rooms';let s=[];
  try{{s=JSON.parse(localStorage.getItem(k)||'[]');}}catch(e){{}}
  let tab='';
  try{{tab=sessionStorage.getItem('roomind.tab')||'';
    if(!tab){{tab=Math.random().toString(36).slice(2);
      sessionStorage.setItem('roomind.tab',tab);}}}}catch(e){{}}
  s=s.filter(p=>!(p.rid===R&&p.token===T));
  s.unshift({{rid:R,name:ME,token:T,mission:MISSION,tab:tab,parent:PARENT,
    role:ISOWNER?'owner':(ISMANAGE?'operator':'member')}});
  localStorage.setItem(k,JSON.stringify(s.slice(0,20)));
  try{{sessionStorage.setItem('roomind.me',ME);}}catch(e){{}}
  }}catch(e){{}}}})();
const box=document.getElementById('thread');
const box2=document.getElementById('side');
function esc(s){{return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');}}
function dueLabel(s){{s=s||'';const l=s.toLowerCase();return (l==='by'||l.indexOf('by ')===0)?s:'by '+s;}}
let CURTAB='chat';
let _seen=0;
function tab(n){{CURTAB=n;['chat','plan','work','room','share'].forEach(x=>{{
  document.getElementById('tab-'+x).classList.toggle('on',x===n);
  const b=document.getElementById('tabbtn-'+x);b.classList.toggle('on',x===n);
  if(x===n)b.classList.remove('live');}});}}
function ping(n){{if(n!==CURTAB)document.getElementById('tabbtn-'+n).classList.add('live');}}
function grow(el){{el.style.height='auto';el.style.height=Math.min(el.scrollHeight,150)+'px';}}
function resultBox(title,body){{return '<div class=result><div class=rhead>'
  +esc(title)+'</div>'+body+'</div>';}}
function newGuard(box){{box.querySelectorAll('.empty-note').forEach(n=>n.remove());
  const ex=box.querySelector('.newform');
  if(!ex)return false;
  ex.classList.remove('nudge');void ex.offsetWidth;ex.classList.add('nudge');
  const i=ex.querySelector('input,textarea,select');if(i)i.focus();
  return true;}}
function show(a,b,t,isMe){{const el=t||box;
  const sys=/\[system\]/.test(a||'');
  el.innerHTML+='<div class="msg'+(isMe?' me':'')+(sys?' sys':'')+'"><div class=who>'+esc(a)
    +'</div><div class=txt>'+esc(b)+'</div></div>';
  el.scrollTop=el.scrollHeight;}}
function who(m){{return m.author+(m.tag?' ·'+m.tag:'')+(m.badge?' ['+m.badge+']':'');}}
async function load(){{const r=await fetch('/rooms/'+R+'/messages?token='+T);
  if(!r.ok){{try{{const k='roomind.rooms';const s=JSON.parse(localStorage.getItem(k)||'[]');localStorage.setItem(k,JSON.stringify(s.filter(p=>!(p.rid===R&&p.token===T))));}}catch(e){{}}alert('Room gone or access revoked');location='/';return;}}
  const ms=await r.json();
  const stick2=box2.scrollHeight-box2.scrollTop-box2.clientHeight<40;
  const keep2=box2.scrollTop;
  box.innerHTML='';box2.innerHTML='';
  window._shown=new Set(ms.map(m=>m.id));
  ms.forEach(m=>{{if((m.id||0)>_seen)_seen=m.id;}});
  const byAsk={{}},doneA=new Set();
  ms.forEach(m=>{{if(m.kind==='answer'&&m.ask_id)byAsk[m.ask_id]=m;}});
  ms.forEach(m=>{{if(m.kind==='answer'){{if(!doneA.has(m.id))showAns(m);}}
    else if(m.kind==='ask'){{show(who(m),m.body,box,true);
      const a=byAsk[m.id];
      if(a){{showAns(a);doneA.add(a.id);}}
      else box.innerHTML+=slotHTML(m.id);}}
    else if(m.kind==='dissent'){{if(!m.rating)showDissent(m,document.getElementById('props'));}}
    else if(m.kind==='redteam'){{}}
    else show(who(m)+(m.kind!=='chat'?' ['+m.kind+']':''),m.body,box2,mine(m));}});
  if(!box.innerHTML)box.innerHTML='<p id=emptyq>Ask your first question below.</p>';
  if(!box2.innerHTML&&ISSOLO)
    box2.innerHTML='<p id=emptyc>Chat wakes when the second seat joins.</p>';
  box2.scrollTop=stick2?box2.scrollHeight:keep2;
  evalBar();shareBox();propList();artList();taskList();pollList();redList();remList();sidesList();sidePicker();roster();meter();state();sideRooms();sideMe();memKeys();slotSweep();setInterval(slotSweep,30000);setInterval(meter,30000);return ms;}}
async function shareBox(){{if(!ISMANAGE||PARENT)return;
  const r=await fetch('/rooms/'+R+'/members?token='+T);
  const ms=await r.json();
  document.getElementById('share').innerHTML=ms.length<2
    ?"<p>Solo chat. <button onclick='shareRoom()'>Share</button></p>"
    :"<p><button onclick='shareRoom()'>Invite more</button></p>";}}
async function shareRoom(){{const r=await fetch('/rooms/'+R+'/invites?token='+T
  +'&uses=20&hours=0',{{method:'POST'}});
  const j=await r.json();
  document.getElementById('share').innerHTML='<p>Room<br><b>'+R+'</b> '
    +'<button data-c="'+R+'" onclick="copyTxt(this)">Copy</button></p>'
    +'<p>Invite<br><b>'+j.invite+'</b> '
    +'<button data-c="'+j.invite+'" onclick="copyTxt(this)">Copy</button></p>'
    +'<p><button data-c="'+j.invite+'" onclick="copyBoth(this)">Copy both</button>'
    +'<br><span class=meta>Join from the home page.</span></p>';}}
async function copyTxt(el){{const t=el.dataset.c;try{{await navigator.clipboard.writeText(t);}}
  catch(e){{const i=document.createElement('textarea');i.value=t;document.body.appendChild(i);i.select();document.execCommand('copy');i.remove();}}
  el.textContent='Copied';setTimeout(()=>el.textContent='Copy',1500);}}
async function copyBoth(el){{const t='Room: '+R+' Invite: '+el.dataset.c;try{{await navigator.clipboard.writeText(t);}}
  catch(e){{const i=document.createElement('textarea');i.value=t;document.body.appendChild(i);i.select();document.execCommand('copy');i.remove();}}
  el.textContent='Copied';setTimeout(()=>el.textContent='Copy both',1500);}}
async function exportRoom(){{const inc=document.getElementById('expside').checked?'&include_sides=true':'';
  const r=await fetch('/rooms/'+R+'/export?token='+T+inc);
  if(!r.ok){{alert('Export failed: '+r.status);return;}}
  const blob=await r.blob();const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);a.download='room-'+R+'.json';a.click();
  setTimeout(()=>URL.revokeObjectURL(a.href),5000);}}
async function showcase(){{let r=await fetch('/rooms/'+R+'/showcase?token='+T);
  let j=await r.json();
  if(!r.ok||!j.url){{r=await fetch('/rooms/'+R+'/showcase?token='+T,{{method:'POST'}});
    if(!r.ok){{document.getElementById('invout').innerHTML='Public link refused: '+r.status;return;}}
    j=await r.json();}}
  document.getElementById('invout').innerHTML=resultBox('Read-only link','<p style="overflow-wrap:anywhere"><b>'+location.origin+j.url+'</b></p><p><button onclick="revokeShowcase()">Revoke link</button></p>');}}
async function revokeShowcase(){{const r=await fetch('/rooms/'+R+'/showcase?token='+T,{{method:'DELETE'}});
  document.getElementById('invout').innerHTML=r.ok?'Link revoked.':'Revoke failed: '+r.status;}}
function linkify(s){{return esc(s).replace(/https?:\/\/[^\\s<)]+/g,u=>'<a href="'+u+'" target=_blank rel=noopener>'+u+'</a>');}}
function ansHTML(m){{let src='';
  const rs=Array.isArray(m.reasons)?m.reasons:String(m.reasons||'').split('\\n').filter(s=>s.trim());
  if(rs.length)src='<div class=src>Sources:<br>• '+rs.map(linkify).join('<br>• ')+'</div>';
  return '<div class="msg agent"><div class=who>'
  +esc(m.author)+'</div><div class=txt>'+esc(m.body)+'</div>'+src+'<div class=rate>'
  +" <button data-v='"+m.id+"|1' onclick='rate(this)' title='Good answer'>▲</button>"
  +" <button data-v='"+m.id+"|0' onclick='rate(this)' title='Bad answer'>▼</button></div></div>";}}
function showAns(m){{box.innerHTML+=ansHTML(m);box.scrollTop=box.scrollHeight;}}
function slotHTML(qid){{return '<div class="msg agent" id=slot-'+qid+' data-t="'+Date.now()
  +'"><div class=who>agent</div><div class="txt pdots"><span></span><span></span><span></span></div></div>';}}
function slotAns(m){{const s=m.ask_id?document.getElementById('slot-'+m.ask_id):null;
  if(s){{s.outerHTML=ansHTML(m);box.scrollTop=box.scrollHeight;}}
  else showAns(m);}}
function slotSweep(){{document.querySelectorAll('[id^=slot-]').forEach(s=>{{
  if(Date.now()-(+s.dataset.t||0)>120000)s.outerHTML='<div class="msg agent"><div class=who>agent</div>'
    +'<div class=txt><span class=dim>No answer arrived.</span></div></div>';}});}}
async function rate(el){{const v=el.dataset.v.split('|');
  await fetch('/rooms/'+R+'/messages/'+v[0]+'/rate?token='+T
    +'&up='+(v[1]==='1'),{{method:'POST'}});
  const card=el.closest('.card');if(card)card.remove();
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
function showDissent(m,t){{const el0=t||document.getElementById('props');
  el0.querySelectorAll('.empty-note').forEach(n=>n.remove());
  let c;try{{c=JSON.parse(m.body);}}catch(e){{
  show(who(m)+' [dissent]',m.body,t);return;}}
  const el=t||box;el.innerHTML+=cardHTML(c,m.id);el.scrollTop=el.scrollHeight;}}
async function redList(){{const box=document.getElementById('redsec');
  if(!box)return;
  const r=await fetch('/rooms/'+R+'/redteam?token='+T);
  if(!r.ok){{box.innerHTML='';return;}}
  const items=(await r.json()).filter(c=>!c.rating);let h='';
  items.forEach(c=>{{h+=redHTML(c,c.id);}});
  box.innerHTML=h||'<p class="dim empty-note">No findings yet. Attack our plan runs the red team.</p>';}}
function redHTML(c,mid){{let h='<div class="card redteam"><b>Red team:</b> '+esc(c.verdict||'');
  (c.flaws||[]).forEach(f=>{{h+='<br>• ['+esc(f.severity||'med')+'] '+esc(f.flaw||'')+' — <i>'+esc(f.receipt||'')+'</i>';}});
  if(c.strongest)h+='<br><b>Holds:</b> '+esc(c.strongest);
  h+='<br><button data-a="'+mid+'" data-v="fixed" onclick="redResolve(this)">Fixed</button>'
    +' <button data-a="'+mid+'" data-v="accepted" onclick="redResolve(this)">Accept risk</button>'
    +' <button data-a="'+mid+'" data-v="dismissed" onclick="redResolve(this)">Dismiss</button></div>';return h;}}
async function redResolve(el){{const r=await fetch('/rooms/'+R+'/redteam/'+el.dataset.a+'/resolve?token='+T+'&verdict='+el.dataset.v,{{method:'POST'}});
  if(!r.ok){{alert('Resolve failed: '+r.status);return;}}
  load();}}
async function redteam(){{document.getElementById('planout').innerHTML='Attacking the plan…';
  const r=await fetch('/rooms/'+R+'/redteam?token='+T,{{method:'POST'}});
  let msg='Attack refused: '+r.status;
  if(r.ok){{const j=await r.json();msg=j.triggered?'Attack posted below.':'No attack: '+esc(j.reason||'unknown');}}
  document.getElementById('planout').innerHTML=msg;load();}}
async function fixMem(el){{const r=await fetch('/rooms/'+R+'/memory/fix?token='+T
  +'&key='+el.dataset.k+'&value='+el.dataset.v,{{method:'POST'}});
  alert(r.ok?'Memory fixed.':'Fix refused: '+r.status);if(r.ok)load();}}
async function propList(){{const box3=document.getElementById('props');
  if(!box3)return;
  const keep=[...box3.querySelectorAll('.card.dissent')];
  const r=await fetch('/rooms/'+R+'/proposals?token='+T);
  if(!r.ok){{box3.innerHTML='';keep.forEach(k=>box3.appendChild(k));return;}}
  const ps=await r.json();let h='';
  ps.forEach(p=>{{h+=propHTML(p);}});
  if(!h&&!keep.length)h='<p class="dim empty-note">Nothing open. Judge cards and logged decisions land here.</p>';
  box3.innerHTML=h;keep.forEach(k=>box3.appendChild(k));}}
function propHTML(p){{return '<div class="card prop"><b>Proposed:</b> '+esc(p.what)
  +'<div class=meta>'+esc(p.who||'unowned')
  +' · '+esc(p.why||'no reason yet')+(p.deadline?' · '+esc(dueLabel(p.deadline)):'')+'</div>'
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
  if(r.status===404){{propList();load();alert('Already settled by someone — list refreshed.');return;}}
  if(!r.ok){{alert('Stamp failed: '+r.status);return;}}
  propList();load();}}
async function propConfirm(el){{const r=await fetch('/rooms/'+R+'/proposals/'+el.dataset.p+'/confirm?token='+T,{{method:'POST'}});
  if(r.status===404){{propList();load();alert('Already settled by someone — list refreshed.');return;}}
  if(!r.ok){{alert('Stamp failed: '+r.status);return;}}
  propList();load();}}
async function propDismiss(el){{await fetch('/rooms/'+R+'/proposals/'+el.dataset.p+'/dismiss?token='+T,{{method:'POST'}});
  propList();}}
function propNew(){{const box3=document.getElementById('props');
  if(newGuard(box3))return;
  const d=document.createElement('div');d.className='card newform';
  d.innerHTML='<b>New decision</b><br><input id=nw placeholder="Decide what?" style="width:90%">'
    +'<input id=no placeholder="Owner" style="width:44%">'
    +'<input id=nd placeholder="Deadline" style="width:44%">'
    +'<input id=ny placeholder="Why" style="width:90%">'
    +'<br><button onclick="propCreate()">Save</button>';
  box3.prepend(d);}}
async function propCreate(){{const q='&what='+encodeURIComponent(document.getElementById('nw').value)
  +'&who='+encodeURIComponent(document.getElementById('no').value)
  +'&why='+encodeURIComponent(document.getElementById('ny').value)
  +'&deadline='+encodeURIComponent(document.getElementById('nd').value);
  const r=await fetch('/rooms/'+R+'/proposals?token='+T+q,{{method:'POST'}});
  if(!r.ok){{alert('Propose failed: '+r.status);return;}}
  propList();}}
async function artList(){{const box=document.getElementById('arts');
  if(!box)return;
  const r=await fetch('/rooms/'+R+'/artifacts?token='+T);
  if(!r.ok){{box.innerHTML='';return;}}
  const items=await r.json();let h='';
  items.forEach(a=>{{h+=artHTML(a);}});
  box.innerHTML=h||'<p class="dim empty-note">No docs yet. + Doc starts the first one.</p>';}}
function artHTML(a){{let h='<div class="card art"><b>'+esc(a.title)+'</b> <span class=meta>'+esc(a.kind)+' · v'+a.version+' · '+esc(a.status)+'</span><div class=txt>'+esc(a.body)+'</div>';
  h+='<br><button data-a="'+a.id+'" onclick="artEdit(this)">Edit</button>';
  if(a.status==='draft')h+=' <button data-a="'+a.id+'" data-t="propose" onclick="artAct(this)">Submit</button>';
  if(a.status==='proposed')h+=' <button data-a="'+a.id+'" data-t="approve" onclick="artAct(this)">Approve</button>';
  if(a.status==='approved')h+=' <button data-a="'+a.id+'" data-t="apply" onclick="artAct(this)">Mark done</button>';
  h+=' <button data-a="'+a.id+'" onclick="artHist(this)">History</button></div>';return h;}}
function artNew(){{const box=document.getElementById('arts');
  if(newGuard(box))return;
  const d=document.createElement('div');d.className='card newform';
  d.innerHTML='<b>New doc, plan, or patch</b><br><input id=nt placeholder="Title" style="width:90%">'
    +'<select id=nk><option value="doc">doc</option><option value="plan">plan</option><option value="patch">patch</option></select>'
    +'<br><textarea id=nb rows=4 placeholder="Write it here" style="width:90%"></textarea>'
    +'<br><button onclick="artCreate()">Create draft</button>';
  box.prepend(d);}}
async function artCreate(){{const q='&title='+encodeURIComponent(document.getElementById('nt').value)
  +'&kind='+encodeURIComponent(document.getElementById('nk').value)
  +'&body='+encodeURIComponent(document.getElementById('nb').value);
  const r=await fetch('/rooms/'+R+'/artifacts?token='+T+q,{{method:'POST'}});
  if(!r.ok){{alert('Create failed: '+r.status);return;}}
  artList();}}
async function artEdit(el){{const r=await fetch('/rooms/'+R+'/artifacts/'+el.dataset.a+'?token='+T);
  const a=await r.json();
  el.parentElement.innerHTML='<input id=at value="'+escQ(a.title)+'" style="width:90%">'
    +'<br><textarea id=ab rows=4 style="width:90%">'+esc(a.body)+'</textarea>'
    +'<br><button data-a="'+a.id+'" onclick="artSave(this)">Save v'+(a.version+1)+'</button>';}}
async function artSave(el){{const q='&title='+encodeURIComponent(document.getElementById('at').value)
  +'&body='+encodeURIComponent(document.getElementById('ab').value);
  const r=await fetch('/rooms/'+R+'/artifacts/'+el.dataset.a+'/edit?token='+T+q,{{method:'POST'}});
  if(!r.ok){{alert('Save failed: '+r.status);return;}}
  artList();load();}}
async function artAct(el){{const r=await fetch('/rooms/'+R+'/artifacts/'+el.dataset.a+'/'+el.dataset.t+'?token='+T,{{method:'POST'}});
  if(!r.ok){{alert('Move failed: '+r.status);return;}}
  artList();load();}}
async function artHist(el){{const r=await fetch('/rooms/'+R+'/artifacts/'+el.dataset.a+'/versions?token='+T);
  document.getElementById('workout').innerHTML=resultBox('Version history','<pre>'+esc(JSON.stringify(await r.json(),null,1))+'</pre>');}}
async function taskList(){{const box=document.getElementById('tasks');
  if(!box)return;
  const r=await fetch('/rooms/'+R+'/tasks?token='+T);
  if(!r.ok){{box.innerHTML='';return;}}
  const items=await r.json();let h='';
  items.forEach(t=>{{h+=taskHTML(t);}});
  box.innerHTML=h||'<p class="dim empty-note">No tasks yet. + Task adds one.</p>';}}
function taskHTML(t){{let h='<div class="card task'+(t.status!=='open'?' done':'')+'"><b>'+esc(t.title)+'</b> <span class=meta>'+esc(t.assignee||'unassigned')+(t.due_text?' · by '+esc(t.due_text):'')+(t.flag?' · '+esc(t.flag):'')+' · '+esc(t.status)+'</span>';
  if(t.details)h+='<div class=txt>'+esc(t.details)+'</div>';
  h+='<br>';
  if(t.status==='open')h+='<button data-a="'+t.id+'" onclick="taskDone(this)">Done</button>';
  else h+='<button data-a="'+t.id+'" onclick="taskReopen(this)">Reopen</button>';
  h+=' <button data-a="'+t.id+'" onclick="taskEdit(this)">Edit</button>';
  h+=' <button data-a="'+t.id+'" onclick="taskDel(this)">Delete</button></div>';return h;}}
function taskNew(){{const box=document.getElementById('tasks');
  if(newGuard(box))return;
  const d=document.createElement('div');d.className='card newform';
  d.innerHTML='<b>New task</b><br><input id=tt placeholder="Do what?" style="width:90%">'
    +'<input id=td placeholder="Details" style="width:90%">'
    +'<input id=ta placeholder="Assignee" style="width:44%">'
    +'<input id=tu placeholder="Due, e.g. Friday" style="width:44%">'
    +'<br><button onclick="taskCreate()">Add task</button>';
  box.prepend(d);}}
async function taskCreate(){{const q='&title='+encodeURIComponent(document.getElementById('tt').value)
  +'&details='+encodeURIComponent(document.getElementById('td').value)
  +'&assignee='+encodeURIComponent(document.getElementById('ta').value)
  +'&due='+encodeURIComponent(document.getElementById('tu').value);
  const r=await fetch('/rooms/'+R+'/tasks?token='+T+q,{{method:'POST'}});
  if(!r.ok){{alert('Add failed: '+r.status);return;}}
  taskList();}}
async function taskEdit(el){{const r=await fetch('/rooms/'+R+'/tasks?token='+T);
  const ts=await r.json();const t=ts.filter(x=>x.id==el.dataset.a)[0];
  if(!t)return;
  el.parentElement.innerHTML='<input id=et value="'+escQ(t.title)+'" style="width:90%">'
    +'<input id=ed value="'+escQ(t.details||'')+'" style="width:90%">'
    +'<input id=ea value="'+escQ(t.assignee||'')+'" placeholder="Assignee" style="width:44%">'
    +'<input id=eu value="'+escQ(t.due_text||'')+'" placeholder="Due" style="width:44%">'
    +'<br><button data-a="'+t.id+'" onclick="taskSave(this)">Save</button>';}}
async function taskSave(el){{const q='&title='+encodeURIComponent(document.getElementById('et').value)
  +'&details='+encodeURIComponent(document.getElementById('ed').value)
  +'&assignee='+encodeURIComponent(document.getElementById('ea').value)
  +'&due='+encodeURIComponent(document.getElementById('eu').value);
  const r=await fetch('/rooms/'+R+'/tasks/'+el.dataset.a+'/edit?token='+T+q,{{method:'POST'}});
  if(!r.ok){{alert('Save failed: '+r.status);return;}}
  taskList();load();}}
async function taskDone(el){{const r=await fetch('/rooms/'+R+'/tasks/'+el.dataset.a+'/done?token='+T,{{method:'POST'}});
  if(!r.ok){{alert('Done failed: '+r.status);return;}}
  taskList();load();}}
async function taskReopen(el){{const r=await fetch('/rooms/'+R+'/tasks/'+el.dataset.a+'/reopen?token='+T,{{method:'POST'}});
  if(!r.ok){{alert('Reopen failed: '+r.status);return;}}
  taskList();load();}}
async function taskDel(el){{if(!confirm('Delete this task?'))return;
  const r=await fetch('/rooms/'+R+'/tasks/'+el.dataset.a+'/delete?token='+T,{{method:'POST'}});
  if(!r.ok){{alert('Delete failed: '+r.status);return;}}
  taskList();load();}}
async function pollList(){{const box=document.getElementById('polls');
  if(!box)return;
  const r=await fetch('/rooms/'+R+'/polls?token='+T);
  if(!r.ok){{box.innerHTML='';return;}}
  const items=await r.json();let h='';
  items.forEach(p=>{{h+=pollHTML(p);}});
  box.innerHTML=h||'<p class="dim empty-note">No votes running. + Vote asks the room.</p>';}}
function pollHTML(p){{let h='<div class="card poll"><b>'+esc(p.question)+'</b> <span class=meta>'+esc(p.state)+' · '+p.total+' votes</span>';
  p.options.forEach((o,i)=>{{const mine=p.my_vote===i?' ★':'';
    h+='<br>';
    if(p.state==='open')h+='<button data-a="'+p.id+'" data-o="'+i+'" onclick="pollVote(this)">'+esc(o)+'</button>';
    else h+='<b>'+esc(o)+'</b>';
    h+=' '+p.tally[i]+mine;
    if(p.by_option[i].length)h+=' <span class=meta>('+p.by_option[i].map(esc).join(', ')+')</span>';}});
  if(p.state==='open')h+='<br><button data-a="'+p.id+'" onclick="pollClose(this)">Close</button>';
  h+='</div>';return h;}}
function pollNew(){{const box=document.getElementById('polls');
  if(newGuard(box))return;
  const d=document.createElement('div');d.className='card newform';
  d.innerHTML='<b>New vote</b><br><input id=pq placeholder="Question?" style="width:90%">'
    +'<input id=po0 placeholder="Option 1" style="width:44%">'
    +'<input id=po1 placeholder="Option 2" style="width:44%">'
    +'<input id=po2 placeholder="Option 3 (optional)" style="width:44%">'
    +'<input id=po3 placeholder="Option 4 (optional)" style="width:44%">'
    +'<br><button onclick="pollCreate()">Start vote</button>';
  box.prepend(d);}}
async function pollCreate(){{const opts=[0,1,2,3].map(i=>document.getElementById('po'+i).value.trim()).filter(v=>v);
  if(opts.length<2){{alert('Give at least 2 options.');return;}}
  const q='&question='+encodeURIComponent(document.getElementById('pq').value)
    +'&options='+encodeURIComponent(JSON.stringify(opts));
  const r=await fetch('/rooms/'+R+'/polls?token='+T+q,{{method:'POST'}});
  if(!r.ok){{alert('Ask failed: '+r.status);return;}}
  pollList();}}
async function pollVote(el){{const r=await fetch('/rooms/'+R+'/polls/'+el.dataset.a+'/vote?token='+T+'&option='+el.dataset.o,{{method:'POST'}});
  if(!r.ok){{alert('Vote failed: '+r.status);return;}}
  pollList();}}
async function pollClose(el){{const r=await fetch('/rooms/'+R+'/polls/'+el.dataset.a+'/close?token='+T,{{method:'POST'}});
  if(!r.ok){{alert('Close failed: '+r.status);return;}}
  pollList();load();}}
async function remList(){{const box4=document.getElementById('rems');
  if(!box4)return;
  const r=await fetch('/rooms/'+R+'/reminders?token='+T);
  if(!r.ok){{box4.innerHTML='';return;}}
  const j=await r.json();
  const sel=document.getElementById('remindtime');
  if(sel){{sel.style.display=(ISMANAGE&&!ISSOLO)?'':'none';
    if(document.activeElement!==sel)sel.value=j.sched;}}
  let h='';
  j.reminders.forEach(m=>{{h+=remHTML(m);}});
  h+='<div class=card><b>New reminder</b><br><input id=rw placeholder="Remind what?" style="width:90%">'
    +'<input id=rd placeholder="Due: tomorrow, Friday…" style="width:44%">'
    +'<input id=ro placeholder="Owner" style="width:44%">'
    +'<br><button onclick="remCreate()">Add reminder</button></div>';
  box4.innerHTML=h;}}
function remHTML(m){{return '<div class="card prop'+(m.done?' done':'')+'"><b>'+esc(m.text)+'</b>'
  +'<div class=meta>'+(m.owner?esc(m.owner)+' · ':'')+(m.due_text?esc(dueLabel(m.due_text)):'no date')
  +(m.flag?(' · <b>'+esc(m.flag)+'</b>'):'')+(m.done?' · done':'')+'</div>'
  +'<button data-p="'+m.id+'" onclick="remEdit(this)">Edit</button>'
  +' <button data-p="'+m.id+'" data-d="'+(m.done?0:1)+'" onclick="remDone(this)">'+(m.done?'Undo':'Done')+'</button>'
  +' <button data-p="'+m.id+'" onclick="remDelete(this)">Delete</button></div>';}}
async function remEdit(el){{const r=await fetch('/rooms/'+R+'/reminders?token='+T);
  const j=await r.json();const m=j.reminders.filter(x=>x.id==el.dataset.p)[0];
  if(!m)return;
  el.parentElement.innerHTML='<input id=ew value="'+escQ(m.text)+'" style="width:90%">'
    +'<input id=ed value="'+escQ(m.due_text||'')+'" placeholder="Due" style="width:44%">'
    +'<input id=eo value="'+escQ(m.owner||'')+'" placeholder="Owner" style="width:44%">'
    +'<br><button data-p="'+m.id+'" onclick="remSave(this)">Save</button>';}}
async function remSave(el){{const q='&text='+encodeURIComponent(document.getElementById('ew').value)
  +'&due='+encodeURIComponent(document.getElementById('ed').value)
  +'&owner='+encodeURIComponent(document.getElementById('eo').value);
  const r=await fetch('/rooms/'+R+'/reminders/'+el.dataset.p+'?token='+T+q,{{method:'POST'}});
  if(!r.ok){{alert('Save failed: '+r.status);return;}}
  remList();}}
async function remCreate(){{const q='&text='+encodeURIComponent(document.getElementById('rw').value)
  +'&due='+encodeURIComponent(document.getElementById('rd').value)
  +'&owner='+encodeURIComponent(document.getElementById('ro').value);
  const r=await fetch('/rooms/'+R+'/reminders?token='+T+q,{{method:'POST'}});
  if(!r.ok){{alert('Remind failed: '+r.status);return;}}
  remList();}}
async function remDone(el){{const r=await fetch('/rooms/'+R+'/reminders/'+el.dataset.p+'?token='+T
  +'&done='+(el.dataset.d==='1'),{{method:'POST'}});
  if(r.ok)remList();}}
async function remDelete(el){{if(!confirm('Delete this reminder?'))return;
  await fetch('/rooms/'+R+'/reminders/'+el.dataset.p+'?token='+T,{{method:'DELETE'}});
  remList();}}
async function setRemindTime(v){{const r=await fetch('/rooms/'+R+'/remind-time?token='+T
  +'&at='+encodeURIComponent(v.trim()),{{method:'POST'}});
  if(!r.ok)alert('Use HH:MM, 24-hour, or off.');
  remList();}}
async function remindNow(){{const r=await fetch('/rooms/'+R+'/remind-now?token='+T,{{method:'POST'}});
  if(!r.ok){{alert('Remind refused: '+r.status);return;}}
  const j=await r.json();
  if(!j.posted)document.getElementById('workout').innerHTML='Nothing open — no nudge posted.';
  const ms=await load();
  if(j.posted){{const n=(ms||[]).filter(m=>m.kind==='system'&&/^Reminder/.test(m.body||'')).pop();
    if(n){{document.getElementById('nudgetxt').textContent=n.body;document.getElementById('nudgeback').classList.add('show');}}}}}}
function showRemind(m){{document.getElementById('nudgetxt').textContent=m.body;
  document.getElementById('nudgeback').classList.add('show');
  const e2=document.getElementById('emptyc');if(e2)e2.remove();
  show('room [system]',m.body,box2);}}
function dismissNudge(){{document.getElementById('nudgeback').classList.remove('show');}}
function newChat(){{document.getElementById('nn').value=ME;
  document.getElementById('newback').classList.add('show');}}
function newChatHide(){{document.getElementById('newback').classList.remove('show');}}
async function newChatGo(){{const m=document.getElementById('nm').value||'Untitled mission';
  const n=document.getElementById('nn').value.trim();
  if(!n){{alert('Type your name');return;}}
  const r=await fetch('/rooms?mission='+encodeURIComponent(m)+'&name='+encodeURIComponent(n),{{method:'POST'}});
  const j=await r.json();
  location='/rooms/'+j.room_id+'/app?token='+j.token;}}
async function sidesList(){{const sec=document.getElementById('sidesec');
  if(!sec)return;
  if(ISSOLO||PARENT){{sec.style.display='none';return;}}
  const r=await fetch('/rooms/'+R+'/sides?token='+T);
  if(!r.ok)return;
  const s=await r.json();
  document.getElementById('sides').innerHTML=s.length?s.map(x=>'<button data-s="'+x.room_id+'" onclick="sideOpen(this)">'+esc(x.mission||x.room_id)+'</button>').join(' '):'<p class=dim>None yet — describe one below.</p>';}}
async function sideOpen(el){{const r=await fetch('/rooms/'+el.dataset.s+'/open-side?ptoken='+T,{{method:'POST'}});
  if(!r.ok){{alert('Open failed: '+r.status);return;}}
  const j=await r.json();
  location='/rooms/'+el.dataset.s+'/app?token='+j.token;}}
async function sidePicker(){{const row=document.getElementById('sidepickrow');
  if(!row)return;
  row.style.display=(ISSOLO||PARENT)?'none':'';}}
async function sidePickOpen(){{const el=document.getElementById('sidepick');
  if(!el)return;
  const r=await fetch('/rooms/'+R+'/members?token='+T);
  if(!r.ok){{el.innerHTML='<p class=dim>Could not load people.</p>';el.style.display='';return;}}
  const ms=await r.json(),sel=window._sidepick||[];
  el.innerHTML=ms.filter(m=>m.name!==ME).map(m=>'<label><input type=checkbox class=sidewho value="'+m.id+'"'
    +(sel.includes(m.id)?' checked':'')+'> '+esc(m.name)+' · '+esc(m.nick)+'</label>').join(' ')
    +'<br><button onclick="sidePickDone()">Done</button> <button class=quiet onclick="sidePickCancel()">Cancel</button>';
  el.style.display='';}}
function sidePickDone(){{const el=document.getElementById('sidepick');
  window._sidepick=[...document.querySelectorAll('.sidewho:checked')].map(c=>c.value);
  if(el)el.style.display='none';
  const b=document.getElementById('sidepickbtn'),n=(window._sidepick||[]).length;
  if(b)b.textContent=n?'Select people ('+n+')':'Select people';}}
function sidePickCancel(){{const el=document.getElementById('sidepick');
  if(el)el.style.display='none';}}
async function roster(){{const sec=document.getElementById('rostersec');
  if(!sec)return;
  if(!PARENT||!ISMANAGE){{sec.style.display='none';return;}}
  sec.style.display='';
  const r=await fetch('/rooms/'+R+'/roster?token='+T);
  if(!r.ok)return;
  const j=await r.json();
  document.getElementById('rosterpick').innerHTML=j.main.length?j.main.map(m=>'<option value="'+m.id+'">'+esc(m.name)+' · '+esc(m.nick)+'</option>').join(''):'<option value="">Everyone is in</option>';}}
async function rosterAdd(){{const p=document.getElementById('rosterpick');
  if(!p.value)return;
  const r=await fetch('/rooms/'+R+'/roster/add?token='+T+'&mid='+p.value,{{method:'POST'}});
  document.getElementById('roomout').innerHTML=r.ok?'Added to the side room.':'Add refused: '+r.status;
  if(r.ok){{roster();load();}}}}
async function sideCreate(){{const i=document.getElementById('sideinput');
  const who=(window._sidepick||[]).join(',');
  const r=await fetch('/rooms/'+R+'/side?token='+T+'&mission='+encodeURIComponent(i.value)+'&mids='+encodeURIComponent(who),{{method:'POST'}});
  if(!r.ok){{alert('Split failed: '+r.status);return;}}
  const j=await r.json();
  location='/rooms/'+j.room_id+'/app?token='+j.token;}}
async function shareBack(){{const r=await fetch('/rooms/'+R+'/share-back?token='+T,{{method:'POST'}});
  if(!r.ok){{alert('Share refused: '+r.status);return;}}
  document.getElementById('roomout').innerHTML='Reported to the main room.';tab('room');}}
function goMain(){{try{{const s=JSON.parse(localStorage.getItem('roomind.rooms')||'[]');
  const pin=s.filter(p=>p.rid===PARENT)[0];
  if(pin){{location='/rooms/'+pin.rid+'/app?token='+pin.token;return;}}}}catch(e){{}}
  location='/';}}
function connect(){{const ws=new WebSocket(
  (location.protocol=='https:'?'wss:':'ws:')+'//'+location.host
  +'/rooms/'+R+'/live?token='+T);
  ws.onmessage=e=>{{const m=JSON.parse(e.data);
    const mk=m.kind||'chat';
    if((mk==='chat'||mk==='ask'||mk==='answer'||mk==='system'||mk==='dissent')&&(m.id||0)>_seen)_seen=m.id;
    if(m.kind==='closed'){{location.reload();return;}}
    if(m.kind==='kicked'){{alert('You were kicked from the room.');location='/';return;}}
    if(m.id&&window._shown&&window._shown.has(m.id)){{if(m.kind==='remind'){{document.getElementById('nudgetxt').textContent=m.body;document.getElementById('nudgeback').classList.add('show');ping('work');}}return;}}
    if(m.id&&window._shown)window._shown.add(m.id);
    if(m.kind==='locked'){{show('room [system]',m.body,box2);ping('chat');return;}}
    if(m.kind==='muted'){{state();return;}}
    if(m.kind==='remind'){{showRemind(m);ping('work');return;}}
    if(m.kind==='system'&&/lock/.test(m.body||'')){{state();}}
    const e2=document.getElementById('emptyc');if(e2)e2.remove();
    if(m.kind==='dissent'){{showDissent(m,document.getElementById('props'));tab('plan');return;}}
    if(m.kind==='redteam'){{redList();ping('plan');return;}}
    if(m.kind==='proposal'){{propList();ping('plan');return;}}
    if(m.kind==='artifact'){{artList();ping('work');return;}}
    if(m.kind==='task'){{taskList();ping('work');return;}}
    if(m.kind==='poll'){{pollList();ping('work');return;}}
    if(m.kind==='reminder'){{remList();ping('work');return;}}
    if(m.kind==='answer'){{slotAns(m);ping('chat');return;}}
    if(m.kind==='ask'){{const e1=document.getElementById('echo');
      if(e1&&m.author===ME&&m.body===window._retry){{
        e1.outerHTML='<div class="msg me"><div class=who>'+esc(who(m))
          +'</div><div class=txt>'+esc(m.body)+'</div></div>';return;}}
      show(who(m),m.body,box,true);box.innerHTML+=slotHTML(m.id);box.scrollTop=box.scrollHeight;return;}}
    if(m.kind==='system'){{try{{sidesList();}}catch(_){{}}ping('room');ping('share');}}
    show(who(m)+(m.kind&&m.kind!=='chat'?' ['+m.kind+']':''),m.body,box2,mine(m));ping('chat');}};
  ws.onclose=e=>{{if(e&&e.code===4000){{location.reload();return;}}
    if(e&&e.code===4001){{location='/';return;}}
    setTimeout(connect,2000);}};
  ws.onopen=()=>{{if(window._wsWasOpen)load();window._wsWasOpen=true;}};
  window._ws=ws;}}
function send(){{const i=document.getElementById('t');
  window._ws.send(i.value);i.value='';i.style.height='auto';}}
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
    +'</div><div class=txt>'+esc(v)+'</div></div>';i.value='';i.style.height='auto';
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
      document.getElementById('rsn').innerHTML='';
      b.disabled=false;load();}}
    if(d.error){{es.close();
      document.getElementById('rsn').innerHTML=d.error+" <button onclick='askRetry()'>Retry</button>";
      b.disabled=false;load();}}}};
  es.onerror=()=>{{es.close();
    document.getElementById('rsn').innerHTML="Send failed. <button onclick='askRetry()'>Retry</button>";
    b.disabled=false;load();}};}}
function renderBrief(j){{let h=j.summary?'<p>'+esc(j.summary)+'</p>':'';
  if((j.decisions||[]).length)h+='<p><b>Decisions</b></p>';
  (j.decisions||[]).forEach(d=>{{h+='<p>• <b>'+esc(d.what||'')+'</b>'
    +(d.who?' — '+esc(d.who):'')+(d.why?' ('+esc(d.why)+')':'')+'</p>';}});
  if((j.open||[]).length)h+='<p><b>Open</b></p>';
  (j.open||[]).forEach(o=>{{h+='<p>○ '+esc(o)+'</p>';}});
  const oks=Object.keys(j.owners||{{}});
  if(oks.length)h+='<p><b>Owners</b></p>';
  oks.forEach(k=>{{h+='<p>'+esc(k)+': '
    +esc((j.owners[k]||[]).join(', '))+'</p>';}});
  const mains=(j.quotes||[]).filter(q=>(q.room||'')==='main');
  const sides=(j.quotes||[]).filter(q=>(q.room||'')!=='main');
  if(mains.length)h+='<p><b>Ledger</b></p>';
  mains.forEach(q=>{{h+='<p>• '+esc(q.text||'')+'</p>';}});
  if(sides.length)h+='<p><b>Side rooms</b></p>';
  sides.forEach(q=>{{h+='<p><i>'+esc(q.room||'')
    +':</i> '+esc(q.text||'')+'</p>';}});
  if(j.sides_hidden)h+='<p class=dim>'+j.sides_hidden+(j.sides_hidden===1?' side room hidden.':' side rooms hidden.')+'</p>';
  return h||'<p class=dim>Quiet room — nothing to sum up yet.</p>';}}
async function brief(){{document.getElementById('planout').innerHTML='Briefing…';
  const inc=document.getElementById('incside').checked?'&include_sides=true':'';
  const r=await fetch('/rooms/'+R+'/brief?token='+T+inc);
  document.getElementById('planout').innerHTML=resultBox('Summary',renderBrief(await r.json()));}}
function renderLedger(rows){{if(!rows||!rows.length)
    return '<p class=dim>No stamped decisions yet.</p>';
  return rows.map(l=>'<p>• <b>'+esc(l.what||'')+'</b>'
    +(l.who?' — '+esc(l.who):'')+(l.deadline?' ('+esc(dueLabel(l.deadline))+')':'')
    +' <span class=meta>'+esc(l.status||'open')+'</span></p>').join('');}}
async function ledger(){{const r=await fetch('/rooms/'+R+'/ledger?token='+T);
  document.getElementById('planout').innerHTML=resultBox('Decisions',renderLedger(await r.json()));}}
function renderCheck(j){{if(!j.triggered)return '<p>All clear — nothing to flag.</p>';
  let h='';
  if(j.card)h+='<p><b>Judge fired:</b> '+esc(j.card.question||'card below')+'</p>';
  if(j.proposal)h+='<p><b>Logged:</b> '+esc(j.proposal.what||'a decision')+'</p>';
  return h;}}
async function check(){{document.getElementById('planout').innerHTML='Judging the thread…';
  const r=await fetch('/rooms/'+R+'/dissent/check?token='
  +T,{{method:'POST'}});
  document.getElementById('planout').innerHTML=resultBox('Review',renderCheck(await r.json()));load();}}
async function mute(){{const r=await fetch('/rooms/'+R+'/dissent/mute?token='+T
  +'&on='+(!window._muted),{{method:'POST'}});
  if(!r.ok){{alert('Mute refused: '+r.status);return;}}
  state();}}
async function invite(u){{const r=await fetch('/rooms/'+R+'/invites?token='+T
  +'&uses='+u+'&hours=0',{{method:'POST'}});
  if(!r.ok){{document.getElementById('invout').innerHTML='Denied (owner or operator only)';return;}}
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
  document.getElementById('roomout').innerHTML=h;}}
async function leaveAs(id){{const r=await fetch('/rooms/'+R+'/leave?token='+T+'&successor_id='+id,{{method:'POST'}});
  if(r.ok)location='/';else alert('Leave failed: '+r.status);}}
async function links(){{const r=await fetch('/rooms/'+R+'/invites?token='+T);
  if(!r.ok){{document.getElementById('invout').innerHTML='Invites failed: '+r.status;return;}}
  const ls=await r.json();const now=new Date().toLocaleTimeString();
  let h='<div data-links=1><p>Room <b>'+R+'</b> '
    +'<button data-c="'+R+'" onclick="copyTxt(this)" title="Copy room id">Copy</button>'
    +' <span class=meta>Updated '+now+'</span></p><p class=dim>Each join spends one use. Leaving never refills it.</p>';
  ls.forEach(l=>{{h+='<div class=invrow><span class=meta>Invite code</span><code>'+l.token+'</code>'
    +"<button data-c='"+l.token+"' onclick='copyTxt(this)' title='Copy invite'>Copy</button>"
    +"<span class=meta>"+l.used+" joined · "+l.left+" left of "+l.max_uses+" · "+l.role+"</span>"
    +"<button data-c='"+l.token+"' onclick='topup(this.dataset.c)'>+5 seats</button></div>";}});
  h+='</div>';
  document.getElementById('invout').innerHTML=resultBox('Invites',ls.length?h:'No invites');
  if(!window._lp){{window._lp=setInterval(()=>{{
    if(document.querySelector('#invout [data-links]'))links();}},5000);}}}}
async function topup(code){{const r=await fetch('/rooms/'+R+'/invites/topup?token='+T
  +'&invite='+code+'&add_uses=5',{{method:'POST'}});
  if(!r.ok){{document.getElementById('invout').innerHTML='Top-up failed: '+r.status;return;}}
  links();}}
async function people(){{const r=await fetch('/rooms/'+R+'/members?token='+T);
  if(!r.ok){{document.getElementById('roomout').innerHTML='People failed: '+r.status;return;}}
  const ms=await r.json();let h='<div>';
  ms.forEach(m=>{{let row="<p><b>"+esc(m.name)+"</b> · "+esc(m.nick)+" ("+m.role+")";
    if(ISOWNER){{row+=" <button data-m='"+m.id+"' onclick='makeOwner(this.dataset.m)'>Make owner</button>";
      row+=" <button data-o='"+m.id+"' onclick='makeOp(this.dataset.o)'>Make operator</button>";}}
    if(ISMANAGE&&(m.role==='member'||(ISOWNER&&m.role==='operator'))){{
      row+=" <button data-k='"+m.id+"' data-n=\\""+escQ(m.name)+"\\" onclick='kickSeat(this)'>Remove</button>";}}
    h+=row+"</p>";}});
  document.getElementById('roomout').innerHTML=resultBox('People',h+'</div>');}}
async function team(){{const r=await fetch('/rooms/'+R+'/teammates?token='+T);
  if(!r.ok){{document.getElementById('workout').innerHTML='Team failed: '+r.status;return;}}
  const ms=await r.json();
  const ra=await fetch('/rooms/'+R+'/away?token='+T);
  const aws=ra.ok?await ra.json():[];
  let h='<div><p class=dim>@Name to ask</p>';
  ms.forEach(m=>{{h+="<p><b>@"+esc(m.name)+"</b> · "+esc(m.role||'teammate')+"<br><span class=meta>"+esc(m.instructions||'no instructions')+"</span>";
    if(ISMANAGE){{h+=" <button data-t='"+m.id+"' onclick='teamEdit(this)'>Edit</button>";
      h+=" <button data-t='"+m.id+"' onclick='teamDel(this)'>Remove</button>";}}
    h+="</p>";}});
  if(ISMANAGE)h+='<p><b>Add</b><br><input id=tn placeholder="Name" style="width:30%">'
    +'<input id=tr placeholder="Role" style="width:30%">'
    +'<input id=ti placeholder="Instructions" style="width:90%">'
    +'<br><button onclick="teamAdd()">Add teammate</button></p>';
  h+='<p><b>Away tasks</b> — work while you are gone</p>';
  aws.forEach(a=>{{h+='<div class="card task'+(a.status==='done'?' done':'')+'"><b>'+esc(a.instruction)+'</b> <span class=meta>@'+esc(a.teammate_name)+' · by '+esc(a.due_text)+' · '+esc(a.status)+'</span>';
    if(a.answer)h+='<div class=meta>Answer</div><div class=txt>'+esc(a.answer)+'</div>';
    h+=" <button data-t='"+a.id+"' onclick='awayDel(this)'>Delete</button></div>";}});
  h+='<p><select id=aw>'+ms.map(m=>'<option value="'+m.id+'">@'+esc(m.name)+'</option>').join('')+'</select>'
    +'<input id=ai placeholder="Do what while away?" style="width:60%">'
    +'<br><input id=au placeholder="Due (required), e.g. today" style="width:90%">'
    +'<br><button onclick="teamAssign()">Assign task</button></p>';
  document.getElementById('workout').innerHTML=resultBox('Team',h+'</div>');}}
async function teamAdd(){{const q='&name='+encodeURIComponent(document.getElementById('tn').value)
  +'&role='+encodeURIComponent(document.getElementById('tr').value)
  +'&instructions='+encodeURIComponent(document.getElementById('ti').value);
  const r=await fetch('/rooms/'+R+'/teammates?token='+T+q,{{method:'POST'}});
  document.getElementById('workout').innerHTML=r.ok?'Teammate added.':'Add failed: '+r.status;
  if(r.ok)team();}}
async function teamEdit(el){{const r=await fetch('/rooms/'+R+'/teammates?token='+T);
  const ms=await r.json();const m=ms.filter(x=>x.id==el.dataset.t)[0];
  if(!m)return;
  el.parentElement.innerHTML='<input id=en value="'+escQ(m.name)+'" style="width:30%">'
    +'<input id=er value="'+escQ(m.role||'')+'" style="width:30%">'
    +'<input id=ei value="'+escQ(m.instructions||'')+'" style="width:90%">'
    +'<br><button data-t="'+m.id+'" onclick="teamSave(this)">Save</button>';}}
async function teamSave(el){{const q='&name='+encodeURIComponent(document.getElementById('en').value)
  +'&role='+encodeURIComponent(document.getElementById('er').value)
  +'&instructions='+encodeURIComponent(document.getElementById('ei').value);
  const r=await fetch('/rooms/'+R+'/teammates/'+el.dataset.t+'/edit?token='+T+q,{{method:'POST'}});
  document.getElementById('workout').innerHTML=r.ok?'Saved.':'Save failed: '+r.status;
  if(r.ok)team();}}
async function teamDel(el){{if(!confirm('Remove this teammate?'))return;
  const r=await fetch('/rooms/'+R+'/teammates/'+el.dataset.t+'?token='+T,{{method:'DELETE'}});
  document.getElementById('workout').innerHTML=r.ok?'Removed.':'Remove failed: '+r.status;
  if(r.ok)team();}}
async function teamAssign(){{const ii=document.getElementById('ai').value.trim(),uu=document.getElementById('au').value.trim();
  if(!ii||!uu){{document.getElementById('workout').innerHTML='Name the job and a due date like today or Friday.';return;}}
  const q='&teammate='+encodeURIComponent(document.getElementById('aw').value)
  +'&instruction='+encodeURIComponent(ii)
  +'&due='+encodeURIComponent(uu);
  const r=await fetch('/rooms/'+R+'/away?token='+T+q,{{method:'POST'}});
  if(!r.ok){{let w='Assign failed: '+r.status;
    try{{const e=await r.json();if(e&&e.Detail)w=e.Detail;}}catch(_){{}}
    document.getElementById('workout').innerHTML=esc(w);return;}}
  document.getElementById('workout').innerHTML='Assigned. Runs in the background when due.';team();}}
async function awayDel(el){{if(!confirm('Delete this away task?'))return;
  const r=await fetch('/rooms/'+R+'/away/'+el.dataset.t+'/delete?token='+T,{{method:'POST'}});
  document.getElementById('workout').innerHTML=r.ok?'Deleted.':'Delete failed: '+r.status;
  if(r.ok)team();}}
async function makeOwner(id){{const r=await fetch('/rooms/'+R+'/owner?token='+T+'&member_id='+id,{{method:'POST'}});
  document.getElementById('roomout').innerHTML=r.ok?'Crown moved.':"Transfer failed: "+r.status;}}
async function makeOp(id){{const r=await fetch('/rooms/'+R+'/operators?token='+T+'&member_id='+id,{{method:'POST'}});
  document.getElementById('roomout').innerHTML=r.ok?'Operator named.':"Grant failed: "+r.status;people();}}
async function closeRoom(){{if(!confirm('Close this room forever for everyone?'))return;
  const r=await fetch('/rooms/'+R+'?token='+T,{{method:'DELETE'}});
  if(r.ok)location='/';else alert('Close failed: '+r.status);}}
function memToggle(){{window._memx=!window._memx;memKeys();}}
async function memKeys(){{const el=document.getElementById('memkeys');
  if(!el)return;
  const r=await fetch('/rooms/'+R+'/memory?token='+T);
  if(!r.ok)return;
  const ks=await r.json();
  if(!ks.length){{el.textContent='Remembers nothing yet.';return;}}
  const pill=k=>'<button data-k="'+escQ(k.key)
    +'" onclick="forgetKeyBy(this)" title="Forget this">'+esc(k.key)+' → '
    +esc(k.value)+' ×</button>';
  if(ks.length<=3||window._memx)el.innerHTML='Remembers: '+ks.map(pill).join(' ')
    +(ks.length>3?' <button onclick="memToggle()">hide</button>':'');
  else el.innerHTML='Remembers: '+ks.slice(0,3).map(pill).join(' ')
    +' <button onclick="memToggle()">+'+(ks.length-3)+' more</button>';}}
async function forgetKeyBy(el){{
  await fetch('/rooms/'+R+'/memory?token='+T+'&key='+encodeURIComponent(el.dataset.k),
  {{method:'DELETE'}});memKeys();}}
async function evalBar(){{try{{
  const r=await fetch('/rooms/'+R+'/eval?token='+T);
  if(!r.ok)return;
  const e=await r.json();
  const ap=e.approval;
  const pc=v=>v==null?'—':Math.round(v*100)+'%';
  let h='Approval: '+(ap.n?pc(ap.pct)+' ('+ap.n+' votes)':'—');
  document.getElementById('strip').innerHTML=h;
}}catch(_){{}}}}
async function evalPanel(){{const r=await fetch('/rooms/'+R+'/eval?token='+T);
  const e=await r.json(),g=e.golden,ap=e.approval;let h='<div>';
  const pc=v=>v==null?'—':Math.round(v*100)+'%';
  if(!g)h+='<p>Exam never run.</p>';
  else{{h+='<p>Golden '+g.score+'/'+g.total
    +' · Precision '+pc(g.precision)+' · Recall '+pc(g.recall)
    +' · False alarms: '+(g.false_alarms.join(', ')||'none')
    +' · Misses: '+(g.misses.join(', ')||'none')+'</p>';
  g.details.forEach(d=>{{h+='<p>'+(d.hit?'✓':'✗')+' <b>'+d.id+'</b> '
    +esc(d.title)+' — '+(d.expected?'must fire':'must silence')
    +' · '+(d.fired?'fired':'silent')+' · '+esc(d.why)+'</p>';}});}}
  h+='<p>Approval: '+(ap.n?pc(ap.pct)+' ('+ap.n+' votes)':'no votes yet')
    +' · Cost: '+(e.cost_per_decision==null?'—':'$'+e.cost_per_decision.toFixed(3)+'/decision')+'</p>';
  const tr=e.trust;
  h+='<p>Trust: '+tr.word+' · fair '
    +(tr.n?Math.round(tr.pct*100)+'% ('+tr.n+')':'no verdicts yet')+'</p>';
  if(ISMANAGE)h+="<p><button onclick='runExam()'>Test the referee</button> "
    +"Ten judge calls. Cost lands in the meter.</p>";
  h+='</div>';document.getElementById('roomout').innerHTML=resultBox('Eval breakdown',h);tab('room');}}
async function runExam(){{if(window._examRun){{document.getElementById('roomout').innerHTML='Exam already running — results land here when done.';return;}}
  window._examRun=true;
  document.getElementById('roomout').innerHTML='Examining, one call per case… you can keep working, results appear here.';
  const x=await fetch('/rooms/'+R+'/eval/exam?token='+T,{{method:'POST'}});
  window._examRun=false;
  if(x.status===409){{document.getElementById('roomout').innerHTML='Exam already running — results land here when done.';return;}}
  if(!x.ok){{document.getElementById('roomout').innerHTML='Exam failed: '+x.status;return;}}
  evalBar();evalPanel();meter();}}
async function kickSeat(el){{const id=el.dataset.k,nm=el.dataset.n;
  if(!confirm('Remove '+nm+' from the room? Their access ends at once. Rejoin needs a fresh invite.'))return;
  const r=await fetch('/rooms/'+R+'/members/'+id+'/kick?token='+T,{{method:'POST'}});
  document.getElementById('roomout').innerHTML=r.ok?nm+' removed.':'Remove refused: '+r.status;
  if(r.ok){{people();roster();}}}}
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
  window._muted=!!s.dissent_muted;
  const M=document.getElementById('mutebtn');if(M){{M.textContent=s.dissent_muted?'Unmute judge':'Mute judge';M.classList.toggle('muted',!!s.dissent_muted);}}
  const MS=document.getElementById('mutestate');if(MS){{MS.textContent=s.dissent_muted?'Judge muted · auto-cards off':'Judge listening';MS.className=s.dissent_muted?'mutebadge muted':'mutebadge off';}}
  const JS=document.getElementById('judgestate');
  if(JS){{const jl=s.judge_last;const JM={{proposal:'logged decision',card:'posted card',queued:'queued card',armed:'armed'}};
    JS.textContent=jl?('Judge '+(JM[jl.outcome]||jl.outcome)+' · '+new Date(jl.at*1000).toLocaleTimeString()):'';}}
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
    const shortM=m=>{{return String(m||'').split('-')
      .map(w=>w.charAt(0).toUpperCase()+w.slice(1)).join(' ');}};
    const opts=[cur].concat(
      (window._models||[]).filter(m=>m&&m!==cur));
    sel.innerHTML=opts.map(m=>"<option value='"+esc(m)+"'>"
      +esc(shortM(m))+"</option>").join('')
      +"<option value='__other__'>Other…</option>";
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
  let h='Cost $'+(u.spent_usd||0).toFixed(4)+' of $'+(u.cap_usd||0)
    +' · Model: '+esc(mine);
  Object.keys(u.by_model||{{}}).forEach(m=>{{const b=u.by_model[m];
    h+='<br>'+esc(m)+': $'+b.usd+' · '+b.tin+' in / '+b.tout+' out';}});
  document.getElementById('meter').innerHTML=h;}}
function sideRooms(){{try{{
  let tab='';try{{tab=sessionStorage.getItem('roomind.tab')||'';}}catch(e){{}}
  let s=[];try{{s=JSON.parse(localStorage.getItem('roomind.rooms')||'[]');}}catch(e){{}}
  if(tab)s=s.filter(p=>p.tab===tab);
  const el=document.getElementById('rooms');if(!el)return;
  if(!s.length){{el.innerHTML='<p class=dim>Join a room and it lands here.</p>';return;}}
  el.innerHTML=s.map(p=>'<div class=rmrow><button class="rm'+(p.rid===R?' on':'')
    +'" data-u="'+p.rid+'|'+p.token+'" onclick="openRoom(this.dataset.u)">'
    +(p.parent?'↳ ':'')+esc(p.mission||p.rid)+'</button>'
    +'<button class=dots data-u="'+p.rid+'|'+p.token+'" data-r="'+(p.role||'member')+'" onclick="roomMenu(this,event)">⋮</button></div>').join('');
}}catch(e){{}}}}
function openRoom(u){{const i=u.split('|');location='/rooms/'+i[0]+'/app?token='+i[1];}}
function roomMenu(el,ev){{ev.stopPropagation();
  const m=document.getElementById('rmmenu');
  const r=el.getBoundingClientRect();
  m.innerHTML='<button data-u="'+el.dataset.u+'" onclick="rmLeave(this)">Leave room</button>'
    +(el.dataset.r==='owner'?'<button data-u="'+el.dataset.u+'" onclick="rmClose(this)">Close room</button>':'');
  m.style.left=Math.min(r.left,innerWidth-180)+'px';m.style.top=r.bottom+4+'px';
  m.classList.toggle('show');}}
document.addEventListener('click',()=>{{const m=document.getElementById('rmmenu');if(m)m.classList.remove('show');}});
function dropPin(u){{const i=u.split('|');
  try{{let s=JSON.parse(localStorage.getItem('roomind.rooms')||'[]');
    s=s.filter(p=>!(p.rid===i[0]&&p.token===i[1]));
    localStorage.setItem('roomind.rooms',JSON.stringify(s));}}catch(e){{}}
  return i;}}
async function rmLeave(el){{const i=el.dataset.u.split('|');
  const r=await fetch('/rooms/'+i[0]+'/members?token='+i[1]);
  if(!r.ok){{alert('Leave failed: '+r.status);return;}}
  const ms=await r.json();
  if(ms.length<2){{if(!confirm('Last seat. Leaving closes the room forever for everyone. Close it?'))return;}}
  else if(!confirm('Leave this room? Your access ends at once.'))return;
  const q=await fetch('/rooms/'+i[0]+'/leave?token='+i[1],{{method:'POST'}});
  if(!q.ok){{alert('Leave failed: '+q.status);return;}}
  dropPin(el.dataset.u);sideRooms();if(i[0]===R)location='/';}}
async function rmClose(el){{if(!confirm('Close this room forever for everyone?'))return;
  const i=el.dataset.u.split('|');
  const r=await fetch('/rooms/'+i[0]+'?token='+i[1],{{method:'DELETE'}});
  if(!r.ok){{alert('Close refused: '+r.status);return;}}
  dropPin(el.dataset.u);sideRooms();if(i[0]===R)location='/';}}
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


def showcase_page(d: dict) -> str:
    """Public read-only story. Mechanical render, zero model cost."""
    h = ["""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>
<style>body{font-family:system-ui,sans-serif;background:#F7F6F3;
color:#1a1814;max-width:680px;margin:0 auto;padding:2em 1.25em}
h1{letter-spacing:-.02em}h2{margin-top:2em;border-bottom:1px solid #ddd}
p,li{color:#333}.dim{color:#888}.card{background:#fff;border:1px solid #e5e2da;
border-radius:10px;padding:.8em 1em;margin:.6em 0}</style>
</head><body>"""]
    h.append(f"<h1>{escape(d.get('mission') or 'Room')}</h1>")
    h.append("<p class=dim>Read-only showcase. Side rooms stay private."
             " No login, no chat, no model spent.</p>")
    h.append("<h2>People</h2><ul>")
    for m in d.get("people", []):
        h.append(f"<li>{escape(m['name'])} ·{escape(m['nick'])}"
                 f" ({escape(m['role'])})</li>")
    h.append("</ul><h2>Decisions</h2>")
    for row in d.get("ledger", []):
        h.append(f"<div class=card><b>{escape(row['what'])}</b>"
                 f"<br><span class=dim>{escape(row.get('who') or 'unowned')}"
                 f" · {escape(row.get('why') or 'no reason yet')}"
                 f"{' · by ' + escape(row['deadline']) if row.get('deadline') else ''}</span></div>")
    h.append("<h2>Artifacts</h2>")
    for a in d.get("artifacts", []):
        h.append(f"<div class=card><b>{escape(a['title'])}</b>"
                 f" <span class=dim>{escape(a['kind'])} · v{a['version']}"
                 f" · {escape(a['status'])}</span>"
                 f"<p>{escape(a['body'])}</p></div>")
    h.append("<h2>Tasks</h2><ul>")
    for t in d.get("tasks", []):
        h.append(f"<li>{escape(t['title'])} — {escape(t['assignee'] or 'unassigned')}"
                 f"{' · by ' + escape(t['due_text']) if t.get('due_text') else ''}"
                 f" · {escape(t['status'])}</li>")
    h.append("</ul><h2>Votes</h2>")
    for p in d.get("polls", []):
        h.append(f"<div class=card><b>{escape(p['question'])}</b>"
                 f" <span class=dim>{escape(p['state'])} · {p['total']} votes</span>")
        for o, n in zip(p["options"], p["tally"]):
            h.append(f"<br>{escape(o)} — {n}")
        h.append("</div>")
    h.append("<h2>Red team</h2>")
    for c in d.get("redteam", []):
        h.append(f"<div class=card><b>{escape(c['verdict'])}</b>")
        for item in c.get("flaws", []):
            h.append(f"<br>• [{escape(item.get('severity') or 'med')}]"
                     f" {escape(item.get('flaw') or '')} —"
                     f" <i>{escape(item.get('receipt') or '')}</i>")
        if c.get("strongest"):
            h.append(f"<br><b>Holds:</b> {escape(c['strongest'])}")
        h.append("</div>")
    h.append("<h2>Recent chat</h2>")
    for m in d.get("chats", []):
        h.append(f"<div class=card><span class=dim>{escape(m['author'])}"
                 + (f" [{m['kind']}]" if m["kind"] != "chat" else "")
                 + f"</span><br>{escape(m['body'])}</div>")
    h.append("</body></html>")
    return "".join(h)
