## 收藏品管理系統
使用django作為後端框架
### 如何執行？
要先建django環境
用migrate定義資料庫架構
去申請ebay api ，api的憑證和使用者要打（創建一個.env檔寫EBAY_CLIENT_ID= EBAY_CLIENT_SECRET＝在裡面）
在terminal打python manage.py runserver
用瀏覽器打localhost就能打開了
Model : 定義一些資料庫的架構。

Template : 使用者基本上就是看到這層，也就是最後所呈現的 Template ( html )。

View : 可以將這層看做是中間層，它主要負責 Model 和 Template 之間的業務邏輯。

記得要push前先pull確保版本一致



