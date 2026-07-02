"""
极简自动发卡系统
- 单文件，零依赖（除Flask）
- 付款后自动返回激活码
- 支持微信/支付宝收款码
"""
import json, os, csv, uuid, time, hashlib
from datetime import datetime

# ============ 配置区 ============
CONFIG = {
    "product_name": "navos 激活码",
    "price": "29.9",
    "tiers": {
        "3D": {"name": "3天体验", "price": "5.8"},
        "7D": {"name": "7天", "price": "13.8"},
        "30D": {"name": "30天", "price": "25.8"},
    },
    # 收款码图片路径（放在 static/ 目录下）
    "wechat_qr": "static/wechat.jpg",
    "alipay_qr": "static/alipay.jpg",
    # 联系方式（付款后显示）
    "contact_qq": "你的QQ号",
    "contact_wx": "你的微信号",
}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "cards.json")
ORDERS_FILE = os.path.join(BASE_DIR, "orders.json")

def load_cards():
    """加载所有激活码到内存"""
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_cards(cards):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)

def load_orders():
    if not os.path.exists(ORDERS_FILE):
        return []
    with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_orders(orders):
    with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)

def import_csv(csv_path):
    """从 gen_code.py 生成的 CSV 导入激活码"""
    cards = load_cards()
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cards.append({
                "code": row["卡号"],
                "card_data": row["卡密"],
                "tier": row["卡号"].split("-")[1] if "-" in row["卡号"] else "30D",
                "used": False,
                "order_id": None,
                "used_at": None,
            })
    save_cards(cards)
    return len(cards)

def get_card(tier):
    """获取一张未使用的激活码"""
    cards = load_cards()
    for card in cards:
        if not card["used"] and card["tier"] == tier:
            return card
    return None

def mark_used(card_id, order_id):
    cards = load_cards()
    for c in cards:
        if c["code"] == card_id:
            c["used"] = True
            c["order_id"] = order_id
            c["used_at"] = datetime.now().isoformat()
            break
    save_cards(cards)

# ============ Flask 路由 ============
from flask import Flask, render_template_string, request, jsonify, send_file

app = Flask(__name__)

HTML_PAGE = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ config.product_name }} - 购买激活码</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, 'Microsoft YaHei', sans-serif;
       background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
       min-height: 100vh; color: #fff; }
