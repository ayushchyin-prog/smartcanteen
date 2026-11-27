import os, sqlite3, json, secrets, hashlib, hmac, re, smtplib, ssl
from email.message import EmailMessage
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit
from contextlib import contextmanager
from threading import Thread
BASE = Path(__file__).resolve().parent
DB = os.getenv("CANTEEN_DB", str(BASE / "canteen.db"))
TZ = ZoneInfo("Asia/Kolkata") if os.name != "nt" or os.getenv("TZ") else None
STATES = ["Received", "Preparing", "Ready", "Collected"]
SEED = [("Samosa","Snacks",15,60,3,"🥟"),("Veg Sandwich","Snacks",45,35,5,"🥪"),("Masala Dosa","Meals",65,30,8,"🥞"),("Veg Thali","Meals",90,30,10,"🍛"),("Noodles","Meals",60,35,7,"🍜"),("Veg Burger","Snacks",55,30,6,"🍔"),("Tea","Drinks",10,100,2,"☕"),("Cold Coffee","Drinks",50,35,4,"🥤"),("Gulab Jamun","Desserts",25,40,2,"🍮")]
def now():
    return datetime.now(TZ).isoformat(timespec="seconds")
def digest(pw,salt):
    return hashlib.pbkdf2_hmac("sha256",pw.encode(),bytes.fromhex(salt),310000).hex()
@contextmanager
def db():
    con=sqlite3.connect(DB,timeout=15)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
