import html from "./index.html";
const states=["Received","Preparing","Ready","Collected"];
const encoder=new TextEncoder();
const hex=b=>Array.from(new Uint8Array(b),x=>x.toString(16).padStart(2,"0")).join("");
const random=()=>hex(crypto.getRandomValues(new Uint8Array(32)));
const hash=async s=>hex(await crypto.subtle.digest("SHA-256",encoder.encode(s)));
async function password(p,s){const key=await crypto.subtle.importKey("raw",encoder.encode(p),"PBKDF2",false,["deriveBits"]);return hex(await crypto.subtle.deriveBits({name:"PBKDF2",hash:"SHA-256",salt:encoder.encode(s),iterations:100000},key,256))}
function equal(a,b){if(typeof a!=="string"||typeof b!=="string"||a.length!==b.length)return false;let diff=0;for(let i=0;i<a.length;i++)diff|=a.charCodeAt(i)^b.charCodeAt(i);return diff===0}
const now=()=>new Date(Date.now()+19800000).toISOString().slice(0,19);
const token=id=>"T-"+String(id).padStart(4,"0");
const cookie=(v,age)=>"canteen="+v+"; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age="+age;
const reply=(v,status=200,c)=>Response.json(v,{status,headers:{"Cache-Control":"no-store","X-Content-Type-Options":"nosniff",...(c?{"Set-Cookie":c}:{})}});
function need(v,msg,status=400){if(!v)throw {status,msg}}
function order(r){let {user_id,request_id,...v}=r;return {...v,items:JSON.parse(v.items),token:token(v.id)}}
const profile=u=>({id:u.id,name:u.name,email:u.email,role:u.role});
export default {async fetch(req,env,ctx){
const url=new URL(req.url),p=url.pathname,post=req.method==="POST",db=env.DB;
const q=(s,...a)=>db.prepare(s).bind(...a);
const all=async(s,...a)=>(await q(s,...a).all()).results;
const first=(s,...a)=>q(s,...a).first();
const run=(s,...a)=>q(s,...a).run();
async function eta(id){let sql="SELECT items FROM orders WHERE status IN ('Received','Preparing')",args=[];if(id!==undefined){sql+=" AND id<=?";args.push(id)}return Math.ceil((await all(sql,...args)).reduce((s,r)=>s+JSON.parse(r.items).reduce((a,i)=>a+i.qty*i.minutes,0),0)/3)}
try{
if(req.method==="GET"&&(p==="/"||p==="/index.html"))return new Response(html,{headers:{"Content-Type":"text/html; charset=utf-8","X-Content-Type-Options":"nosniff","Cache-Control":"no-cache"}});
need(req.method==="GET"||post,"Method not allowed",405);
let d={};
if(post){need(req.headers.get("Origin")===url.origin,"Invalid origin",403);const t=await req.text();need(t.length>0&&t.length<=65536,"Invalid request size");try{d=JSON.parse(t)}catch{throw {status:400,msg:"Invalid JSON"}}need(d&&typeof d==="object"&&!Array.isArray(d),"Invalid request")}
const raw=(req.headers.get("Cookie")||"").match(/(?:^|;\s*)canteen=([0-9a-f]{64})(?:;|$)/)?.[1];
const session=raw?await hash(raw):null;
let u=session?await first("SELECT users.* FROM users JOIN sessions ON users.id=sessions.user_id WHERE token=? AND expiry>?",session,Math.floor(Date.now()/1000)):null;
if(!post&&p==="/api/menu")return reply({menu:await all("SELECT * FROM menu ORDER BY id"),wait:await eta()});
if(!post&&p==="/api/serving")return reply((await all("SELECT id FROM orders WHERE status='Ready' ORDER BY id")).map(x=>({token:token(x.id)})));
if(!post&&p==="/api/me")return reply({user:u?profile(u):null});
if(post&&(p==="/api/signup"||p==="/api/login")){
const email=String(d.email||"").trim().toLowerCase(),pw=String(d.password||""),staff=String(env.STAFF_EMAIL||"staff@techzy.example").toLowerCase();
need(email.length<=254&&/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)&&pw.length>=1&&pw.length<=128,"Invalid credentials");
if(p.endsWith("signup")){const name=String(d.name||"").trim();need(email!==staff,"Reserved account",403);need(name.length>=1&&name.length<=80&&pw.length>=8,"Name and 8+ character password required");need(!await first("SELECT id FROM users WHERE email=?",email),"Email already registered",409);const salt=random();try{await run("INSERT INTO users(name,email,salt,hash) VALUES(?,?,?,?)",name,email,salt,await password(pw,salt))}catch(e){if(String(e).includes("UNIQUE"))throw {status:409,msg:"Email already registered"};throw e}}
u=await first("SELECT * FROM users WHERE email=?",email);
if(email===staff&&!u&&env.STAFF_PASSWORD&&env.STAFF_PASSWORD.length>=12&&equal(pw,env.STAFF_PASSWORD)){const salt=random();await run("INSERT OR IGNORE INTO users(name,email,salt,hash,role) VALUES(?,?,?,?, 'staff')","Canteen Staff",email,salt,await password(pw,salt));u=await first("SELECT * FROM users WHERE email=?",email)}
need(u&&equal(u.hash,await password(pw,u.salt)),"Invalid email or password",401);
const t=random();await run("INSERT INTO sessions VALUES(?,?,?)",await hash(t),u.id,Math.floor(Date.now()/1000)+86400);
return reply({user:profile(u)},200,cookie(t,86400))}
need(u,"Please sign in",401);
if(post&&p==="/api/logout"){await run("DELETE FROM sessions WHERE token=?",session);return reply({},200,cookie("",0))}
if(!post&&p==="/api/orders"){const rows=await all("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC",u.id);return reply(await Promise.all(rows.map(async r=>({...order(r),wait:states.indexOf(r.status)<2?await eta(r.id):0}))))}
if(!post&&p==="/api/notices")return reply(await all("SELECT body,created FROM notices WHERE user_id=? ORDER BY id DESC LIMIT 30",u.id));
if(post&&p==="/api/order"){
need(u.role==="student","Student account required",403);const payment=d.payment,id=String(d.request_id||""),cart=d.cart;need(["mock","counter"].includes(payment)&&id.length>=8&&id.length<=100,"Invalid checkout");need(cart&&typeof cart==="object"&&!Array.isArray(cart)&&Object.keys(cart).length>=1&&Object.keys(cart).length<=50,"Cart is empty");
let old=await first("SELECT * FROM orders WHERE user_id=? AND request_id=?",u.id,id);if(old)return reply(order(old));
let items=[],total=0;for(const [k,v] of Object.entries(cart)){need(/^\d+$/.test(k)&&Number.isInteger(v)&&v>=1&&v<=20,"Invalid quantity");let m=await first("SELECT * FROM menu WHERE id=?",Number(k));need(m&&m.stock>=v,"Not enough stock",409);items.push({id:m.id,name:m.name,price:m.price,minutes:m.minutes,qty:v});total+=m.price*v}
try{let r=await first("INSERT INTO orders(user_id,created,status,payment,paid,total,items,request_id) VALUES(?,?,?,?,?,?,?,?) RETURNING *",u.id,now(),"Received",payment,payment==="mock"?1:0,total,JSON.stringify(items),id);return reply(order(r),201)}catch(e){old=await first("SELECT * FROM orders WHERE user_id=? AND request_id=?",u.id,id);if(old)return reply(order(old));if(String(e).includes("Stock or price changed"))throw {status:409,msg:"Stock or price changed"};throw e}}
need(u.role==="staff","Staff access required",403);
if(!post&&p==="/api/staff"){let rows=await all("SELECT orders.*,users.name AS student FROM orders JOIN users ON users.id=orders.user_id ORDER BY orders.id DESC"),daily=rows.filter(r=>r.created.slice(0,10)===now().slice(0,10)),hours=Array(24).fill(0);for(let r of daily)hours[Number(r.created.slice(11,13))]++;return reply({orders:rows.map(order),stats:{orders:daily.length,sales:daily.reduce((s,r)=>s+(r.paid?r.total:0),0),unpaid:daily.reduce((s,r)=>s+(r.paid?0:r.total),0),hours},wait:await eta()})}
if(post&&p==="/api/status"){let r=await first("SELECT * FROM orders WHERE id=?",d.id);need(r,"Order not found",404);need(states.includes(d.status)&&states.indexOf(d.status)===states.indexOf(r.status)+1,"Invalid transition",409);need(d.status!=="Collected"||r.paid,"Record cash payment first");const res=await run("UPDATE orders SET status=? WHERE id=? AND status=?",d.status,r.id,r.status);need(res.meta.changes===1,"Order status changed",409);return reply({ok:true})}
if(post&&p==="/api/paid"){let r=await run("UPDATE orders SET paid=1 WHERE id=? AND payment='counter'",d.id);need(r.meta.changes===1,"Not a counter order");return reply({ok:true})}
if(post&&p==="/api/stock"){need(Number.isInteger(d.stock)&&d.stock>=0&&d.stock<=100000,"Invalid stock");let r=await run("UPDATE menu SET stock=? WHERE id=?",d.stock,d.id);need(r.meta.changes===1,"Unknown item",404);return reply({ok:true})}
return reply({error:"Not found"},404)
}catch(e){if(e.status)return reply({error:e.msg},e.status);console.error(String(e));return reply({error:"Server error"},500)}
}};
