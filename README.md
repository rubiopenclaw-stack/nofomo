# 📈 NoFOMO - 股票交易記錄與點位建議系統

> 記錄每一筆股票交易，並於交易當下提供技術分析建議，幫助投資人避免重蹈相同錯誤。

## 🛠 技術棧

| 層面 | 技術 |
|------|------|
| 前端 | React + Vite |
| 後端 | FastAPI (Python) |
| 伺服器 | Flask |
| 資料儲存 | JSON 檔案 |

## 🎯 核心功能

- 📊 **即時股價** - 搜尋最新報價、52週高低點
- 📝 **交易記錄** - 記錄每筆買賣、價位、數量
- 💡 **點位建議** - 根據技術分析給出買入/賣出建議
- 📈 **總資產儀表板** - 追蹤持倉、損益、報酬率
- 🔍 **錯誤回顧** - 分析過去失誤操作，提出改進建議

---

## 🚀 快速開始

### 後端（FastAPI）

```bash
cd nofomo
pip install -r requirements.txt
python -m src.api
```

後端伺服器：http://localhost:5000

### 前端（React + Vite）

```bash
cd ui
npm install
npm run dev
```

前端伺服器：http://localhost:5173

---

## 📡 API 端點說明

### 報價與分析

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/quote` | GET | 查詢個股報價 |
| `/api/analyze` | GET | 技術分析報告 |
| `/api/batch-quote` | GET | 批量查詢報價 |
| `/api/watchlist` | GET | 取得自選股清單 |

### 交易記錄

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/trades` | GET | 取得所有交易紀錄 |
| `/api/trades` | POST | 新增交易紀錄 |
| `/api/trades/analysis` | GET | 交易紀錄分析 |

### 投資組合

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/portfolio` | GET | 取得目前持倉 |
| `/api/portfolio/summary` | GET | **總資產儀表板** |
| `/api/portfolio/performance` | GET | 投資組合績效 |
| `/api/history` | GET | 歷史記錄 |

### 警示與訊號

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/alerts` | GET/POST/DELETE | 價格警示 |
| `/api/alerts/check` | GET | 檢查警示觸發 |
| `/api/signals` | GET | 交易訊號 |
| `/api/risk评估` | GET | 風險評估 |

---

## 📋 技術指標說明

| 指標 | 用途 |
|------|------|
| MA5/20/60 | 判斷趨勢方向 |
| RSI | 超買超賣判斷 (<30 買, >70 賣) |
| MACD | 動能與背離分析 |
| 布林通道 | 波動範圍與支撐壓力 |

---

## 📁 專案結構

```
nofomo/
├── src/
│   ├── api.py           # FastAPI 後端伺服器
│   ├── analyzer.py      # 技術分析模組
│   └── portfolio.py    # 持倉管理
├── ui/                  # React + Vite 前端
│   ├── src/             # React 元件
│   └── package.json
├── data/
│   ├── trades/          # 交易記錄
│   └── portfolio.json   # 持倉資料
├── requirements.txt
└── README.md
```

---

## 📊 評分標準

| 評分 | 條件 | 操作建議 |
|------|------|----------|
| ⭐⭐⭐⭐⭐ | 強烈買入 | 均線多頭 + RSI 40-60 + MACD金叉 + 放量 |
| ⭐⭐⭐⭐ | 偏多買入 | 趨勢向上 + 回調至MA20支撐 |
| ⭐⭐⭐ | 觀察等待 | 訊號混合，小倉試單 |
| ⭐⭐ | 謹慎操作 | 趨勢不明，設嚴格停損 |
| ⭐ | 不建議買入 | 空頭趨勢 + RSI超買 |

---

## ⚙️ 停損與目標原則

- **停損**: 買入價下方 5-8%
- **第一目標**: 買入價 +10-15%
- **第二目標**: 買入價 +20-30%
- **風報比**: 至少 1:2

---

## License

MIT
