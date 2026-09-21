import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import os

DB_FILE = "book_data.db"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}
BASE_URL = "https://books.toscrape.com/catalogue/page-{}.html"
STAR_MAP = {"One":1, "Two":2, "Three":3, "Four":4, "Five":5}

# 初始化数据库表
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS book_info (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        price REAL,
        star INTEGER,
        category TEXT,
        stock TEXT,
        description TEXT,
        img_url TEXT
    )
    ''')
    conn.commit()
    conn.close()

def save_book(data):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute('''
    INSERT INTO book_info(title,price,star,category,stock,description,img_url)
    VALUES(?,?,?,?,?,?,?)
    ''', (
        data["title"], data["price"], data["star"], data["category"],
        data["stock"], data["desc"], data["img"]
    ))
    conn.commit()
    conn.close()

def get_category(soup):
    bread = soup.select(".breadcrumb li")
    return bread[-2].get_text(strip=True) if len(bread)>=2 else "Unknown"

def get_book_detail(detail_url):
    res = requests.get(detail_url, headers=HEADERS)
    soup = BeautifulSoup(res.text, "html.parser")
    stock = soup.select_one(".instock.availability").get_text(strip=True)
    desc_tag = soup.select_one("#product_description ~ p")
    desc = desc_tag.get_text(strip=True) if desc_tag else ""
    return stock, desc

def crawl_all():
    init_db()
    page = 1
    while True:
        url = BASE_URL.format(page)
        print(f"正在爬取第{page}页: {url}")
        res = requests.get(url, headers=HEADERS)
        if res.status_code != 200:
            break
        soup = BeautifulSoup(res.text, "html.parser")
        books = soup.select(".product_pod")
        if not books:
            break
        cate = get_category(soup)
        for item in books:
            title = item.h3.a["title"]
            price_text = item.select_one(".price_color").text
            # 只保留数字和小数点
            clean_price = ''.join([c for c in price_text if c.isdigit() or c == '.'])
            price = float(clean_price)
            star_cls = item.select_one(".star-rating")["class"][1]
            star = STAR_MAP[star_cls]
            img_src = item.select_one("img")["src"]
            img = "https://books.toscrape.com/" + img_src.replace("../", "")
            href = item.h3.a["href"]
            detail_link = "https://books.toscrape.com/catalogue/" + href.replace("../", "")
            stock, desc = get_book_detail(detail_link)
            book_data = {
                "title": title,
                "price": price,
                "star": star,
                "category": cate,
                "stock": stock,
                "desc": desc,
                "img": img
            }
            save_book(book_data)
            time.sleep(0.4)
        page += 1
        time.sleep(0.8)
    print("✅ 全部书籍爬取完成，数据存入 book_data.db")

if __name__ == "__main__":
    crawl_all()