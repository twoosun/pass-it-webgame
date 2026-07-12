import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';
import { WebSocketServer, WebSocket } from 'ws';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), 'public');
const PORT = Number(process.env.PORT || 3000);
const TICK = 1000 / 30;
const ROUND_MIN_MS = 42_000;
const ROUND_VARIANCE_MS = 6_000;
const INTERMISSION_MS = 4_000;
const MAX_PLAYERS = 4;
const COLORS = ['#ff4f77', '#54d7ff', '#ffd84d', '#9a7cff'];
const SPAWNS = [{x:170,y:170},{x:830,y:170},{x:170,y:530},{x:830,y:530}];
const rooms = new Map();

const server = http.createServer(async (req, res) => {
  try {
    const urlPath = new URL(req.url, 'http://localhost').pathname;
    if(urlPath==='/api/rooms'){
      const body=JSON.stringify(roomList());
      res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'}).end(body);return;
    }
    const requested = urlPath === '/' ? 'index.html' : urlPath.slice(1);
    const safe = normalize(requested).replace(/^(\.\.[/\\])+/, '');
    const file = await readFile(join(ROOT, safe));
    const types = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'};
    res.writeHead(200, {
      'Content-Type': types[extname(safe)] || 'application/octet-stream',
      'Cache-Control': 'no-store, no-cache, must-revalidate',
      'Pragma': 'no-cache'
    }).end(file);
  } catch { res.writeHead(404).end('Not found'); }
});

const wss = new WebSocketServer({ server });
const send = (ws, data) => ws?.readyState === WebSocket.OPEN && ws.send(JSON.stringify(data));
const broadcast = (room, data) => room.players.forEach(p => send(p.ws, data));
const cleanName = value => String(value || 'PLAYER').trim().slice(0, 12) || 'PLAYER';
const code = () => {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let result;
  do { result = Array.from({length: 5}, () => chars[Math.floor(Math.random()*chars.length)]).join(''); } while (rooms.has(result));
  return result;
};

function makeRoom(host, password='') {
  const room = { code: code(), password:String(password||'').slice(0,12), players: [], hostId: host.id, status: 'lobby', round: 0, roundEnds: 0, nextRoundAt: 0, loserId: null, barAngle: 0, projectiles:[] };
  rooms.set(room.code, room); return room;
}

function roomList() {
  return [...rooms.values()].filter(r=>r.status==='lobby').map(r=>({code:r.code,locked:!!r.password,players:r.players.filter(p=>!p.bot).length,max:MAX_PLAYERS}));
}
function broadcastRoomList(){wss.clients.forEach(ws=>send(ws,{type:'rooms',rooms:roomList()}));}

function addPlayer(room, ws, name) {
  const slot = room.players.length;
  const p = { id: crypto.randomUUID().slice(0,8), ws, name: cleanName(name), color: COLORS[slot], x: SPAWNS[slot].x, y: SPAWNS[slot].y, vx:0, vy:0, z:0, vz:0, input:{}, facing:{x:1,y:0}, dashReady:0, passReady:0, throwReady:0, parryReady:0, parryUntil:0, bomb:false, score:0, throwsLeft:2 };
  room.players.push(p); ws.player = p; ws.room = room;
  broadcastLobby(room); return p;
}

function addBot(room, index) {
  const slot = room.players.length;
  const p = { id:`bot-${crypto.randomUUID().slice(0,6)}`, ws:null, bot:true, name:`AI ${index}`, color:COLORS[slot], x:SPAWNS[slot].x, y:SPAWNS[slot].y, vx:0, vy:0, z:0, vz:0, input:{}, facing:{x:1,y:0}, dashReady:0, passReady:0, throwReady:0, parryReady:0, parryUntil:0, bomb:false, score:0, thinkAt:0, throwsLeft:2, aiSide:index%2?1:-1, aiGoal:null, aiGoalAt:0, lastX:SPAWNS[slot].x, lastY:SPAWNS[slot].y, stuckAt:0 };
  room.players.push(p);
  return p;
}

