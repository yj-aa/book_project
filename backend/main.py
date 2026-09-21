from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
import sqlite3
import requests
import hashlib
import uuid
import os
from jinja2 import Environment, FileSystemLoader, select_autoescape


def _load_env():
    """从 backend/.env 加载环境变量（无需安装 python-dotenv）。"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


_load_env()

app = FastAPI()
jinja_env = Environment(
    loader=FileSystemLoader(r"d:\data\pythonProject\book_project\templates"),
    autoescape=select_autoescape(["html", "htm"]),
    cache_size=0
)
DB_FILE = r"d:\data\pythonProject\book_project\book_data.db"

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_URL = os.getenv("LLM_URL", "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation")

sessions = {}

def get_db_conn():
    return sqlite3.connect(DB_FILE, timeout=30, check_same_thread=False)

def init_tables():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        book_id INTEGER NOT NULL,
        UNIQUE(user_id, book_id)
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        book_id INTEGER NOT NULL,
        price REAL NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL
    )''')
    cur.execute('SELECT COUNT(*) FROM users WHERE username = ?', ('admin',))
    cnt = cur.fetchone()[0]
    if cnt == 0:
        pwd = hashlib.sha256(b'admin123').hexdigest()
        cur.execute('INSERT INTO users (username, password) VALUES (?, ?)', ('admin', pwd))
        conn.commit()
    conn.close()

init_tables()

def get_session_user(request: Request):
    session_id = request.cookies.get('session_id')
    if session_id and session_id in sessions:
        return sessions[session_id]
    return None

def set_session(response, user_id, username):
    session_id = str(uuid.uuid4())
    sessions[session_id] = {'id': user_id, 'username': username}
    response.set_cookie(key='session_id', value=session_id)
    return response

async def require_login(request: Request):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url='/login', status_code=302)
    return user

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    template = jinja_env.get_template("login.html")
    return HTMLResponse(content=template.render(error=error))

@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    db = get_db_conn()
    cur = db.cursor()
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    cur.execute("SELECT id, username FROM users WHERE username = ? AND password = ?", (username, pwd_hash))
    user = cur.fetchone()
    db.close()
    if user:
        response = RedirectResponse(url='/', status_code=302)
        return set_session(response, user[0], user[1])
    template = jinja_env.get_template("login.html")
    return HTMLResponse(content=template.render(error="用户名或密码错误"))

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, error: str = "", success: str = ""):
    template = jinja_env.get_template("register.html")
    return HTMLResponse(content=template.render(error=error, success=success))

@app.post("/register", response_class=HTMLResponse)
async def register(request: Request, username: str = Form(...), password: str = Form(...), confirm_password: str = Form(...)):
    if password != confirm_password:
        template = jinja_env.get_template("register.html")
        return HTMLResponse(content=template.render(error="两次输入的密码不一致"))
    if len(username) < 3:
        template = jinja_env.get_template("register.html")
        return HTMLResponse(content=template.render(error="用户名至少需要3个字符"))
    if len(password) < 6:
        template = jinja_env.get_template("register.html")
        return HTMLResponse(content=template.render(error="密码至少需要6个字符"))
    db = get_db_conn()
    cur = db.cursor()
    try:
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, pwd_hash))
        db.commit()
    except sqlite3.IntegrityError:
        db.close()
        template = jinja_env.get_template("register.html")
        return HTMLResponse(content=template.render(error="用户名已存在"))
    db.close()
    template = jinja_env.get_template("register.html")
    return HTMLResponse(content=template.render(success="注册成功！请登录"))

@app.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    response = RedirectResponse(url='/login', status_code=302)
    response.delete_cookie(key='session_id')
    session_id = request.cookies.get('session_id')
    if session_id and session_id in sessions:
        del sessions[session_id]
    return response



@app.post("/admin/delete", response_class=HTMLResponse)
async def admin_delete(request: Request, book_id: int = Form(...), page: int = Form(1), search: str = Form(""), category: str = Form("")):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url='/login', status_code=302)
    if user['username'] != 'admin':
        return HTMLResponse(content="<h1>403 禁止访问</h1>", status_code=403)
    db = get_db_conn()
    cur = db.cursor()
    cur.execute("DELETE FROM book_info WHERE id = ?", (book_id,))
    cur.execute("DELETE FROM favorites WHERE book_id = ?", (book_id,))
    db.commit()
    cur.close()
    db.close()
    url = f'/admin?tab=books&page={page}'
    if search:
        url += f'&search={search}'
    if category:
        url += f'&category={category}'
    return RedirectResponse(url=url, status_code=302)

@app.post("/admin/ship_order", response_class=HTMLResponse)
async def admin_ship_order(request: Request, order_id: int = Form(...)):
    user = get_session_user(request)
    if not user or user['username'] != 'admin':
        return HTMLResponse(content="<h1>403 禁止访问</h1>", status_code=403)
    db = get_db_conn()
    cur = db.cursor()
    cur.execute("UPDATE orders SET status = 'shipped' WHERE id = ? AND status = 'pending'", (order_id,))
    db.commit()
    cur.close()
    db.close()
    return RedirectResponse(url='/admin?tab=orders', status_code=302)

@app.post("/admin/complete_order", response_class=HTMLResponse)
async def admin_complete_order(request: Request, order_id: int = Form(...)):
    user = get_session_user(request)
    if not user or user['username'] != 'admin':
        return HTMLResponse(content="<h1>403 禁止访问</h1>", status_code=403)
    db = get_db_conn()
    cur = db.cursor()
    cur.execute("UPDATE orders SET status = 'completed' WHERE id = ? AND status = 'shipped'", (order_id,))
    db.commit()
    cur.close()
    db.close()
    return RedirectResponse(url='/admin?tab=orders', status_code=302)

@app.post("/admin/update_price", response_class=HTMLResponse)
async def admin_update_price(request: Request, book_id: int = Form(...), price: float = Form(...), page: int = Form(1), search: str = Form(""), category: str = Form("")):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url='/login', status_code=302)
    if user['username'] != 'admin':
        return HTMLResponse(content="<h1>403 禁止访问</h1>", status_code=403)
    db = get_db_conn()
    cur = db.cursor()
    cur.execute("UPDATE book_info SET price = ? WHERE id = ?", (price, book_id))
    db.commit()
    cur.close()
    db.close()
    url = f'/admin?tab=books&page={page}'
    if search:
        url += f'&search={search}'
    if category:
        url += f'&category={category}'
    return RedirectResponse(url=url, status_code=302)

@app.post("/admin/update_stock", response_class=HTMLResponse)
async def admin_update_stock(request: Request, book_id: int = Form(...), stock: int = Form(...), page: int = Form(1), search: str = Form(""), category: str = Form("")):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url='/login', status_code=302)
    if user['username'] != 'admin':
        return HTMLResponse(content="<h1>403 禁止访问</h1>", status_code=403)
    db = get_db_conn()
    cur = db.cursor()
    cur.execute("UPDATE book_info SET stock = ? WHERE id = ?", (stock, book_id))
    db.commit()
    cur.close()
    db.close()
    url = f'/admin?tab=books&page={page}'
    if search:
        url += f'&search={search}'
    if category:
        url += f'&category={category}'
    return RedirectResponse(url=url, status_code=302)

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, page: int = 1, tab: str = 'dashboard', search: str = "", category: str = ""):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url='/login', status_code=302)
    if user['username'] != 'admin':
        return HTMLResponse(content="<h1>403 禁止访问</h1><p>只有管理员可以访问此页面</p><a href='/'>返回首页</a>", status_code=403)
    db = get_db_conn()
    cur = db.cursor()
    page_size = 16
    offset = (page-1)*page_size

    if tab == 'orders':
        query = """SELECT o.id, b.title, b.price, b.star, b.category, o.quantity, o.created_at, b.img_url, o.created_at, o.status, u.username
                   FROM orders o JOIN book_info b ON o.book_id = b.id JOIN users u ON o.user_id = u.id
                   ORDER BY o.created_at DESC LIMIT ?,?"""
        cur.execute(query, (offset, page_size))
        orders = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM orders")
        total = cur.fetchone()[0]
        total_page = (total + page_size -1)//page_size
        cur.close()
        db.close()
        template = jinja_env.get_template("admin.html")
        html = template.render(orders=orders, page=page, total_page=total_page, total=total, user=user, active_tab='orders')

    elif tab == 'users':
        query = "SELECT id, username FROM users WHERE 1=1"
        params = []
        if search:
            query += " AND username LIKE ?"
            params.append(f"%{search}%")
        query += " ORDER BY id DESC LIMIT ?,?"
        params.extend([offset, page_size])
        cur.execute(query, params)
        users = cur.fetchall()
        count_query = "SELECT COUNT(*) FROM users WHERE 1=1"
        count_params = []
        if search:
            count_query += " AND username LIKE ?"
            count_params.append(f"%{search}%")
        cur.execute(count_query, count_params)
        total = cur.fetchone()[0]
        total_page = (total + page_size -1)//page_size
        cur.close()
        db.close()
        template = jinja_env.get_template("admin.html")
        html = template.render(users=users, page=page, total_page=total_page, total=total, user=user, active_tab='users', search=search)

    elif tab == 'books':
        query = "SELECT * FROM book_info WHERE 1=1"
        params = []
        if search:
            query += " AND title LIKE ?"
            params.append(f"%{search}%")
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " LIMIT ?,?"
        params.extend([offset, page_size])
        cur.execute(query, params)
        books = cur.fetchall()
        count_query = "SELECT COUNT(*) FROM book_info WHERE 1=1"
        count_params = []
        if search:
            count_query += " AND title LIKE ?"
            count_params.append(f"%{search}%")
        if category:
            count_query += " AND category = ?"
            count_params.append(category)
        cur.execute(count_query, count_params)
        total = cur.fetchone()[0]
        total_page = (total + page_size -1)//page_size
        cur.execute("SELECT DISTINCT category FROM book_info")
        categories = [row[0] for row in cur.fetchall()]
        cur.close()
        db.close()
        template = jinja_env.get_template("admin.html")
        html = template.render(books=books, page=page, total_page=total_page, total=total, user=user, active_tab='books', search=search, categories=categories, selected_category=category)

    else:
        cur.execute("SELECT COUNT(*) FROM book_info")
        total_books = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orders")
        total_orders = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(price * quantity), 0) FROM orders WHERE status = 'completed'")
        total_sales = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
        pending_orders = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orders WHERE status = 'shipped'")
        shipped_orders = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed'")
        completed_orders = cur.fetchone()[0]
        
        cur.execute("""SELECT b.category, COUNT(*) as count 
                       FROM book_info b GROUP BY b.category ORDER BY count DESC LIMIT 5""")
        category_stats = cur.fetchall()
        
        cur.execute("""SELECT strftime('%Y-%m-%d', o.created_at) as date, COUNT(*) as count, SUM(o.price * o.quantity) as revenue 
                       FROM orders o WHERE o.created_at >= datetime('now', '-7 days') 
                       GROUP BY date ORDER BY date""")
        recent_orders = cur.fetchall()
        
        cur.execute("""SELECT b.title, b.id, COUNT(o.id) as order_count, SUM(o.price * o.quantity) as total_revenue
                       FROM book_info b LEFT JOIN orders o ON b.id = o.book_id 
                       GROUP BY b.id ORDER BY order_count DESC LIMIT 5""")
        top_books = cur.fetchall()
        
        cur.execute("""SELECT u.username, COUNT(o.id) as order_count, SUM(o.price * o.quantity) as total_spent 
                       FROM users u LEFT JOIN orders o ON u.id = o.user_id 
                       GROUP BY u.id ORDER BY total_spent DESC LIMIT 5""")
        top_users = cur.fetchall()
        
        cur.execute("""SELECT b.category, COUNT(o.id) as sales_count, COALESCE(SUM(o.price * o.quantity), 0) as sales_revenue
                       FROM book_info b LEFT JOIN orders o ON b.id = o.book_id 
                       GROUP BY b.category ORDER BY sales_revenue DESC LIMIT 5""")
        category_sales = cur.fetchall()
        
        cur.execute("""SELECT strftime('%Y-%m', o.created_at) as month, COUNT(*) as count, COALESCE(SUM(o.price * o.quantity), 0) as revenue
                       FROM orders o WHERE o.created_at >= datetime('now', '-6 months')
                       GROUP BY month ORDER BY month""")
        monthly_sales = cur.fetchall()
        
        cur.execute("""SELECT b.title, b.id, b.stock, b.price 
                       FROM book_info b WHERE b.stock <= 10 ORDER BY b.stock ASC LIMIT 5""")
        low_stock = cur.fetchall()
        
        cur.execute("SELECT COALESCE(AVG(price * quantity), 0) FROM orders WHERE status = 'completed'")
        avg_order_value = cur.fetchone()[0]
        
        cur.execute("""SELECT strftime('%Y-%m-%d', o.created_at) as date, COUNT(*) as count
                       FROM orders o WHERE o.created_at >= datetime('now', '-30 days')
                       GROUP BY date ORDER BY date""")
        daily_orders_30d = cur.fetchall()
        
        cur.close()
        db.close()
        template = jinja_env.get_template("admin.html")
        html = template.render(
            user=user, active_tab='dashboard',
            total_books=total_books, total_users=total_users, total_orders=total_orders,
            total_sales=total_sales, pending_orders=pending_orders, shipped_orders=shipped_orders,
            completed_orders=completed_orders, category_stats=category_stats,
            recent_orders=recent_orders, top_books=top_books, top_users=top_users,
            category_sales=category_sales, monthly_sales=monthly_sales, low_stock=low_stock,
            avg_order_value=avg_order_value, daily_orders_30d=daily_orders_30d
        )
    return HTMLResponse(content=html)

@app.post("/admin/delete_user", response_class=HTMLResponse)
async def admin_delete_user(request: Request, user_id: int = Form(...), page: int = Form(1), search: str = Form("")):
    user = get_session_user(request)
    if not user or user['username'] != 'admin':
        return HTMLResponse(content="<h1>403 禁止访问</h1>", status_code=403)
    db = get_db_conn()
    cur = db.cursor()
    cur.execute("DELETE FROM orders WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM favorites WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    cur.close()
    db.close()
    url = f'/admin?tab=users&page={page}'
    if search:
        url += f'&search={search}'
    return RedirectResponse(url=url, status_code=302)

@app.get("/admin/export_books", response_class=HTMLResponse)
async def export_books(request: Request):
    user = get_session_user(request)
    if not user or user['username'] != 'admin':
        return HTMLResponse(content="<h1>403 禁止访问</h1>", status_code=403)
    db = get_db_conn()
    cur = db.cursor()
    cur.execute("SELECT * FROM book_info")
    books = cur.fetchall()
    cur.close()
    db.close()
    import csv
    from io import StringIO
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', '书名', '价格', '评分', '分类', '库存', '描述', '封面URL'])
    for book in books:
        writer.writerow([book[0], book[1], book[2], book[3], book[4], book[5], book[6], book[7]])
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content=output.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename=books.csv'})

@app.get("/admin/export_orders", response_class=HTMLResponse)
async def export_orders(request: Request):
    user = get_session_user(request)
    if not user or user['username'] != 'admin':
        return HTMLResponse(content="<h1>403 禁止访问</h1>", status_code=403)
    db = get_db_conn()
    cur = db.cursor()
    cur.execute("""SELECT o.id, b.title, b.price, o.quantity, o.status, o.created_at, u.username
                   FROM orders o JOIN book_info b ON o.book_id = b.id JOIN users u ON o.user_id = u.id""")
    orders = cur.fetchall()
    cur.close()
    db.close()
    import csv
    from io import StringIO
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['订单ID', '书名', '单价', '数量', '状态', '下单时间', '购买用户'])
    for order in orders:
        writer.writerow([order[0], order[1], order[2], order[3], order[4], order[5], order[6]])
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content=output.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename=orders.csv'})

@app.post("/buy", response_class=HTMLResponse)
async def buy_book(request: Request, book_id: int = Form(...), page: int = Form(1)):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url='/login', status_code=302)
    db = get_db_conn()
    cur = db.cursor()
    cur.execute("SELECT stock, price, title FROM book_info WHERE id = ?", (book_id,))
    book = cur.fetchone()
    if not book:
        db.close()
        return RedirectResponse(url=f'/?page={page}', status_code=302)
    stock = int(book[0])
    if stock <= 0:
        db.close()
        return RedirectResponse(url=f'/?page={page}', status_code=302)
    cur.execute("UPDATE book_info SET stock = stock - 1 WHERE id = ?", (book_id,))
    import datetime
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur.execute("INSERT INTO orders (user_id, book_id, price, quantity, status, created_at) VALUES (?, ?, ?, 1, 'pending', ?)",
                (user['id'], book_id, book[1], now))
    db.commit()
    cur.close()
    db.close()
    return RedirectResponse(url=f'/orders', status_code=302)

@app.post("/cancel_order", response_class=HTMLResponse)
async def cancel_order(request: Request, order_id: int = Form(...)):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url='/login', status_code=302)
    db = get_db_conn()
    cur = db.cursor()
    cur.execute("SELECT status, book_id FROM orders WHERE id = ? AND user_id = ?", (order_id, user['id']))
    order = cur.fetchone()
    if order and order[0] == 'pending':
        cur.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
        cur.execute("UPDATE book_info SET stock = stock + 1 WHERE id = ?", (order[1],))
        db.commit()
    cur.close()
    db.close()
    return RedirectResponse(url='/orders', status_code=302)

@app.post("/delete_order")
async def delete_order(request: Request, order_id: int = Form(...)):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url='/login', status_code=302)
    db = get_db_conn()
    cur = db.cursor()
    cur.execute("SELECT status FROM orders WHERE id = ? AND user_id = ?", (order_id, user['id']))
    order = cur.fetchone()
    if order and order[0] == 'cancelled':
        cur.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        db.commit()
    cur.close()
    db.close()
    return RedirectResponse(url='/orders', status_code=302)

@app.get("/orders", response_class=HTMLResponse)
async def orders(request: Request, page: int=1):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url='/login', status_code=302)
    db = get_db_conn()
    cur = db.cursor()
    page_size = 12
    offset = (page-1)*page_size
    cur.execute("""SELECT o.id, b.title, b.price, b.star, b.category, o.quantity, o.created_at, b.img_url, o.created_at, o.status 
                   FROM orders o JOIN book_info b ON o.book_id = b.id 
                   WHERE o.user_id = ? ORDER BY o.created_at DESC LIMIT ?,?""", 
                (user['id'], offset, page_size))
    orders = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user['id'],))
    total = cur.fetchone()[0]
    total_page = (total + page_size -1)//page_size
    cur.close()
    db.close()
    template = jinja_env.get_template("orders.html")
    html = template.render(orders=orders, user=user, page=page, total_page=total_page)
    return HTMLResponse(content=html)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, page: int=1, show_favorites: int=0, tab: str = 'books', category: str = ""):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url='/login', status_code=302)
    
    if tab == 'orders':
        db = get_db_conn()
        cur = db.cursor()
        page_size = 12
        offset = (page-1)*page_size
        cur.execute("""SELECT o.id, b.title, b.price, b.star, b.category, o.quantity, o.created_at, b.img_url, o.created_at, o.status 
                       FROM orders o JOIN book_info b ON o.book_id = b.id 
                       WHERE o.user_id = ? ORDER BY o.created_at DESC LIMIT ?,?""", 
                    (user['id'], offset, page_size))
        orders = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user['id'],))
        total = cur.fetchone()[0]
        total_page = (total + page_size -1)//page_size
        cur.close()
        db.close()
        template = jinja_env.get_template("orders.html")
        html = template.render(orders=orders, user=user, page=page, total_page=total_page, active_tab='orders')
        return HTMLResponse(content=html)
    
    db = get_db_conn()
    cur = db.cursor()
    
    # 获取所有分类
    cur.execute("SELECT DISTINCT category FROM book_info ORDER BY category")
    categories = [row[0] for row in cur.fetchall()]
    
    if tab == 'favorites' or show_favorites:
        cur.execute("SELECT b.* FROM book_info b JOIN favorites f ON b.id = f.book_id WHERE f.user_id = ?", (user['id'],))
        books = cur.fetchall()
        total = len(books)
        total_page = 1
    else:
        page_size = 12
        offset = (page-1)*page_size
        if category:
            cur.execute("SELECT * FROM book_info WHERE category = ? LIMIT ?,?", (category, offset, page_size))
            books = cur.fetchall()
            cur.execute("SELECT COUNT(*) FROM book_info WHERE category = ?", (category,))
            total = cur.fetchone()[0]
        else:
            cur.execute("SELECT * FROM book_info LIMIT ?,?", (offset, page_size))
            books = cur.fetchall()
            cur.execute("SELECT COUNT(*) FROM book_info")
            total = cur.fetchone()[0]
        total_page = (total + page_size -1)//page_size
    cur.execute("SELECT book_id FROM favorites WHERE user_id = ?", (user['id'],))
    favorite_ids = set([row[0] for row in cur.fetchall()])
    cur.close()
    db.close()
    template = jinja_env.get_template("index.html")
    html = template.render(
        books=books,
        page=page,
        total_page=total_page,
        show_favorites=(tab == 'favorites' or show_favorites),
        favorite_ids=favorite_ids,
        user=user,
        categories=categories,
        selected_category=category
    )
    return HTMLResponse(content=html)

@app.get("/book/{book_id}", response_class=HTMLResponse)
async def book_detail(request: Request, book_id: int):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url='/login', status_code=302)
    db = get_db_conn()
    cur = db.cursor()
    cur.execute("SELECT * FROM book_info WHERE id = ?", (book_id,))
    book = cur.fetchone()
    cur.execute("SELECT book_id FROM favorites WHERE user_id = ?", (user['id'],))
    favorite_ids = set([row[0] for row in cur.fetchall()])
    cur.close()
    db.close()
    if not book:
        template = jinja_env.get_template("index.html")
        return HTMLResponse(content=template.render(books=[], page=1, total_page=1, favorite_ids=favorite_ids, user=user))
    template = jinja_env.get_template("book_detail.html")
    html = template.render(book=book, favorite_ids=favorite_ids, user=user)
    return HTMLResponse(content=html)

@app.post("/toggle_favorite", response_class=HTMLResponse)
async def toggle_favorite(request: Request, book_id: int = Form(...), page: int = Form(1), show_favorites: int = Form(0)):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url='/login', status_code=302)
    db = get_db_conn()
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM favorites WHERE user_id = ? AND book_id = ?", (user['id'], book_id))
    exists = cur.fetchone()[0] > 0
    if exists:
        cur.execute("DELETE FROM favorites WHERE user_id = ? AND book_id = ?", (user['id'], book_id))
    else:
        cur.execute("INSERT OR IGNORE INTO favorites (user_id, book_id) VALUES (?, ?)", (user['id'], book_id))
    db.commit()
    db.close()
    referer = request.headers.get("referer", "/")
    if "/book/" in referer:
        return await book_detail(request, book_id=book_id)
    return await index(request, page=page, show_favorites=show_favorites)

@app.post("/chat", response_class=HTMLResponse)
async def chat(request: Request, question: str = Form(...), page: int = Form(1)):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url='/login', status_code=302)
    db = get_db_conn()
    cur = db.cursor()
    cur.execute("SELECT id,title,price,star,category,description,img_url FROM book_info LIMIT 80")
    all_books = cur.fetchall()
    context = ""
    for b in all_books:
        context += f"ID:{b[0]},书名:{b[1]},分类:{b[4]},价格:{b[2]}镑,评分{b[3]}星,简介:{b[5]}\n"
    prompt = f"""你是图书专属智能助手，只能依据下面给出的图书数据回答用户，禁止编造不存在的书籍：
