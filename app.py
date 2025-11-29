from flask import Flask, render_template, jsonify
from stellar_sdk import Server, Keypair

app = Flask(__name__)
server = Server("https://horizon-testnet.stellar.org")

# Senin hesap listen
ACCOUNTS = [
    {
        "name": "Ana Hesap",
        "secret": "SCBVGAAX3ERTCL3V23BCAKLJWZ64VMCDXWIICDZFFFARRX6PPQYAKUJC",
                "ratio": 0   # Ana hesap 0 ortak
    },
    {
        "name": "Ayşe",
        "secret": "SDZQGZ54DUEKPEYBKZGR4AQCYIV7MLLVJGXFJA3YHQGFFQGSBCKOZLHR",
                "ratio": 40  # %40 ortak
    },
    {
        "name": "Ahmet",
        "secret": "SAHE6PW3YF5OJAYSRLOBL54SX6NVUWOVXFVVVT2RLWSIHZFQA62Q2ACZ",
                "ratio": 60  # %60 ortak
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


if __name__ == "__main__":
    app.run(debug=True)