.container { max-width: 800px; margin: 0 auto; padding: 20px; }
.header { text-align: center; padding: 40px 20px; }
.header h1 { font-size: 28px; background: linear-gradient(90deg, #e94560, #f5a623);
             -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.header p { color: #888; margin-top: 10px; }

.tiers { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
         gap: 15px; margin: 30px 0; }
.tier-card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px; padding: 25px 15px; text-align: center;
            cursor: pointer; transition: all 0.3s; position: relative; }
.tier-card:hover { transform: translateY(-3px); border-color: #e94560;
                    background: rgba(233,69,96,0.1); }
.tier-card.selected { border-color: #e94560; background: rgba(233,69,96,0.15);
                     box-shadow: 0 0 20px rgba(233,69,96,0.3); }
.tier-card .check { display: none; position: absolute; top: 8px; right: 8px;
                   width: 22px; height: 22px; background: #e94560; border-radius: 50%;
                   line-height: 22px; font-size: 14px; }
.tier-card.selected .check { display: block; }
.tier-name { font-size: 18px; font-weight: bold; margin-bottom: 8px; }
.tier-price { font-size: 24px; color: #e94560; font-weight: bold; }
.tier-price span { font-size: 12px; color: #888; }

.pay-section { background: rgba(255,255,255,0.05); border-radius: 16px;
              padding: 30px; margin-top: 20px; }
.pay-title { font-size: 18px; margin-bottom: 20px; text-align: center; }
.qr-codes { display: flex; justify-content: center; gap: 40px; flex-wrap: wrap; }
.qr-item { text-align: center; }
.qr-item img { width: 180px; height: 180px; border-radius: 10px;
               background: #fff; padding: 10px; }
.qr-item p { margin-top: 8px; color: #aaa; }

.pay-warning { background: rgba(245,166,35,0.15); border: 1px solid #f5a623;
               border-radius: 8px; padding: 12px 20px; margin-top: 20px;
               text-align: center; font-size: 14px; color: #f5a623; }
.pay-warning strong { color: #fff; }

.order-section { margin-top: 30px; }
.input-group { max-width: 400px; margin: 0 auto 20px; }
.input-group input { width: 100%; padding: 12px 16px; border: 1px solid rgba(255,255,255,0.2);
                    border-radius: 8px; background: rgba(255,255,255,0.05); color: #fff;
                    font-size: 14px; outline: none; transition: border-color 0.3s; }
.input-group input:focus { border-color: #e94560; }
.input-group input::placeholder { color: #555; }

.btn-buy { display: block; width: 200px; margin: 20px auto; padding: 14px;
           background: linear-gradient(90deg, #e94560, #f5a623); color: #fff;
           border: none; border-radius: 30px; font-size: 16px; font-weight: bold;
           cursor: pointer; transition: transform 0.2s; }
.btn-buy:hover { transform: scale(1.05); }
.btn-buy:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

.result-box { background: rgba(233,69,96,0.1); border: 1px solid #e94560;
              border-radius: 12px; padding: 20px; margin-top: 20px; display: none; }
.result-box.show { display: block; animation: fadeIn 0.5s; }
.result-label { color: #888; font-size: 13px; margin-bottom: 8px; }
.result-code { font-family: monospace; font-size: 14px; word-break: break-all;
               background: rgba(0,0,0,0.3); padding: 15px; border-radius: 8px;
               color: #00ff88; user-select: all; }
.btn-copy { margin-top: 10px; padding: 8px 20px; background: #e94560; color: #fff;
            border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }

.contact { text-align: center; margin-top: 30px; color: #666; font-size: 13px; }
.footer { text-align: center; margin-top: 40px; color: #444; font-size: 12px; }
@keyframes fadeIn { from {opacity:0;transform:translateY(10px);} to {opacity:1;transform:translateY(0);} }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{{ config.product_name }}</h1>
    <p>选择套餐 → 扫码付款 → 自动获取激活码</p>
  </div>

  <div class="tiers">
    {% for tid, tier in config.tiers.items() %}
    <div class="tier-card" data-tier="{{ tid }}" onclick="selectTier(this)">
      <div class="check">✓</div>
      <div class="tier-name">{{ tier.name }}</div>
      <div class="tier-price">¥{{ tier.price }}<span>/份</span></div>
    </div>
    {% endfor %}
  </div>

  <div class="pay-section">
    <div class="pay-title">📱 请使用支付宝扫码支付 <span id="payAmount" style="color:#e94560;font-weight:bold;">¥5.8</span></div>
    <div class="qr-codes">
      <div class="qr-item">
        <img id="alipayQr" src="/static/5.8.jpg" alt="支付宝">
        <p>支付宝</p>
      </div>
    </div>

    <div class="pay-warning">
      ⚠️ 请务必支付<strong>正确金额</strong>，金额不符将无法获取激活码，且订单将被记录
    </div>

    <div class="order-section">
      <div class="input-group">
        <input type="text" id="buyerContact" placeholder="您的联系方式（QQ/微信号），用于发送激活码">
      </div>
      <button class="btn-buy" id="buyBtn" onclick="confirmPay()">
        我已付款，获取激活码
      </button>
    </div>
  </div>

  <div class="result-box" id="resultBox">
    <div class="result-label">🎉 您的激活数据（请复制完整内容）：</div>
    <div class="result-code" id="resultCode"></div>
    <button class="btn-copy" onclick="copyCode()">复制激活数据</button>
  </div>

  <div class="contact">
    如有问题请联系 QQ：{{ config.contact_qq }} | 微信：{{ config.contact_wx }}
  </div>

  <div class="footer">Powered by 离线激活系统</div>
</div>

<script>
// 档位收款码映射（仅支付宝）
const QR_MAP = {
  '3D':  { alipay: '/static/5.8.jpg', price: '¥5.8' },
  '7D':  { alipay: '/static/13.8.jpg', price: '¥13.8' },
  '30D': { alipay: '/static/25.8.jpg', price: '¥25.8' },
};

let selectedTier = '3D';
document.querySelector(`[data-tier="${selectedTier}"]`).classList.add('selected');

function selectTier(el) {
  document.querySelectorAll('.tier-card').forEach(c => c.classList.remove('selected'));
  el.classList.add('selected');
  selectedTier = el.dataset.tier;
  // 切换收款码和金额
  const qr = QR_MAP[selectedTier];
  document.getElementById('alipayQr').src = qr.alipay;
  document.getElementById('payAmount').textContent = qr.price;
}

async function confirmPay() {
  const btn = document.getElementById('buyBtn');
  const contact = document.getElementById('buyerContact').value.trim();
  
  if (!contact) {
    alert('请填写联系方式'); return;
  }

  btn.disabled = true;
  btn.textContent = '正在处理...';

  try {
    const resp = await fetch('/api/buy', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ tier: selectedTier, contact: contact })
    });
    const data = await resp.json();

    if (data.ok) {
      document.getElementById('resultCode').textContent = data.card_data;
      document.getElementById('resultBox').classList.add('show');
      btn.textContent = '✓ 激活码已发放';
    } else {
      alert(data.error || '发放失败，请联系客服');
      btn.disabled = false;
      btn.textContent = '我已付款，获取激活码';
    }
  } catch(e) {
    alert('网络错误，请重试');
    btn.disabled = false;
    btn.textContent = '我已付款，获取激活码';
  }
}

function copyCode() {
  const code = document.getElementById('resultCode').textContent;
  navigator.clipboard.writeText(code).then(() => {
    alert('已复制！请粘贴到工具的激活对话框中');
  }).catch(() => {
    // fallback
    const ta = document.createElement('textarea');
    ta.value = code; document.body.appendChild(ta);
    ta.select(); document.execCommand('copy');
    document.body.removeChild(ta);
    alert('已复制！');
  });
}
</script>
</body>
</html>'''

@app.route('/')
def index():
    return render_template_string(HTML_PAGE, config=CONFIG)

@app.route('/api/buy', methods=['POST'])
def api_buy():
    data = request.get_json() or {}
    tier = data.get('tier', '30D')
    contact = data.get('contact', '')

    card = get_card(tier)
    if not card:
        return jsonify({"ok": False, "error": f"{tier} 档位库存不足，请稍后尝试或联系客服"})

    order_id = str(uuid.uuid4())[:8].upper()
    mark_used(card['code'], order_id)

    # 记录订单
    orders = load_orders()
    orders.append({
        "order_id": order_id,
        "tier": tier,
        "card_code": card['code'],
        "contact": contact,
        "time": datetime.now().isoformat(),
    })
    save_orders(orders)

    return jsonify({
        "ok": True,
        "card_data": card['card_data'],
        "card_code": card['code'],
        "order_id": order_id,
    })

@app.route('/admin')
def admin():
    """管理面板：查看库存和订单"""
    cards = load_cards()
    orders = load_orders()
    
    total = len(cards)
    used = sum(1 for c in cards if c['used'])
    available = total - used
    
    by_tier = {}
    for t in CONFIG['tiers']:
        tc = [c for c in cards if c['tier'] == t]
        by_tier[t] = {"total": len(tc), "available": sum(1 for c in tc if not c['used'])}
    
    html = f'''
    <!DOCTYPE html><html><head><meta charset="UTF-8"><title>管理面板</title>
    <style>
      body {{ font-family:sans-serif; background:#1a1a2e; color:#fff; padding:20px; }}
      .stats {{ display:flex; gap:20px; margin-bottom:20px; }}
      .stat {{ background:rgba(255,255,255,0.05); padding:20px; border-radius:10px; min-width:120px; }}
      .stat h3 {{ color:#e94560; font-size:28px; }}
      table {{ width:100%; border-collapse:collapse; background:rgba(255,255,255,0.03); }}
      th,td {{ padding:10px; text-align:left; border-bottom:1px solid rgba(255,255,255,0.1); font-size:13px; }}
      th {{ color:#e94560; }}
      a {{ color:#4da6ff; }}
    </style></head><body>
    <h1>📊 发卡系统管理面板</h1>
    <div class="stats">
      <div class="stat"><h3>{total}</h3><p>总库存</p></div>
      <div class="stat"><h3 style=color:#00ff88>{available}</h3><p>可用</p></div>
      <div class="stat"><h3 style=color:#f5a623>{used}</h3><p>已售</p></div>
    </div>
    
    <h2>各档位库存</h2>
    <table><tr><th>档位</th><th>总库存</th><th>可用</th><th>已售</th></tr>
    '''
    for t, info in by_tier.items():
        name = CONFIG['tiers'][t]['name']
        sold = info['total'] - info['available']
        html += f'<tr><td>{t} ({name})</td><td>{info["total"]}</td><td style=color:#00ff88>{info["available"]}</td><td>{sold}</td></tr>'
    html += '</table>'
    
    html += f'''
    <h2 style="margin-top:30px">最近订单 ({len(orders)})</h2>
    <table><tr><th>时间</th><th>订单号</th><th>档位</th><th>激活码</th><th>联系</th></tr>
    '''
    for o in reversed(orders[-20:]):
        html += f'<tr><td>{o["time"][:16]}</td><td>{o["order_id"]}</td><td>{o["tier"]}</td><td>{o["card_code"]}</td><td>{o["contact"]}</td></tr>'
    html += '</table><br><a href="/">← 返回首页</a></body></html>'
    return html

@app.route('/admin/import', methods=['GET', 'POST'])
def admin_import():
    """导入CSV"""
    if request.method == 'POST':
        if 'file' in request.files:
            f = request.files['file']
            path = os.path.join(BASE_DIR, '_upload_' + f.filename)
            f.save(path)
            count = import_csv(path)
            os.remove(path)
            return f'导入成功！共 {count} 个激活码<br><a href="/admin">返回管理面板</a>'
        return '没有上传文件'
    return '''
    <!DOCTYPE html><html><head><meta charset="UTF-8"><title>导入激活码</title>
    <style>body{font-family:sans-serif;background:#1a1a2e;color:#fff;padding:20px;}</style></head>
    <body>
    <h1>导入激活码 CSV</h1>
    <form method="post" enctype="multipart/form-data">
      <input type="file" name="file" accept=".csv"><br><br>
      <button>导入</button>
    </form><br><a href="/admin">← 返回管理面板</a>
    </body></html>'''

if __name__ == '__main__':
    # 初始化数据
    if not os.path.exists(DATA_FILE):
        save_cards([])
    if not os.path.exists(ORDERS_FILE):
        save_orders([])
    
    # 创建 static 目录存放收款码
    os.makedirs(os.path.join(BASE_DIR, 'static'), exist_ok=True)
    
    # 支持云部署：从环境变量读取端口，默认5000
    port = int(os.environ.get('PORT', 5000))
    
    print("=" * 50)
    print("   极简发卡系统已启动")
    print(f"   首页: http://localhost:{port}")
    print(f"   管理: http://localhost:{port}/admin")
    print(f"   导入: http://localhost:{port}/admin/import")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port, debug=True)