function broadcastLobby(room) {
  broadcast(room, {type:'lobby', code:room.code, hostId:room.hostId, status:room.status, players:room.players.map(({id,name,color,score,bot})=>({id,name,color,score,bot:!!bot}))});
}

function startGame(room) {
  // Solo rooms start as practice matches with AI players.
  if (room.status !== 'lobby' || room.players.length < 1) return;
  const humans = room.players.filter(p=>!p.bot);
  if (humans.length === 1) { addBot(room, 1); addBot(room, 2); }
  room.round = 0; room.players.forEach(p => p.score = 0); startRound(room);
}

function startRound(room) {
  room.status = 'playing'; room.round++; room.loserId = null; room.fuseStarted=Date.now(); room.roundEnds = room.fuseStarted + ROUND_MIN_MS + Math.random()*ROUND_VARIANCE_MS;
  room.fuseSeed=Math.random()*10;room.fuseTimeline=buildFuseTimeline();
  room.projectiles=[];
  room.players.forEach((p,i) => Object.assign(p, {x:SPAWNS[i].x,y:SPAWNS[i].y,vx:0,vy:0,z:0,vz:0,bomb:false,dead:false,passReady:0,parryReady:0,parryUntil:0,throwsLeft:2}));
  room.players[Math.floor(Math.random()*room.players.length)].bomb = true;
  broadcast(room, {type:'roundStart', round:room.round, endsAt:room.roundEnds}); broadcastLobby(room);
}

function endRound(room, forcedLoser=null, reason='bomb') {
  if(room.status!=='playing')return;
  room.status = 'results'; const loser = forcedLoser||room.players.find(p=>p.bomb); room.loserId = loser?.id;
  room.players.forEach(p => { if (p.id !== room.loserId) p.score++; });
  room.nextRoundAt = Date.now() + INTERMISSION_MS;
  if(reason==='bomb')broadcast(room, {type:'explosion',x:loser?.x||500,y:(loser?.y||350)-(loser?.z||0),playerId:room.loserId});
  broadcast(room, {type:'roundEnd', loserId:room.loserId, reason, nextAt:room.nextRoundAt, final:room.round>=5}); broadcastLobby(room);
}

const onPlatform=(x,y)=>{
  const island=x>60&&x<940&&y>60&&y<640;
  const chasm=x>380&&x<620&&y>255&&y<445;
  const bridge=x>365&&x<635&&y>320&&y<400;
  return island&&(!chasm||bridge);
};
const moveToward=(value,target,maxDelta)=>Math.abs(target-value)<=maxDelta?target:value+Math.sign(target-value)*maxDelta;
function buildFuseTimeline(){
  const events=[{time:0,stage:0}];let time=7+Math.random()*3,stage=0;
  while(time<32){
    let delta;if(stage===0)delta=1;else if(stage===3)delta=Math.random()<.62?-1:0;else delta=Math.random()<.58?1:-1;
    if(delta){stage=Math.max(0,Math.min(3,stage+delta));events.push({time,stage});}
    time+=2.4+Math.random()*3.4;
  }
  time=32;
  while(stage<4){time+=.9+Math.random()*.4;stage++;events.push({time,stage});}
  return events;
}
function fuseSignal(room,now){
  const t=(now-room.fuseStarted)/1000;
  let stage=0;for(const event of room.fuseTimeline||[]){if(t<event.time)break;stage=event.stage;}
  const rates=[99,1.2,.72,.4,Math.max(.11,.25-Math.max(0,t-36)*.01)],rate=rates[stage];
  const pauseCycle=6.2+room.fuseSeed%2.5,active=stage>0&&((t+room.fuseSeed)%pauseCycle)<(stage===4?pauseCycle-.45:3.5+stage*.55);
  const pulse=active&&((t%rate)<rate*.42);
  return {stage,pulse};
}
function throwBomb(room,p,now){
  if(!p.bomb||p.throwsLeft<=0||now<p.passReady||now<p.throwReady)return;
  const f=p.facing||{x:1,y:0};p.bomb=false;p.throwsLeft--;
  p.throwReady=now+900;
  room.projectiles.push({id:crypto.randomUUID().slice(0,7),ownerId:p.id,x:p.x,y:p.y,z:Math.max(25,p.z+20),vx:f.x*760,vy:f.y*760,createdAt:now});
  broadcast(room,{type:'thrown',from:p.id,throwsLeft:p.throwsLeft});
}

