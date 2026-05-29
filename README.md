# 收藏品管理系統 — Collect Terminal

一個以 Django 為後端的個人收藏品投資組合追蹤系統，支援搜尋 eBay 商品與 Pokémon TCG 卡牌、記錄買入價格與數量，並提供 P&L、ROI、Analytics 等多頁儀表板。

---

## 環境需求

- Python 3.9 以上
- pip

---

## 快速開始

### 1. Clone 專案

```bash
git clone <repo-url>
cd dbms_final_project
```

### 2. 建立虛擬環境並安裝套件

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install django requests python-dotenv
```

### 3. 設定 eBay API 金鑰

在專案根目錄建立 `.env` 檔案（與 `manage.py` 同層）：

```
EBAY_CLIENT_ID=你的_eBay_Client_ID
EBAY_CLIENT_SECRET=你的_eBay_Client_Secret
```

> eBay API 金鑰申請：前往 [eBay Developer Program](https://developer.ebay.com/)，建立 Application 後取得 **Production** 的 Client ID 與 Client Secret。
>
> Pokémon TCG API 不需要金鑰，直接可用。

### 4. 初始化資料庫

```bash
python manage.py migrate
```

### 5. 建立管理員帳號（可選）

```bash
python manage.py createsuperuser
```

建立後可從 `http://localhost:8000/admin/` 管理資料庫內容。

### 6. 啟動伺服器

```bash
python manage.py runserver
```

打開瀏覽器前往 `http://localhost:8000`，先至右上角**註冊**帳號即可開始使用。

---

## 主要功能

| 頁面 | 說明 |
|---|---|
| Dashboard | 投資組合總覽、今日漲跌、Top Gainers / Losers |
| Inventory | 收藏品清單，支援查看詳情、編輯備註 |
| Search | 搜尋 eBay 商品或 Pokémon TCG 卡牌並加入收藏 |
| ROI | 各品項報酬率排行 |
| Analytics | 時序走勢圖、Sharpe / Sortino / Calmar Ratio、Drawdown |
| Market | 全市場漲跌排行、類別 Heatmap、PTCG 最新新聞 |

---

## 協作注意事項

- Push 前請先 `git pull` 確保版本一致
- `.env` 檔案已被 `.gitignore` 排除，請勿 commit 金鑰
