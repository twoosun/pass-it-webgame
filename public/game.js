const $=s=>document.querySelector(s); const home=$('#home'),lobby=$('#lobby'),game=$('#game'),canvas=$('#canvas'),ctx=canvas.getContext('2d');
let ws,myId,room={players:[],projectiles:[],status:'lobby'},clockOffset=0,messageUntil=0,explosions=[],impacts=[],shakeUntil=0,visualPlayers=new Map(),audioCtx,musicStage=-1,nextMusicBeat=0,musicStep=0;
function ensureAudio(){try{audioCtx ||= new (window.AudioContext||window.webkitAudioContext)();if(audioCtx.state==='suspended')audioCtx.resume()}catch{}return audioCtx}
function sound(freq=180,duration=.09,type='square'){try{ensureAudio();const o=audioCtx.createOscillator(),g=audioCtx.createGain();o.type=type;o.frequency.value=freq;g.gain.setValueAtTime(.08,audioCtx.currentTime);g.gain.exponentialRampToValueAtTime(.001,audioCtx.currentTime+duration);o.connect(g).connect(audioCtx.destination);o.start();o.stop(audioCtx.currentTime+duration)}catch{}}
function musicTone(freq,duration=.2,gainValue=.025){if(!audioCtx||audioCtx.state!=='running')return;const o=audioCtx.createOscillator(),g=audioCtx.createGain();o.type=musicStage>=3?'sawtooth':'triangle';o.frequency.value=freq;g.gain.setValueAtTime(gainValue,audioCtx.currentTime);g.gain.exponentialRampToValueAtTime(.001,audioCtx.currentTime+duration);o.connect(g).connect(audioCtx.destination);o.start();o.stop(audioCtx.currentTime+duration)}
setInterval(()=>{if(musicStage<0||!audioCtx||audioCtx.state!=='running'||audioCtx.currentTime<nextMusicBeat)return;const gaps=[1.7,1.18,.78,.48,.255],notes=[[82,110],[98,123,147],[110,147,165],[123,165,196],[131,196,247]],set=notes[musicStage]||notes[0];musicTone(set[musicStep++%set.length],musicStage>=3?.18:.32,musicStage===4?.038:.022);if(musicStage>=2&&musicStep%2===0)musicTone(set[0]/2,.22,.018);nextMusicBeat=audioCtx.currentTime+gaps[musicStage];},70);
function explosionSound(){try{audioCtx ||= new AudioContext();const t=audioCtx.currentTime,noise=audioCtx.createBuffer(1,audioCtx.sampleRate*.65,audioCtx.sampleRate),data=noise.getChannelData(0);for(let i=0;i<data.length;i++)data[i]=(Math.random()*2-1)*Math.pow(1-i/data.length,2);const src=audioCtx.createBufferSource(),filter=audioCtx.createBiquadFilter(),gain=audioCtx.createGain();src.buffer=noise;filter.type='lowpass';filter.frequency.setValueAtTime(1800,t);filter.frequency.exponentialRampToValueAtTime(90,t+.6);gain.gain.setValueAtTime(.3,t);gain.gain.exponentialRampToValueAtTime(.001,t+.65);src.connect(filter).connect(gain).connect(audioCtx.destination);src.start();const o=audioCtx.createOscillator(),g=audioCtx.createGain();o.type='sine';o.frequency.setValueAtTime(130,t);o.frequency.exponentialRampToValueAtTime(38,t+.55);g.gain.setValueAtTime(.28,t);g.gain.exponentialRampToValueAtTime(.001,t+.6);o.connect(g).connect(audioCtx.destination);o.start();o.stop(t+.65)}catch{}}
function impact(x,y,color='#fff',strong=true){impacts.push({x,y,color,started:performance.now()});if(strong)shakeUntil=performance.now()+180;}
function show(el){[home,lobby,game].forEach(x=>x.classList.add('hidden'));el.classList.remove('hidden')}
function connect(action){ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}`);ws.onopen=()=>ws.send(JSON.stringify(action));ws.onmessage=e=>handle(JSON.parse(e.data));ws.onclose=()=>{if(!game.classList.contains('hidden')) flash('CONNECTION LOST',999999,'danger')};}
$('#create').onclick=()=>{ensureAudio();connect({type:'create',name:$('#name').value,password:$('#create-password').value})}; $('#join').onclick=()=>{ensureAudio();connect({type:'join',name:$('#name').value,code:$('#code').value,password:$('#join-password').value})};
async function fetchRooms(){try{const rooms=await fetch('/api/rooms',{cache:'no-store'}).then(r=>r.json());$('#room-list').innerHTML=rooms.length?rooms.map(r=>`<div class="room-item"><b>${r.locked?'🔒':'🔓'} ${r.code}</b><span>${r.players}/${r.max}</span><button data-room="${r.code}">SELECT</button></div>`).join(''):'No rooms are waiting.';$('#room-list').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('#code').value=b.dataset.room;$('#join-password').focus()});}catch{$('#room-list').textContent='Could not load rooms.'}}
$('#refresh').onclick=fetchRooms;fetchRooms();setInterval(()=>{if(!home.classList.contains('hidden'))fetchRooms()},5000);
$('#code').onkeydown=e=>{if(e.key==='Enter')$('#join').click()};
$('#room-code').onclick=()=>navigator.clipboard?.writeText($('#room-code').textContent);
$('#start').onclick=()=>{
 ensureAudio();
 const button=$('#start');
 button.textContent='LOADING GAME...'; button.disabled=true;
 if(ws?.readyState===WebSocket.OPEN) ws.send(JSON.stringify({type:'start'}));
 else { button.textContent='SERVER ERROR — REFRESH'; button.disabled=false; }
 setTimeout(()=>{if(!game.classList.contains('hidden'))return;button.disabled=false;renderLobby();$('#lobby-hint') && ($('#lobby-hint').textContent='Refresh the page if the game does not start.');},2500);
};
function handle(m){
 if(m.type==='joined'){
   myId=m.id;
   // Recalculate host controls regardless of message arrival order.
   renderLobby();
   show(lobby);
 }
 if(m.type==='error')$('#error').textContent=m.message;
 if(m.type==='lobby'){room={...room,...m};renderLobby();if(m.status==='lobby')show(lobby)}
 if(m.type==='roundStart'){room.round=m.round;room.endsAt=m.endsAt;show(game);flash(`ROUND ${m.round}`,1800)}
 if(m.type==='state'){room={...room,...m};clockOffset=m.now-Date.now();updateHud()}
 if(m.type==='passed'){impact(m.x,m.y,'#ffdf3e');sound(115,.13,'sawtooth');if(m.to===myId)flash('YOU GOT THE BOMB!',1100,'danger');else if(m.from===myId)flash('PASS!',800,'alert')}
 if(m.type==='parry'){impact(m.x,m.y,'#6ff7ff',false);sound(480,.06,'sine')}
 if(m.type==='parried'){impact(m.x,m.y,'#6ff7ff');sound(760,.15,'square');if(m.playerId===myId)flash('PARRY!',700,'alert')}
 if(m.type==='thrown'&&m.from===myId)flash(`THROW! ${m.throwsLeft} LEFT`,900,'alert')
 if(m.type==='fell'&&m.playerId===myId)flash('YOU FELL!',3000,'danger')
 if(m.type==='explosion'){explosions.push({x:m.x,y:m.y,started:performance.now()});shakeUntil=performance.now()+650;explosionSound()}
 if(m.type==='roundEnd'){const p=room.players.find(x=>x.id===m.loserId),fall=m.reason==='fall';flash(m.loserId===myId?(fall?'YOU FELL!\nROUND LOST':'💥 BOOM!\nROUND LOST'):`${fall?'⬇️':'💥'} ${p?.name||''} ${fall?'FELL!':'BOOM!'}`,3500,'danger')}
 if(m.type==='gameOver'){const sorted=[...room.players].sort((a,b)=>b.score-a.score);flash(`🏆 ${sorted[0]?.name} WINS!`,999999,'alert')}
}
function renderLobby(){ $('#room-code').textContent=room.code||'';$('#players').innerHTML=room.players.map(p=>`<div class="player-card"><i class="dot" style="background:${p.color}"></i><b>${escapeHtml(p.name)}</b>${p.bot?'<span class="host">AI</span>':p.id===room.hostId?'<span class="host">HOST</span>':''}</div>`).join(''); const host=myId===room.hostId;$('#start').classList.toggle('hidden',!host);$('#waiting').classList.toggle('hidden',host);const hint=$('#lobby-hint');if(hint)hint.classList.toggle('hidden',!host);$('#start').disabled=false;$('#start').textContent=room.players.length<2?'PRACTICE WITH AI':`START GAME (${room.players.length})`; }
const escapeHtml=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function flash(text,ms,cls='alert'){const el=$('#message');el.textContent=text;el.className=cls;messageUntil=Date.now()+ms;}
function updateHud(){const me=room.players.find(p=>p.id===myId);$('#round').textContent=`${room.round} / 5`;$('#score').textContent=me?.score||0;$('#throws').textContent=me?.throwsLeft??2;const now=Date.now()+clockOffset,indicator=$('#fuse-indicator');indicator.dataset.stage=room.fuseStage||0;indicator.classList.toggle('pulse',!!room.fusePulse);indicator.querySelectorAll('i').forEach((dot,i)=>dot.classList.toggle('on',i<(room.fuseStage||0)));const nextStage=room.status==='playing'?(room.fuseStage||0):-1;if(nextStage!==musicStage){musicStage=nextStage;nextMusicBeat=0;musicStep=0;}const pc=Math.max(0,(me?.parryReady||0)-now);$('#parry').textContent=pc?`${(pc/1000).toFixed(1)}s`:'READY';}
const input={}; const keys={KeyW:'up',ArrowUp:'up',KeyS:'down',ArrowDown:'down',KeyA:'left',ArrowLeft:'left',KeyD:'right',ArrowRight:'right',Space:'jump',ShiftLeft:'dash',ShiftRight:'dash',KeyE:'throw',KeyQ:'parry'};
addEventListener('keydown',e=>{if(keys[e.code]){e.preventDefault();input[keys[e.code]]=true;sendInput()}});addEventListener('keyup',e=>{if(keys[e.code]){input[keys[e.code]]=false;sendInput()}});
$('#mobile').querySelectorAll('button').forEach(b=>{for(const ev of ['pointerdown','pointerup','pointercancel'])b.addEventListener(ev,e=>{e.preventDefault();input[b.dataset.key]=ev==='pointerdown';sendInput()})});
function sendInput(){if(ws?.readyState===1)ws.send(JSON.stringify({type:'input',input}))}
setInterval(sendInput,100);
function rounded(x,y,w,h,r,color){ctx.fillStyle=color;ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fill()}
function draw(){requestAnimationFrame(draw);if(game.classList.contains('hidden'))return;ctx.clearRect(0,0,1000,700);ctx.save();if(performance.now()<shakeUntil)ctx.translate((Math.random()-.5)*12,(Math.random()-.5)*12);
 const g=ctx.createLinearGradient(0,0,0,700);g.addColorStop(0,'#090b20');g.addColorStop(1,'#111638');ctx.fillStyle=g;ctx.fillRect(0,0,1000,700);
 // A single floating island with a central chasm and bridge.
 rounded(60,78,880,580,30,'#151a3a');rounded(60,60,880,580,30,'#35417d');
 ctx.fillStyle='#10142f';ctx.fillRect(380,255,240,190);ctx.fillStyle='#090b20';ctx.fillRect(390,265,220,170);
 ctx.strokeStyle='#8190d066';ctx.lineWidth=5;ctx.beginPath();ctx.roundRect(60,60,880,580,30);ctx.stroke();
 ctx.strokeStyle='#ffffff0d';ctx.lineWidth=2;for(let x=90;x<940;x+=50){ctx.beginPath();ctx.moveTo(x,70);ctx.lineTo(x,630);ctx.stroke()}for(let y=90;y<640;y+=50){ctx.beginPath();ctx.moveTo(70,y);ctx.lineTo(930,y);ctx.stroke()}
 // jump pad
 rounded(120,450,120,120,25,'#6148c9');ctx.strokeStyle='#d1c9ff';ctx.lineWidth=8;ctx.beginPath();ctx.arc(180,510,32,0,Math.PI*2);ctx.stroke();ctx.fillStyle='#fff';ctx.font='900 22px Outfit';ctx.textAlign='center';ctx.fillText('JUMP',180,518);
 // bridge
 rounded(365,320,270,80,12,'#5967a5');ctx.fillStyle='#8492d1';for(let x=385;x<630;x+=42)ctx.fillRect(x,330,6,60);ctx.fillStyle='#dce2ff';ctx.font='700 13px Outfit';ctx.fillText('BRIDGE',500,418);
 // spinner
 ctx.save();ctx.translate(500,175);ctx.rotate(room.barAngle||0);rounded(-150,-16,300,32,16,'#ffce3b');ctx.restore();ctx.fillStyle='#ff724b';ctx.beginPath();ctx.arc(500,175,28,0,Math.PI*2);ctx.fill();
 // moving wall
 const wallX=room.wallX||760;rounded(wallX-25,255,50,190,10,'#e75178');ctx.fillStyle='#ffffff40';ctx.fillRect(wallX-12,270,10,160);
 for(const b of room.projectiles||[]){const speed=Math.hypot(b.vx,b.vy)||1;ctx.strokeStyle='#ffcc4d99';ctx.lineWidth=8;ctx.beginPath();ctx.moveTo(b.x-b.vx/speed*38,b.y-b.z-b.vy/speed*38);ctx.lineTo(b.x,b.y-b.z);ctx.stroke();ctx.font='32px serif';ctx.textAlign='center';ctx.fillText('💣',b.x,b.y-b.z)}
 const visible=(room.players||[]).map(p=>{let v=visualPlayers.get(p.id);if(!v){v={...p};visualPlayers.set(p.id,v)}const blend=(p.id===myId)?0.42:0.28;v.x+=(p.x-v.x)*blend;v.y+=(p.y-v.y)*blend;v.z+=(p.z-v.z)*blend;Object.assign(v,{...p,x:v.x,y:v.y,z:v.z});return v});
 visible.sort((a,b)=>a.y-b.y).forEach(drawPlayer);
 const now=performance.now();explosions=explosions.filter(e=>now-e.started<1100);for(const e of explosions){const t=(now-e.started)/1100,r=25+t*150;ctx.globalAlpha=1-t;ctx.fillStyle=t<.35?'#fff4a5':t<.7?'#ff8b32':'#ff315f';ctx.beginPath();ctx.arc(e.x,e.y,r,0,Math.PI*2);ctx.fill();ctx.strokeStyle='#fff';ctx.lineWidth=10*(1-t);ctx.beginPath();ctx.arc(e.x,e.y,r*1.25,0,Math.PI*2);ctx.stroke();ctx.globalAlpha=1;}
 impacts=impacts.filter(e=>now-e.started<450);for(const e of impacts){const t=(now-e.started)/450;ctx.globalAlpha=1-t;ctx.strokeStyle=e.color;ctx.lineWidth=10*(1-t)+2;ctx.beginPath();ctx.arc(e.x,e.y,15+t*75,0,Math.PI*2);ctx.stroke();ctx.globalAlpha=1;}
 ctx.restore();
 if(Date.now()>messageUntil)$('#message').textContent='';
}
function drawPlayer(p){const sy=p.y-p.z, me=p.id===myId,falling=p.z<0,scale=falling?Math.max(.22,1+p.z/650):1;if(!falling){ctx.globalAlpha=.28;ctx.fillStyle='#000';ctx.beginPath();ctx.ellipse(p.x,p.y+18,27,12,0,0,Math.PI*2);ctx.fill();}ctx.globalAlpha=falling?Math.max(.25,scale):1;
 if(falling){ctx.strokeStyle='#ffffff55';ctx.lineWidth=3;for(let i=0;i<4;i++){ctx.beginPath();ctx.moveTo(p.x-18+i*12,sy-65);ctx.lineTo(p.x-12+i*8,sy-35);ctx.stroke();}}
 ctx.fillStyle=p.color;ctx.beginPath();ctx.arc(p.x,sy,25*scale,0,Math.PI*2);ctx.fill();ctx.lineWidth=(me?5:3)*scale;ctx.strokeStyle=me?'#fff':'#15172e';ctx.stroke();
 ctx.fillStyle='#15172e';ctx.beginPath();ctx.arc(p.x-8*scale,sy-4*scale,3*scale,0,7);ctx.arc(p.x+8*scale,sy-4*scale,3*scale,0,7);ctx.fill();ctx.fillStyle='#fff';ctx.font='700 13px Outfit';ctx.textAlign='center';if(!falling)ctx.fillText(p.name,p.x,sy-35);
 if(p.bomb){if(room.fusePulse){ctx.shadowColor=room.fuseStage>=4?'#ff274f':'#ffc83d';ctx.shadowBlur=18+room.fuseStage*7;ctx.fillStyle=room.fuseStage>=4?'#ff274f':'#ffc83d';ctx.beginPath();ctx.arc(p.x,sy-37,18+room.fuseStage*2,0,Math.PI*2);ctx.fill();}ctx.font='35px serif';ctx.fillText('💣',p.x,sy-27);ctx.shadowBlur=0;const remain=Math.max(0,p.passReady-(Date.now()+clockOffset));if(remain){ctx.fillStyle='#ffed58';ctx.font='900 12px Outfit';ctx.fillText((remain/1000).toFixed(1),p.x,sy+5);}}
 if((p.parryUntil||0)>Date.now()+clockOffset){ctx.strokeStyle='#6ff7ff';ctx.lineWidth=7;ctx.globalAlpha=.75;ctx.beginPath();ctx.arc(p.x,sy,42,0,Math.PI*2);ctx.stroke();ctx.globalAlpha=1;}
 ctx.globalAlpha=1;}
draw();