function physics(room, dt, now) {
  room.barAngle += dt * 1.7;
  for (const p of room.players) {
    if(p.dead)continue;
    if (p.bot && now >= p.thinkAt) {
      const others=room.players.filter(x=>x!==p), bomb=room.players.find(x=>x.bomb);
      const target=p.bomb?others.sort((a,b)=>Math.hypot(a.x-p.x,a.y-p.y)-Math.hypot(b.x-p.x,b.y-p.y))[0]:bomb;
      if(target){const dist=Math.hypot(target.x-p.x,target.y-p.y);let dx,dy;
        if(p.bomb){dx=target.x+target.vx*.28-p.x;dy=target.y+target.vy*.28-p.y;const dl=Math.hypot(dx,dy)||1;dx+=-dy/dl*p.aiSide*Math.min(120,dist*.25);dy+=dx/dl*p.aiSide*Math.min(90,dist*.18);}
        else{dx=p.x-target.x;dy=p.y-target.y;const dl=Math.hypot(dx,dy)||1;dx+=-dy/dl*p.aiSide*150;dy+=dx/dl*p.aiSide*110;if(dist>430){if(!p.aiGoal||now>p.aiGoalAt){const goals=[{x:210,y:180},{x:790,y:180},{x:210,y:520},{x:790,y:520},{x:500,y:360}];p.aiGoal=goals[Math.floor(Math.random()*goals.length)];p.aiGoalAt=now+1800+Math.random()*1800;}dx=p.aiGoal.x-p.x;dy=p.aiGoal.y-p.y;}}
        const nx=p.x+Math.sign(dx)*65,ny=p.y+Math.sign(dy)*65;
        if(!onPlatform(nx,ny)){let ax,ay;if(p.y<300){ax=p.x<500?260:740;ay=175;}else if(p.y>420){ax=p.x<500?260:740;ay=525;}else{ax=500;ay=360;}dx=ax-p.x;dy=ay-p.y;}
        if(p.x<120)dx=Math.abs(dx)+180;if(p.x>880)dx=-Math.abs(dx)-180;if(p.y<120)dy=Math.abs(dy)+180;if(p.y>580)dy=-Math.abs(dy)-180;
        if(now-p.stuckAt>700){const moved=Math.hypot(p.x-p.lastX,p.y-p.lastY);if(moved<18){p.aiSide*=-1;dx+=p.aiSide*280;dy-=p.aiSide*220;p.input.jump=true;p.input.dash=true;}p.lastX=p.x;p.lastY=p.y;p.stuckAt=now;}
        p.input.left=dx< -18;p.input.right=dx>18;p.input.up=dy< -18;p.input.down=dy>18;}
      const td=target?Math.hypot(target.x-p.x,target.y-p.y):999;p.input.jump=p.input.jump||Math.random()<.09;p.input.dash=p.input.dash||(p.bomb&&td>170&&td<420&&Math.random()<.3);p.input.throw=p.bomb&&p.throwsLeft>0&&td>180&&td<650&&Math.random()<.16;p.input.parry=!p.bomb&&bomb&&td<105&&Math.random()<.45;p.thinkAt=now+150+Math.random()*220;
    }
    const ix = (p.input.right?1:0)-(p.input.left?1:0), iy=(p.input.down?1:0)-(p.input.up?1:0);
    const len = Math.hypot(ix,iy)||1;
    if(ix||iy)p.facing={x:ix/len,y:iy/len};
    const grounded=p.z===0&&onPlatform(p.x,p.y), maxSpeed=grounded?380:325;
    const targetX=(ix?ix/len:0)*maxSpeed,targetY=(iy?iy/len:0)*maxSpeed;
    const control=grounded?(ix||iy?3400:4000):(ix||iy?1500:220);
    p.vx=moveToward(p.vx,targetX,control*dt);p.vy=moveToward(p.vy,targetY,control*dt);
    if (p.input.dash && now >= p.dashReady && (ix||iy)) { p.vx += ix/len*550; p.vy += iy/len*550; p.dashReady=now+1500; }
    p.input.dash=false;
    if (p.input.jump && grounded) p.vz=470; p.input.jump=false;
    if(p.input.throw){throwBomb(room,p,now);p.input.throw=false;}
    if(p.input.parry){if(now>=p.parryReady){p.parryUntil=now+650;p.parryReady=now+3000;broadcast(room,{type:'parry',playerId:p.id,x:p.x,y:p.y});}p.input.parry=false;}
    // Vertical input modifies ascent and descent while airborne.
    if(p.z>0||!onPlatform(p.x,p.y)){if(p.input.up)p.vz+=650*dt;if(p.input.down)p.vz-=900*dt;p.vz=Math.max(-900,Math.min(540,p.vz));}
    if (grounded && p.x>120 && p.x<240 && p.y>450 && p.y<570) p.vz=650; // jump pad
    const prevX=p.x,prevY=p.y;
    p.x += p.vx*dt; p.y += p.vy*dt; p.z += p.vz*dt; p.vz -= 1050*dt;
    if(p.bot&&p.z<=0&&!onPlatform(p.x,p.y)){p.x=prevX;p.y=prevY;p.z=0;p.vz=0;p.vx*=-.15;p.vy*=-.15;}
    if (p.z<0 && onPlatform(p.x,p.y)) {p.z=0;p.vz=0;}
    if(p.z < -520){p.dead=true;broadcast(room,{type:'fell',playerId:p.id});endRound(room,p,'fall');return;}
    p.x=Math.max(35,Math.min(965,p.x)); p.y=Math.max(35,Math.min(665,p.y));
    // moving wall
    const wallX=760+Math.sin(now/850)*95;
    if(p.z<55 && Math.abs(p.x-wallX)<35 && p.y>255&&p.y<445){p.x += p.x<wallX?-12:12;p.vx*= -.3;}
    // spinning bar
    const dx=p.x-500,dy=p.y-175, proj=dx*Math.cos(room.barAngle)+dy*Math.sin(room.barAngle), perp=-dx*Math.sin(room.barAngle)+dy*Math.cos(room.barAngle);
    if(p.z<45 && Math.abs(proj)<145 && Math.abs(perp)<22){p.vx+=Math.cos(room.barAngle+Math.PI/2)*260;p.vy+=Math.sin(room.barAngle+Math.PI/2)*260;}
  }
  for(const b of room.projectiles){b.x+=b.vx*dt;b.y+=b.vy*dt;const hit=room.players.find(p=>!p.dead&&p.id!==b.ownerId&&Math.hypot(p.x-b.x,p.y-b.y)<38&&Math.abs(p.z-b.z)<65);if(hit&&now<hit.parryUntil){const oldOwner=b.ownerId;b.ownerId=hit.id;b.vx*=-1;b.vy*=-1;b.createdAt=now;broadcast(room,{type:'parried',playerId:hit.id,against:oldOwner,x:hit.x,y:hit.y});}else if(hit){hit.bomb=true;hit.passReady=now+2000;b.done=true;broadcast(room,{type:'passed',from:b.ownerId,to:hit.id,lockedUntil:hit.passReady,thrown:true,x:hit.x,y:hit.y});}else if(now-b.createdAt>1400||b.x<20||b.x>980||b.y<20||b.y>680){const owner=room.players.find(p=>p.id===b.ownerId)||room.players[0];owner.bomb=true;owner.passReady=now+700;b.done=true;}}
  room.projectiles=room.projectiles.filter(b=>!b.done);
  for(let i=0;i<room.players.length;i++) for(let j=i+1;j<room.players.length;j++){
    const a=room.players[i],b=room.players[j],d=Math.hypot(a.x-b.x,a.y-b.y);
    if(!a.dead&&!b.dead&&d<46 && Math.abs(a.z-b.z)<45){
      const bomb=a.bomb?a:b.bomb?b:null, receiver=bomb===a?b:a;
      if(bomb && now>=bomb.passReady&&now<receiver.parryUntil){const nx=(bomb.x-receiver.x)/(d||1),ny=(bomb.y-receiver.y)/(d||1);bomb.vx+=nx*520;bomb.vy+=ny*520;bomb.passReady=now+500;broadcast(room,{type:'parried',playerId:receiver.id,against:bomb.id,x:receiver.x,y:receiver.y});}
      else if(bomb && now>=bomb.passReady){bomb.bomb=false;receiver.bomb=true;receiver.passReady=now+2000;broadcast(room,{type:'passed',from:bomb.id,to:receiver.id,lockedUntil:receiver.passReady,x:receiver.x,y:receiver.y});}
      if(d>0){const nx=(a.x-b.x)/d,ny=(a.y-b.y)/d;a.x+=nx*2;b.x-=nx*2;a.y+=ny*2;b.y-=ny*2;}
    }
  }
}

