from flask import Flask, render_template, jsonify,request
from stellar_sdk import Server, Keypair,TransactionBuilder, Network, Asset
import requests 
app = Flask(__name__)
server = Server("https://horizon-testnet.stellar.org")

# Ana Hesap
MASTER_SECRET = "SBKRI4OJ5VSQA3DPCRKQD362A7T4UN3DWWNP6G5TLEM7AYNVBPUKYSWM"
master_keypair = Keypair.from_secret(MASTER_SECRET)
master_public = master_keypair.public_key

#Fatura 
MASTER_INVOICE_SECRET = "SAK5JKTQO62LYHM3WJFMVEH5MKJOPTM7JI5GXQD26EL56RVKPL6HN6NV"
master_invoice_keypair = Keypair.from_secret(MASTER_INVOICE_SECRET)
master_invoice_public = master_invoice_keypair.public_key

MIN_BALANCE = 1
BASE_FEE = 100

# Senin hesap listen
ACCOUNTS = [
    {
        "name": "Ana Hesap",
        "secret": "SBKRI4OJ5VSQA3DPCRKQD362A7T4UN3DWWNP6G5TLEM7AYNVBPUKYSWM",
                "ratio": 0   # Ana hesap 0 ortak
    },
    {
        "name": "Ayşe Duran",
        "secret": "SDZQGZ54DUEKPEYBKZGR4AQCYIV7MLLVJGXFJA3YHQGFFQGSBCKOZLHR",
                "ratio": 40  # %40 ortak
    },
    {
        "name": "Ahmet Bakır",
        "secret": "SAHE6PW3YF5OJAYSRLOBL54SX6NVUWOVXFVVVT2RLWSIHZFQA62Q2ACZ",
                "ratio": 60  # %60 ortak
    },
        {
        "name": "Faturalar",
        "secret": "SAK5JKTQO62LYHM3WJFMVEH5MKJOPTM7JI5GXQD26EL56RVKPL6HN6NV",
                "ratio": 0  # %60 ortak
    }
]


def get_wallet_data():
    walletss = []

    for acct in ACCOUNTS:
        keypair = Keypair.from_secret(acct["secret"])
        public_key = keypair.public_key

        # Stellar'dan tüm hesap verisi
        data = server.accounts().account_id(public_key).call()

        # XLM bakiyesi
        native_balance = next(
            (b['balance'] for b in data["balances"] if b["asset_type"] == "native"),
            "0"
        )

        walletss.append({
            "name": acct["name"],
            "publicKey": public_key,
            "sequence": data["sequence"],
            "balance": native_balance,
            "network": "Testnet",
                "partnershipRatio": acct["ratio"],  # ★ eklenen satır
            "raw": data  # tüm gelen datayı da ekledim
        })

    return walletss


@app.route("/")
def index():
    walletss = get_wallet_data()
    return render_template("index.html", walletss=walletss)


@app.route("/api/wallets")
def api_wallets():
    return jsonify(get_wallet_data())

@app.route("/distribute", methods=["POST"])
def distribute():
    data = request.json
    members = data.get("members", [])

    master_account = server.accounts().account_id(master_public).call()
    native_balance = float(next(b['balance'] for b in master_account['balances'] if b['asset_type']=="native"))
    available_balance = native_balance - MIN_BALANCE - (BASE_FEE / 10000000 * len(members))
    if available_balance <= 0:
        return jsonify({"error": "Yeterli bakiye yok!"}), 400

    tx_builder = TransactionBuilder(
        source_account=server.load_account(master_public),
        network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
        base_fee=BASE_FEE
    )

    distribution = []
    for m in members:
        amount = round(available_balance * (m['share']/100), 7)
        tx_builder.append_payment_op(destination=m['publicKey'], asset=Asset.native(), amount=str(amount))
        distribution.append({"name": m['name'], "amount": amount})

    tx = tx_builder.set_timeout(180).build()
    tx.sign(master_keypair)
    try:
        result = server.submit_transaction(tx)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    # Güncel bakiyeler
    all_accounts = [{"name":"Ana Hesap","publicKey":master_public}] + members
    balances = []
    for acct in all_accounts:
        acc_data = server.accounts().account_id(acct['publicKey']).call()
        xlm_balance = float(next(b['balance'] for b in acc_data['balances'] if b['asset_type']=="native"))
        balances.append({"name": acct['name'], "balance": xlm_balance})

    return jsonify({"distribution": distribution, "balances": balances, "tx_result": result})


@app.route("/indistribute", methods=["POST"])
def indistribute():
    data = request.json
    members = data.get("members", [])  # partnerler listesi {name, publicKey, shareAmount}

    # Faturalar hesabı
    invoice_account = server.accounts().account_id(master_invoice_public).call()
    invoice_keypair = master_invoice_keypair

    # Transaction
    tx_builder = TransactionBuilder(
        source_account=server.load_account(master_invoice_public),
        network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
        base_fee=BASE_FEE
    )

    distribution = []

    # Her partner’den fatura payını çekip Faturalar hesabına ekle
    for m in members:
        # Partner hesabı yükle
        partner_account_data = server.accounts().account_id(m['publicKey']).call()
        partner_balance = float(next(b['balance'] for b in partner_account_data['balances'] if b['asset_type'] == "native"))

        # Partner bakiyesi yetersizse hata vermek yerine mümkün olan kadar çek
        amount_to_send = min(partner_balance - MIN_BALANCE, m['shareAmount'])
        if amount_to_send <= 0:
            continue  # bu partnerden çekilemez

        # Partner → Faturalar transferi
        tx_builder.append_payment_op(
            destination=master_invoice_public,
            asset=Asset.native(),
            amount=str(round(amount_to_send, 7)),
            source=m['publicKey']  # partner kaynak hesap
        )

        distribution.append({"name": m['name'], "amount": round(amount_to_send, 7)})

    # İşlemi imzala
    tx = tx_builder.set_timeout(180).build()
    for m in members:
        # Her partner kendi secret ile imzalar
        keypair = Keypair.from_secret(next(a['secret'] for a in ACCOUNTS if a['name']==m['name']))
        tx.sign(keypair)
    tx.sign(master_invoice_keypair)  # Faturalar hesabı da imzalar

    try:
        result = server.submit_transaction(tx)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    # Güncel bakiyeler
    all_accounts = [{"name":"Faturalar","publicKey":master_invoice_public}] + members
    balances = []
    for acct in all_accounts:
        acc_data = server.accounts().account_id(acct['publicKey']).call()
        xlm_balance = float(next(b['balance'] for b in acc_data['balances'] if b['asset_type']=="native"))
        balances.append({"name": acct['name'], "balance": xlm_balance})

    return jsonify({"distribution": distribution, "balances": balances, "tx_result": result})

@app.route("/api/xlm-to-try/<amount>")
def xlm_to_try(amount):
    try:
        amount = float(amount)
        import requests
        coingecko_url = "https://api.coingecko.com/api/v3/simple/price?ids=stellar&vs_currencies=try"
        r = requests.get(coingecko_url)
        r.raise_for_status()
        data = r.json()
        xlm_try = data['stellar']['try']
        total_try = amount * xlm_try
        return jsonify({"try": round(total_try, 2)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
