"""Run: python smoke_test.py. Uses only the standard library."""
import os, sys, tempfile, subprocess, time, json, urllib.request, urllib.error, http.cookiejar, socket
from pathlib import Path
def client():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def call(c,path,data=None,expected=200):
    req=urllib.request.Request(base+"/api/"+path,data=None if data is None else json.dumps(data).encode(),headers={"Content-Type":"application/json"})
    try: r=c.open(req,timeout=5)
    except urllib.error.HTTPError as e: r=e
    with r:
        assert r.code==expected,(path,r.code,r.read())
        return json.load(r)
with tempfile.TemporaryDirectory() as d:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    base="http://127.0.0.1:"+str(port)
    p=subprocess.Popen([sys.executable,str(Path(__file__).with_name("server.py"))],env={**os.environ,"PORT":str(port),"HOST":"127.0.0.1","CANTEEN_DB":str(Path(d)/"test.db"),"STAFF_EMAIL":"staff@example.test","STAFF_PASSWORD":"TestOnly!12345","SMTP_HOST":"","HTTPS_COOKIE":"0"})
    try:
        student,staff,other,public=client(),client(),client(),client()
        for _ in range(50):
            try: menu=call(public,"menu");break
            except (OSError,urllib.error.URLError):time.sleep(.2)
        else: raise RuntimeError("Server did not start")
        assert menu["menu"]
        item=menu["menu"][0]
        call(student,"signup",{"name":"Test Student","email":"student@example.test","password":"TestOnly!123"})
        call(other,"signup",{"name":"Other Student","email":"other@example.test","password":"TestOnly!123"})
        call(staff,"login",{"email":"staff@example.test","password":"TestOnly!12345"})
        call(student,"staff",expected=403)
        order=call(student,"order",{"cart":{str(item["id"]):2},"payment":"mock","request_id":"test-request-001"},201)
        assert order["total"]==item["price"]*2 and order["status"]=="Received"
        same=call(student,"order",{"cart":{str(item["id"]):2},"payment":"mock","request_id":"test-request-001"})
        assert same["id"]==order["id"]
        assert call(other,"orders")==[]
        assert call(public,"menu")["menu"][0]["stock"]==item["stock"]-2
        call(staff,"status",{"id":order["id"],"status":"Ready"},409)
        for status in ("Preparing","Ready"):
            call(staff,"status",{"id":order["id"],"status":status})
        assert call(student,"orders")[0]["status"]=="Ready"
        assert order["token"] in [x["token"] for x in call(public,"serving")]
        call(staff,"status",{"id":order["id"],"status":"Collected"})
        assert call(public,"serving")==[]
        cash=call(student,"order",{"cart":{str(item["id"]):1},"payment":"counter","request_id":"test-request-002"},201)
        for status in ("Preparing","Ready"):call(staff,"status",{"id":cash["id"],"status":status})
        call(staff,"status",{"id":cash["id"],"status":"Collected"},400)
        call(staff,"paid",{"id":cash["id"]})
        call(staff,"status",{"id":cash["id"],"status":"Collected"})
        assert call(staff,"staff")["stats"]["orders"]==2
        assert len(call(student,"notices"))>=8
        call(staff,"stock",{"id":item["id"],"stock":0})
        call(student,"order",{"cart":{str(item["id"]):1},"payment":"mock","request_id":"test-request-003"},409)
        call(student,"logout",{})
        call(student,"orders",expected=401)
        print("PASS: auth, access control, stock, tokens, idempotency, status, collection, cash, analytics and notifications")
    finally:
        p.terminate()
        p.wait(timeout=5)