function state(room, now) {
  const fuse=fuseSignal(room,now);broadcast(room,{type:'state',now,round:room.round,status:room.status,endsAt:room.roundEnds,fuseStage:fuse.stage,fusePulse:fuse.pulse,barAngle:room.barAngle,wallX:760+Math.sin(now/850)*95,projectiles:room.projectiles,players:room.players.map(p=>({id:p.id,name:p.name,color:p.color,x:p.x,y:p.y,z:p.z,dead:!!p.dead,bomb:p.bomb,passReady:p.passReady,dashReady:p.dashReady,parryReady:p.parryReady,parryUntil:p.parryUntil,throwsLeft:p.throwsLeft,score:p.score}))});
}

wss.on('connection', ws => {
  send(ws,{type:'hello'});
  send(ws,{type:'rooms',rooms:roomList()});
  ws.on('message', raw => { try {
    const m=JSON.parse(raw);
    if(m.type==='list')send(ws,{type:'rooms',rooms:roomList()});
    if(m.type==='create'){ const stub={id:crypto.randomUUID().slice(0,8)}; const room=makeRoom(stub,m.password); const p=addPlayer(room,ws,m.name); room.hostId=p.id; send(ws,{type:'joined',id:p.id,code:room.code}); broadcastLobby(room); broadcastRoomList(); }
    if(m.type==='join'){ const room=rooms.get(String(m.code||'').toUpperCase()); if(!room) return send(ws,{type:'error',message:'Room not found.'}); if(room.password&&room.password!==String(m.password||''))return send(ws,{type:'error',message:'Incorrect password.'}); if(room.players.length>=MAX_PLAYERS)return send(ws,{type:'error',message:'The room is full.'}); if(room.status!=='lobby')return send(ws,{type:'error',message:'The game has already started.'}); const p=addPlayer(room,ws,m.name);send(ws,{type:'joined',id:p.id,code:room.code});broadcastRoomList(); }
    if(m.type==='start'&&ws.room?.hostId===ws.player?.id) startGame(ws.room);
    if(m.type==='input'&&ws.player) ws.player.input={...ws.player.input,...m.input};
  } catch {} });
  ws.on('close',()=>{const r=ws.room,p=ws.player;if(!r||!p)return;r.players=r.players.filter(x=>x!==p);const humans=r.players.filter(x=>!x.bot);if(!humans.length)rooms.delete(r.code);else{if(r.hostId===p.id)r.hostId=humans[0].id;if(r.status==='playing'&&p.bomb)r.players[0].bomb=true;broadcastLobby(r);}});
});

setInterval(()=>{const now=Date.now();for(const room of rooms.values()){if(room.status==='playing'){physics(room,TICK/1000,now);if(now>=room.roundEnds)endRound(room);}else if(room.status==='results'&&now>=room.nextRoundAt){if(room.round>=5){room.status='finished';broadcast(room,{type:'gameOver'});broadcastLobby(room);}else startRound(room);}if(room.status!=='lobby')state(room,now);}},TICK);

server.listen(PORT,()=>console.log(`PASS IT! running at http://localhost:${PORT}`));