【图书知识库】
{context}
用户问题：{question}

要求：
1. 首先给出文字回答，解释推荐理由
2. 如果推荐了书籍，必须在回答末尾以JSON格式返回推荐书籍的ID列表，格式如下：
[推荐书籍ID: [1, 5, 12]]
3. ID必须是知识库中真实存在的ID
"""
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type":"application/json"}
    payload = {
        "model": "qwen-plus",
        "input": {"messages": [{"role":"user","content": prompt}]},
        "parameters": {"temperature": 0.7}
    }
    recommended_books = []
    try:
        res = requests.post(LLM_URL, json=payload, headers=headers, timeout=30)
        res.raise_for_status()
        ans = res.json()["output"]["text"]
        import re
        id_match = re.search(r'\[推荐书籍ID:\s*\[([^\]]+)\]\]', ans)
        if id_match:
            ids = [int(x.strip()) for x in id_match.group(1).split(',') if x.strip().isdigit()]
            if ids:
                placeholders = ','.join(['?' for _ in ids])
                cur.execute(f"SELECT * FROM book_info WHERE id IN ({placeholders})", ids)
                recommended_books = cur.fetchall()
            ans = ans.replace(id_match.group(0), '')
    except requests.exceptions.HTTPError as e:
        if res.status_code == 401:
            ans = "❌ 抱歉，API Key 无效，请检查你的 API Key 是否正确。"
        elif res.status_code == 402:
            ans = "❌ 抱歉，API 账户余额不足，请充值后再试。"
        else:
            ans = f"❌ API 请求失败，错误代码：{res.status_code}"
    except Exception as e:
        ans = f"❌ 请求发生错误：{str(e)}"
    page_size = 12
    offset = (page-1)*page_size
    cur.execute("SELECT * FROM book_info LIMIT ?,?", (offset, page_size))
    books = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM book_info")
    total = cur.fetchone()[0]
    total_page = (total + page_size -1)//page_size
    cur.execute("SELECT book_id FROM favorites WHERE user_id = ?", (user['id'],))
    favorite_ids = set([row[0] for row in cur.fetchall()])
    cur.close()
    db.close()
    template = jinja_env.get_template("index.html")
    html = template.render(
        books=books,
        page=page,
        total_page=total_page,
        ans=ans,
        question=question,
        recommended_books=recommended_books,
        favorite_ids=favorite_ids,
        user=user
    )
    return HTMLResponse(content=html)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", reload=False)