def init():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,salt TEXT NOT NULL, hash TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'student');
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),expiry INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS menu(id INTEGER PRIMARY KEY,name TEXT,category TEXT,price INTEGER,stock INTEGER,minutes INTEGER,emoji TEXT);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER REFERENCES users(id),created TEXT,status TEXT,payment TEXT,paid INTEGER,total INTEGER,items TEXT,request_id TEXT,UNIQUE(user_id,request_id));
        CREATE TABLE IF NOT EXISTS notices(id INTEGER PRIMARY KEY,user_id INTEGER,body TEXT,created TEXT);
        """)
        if not c.execute("SELECT 1 FROM menu LIMIT 1").fetchone():
            c.executemany("INSERT INTO menu(name,category,price,stock,minutes,emoji) VALUES(?,?,?,?,?,?)",SEED)
        email=os.getenv("STAFF_EMAIL","").strip().lower()
        pw=os.getenv("STAFF_PASSWORD","")
        if email and len(pw)>=10 and not c.execute("SELECT 1 FROM users WHERE email=?",(email,)).fetchone():
            salt=secrets.token_hex(16)
            c.execute("INSERT INTO users(name,email,salt,hash,role) VALUES(?,?,?,?, 'staff')",("Canteen Staff",email,salt,digest(pw,salt)))
        elif not email or len(pw)<10:
            print("Set STAFF_EMAIL and STAFF_PASSWORD (10+ characters) to enable staff login.")
def notify(email,body):
    if not os.getenv("SMTP_HOST"): return
    try:
        msg=EmailMessage()
        msg["Subject"]="Techzy Smart Canteen – order update"
        msg["From"]=os.environ["SMTP_FROM"]
        msg["To"]=email
        msg.set_content(body)
        with smtplib.SMTP(os.environ["SMTP_HOST"],int(os.getenv("SMTP_PORT","587")),timeout=10) as s:
            s.starttls(context=ssl.create_default_context())
            if os.getenv("SMTP_USER"): s.login(os.environ["SMTP_USER"],os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
    except Exception as e: print("Email not sent:",type(e).__name__)
def order_dict(row):
    d=dict(row)
    d["items"]=json.loads(d["items"])
    d["token"]="T-"+str(d["id"]).zfill(4)
    d.pop("request_id",None)
    d.pop("user_id",None)
    return d
def estimate(c,order_id=None):
    sql="SELECT items FROM orders WHERE status IN ('Received','Preparing')"
    args=()
    if order_id is not None:
        sql+=" AND id<=?"
        args=(order_id,)
    workload=sum(sum(i["minutes"]*i["qty"] for i in json.loads(r["items"])) for r in c.execute(sql,args))
    return (workload+2)//3
class Error(Exception):
    def __init__(self,status,msg): self.status,self.msg=status,msg
def need(condition,msg,status=400):
    if not condition: raise Error(status,msg)
class Handler(BaseHTTPRequestHandler):
    def reply(self,status,data,cookie=None):
        body=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        if cookie: self.send_header("Set-Cookie",cookie)
        self.send_header("Content-Length",str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def user(self,c):
        jar=SimpleCookie(self.headers.get("Cookie",""))
        token=jar.get("canteen")
        if not token: return None
        return c.execute("SELECT users.* FROM users JOIN sessions ON sessions.user_id=users.id WHERE token=? AND expiry>strftime('%s','now')",(hashlib.sha256(token.value.encode()).hexdigest(),)).fetchone()
    def cookie(self,value,age):
        return "canteen="+value+"; Path=/; HttpOnly; SameSite=Strict; Max-Age="+str(age)+("; Secure" if os.getenv("HTTPS_COOKIE")=="1" else "")
    def do_GET(self): self.handle_api(False)
    def do_POST(self): self.handle_api(True)
    def handle_api(self,post):
        path=urlsplit(self.path).path
        try:
            if not post and path in ("/","/index.html"):
                body=(BASE/"index.html").read_bytes()
                self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Content-Length",str(len(body)));self.send_header("X-Content-Type-Options","nosniff");self.end_headers();self.wfile.write(body);return
            data={}
            if post:
                origin=self.headers.get("Origin")
                if origin: need(urlsplit(origin).netloc==self.headers.get("Host"),"Invalid origin",403)
                n=int(self.headers.get("Content-Length","0"))
                need(0<n<=65536,"Invalid request size")
                data=json.loads(self.rfile.read(n))
                need(isinstance(data,dict),"Invalid request")
            with db() as c:
                u=self.user(c)
                if not post and path=="/api/menu":
                    return self.reply(200,{"menu":[dict(r) for r in c.execute("SELECT * FROM menu ORDER BY id")],"wait":estimate(c)})
                if not post and path=="/api/serving":
                    return self.reply(200,[{"token":"T-"+str(r["id"]).zfill(4)} for r in c.execute("SELECT id FROM orders WHERE status='Ready' ORDER BY id")])
                if not post and path=="/api/me":
                    return self.reply(200,{"user":{k:u[k] for k in ("id","name","email","role")} if u else None})
                if post and path in ("/api/signup","/api/login"):
                    email=str(data.get("email","")).strip().lower()
                    pw=str(data.get("password",""))
                    need(len(email)<=254 and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email),"Enter a valid email")
                    need(1<=len(pw)<=128,"Invalid password")
                    if path.endswith("signup"):
                        name=str(data.get("name","")).strip()
                        need(1<=len(name)<=80 and len(pw)>=8,"Name and password of 8+ characters required")
                        need(email!=os.getenv("STAFF_EMAIL","").strip().lower(),"Reserved account",403)
                        salt=secrets.token_hex(16)
                        try: c.execute("INSERT INTO users(name,email,salt,hash) VALUES(?,?,?,?)",(name,email,salt,digest(pw,salt)))
                        except sqlite3.IntegrityError: raise Error(409,"Email already registered")
                    user=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
                    need(user and hmac.compare_digest(user["hash"],digest(pw,user["salt"])),"Invalid email or password",401)
                    token=secrets.token_urlsafe(32)
                    c.execute("DELETE FROM sessions WHERE expiry<=strftime('%s','now')")
                    c.execute("INSERT INTO sessions VALUES(?,?,strftime('%s','now')+86400)",(hashlib.sha256(token.encode()).hexdigest(),user["id"]))
                    c.commit()
                    return self.reply(200,{"user":{k:user[k] for k in ("id","name","email","role")}},self.cookie(token,86400))
                need(u,"Please sign in",401)
                if post and path=="/api/logout":
                    jar=SimpleCookie(self.headers.get("Cookie",""))
                    if jar.get("canteen"): c.execute("DELETE FROM sessions WHERE token=?",(hashlib.sha256(jar["canteen"].value.encode()).hexdigest(),))
                    c.commit()
                    return self.reply(200,{},self.cookie("",0))
                if not post and path=="/api/orders":
                    return self.reply(200,[dict(order_dict(r),wait=estimate(c,r["id"]) if r["status"] in STATES[:2] else 0) for r in c.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC",(u["id"],))])
                if not post and path=="/api/notices":
                    return self.reply(200,[dict(r) for r in c.execute("SELECT body,created FROM notices WHERE user_id=? ORDER BY id DESC LIMIT 30",(u["id"],))])
                if post and path=="/api/order":
                    need(u["role"]=="student","Student account required",403)
                    method=data.get("payment")
                    need(method in ("mock","counter"),"Select payment method")
                    request_id=str(data.get("request_id",""))
                    need(8<=len(request_id)<=100,"Missing request identifier")
                    cart=data.get("cart")
                    need(isinstance(cart,dict) and 1<=len(cart)<=50,"Cart is empty")
                    c.execute("BEGIN IMMEDIATE")
                    existing=c.execute("SELECT * FROM orders WHERE user_id=? AND request_id=?",(u["id"],request_id)).fetchone()
                    if existing: return self.reply(200,order_dict(existing))
                    items=[]; total=0
                    for key,qty in cart.items():
                        need(key.isdigit() and type(qty)==int and 1<=qty<=20,"Invalid quantity")
                        m=c.execute("SELECT * FROM menu WHERE id=?",(int(key),)).fetchone()
                        need(m and m["stock"]>=qty,"Item unavailable or not enough stock",409)
                        c.execute("UPDATE menu SET stock=stock-? WHERE id=?",(qty,m["id"]))
                        items.append({k:m[k] for k in ("id","name","price","minutes")} | {"qty":qty})
                        total+=m["price"]*qty
                    oid=c.execute("INSERT INTO orders(user_id,created,status,payment,paid,total,items,request_id) VALUES(?,?,?,?,?,?,?,?)",(u["id"],now(),"Received",method,int(method=="mock"),total,json.dumps(items),request_id)).lastrowid
                    msg="Order T-"+str(oid).zfill(4)+" received."
                    c.execute("INSERT INTO notices(user_id,body,created) VALUES(?,?,?)",(u["id"],msg,now()))
                    result=order_dict(c.execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone())
                    c.commit();Thread(target=notify,args=(u["email"],msg),daemon=True).start()
                    return self.reply(201,result)
                need(u["role"]=="staff","Staff access required",403)
                if not post and path=="/api/staff":
                    rows=c.execute("SELECT orders.*,users.name AS student FROM orders JOIN users ON users.id=orders.user_id ORDER BY orders.id DESC").fetchall()
                    today=now()[:10]
                    daily=[r for r in rows if r["created"][:10]==today]
                    hours=[0]*24
                    for r in daily: hours[int(r["created"][11:13])]+=1
                    return self.reply(200,{"orders":[order_dict(r) for r in rows],"stats":{"orders":len(daily),"sales":sum(r["total"] for r in daily if r["paid"]),"unpaid":sum(r["total"] for r in daily if not r["paid"]),"hours":hours},"wait":estimate(c)})
                if post and path=="/api/status":
                    c.execute("BEGIN IMMEDIATE")
                    r=c.execute("SELECT orders.*,users.email FROM orders JOIN users ON users.id=orders.user_id WHERE orders.id=?",(data.get("id"),)).fetchone()
                    need(r,"Order not found",404)
                    target=data.get("status")
                    need(target in STATES and STATES.index(target)==STATES.index(r["status"])+1,"Invalid status transition",409)
                    need(target!="Collected" or r["paid"],"Mark counter payment received first")
                    c.execute("UPDATE orders SET status=? WHERE id=?",(target,r["id"]))
                    msg="Order T-"+str(r["id"]).zfill(4)+": "+target
                    c.execute("INSERT INTO notices(user_id,body,created) VALUES(?,?,?)",(r["user_id"],msg,now()))
                    c.commit();Thread(target=notify,args=(r["email"],msg),daemon=True).start()
                    return self.reply(200,{"ok":True})
                if post and path=="/api/paid":
                    r=c.execute("SELECT payment FROM orders WHERE id=?",(data.get("id"),)).fetchone()
                    need(r and r["payment"]=="counter","Not a counter order")
                    c.execute("UPDATE orders SET paid=1 WHERE id=?",(data["id"],));c.commit()
                    return self.reply(200,{"ok":True})
                if post and path=="/api/stock":
                    stock=data.get("stock")
                    need(type(stock)==int and 0<=stock<=100000,"Invalid stock")
                    need(c.execute("UPDATE menu SET stock=? WHERE id=?",(stock,data.get("id"))).rowcount==1,"Unknown item",404)
                    c.commit();return self.reply(200,{"ok":True})
                raise Error(404,"Not found")
        except Error as e: self.reply(e.status,{"error":e.msg})
        except (ValueError,TypeError,KeyError): self.reply(400,{"error":"Invalid request"})
        except Exception as e:
            print(type(e).__name__,str(e)); self.reply(500,{"error":"Server error"})
if __name__=="__main__":
    init()
    port=int(os.getenv("PORT","8000"))
    print("Smart Canteen: http://localhost:"+str(port))
    ThreadingHTTPServer((os.getenv("HOST","127.0.0.1"),port),Handler).serve_forever()
